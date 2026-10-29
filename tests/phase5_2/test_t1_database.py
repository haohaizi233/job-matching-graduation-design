# -*- coding: utf-8 -*-
"""T1（B1 门禁）：数据库 Schema、约束、索引、迁移与事务。

覆盖任务 3.3：
  * 新数据库初始化（空库 upgrade head）；
  * 重复执行不破坏现有数据；
  * 失败事务回滚（无半成功记录）；
  * 基本回退验证（downgrade base 后可再升级）；
  * 约束与索引验证（唯一约束 / 外键 / 索引）。

说明：本组在 SQLite 上执行；PostgreSQL 语义差异由 T7 集成测试覆盖
（未提供 PostgreSQL 环境时 T7 显式记 NOT_RUN，不得当作 PASS）。
"""
from __future__ import annotations

import unittest
from datetime import datetime

from _util import ROOT, BusinessHarness, run_downgrade, run_migrations  # noqa: E402


class T1MigrationGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def _inspector(self):
        from sqlalchemy import inspect
        from job_matching.infra.persistence import get_engine
        return inspect(get_engine())

    def test_fresh_upgrade_creates_all_tables(self):
        tables = set(self._inspector().get_table_names())
        for t in ("users", "auth_sessions", "student_profiles", "resumes", "jobs",
                  "recommendation_runs", "recommendation_items",
                  "recommendation_feedback"):
            self.assertIn(t, tables, f"迁移未创建表 {t}")

    def test_repeated_upgrade_preserves_existing_data(self):
        from job_matching.infra.persistence import User, get_session, session_scope
        from job_matching.service.accounts import hash_password

        with session_scope() as s:
            s.add(User(username="keep_me", password_hash=hash_password("KeepMe!2026x"),
                       role="student", status="active", failed_login_count=0,
                       created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        # 重复执行 upgrade head：不重建、不破坏
        run_migrations(self.h.db_url)
        session = get_session()
        try:
            rows = session.query(User).filter(User.username == "keep_me").count()
        finally:
            session.close()
        self.assertEqual(rows, 1, "重复迁移破坏了既有数据")

    def test_downgrade_and_reupgrade(self):
        run_downgrade(self.h.db_url, "base")
        tables = set(self._inspector().get_table_names())
        self.assertNotIn("users", tables, "downgrade 未删除表")
        run_migrations(self.h.db_url)
        tables = set(self._inspector().get_table_names())
        self.assertIn("users", tables, "回退后无法再升级")

    def test_unique_constraints(self):
        from sqlalchemy.exc import IntegrityError
        from job_matching.infra.persistence import (Job, RecommendationItem,
                                                    RecommendationRun, Resume,
                                                    StudentProfile, User,
                                                    session_scope)
        from job_matching.service.accounts import hash_password

        with session_scope() as s:
            u = User(username="uq_user", password_hash=hash_password("Uq!2026pass"),
                     role="student", status="active", created_at=datetime.utcnow(),
                     updated_at=datetime.utcnow())
            s.add(u)
            s.flush()
            s.add(Resume(user_id=u.id, original_filename="a.txt", storage_key="k1",
                         file_sha256="aa", file_size=1, parse_status="ok",
                         uploaded_at=datetime.utcnow(), updated_at=datetime.utcnow()))
            s.flush()
            s.add(StudentProfile(user_id=u.id, profile_version=1,
                                 profile_data={"profile": {}}, confirmed=0,
                                 created_at=datetime.utcnow(),
                                 updated_at=datetime.utcnow()))
            s.flush()
            j = Job(title="t", job_description="d", source="manual",
                    source_license="UNKNOWN", status="published",
                    created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            s.add(j)
            s.flush()
            run = RecommendationRun(user_id=u.id, profile_version=1,
                                    scoring_method="baseline_skill_text_v1",
                                    scoring_config_version="scoring_config_v1",
                                    job_set_snapshot=[], request_fingerprint="fp1",
                                    status="completed", created_at=datetime.utcnow())
            s.add(run)
            s.flush()
            s.add(RecommendationItem(run_id=run.id, job_id=j.id, rank=1, score=0.5,
                                     score_type="heuristic_score",
                                     explanation_snapshot={}, job_snapshot_version="v",
                                     created_at=datetime.utcnow()))
            s.flush()

        cases = {
            "users.username 唯一": lambda s: s.add(User(
                username="uq_user", password_hash="x", role="student", status="active",
                created_at=datetime.utcnow(), updated_at=datetime.utcnow())),
            "resumes(user,file_sha256) 唯一": lambda s: s.add(Resume(
                user_id=self._user_id(), original_filename="b.txt", storage_key="k2",
                file_sha256="aa", file_size=1, parse_status="ok",
                uploaded_at=datetime.utcnow(), updated_at=datetime.utcnow())),
            "student_profiles(user,version) 唯一": lambda s: s.add(StudentProfile(
                user_id=self._user_id(), profile_version=1, profile_data={},
                confirmed=0, created_at=datetime.utcnow(), updated_at=datetime.utcnow())),
            "recommendation_items(run,rank) 唯一": lambda s: s.add(RecommendationItem(
                run_id=self._run_id(), job_id=self._job_id(), rank=1, score=0.1,
                score_type="heuristic_score", explanation_snapshot={},
                job_snapshot_version="v", created_at=datetime.utcnow())),
        }
        for name, insert in cases.items():
            with self.assertRaises(IntegrityError, msg=f"{name} 未生效"):
                with session_scope() as s:
                    insert(s)

    def test_foreign_key_enforcement_and_cascade(self):
        from sqlalchemy.exc import IntegrityError
        from job_matching.infra.persistence import (Resume, User, get_session,
                                                    session_scope)

        with self.assertRaises(IntegrityError, msg="外键未强制"):
            with session_scope() as s:
                s.add(Resume(user_id="no-such-user", original_filename="x.txt",
                             storage_key="k", file_sha256="zz", file_size=1,
                             parse_status="ok", uploaded_at=datetime.utcnow(),
                             updated_at=datetime.utcnow()))
        # 级联：删除用户 -> 简历行删除（本测试自建数据，避免与其他用例顺序耦合）
        with session_scope() as s:
            u = User(username="fk_user", password_hash="x", role="student",
                     status="active", created_at=datetime.utcnow(),
                     updated_at=datetime.utcnow())
            s.add(u)
            s.flush()
            s.add(Resume(user_id=u.id, original_filename="fk.txt", storage_key="kfk",
                         file_sha256="fksha", file_size=1, parse_status="ok",
                         uploaded_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        session = get_session()
        try:
            u = session.query(User).filter(User.username == "fk_user").first()
            uid = u.id
            session.delete(u)
            session.commit()
            left = session.query(Resume).filter(Resume.user_id == uid).count()
        finally:
            session.close()
        self.assertEqual(left, 0, "users 删除后 resumes 未级联清理")

    def test_transaction_rollback_leaves_no_partial_rows(self):
        from job_matching.infra.persistence import (RecommendationItem, User,
                                                    get_session, session_scope)

        before = self._count(User)
        with self.assertRaises(RuntimeError):
            with session_scope() as s:
                s.add(User(username="rollback_user", password_hash="x", role="student",
                           status="active", created_at=datetime.utcnow(),
                           updated_at=datetime.utcnow()))
                s.flush()
                raise RuntimeError("模拟事务中途失败")
        self.assertEqual(self._count(User), before, "失败事务留下半成功记录")

        before_items = self._count(RecommendationItem)
        with self.assertRaises(RuntimeError):
            with session_scope() as s:
                s.add(RecommendationItem(run_id="no-such-run", job_id="no-such-job",
                                         rank=99, score=0.0,
                                         score_type="heuristic_score",
                                         explanation_snapshot={}, job_snapshot_version="v",
                                         created_at=datetime.utcnow()))
                raise RuntimeError("模拟写入中断")
        self.assertEqual(self._count(RecommendationItem), before_items)

    def test_indexes_exist(self):
        idx = {i["name"] for i in self._inspector().get_indexes("jobs")}
        for name in ("ix_jobs_status_category", "ix_jobs_status_city"):
            self.assertIn(name, idx, f"缺少索引 {name}")
        idx_users = {i["name"] for i in self._inspector().get_indexes("users")}
        self.assertIn("ix_users_role_status", idx_users)
        idx_runs = {i["name"] for i in self._inspector().get_indexes("recommendation_runs")}
        self.assertIn("ix_reco_runs_user_created", idx_runs)

    def test_json_columns_roundtrip(self):
        from job_matching.infra.persistence import StudentProfile, User, get_session, session_scope

        payload = {"profile": {"major": {"value": "软件工程", "fact_source": "rule_parsed"}},
                   "extraction_snapshot": {"k": [1, 2, {"n": "中文"}]},
                   "user_edits": {}}
        with session_scope() as s:
            u = User(username="json_user", password_hash="x", role="student",
                     status="active", created_at=datetime.utcnow(),
                     updated_at=datetime.utcnow())
            s.add(u)
            s.flush()
            s.add(StudentProfile(user_id=u.id, profile_version=1,
                                 profile_data=payload, confirmed=0,
                                 created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        session = get_session()
        try:
            row = (session.query(StudentProfile)
                   .join(User, User.id == StudentProfile.user_id)
                   .filter(User.username == "json_user").first())
            self.assertEqual(row.profile_data["extraction_snapshot"]["k"][2]["n"], "中文")
        finally:
            session.close()

    # ---------------------------------------------------------- 辅助
    def _count(self, model) -> int:
        from job_matching.infra.persistence import get_session
        session = get_session()
        try:
            return session.query(model).count()
        finally:
            session.close()

    def _user_id(self) -> str:
        from job_matching.infra.persistence import User, get_session
        session = get_session()
        try:
            return session.query(User).filter(User.username == "uq_user").first().id
        finally:
            session.close()

    def _run_id(self) -> str:
        from job_matching.infra.persistence import RecommendationRun, get_session
        session = get_session()
        try:
            return session.query(RecommendationRun).first().id
        finally:
            session.close()

    def _job_id(self) -> str:
        from job_matching.infra.persistence import Job, get_session
        session = get_session()
        try:
            return session.query(Job).first().id
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
