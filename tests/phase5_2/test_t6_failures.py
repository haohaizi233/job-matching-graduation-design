# -*- coding: utf-8 -*-
"""T6（链路E）：异常事务与失败路径 —— 验证状态一致性，杜绝半成功业务记录。

模拟场景：
  * 数据库连接失败 / 写入失败（含"文件已写但落库失败"）；
  * 解析失败（上传仍留档，可重新解析）；
  * 推荐执行失败（不落任何运行记录）；
  * 模型不存在 / 模型不兼容；
  * 请求重复（幂等）；
  * 服务异常中断（条目写入中途失败 -> 整体回滚）。

纪律：每条失败路径都要断言**数据库与私有存储的最终状态**，
不允许"报错但留了一半数据"。
"""
from __future__ import annotations

import unittest
from unittest import mock

from _util import SYNTHETIC_JOB_TEXT, BusinessHarness, synthetic_resume_bytes  # noqa: E402


class T6FailureTransactions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_t6")
        _u, cls.admin_token = cls.h.login("admin_t6", "Adm1n!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 工具
    def _student(self, name: str) -> str:
        self.h.register(name, "Stu!2026pass")
        _u, token = self.h.login(name, "Stu!2026pass")
        self.h.upload_resume(token)
        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(token),
                              json={"confirm": True})
        assert r.status_code == 200, r.text
        return token

    def _storage_file_count(self) -> int:
        root = self.h.biz.students.store.root
        return sum(1 for p in root.rglob("*") if p.is_file()) if root.exists() else 0

    # ---------------------------------------------------------- 数据库失败
    def test_db_write_failure_after_file_save_leaves_no_orphan(self):
        """文件上传成功但数据库写入失败：必须清理已写文件。"""
        import job_matching.service.profile_store as ps

        token = self._student("stu_dbfail")
        # 基线在建号上传之后取：只排除本用例自己那条合法简历文件，
        # 失败上传写入的文件必须被清理（不得有新增文件）
        before = self._storage_file_count()
        # 只让"落库"环节失败（文件已经写入私有存储）
        with mock.patch.object(ps, "session_scope",
                               side_effect=RuntimeError("模拟数据库不可用")):
            r = self.h.upload_resume(token, content=synthetic_resume_bytes(),
                                     filename="orphan_check.txt")
        self.assertEqual(r.status_code, 500, r.text)
        self.assertEqual(self._storage_file_count(), before,
                         "落库失败后残留孤儿文件")

    def test_db_unavailable_returns_error_not_partial(self):
        token = self._student("stu_dbdown")
        self.h.biz.students._session_factory = mock.Mock(
            side_effect=RuntimeError("模拟连接失败"))
        before = self._storage_file_count()
        try:
            r = self.h.upload_resume(token, content=synthetic_resume_bytes(),
                                     filename="dbdown.txt")
            self.assertEqual(r.status_code, 500, r.text)
            self.assertEqual(r.json()["error"]["code"], "INTERNAL_ERROR")
        finally:
            from job_matching.infra.persistence import get_session_factory
            self.h.biz.students._session_factory = get_session_factory()
        self.assertEqual(self._storage_file_count(), before,
                         "数据库不可用时不得留下未入库文件")

    # ---------------------------------------------------------- 解析失败
    def test_parse_failure_keeps_resume_row_without_profile(self):
        from job_matching.service.profile_store import StudentDataService

        token = self._student("stu_parsefail")
        with mock.patch.object(StudentDataService, "_parse_profile",
                               side_effect=RuntimeError("模拟解析器异常")):
            r = self.h.upload_resume(token, content=synthetic_resume_bytes(),
                                     filename="parsefail.txt")
        self.assertEqual(r.status_code, 200, r.text)
        resume = r.json()["data"]["resume"]
        self.assertEqual(resume["parse_status"], "failed")
        self.assertNotIn("profile", r.json()["data"])
        # 简历行与文件都在（属于用户，不是孤儿），可重新解析
        r = self.h.client.post(f"/api/v1/resumes/{resume['id']}/reparse",
                               headers=self.h.auth(token), json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(r.json()["data"]["resume"]["parse_status"], ("ok", "partial"))

    # ---------------------------------------------------------- 推荐失败
    def test_recommendation_failure_leaves_no_rows(self):
        from job_matching.service.reco_store import RecommendationRun

        r = self.h.client.post("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                               json={"title": "T6-失败链路合成岗",
                                     "job_description": SYNTHETIC_JOB_TEXT,
                                     "source": "synthetic",
                                     "source_license": "CC0-synthetic"})
        job_id = r.json()["data"]["job"]["id"]
        self.h.client.post(f"/api/v1/jobs/{job_id}/parse",
                           headers=self.h.auth(self.admin_token))
        token = self._student("stu_recofail")

        def _count_runs() -> int:
            from job_matching.infra.persistence import get_session
            s = get_session()
            try:
                return s.query(RecommendationRun).count()
            finally:
                s.close()

        before = _count_runs()
        with mock.patch.object(type(self.h.biz.core.matching), "rank",
                               side_effect=RuntimeError("模拟评分服务崩溃")):
            r = self.h.client.post("/api/v1/recommendations",
                                   headers=self.h.auth(token),
                                   json={"job_ids": [job_id]})
        self.assertEqual(r.status_code, 500, r.text)
        self.assertEqual(_count_runs(), before, "推荐失败不得留下半成功运行记录")

    def test_model_missing_without_fallback_is_error(self):
        r = self.h.client.post("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                               json={"title": "T6-模型缺失合成岗",
                                     "job_description": SYNTHETIC_JOB_TEXT,
                                     "source": "synthetic",
                                     "source_license": "CC0-synthetic"})
        job_id = r.json()["data"]["job"]["id"]
        self.h.client.post(f"/api/v1/jobs/{job_id}/parse",
                           headers=self.h.auth(self.admin_token))
        token = self._student("stu_nomodel")
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"mode": "experimental_model",
                                     "model_id": "no_such_model",
                                     "allow_fallback": False,
                                     "job_ids": [job_id]})
        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(r.json()["error"]["code"], "MODEL_MISSING")

        # 允许降级 -> 显式告警 + 启发式分（不得伪装成模型分）
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"mode": "experimental_model",
                                     "model_id": "no_such_model",
                                     "allow_fallback": True,
                                     "job_ids": [job_id]})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(data["result_summary"]["score_type"], "heuristic_score")
        self.assertTrue(any("degrad" in w or "fallback" in w.lower() or "baseline" in w
                            for w in data["result_summary"]["warnings"]),
                        data["result_summary"]["warnings"])
        # Phase5-3 / M5：降级必须可追溯（API 显式字段 + 运行记录持久化）
        deg = data["result_summary"].get("degradation")
        self.assertIsNotNone(deg, "result_summary.degradation 不得丢失")
        self.assertTrue(deg.get("degraded"))
        self.assertEqual(deg.get("requested_model_id"), "no_such_model")
        run_id = data["run"]["id"]
        rr = self.h.client.get(f"/api/v1/recommendations/{run_id}",
                               headers=self.h.auth(token))
        self.assertEqual(rr.status_code, 200, rr.text)
        persisted = rr.json()["data"]["run"].get("degradation_info")
        self.assertIsNotNone(persisted, "降级信息必须持久化到运行记录")
        self.assertTrue(persisted.get("degraded"))
        self.assertEqual(persisted.get("reason_code"), "MODEL_MISSING")

        # 未降级运行不得携带降级快照（不乐观回填）
        r2 = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json={"mode": "baseline", "job_ids": [job_id]})
        self.assertEqual(r2.status_code, 200, r2.text)
        d2 = r2.json()["data"]
        self.assertIsNone(d2["result_summary"].get("degradation"))
        self.assertIsNone(d2["run"].get("degradation_info"))

    def test_model_env_incompatible_is_registered_not_run(self):
        self.skipTest("NOT_RUN: 需要旧依赖栈 checkpoint 才能真实复现 MODEL_ENV_INCOMPATIBLE；"
                      "本地合成环境无法合法构造，留待 Artifact-dependent 流程验证")

    # ---------------------------------------------------------- 中断与重复
    def test_service_interruption_mid_items_rolls_back_all(self):
        import job_matching.service.reco_store as rs

        r = self.h.client.post("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                               json={"title": "T6-中断链路合成岗",
                                     "job_description": SYNTHETIC_JOB_TEXT,
                                     "source": "synthetic",
                                     "source_license": "CC0-synthetic"})
        job_id = r.json()["data"]["job"]["id"]
        self.h.client.post(f"/api/v1/jobs/{job_id}/parse",
                           headers=self.h.auth(self.admin_token))
        token = self._student("stu_interrupt")
        real_item = rs.RecommendationItem
        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("模拟服务异常中断")
            return real_item(*args, **kwargs)

        with mock.patch.object(rs, "RecommendationItem", side_effect=_boom):
            r = self.h.client.post("/api/v1/recommendations",
                                   headers=self.h.auth(token),
                                   json={"job_ids": [job_id, self._second_job_id()]})
        self.assertEqual(r.status_code, 500, r.text)
        self.assertEqual(calls["n"], 2)

        from job_matching.infra.persistence import (RecommendationItem,
                                                    RecommendationRun,
                                                    get_session)
        from job_matching.infra.persistence import User as PgUser
        s = get_session()
        try:
            uid = s.query(PgUser).filter(PgUser.username == "stu_interrupt").first().id
            user_runs = (s.query(RecommendationRun)
                         .filter(RecommendationRun.user_id == uid).all())
            self.assertEqual(user_runs, [], "中断的推荐运行不得留下半成功记录")
            run_ids = [r_.id for r_ in s.query(RecommendationRun).all()]
            orphans = (s.query(RecommendationItem)
                       .filter(RecommendationItem.run_id.notin_(run_ids)).count())
            self.assertEqual(orphans, 0, "存在孤儿推荐条目")
        finally:
            s.close()

    def _second_job_id(self) -> str:
        r = self.h.client.post("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                               json={"title": "T6-中断链路合成岗B",
                                     "job_description": SYNTHETIC_JOB_TEXT,
                                     "source": "synthetic",
                                     "source_license": "CC0-synthetic"})
        jid = r.json()["data"]["job"]["id"]
        self.h.client.post(f"/api/v1/jobs/{jid}/parse",
                           headers=self.h.auth(self.admin_token))
        return jid

    def test_duplicate_request_returns_same_run(self):
        r = self.h.client.post("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                               json={"title": "T6-重复提交合成岗",
                                     "job_description": SYNTHETIC_JOB_TEXT,
                                     "source": "synthetic",
                                     "source_license": "CC0-synthetic"})
        job_id = r.json()["data"]["job"]["id"]
        self.h.client.post(f"/api/v1/jobs/{job_id}/parse",
                           headers=self.h.auth(self.admin_token))
        token = self._student("stu_dup")
        body = {"job_ids": [job_id]}
        r1 = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json=body)
        r2 = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json=body)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["data"]["run"]["id"], r2.json()["data"]["run"]["id"])
        self.assertTrue(r1.json()["data"]["created"])
        self.assertFalse(r2.json()["data"]["created"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
