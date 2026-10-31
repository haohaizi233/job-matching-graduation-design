# -*- coding: utf-8 -*-
"""R9（P1-08 / P1-09 门禁）：PostgreSQL 正式集成 + API 契约与安全边界。

PostgreSQL 纪律：
  * 只用**独立测试库**（JM_TEST_DATABASE_URL_POSTGRES 指向的临时库），
    绝不触碰开发/生产业务库；
  * 未提供 PG 环境时显式 NOT_RUN（skip），**不冒充 PASS**；
  * 降级/重升级只允许在隔离的临时测试库上执行；
  * 用例完成后执行 downgrade 清理测试库。

API 契约与安全边界：
  * 成功/失败响应信封字段稳定（request_id 全链路）；
  * 业务端点必须认证；历史演示端点仅在 local_dev 可用；
  * production/staging 未过安全门禁拒绝启动，通过后阻断未保护的历史端点。
"""
from __future__ import annotations

import os
import threading
import unittest

from _util import SYNTHETIC_JOB_TEXT, BusinessHarness, run_downgrade, run_migrations  # noqa: E402


class R9PostgreSQLAndContract(unittest.TestCase):
    # ============================================================ PostgreSQL
    def _pg_url(self) -> str:
        return (os.environ.get("JM_TEST_DATABASE_URL_POSTGRES") or "").strip()

    def _require_pg(self) -> str:
        url = self._pg_url()
        if not url:
            self.skipTest("NOT_RUN: 未提供 JM_TEST_DATABASE_URL_POSTGRES；"
                          "SQLite 通过不代表 PostgreSQL 兼容，本组不得计入 PASS")
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            self.skipTest("ENV_INCOMPATIBLE: 缺少 psycopg2，无法连接 PostgreSQL")
        return url

    def test_pg_migrate_upgrade_downgrade_reupgrade(self):
        url = self._require_pg()
        from sqlalchemy import create_engine, inspect
        try:
            run_migrations(url)
            eng = create_engine(url, future=True)
            insp = inspect(eng)
            tables = set(insp.get_table_names())
            for t in ("users", "student_profiles", "resumes", "jobs",
                      "recommendation_runs", "recommendation_items"):
                self.assertIn(t, tables, f"PG 缺表 {t}")
            eng.dispose()

            # 降级到 base 后重新升级（仅限隔离测试库）
            run_downgrade(url, "base")
            eng = create_engine(url, future=True)
            self.assertNotIn("jobs", set(inspect(eng).get_table_names()))
            eng.dispose()
            run_migrations(url)
            eng = create_engine(url, future=True)
            self.assertIn("jobs", set(inspect(eng).get_table_names()))
            eng.dispose()
        finally:
            try:
                run_downgrade(url, "base")   # 安全清理测试库
            except Exception:  # noqa: BLE001
                pass

    def test_pg_constraints_jsonb_and_transactions(self):
        url = self._require_pg()
        from sqlalchemy import create_engine, select
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import sessionmaker
        from job_matching.infra.persistence import (Job, RecommendationRun, Resume,
                                                    StudentProfile, User)
        from job_matching.service.accounts import hash_password

        try:
            run_migrations(url)
            eng = create_engine(url, future=True)
            fac = sessionmaker(bind=eng, future=True)

            s = fac()
            try:
                u = User(username="pg_user_r9", password_hash=hash_password("Pg!2026pass"),
                         role="student")
                s.add(u)
                s.flush()

                # JSONB 存取 + 路径查询
                s.add(StudentProfile(
                    user_id=u.id, profile_version=1, confirmed=1,
                    profile_data={"profile": {"major": {"value": "软件工程"}}}))
                s.flush()
                got = s.execute(
                    select(StudentProfile).where(
                        StudentProfile.profile_data["profile"]["major"]["value"]
                        .as_string() == "软件工程")).scalars().first()
                self.assertIsNotNone(got, "JSONB 路径查询必须命中")
                # 先提交用户与画像：后续唯一约束用例触发 IntegrityError 后
                # rollback 只回滚失败语句，不得连带丢掉前置数据（R9 修复点）
                s.commit()

                # 唯一约束：(user_id, profile_version)
                s.add(StudentProfile(user_id=u.id, profile_version=1,
                                     profile_data={}))
                with self.assertRaises(IntegrityError):
                    s.flush()
                s.rollback()

                u = s.execute(select(User).where(
                    User.username == "pg_user_r9")).scalars().first()
                s.add(Resume(user_id=u.id, original_filename="a.txt",
                             storage_key="resumes/x/a.txt",
                             file_sha256="d" * 64, file_size=1,
                             parse_status="ok", data_source="synthetic",
                             source_audit=[]))
                s.flush()
                # 唯一约束：(user_id, file_sha256)
                s.add(Resume(user_id=u.id, original_filename="b.txt",
                             storage_key="resumes/x/b.txt",
                             file_sha256="d" * 64, file_size=1,
                             parse_status="ok", data_source="synthetic",
                             source_audit=[]))
                with self.assertRaises(IntegrityError):
                    s.flush()
                s.rollback()
            finally:
                s.close()

            # 并发重复推荐：唯一约束只允许一条（PG 约束名在异常信息中可识别）
            errors: list = []
            ok_count = [0]
            barrier = threading.Barrier(4)

            def _insert(i: int):
                ss = fac()
                try:
                    barrier.wait(timeout=30)
                    uu = ss.execute(select(User).where(
                        User.username == "pg_user_r9")).scalars().first()
                    ss.add(RecommendationRun(
                        user_id=uu.id, profile_version=1,
                        scoring_method="baseline_skill_text_v1",
                        scoring_config_version="scoring_config_v1",
                        job_set_snapshot=[],
                        request_fingerprint="f" * 64,
                        request_semantic_hash="e" * 64, status="completed"))
                    ss.commit()
                    ok_count[0] += 1
                except IntegrityError as e:
                    errors.append(e)
                    ss.rollback()
                finally:
                    ss.close()

            ts = [threading.Thread(target=_insert, args=(i,)) for i in range(4)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=60)
            self.assertEqual(ok_count[0], 1,
                             "并发相同指纹只允许落一条运行记录")
            self.assertTrue(errors, "其余并发请求必须被唯一约束拦截")
            self.assertTrue(any("uq_reco_runs_user_fingerprint" in str(e.orig)
                                or "request_fingerprint" in str(e.orig)
                                for e in errors),
                            "PG 唯一约束冲突应可识别约束/业务键")
            eng.dispose()
        finally:
            try:
                run_downgrade(url, "base")
            except Exception:  # noqa: BLE001
                pass

    # ============================================================ API 契约
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r9")
        _u, cls.admin_token = cls.h.login("admin_r9", "Adm1n!2026pass")
        cls.token = cls.h.student("stu_r9")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_success_envelope_contract(self):
        r = self.h.client.get("/api/v1/jobs", headers=self.h.auth(self.token))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("request_id", body)
        self.assertIn("api_version", body)
        self.assertIn("data", body)
        self.assertEqual(body["api_version"], "v1")

    def test_error_envelope_contract(self):
        r = self.h.client.get("/api/v1/jobs/no-such-job", headers=self.h.auth(self.token))
        self.assertEqual(r.status_code, 404, r.text)
        err = r.json()["error"]
        for k in ("code", "message", "request_id"):
            self.assertIn(k, err)
        self.assertEqual(err["code"], "NOT_FOUND")

    def test_business_endpoints_require_auth(self):
        calls = [
            ("GET", "/api/v1/jobs", None),
            ("GET", "/api/v1/resumes", None),
            ("GET", "/api/v1/students/me/profile", None),
            ("POST", "/api/v1/recommendations", {}),
        ]
        for method, path, body in calls:
            r = self.h.client.request(method, path, json=body)
            self.assertEqual(r.status_code, 401, f"{method} {path}: {r.text}")
            self.assertEqual(r.json()["error"]["code"], "AUTH_REQUIRED",
                             f"{method} {path} 未认证必须 401")

    def test_legacy_demo_endpoints_available_in_dev(self):
        r = self.h.client.get("/api/v1/health")
        self.assertEqual(r.status_code, 200, r.text)
        r = self.h.client.get("/api/v1/models")
        self.assertEqual(r.status_code, 200, r.text)
        # 历史解析/匹配演示端点在 local_dev 仍可达（路由存在 = 参数校验错误而非 404）
        r = self.h.client.post("/api/v1/profiles/job/parse", json={})
        self.assertIn(r.status_code, (400, 422), r.text)
        r = self.h.client.post("/api/v1/matching/rank", json={})
        self.assertIn(r.status_code, (400, 422), r.text)

    def test_production_gate_rejects_unsafe_settings(self):
        from job_matching.service.business_api import (create_business_app,
                                                       make_business_services)
        from job_matching.service.errors import ServiceError
        from job_matching.service.settings import ServiceSettings
        import tempfile
        with tempfile.TemporaryDirectory(prefix="jm_r9_gate_") as td:
            st = ServiceSettings(api_env="production")   # 默认值不满足生产安全要求
            biz = make_business_services(database_url=self.h.db_url,
                                         storage_root=td, settings=st)
            with self.assertRaises(ServiceError) as ctx:
                create_business_app(biz)
            self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_production_blocks_unprotected_legacy_endpoints(self):
        from job_matching.service.business_api import (create_business_app,
                                                       make_business_services)
        from job_matching.service.settings import ServiceSettings
        import tempfile
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory(prefix="jm_r9_block_") as td:
            st = ServiceSettings(api_env="production", require_auth=True,
                                 allow_research_models=False,
                                 deployment_scope="university_thesis_staging")
            biz = make_business_services(database_url=self.h.db_url,
                                         storage_root=td, settings=st)
            app = create_business_app(biz)
            c = TestClient(app, raise_server_exceptions=False)
            try:
                for path in ("/api/v1/profiles/job/parse",
                             "/api/v1/matching/rank"):
                    r = c.post(path, json={})
                    self.assertEqual(r.status_code, 403,
                                     f"正式环境必须阻断未保护的 {path}")
                    self.assertEqual(r.json()["error"]["code"], "FORBIDDEN")
                # 已受保护的业务端点不受影响（401 而非 403）
                r = c.get("/api/v1/jobs")
                self.assertEqual(r.status_code, 401)
                r = c.get("/api/v1/health")
                self.assertEqual(r.status_code, 200)
            finally:
                c.close()

    def test_job_crud_contract_fields_stable(self):
        """历史字段语义不变（只加不减）：Phase5-2R 新增字段并存。"""
        h = self.h
        r = h.create_job(self.admin_token, title="R9-契约岗",
                         job_description=SYNTHETIC_JOB_TEXT)
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()["data"]["job"]
        for k in ("id", "title", "job_description", "status", "job_category",
                  "city", "education_min", "created_at", "updated_at",
                  "profile_parsed", "source", "source_license"):
            self.assertIn(k, job, f"历史字段 {k} 不得缺失")
        for k in ("job_content_hash", "profile_source_hash", "profile_status",
                  "profile_current", "parser_version", "data_source",
                  "data_source_declared", "source_audit"):
            self.assertIn(k, job, f"新增字段 {k} 必须存在")
        r = h.client.post(f"/api/v1/jobs/{job['id']}/parse",
                          headers=h.auth(self.admin_token))
        self.assertEqual(r.status_code, 200, r.text)
        parsed = r.json()["data"]["job"]
        self.assertTrue(parsed["profile_parsed"])
        self.assertIn("structured_profile", parsed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
