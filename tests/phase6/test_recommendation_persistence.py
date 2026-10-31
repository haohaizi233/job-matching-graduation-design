# -*- coding: utf-8 -*-
"""Phase6 / M5 推荐持久化：运行快照、模型版本落库、历史解释可回放、反馈闭环。

覆盖任务书 M5-6/7/9/11 与 4.4-9/10：
  * 模型 ID / 模型版本 / 评分配置版本写入数据库（runs + items 快照）；
  * 历史解释可回放：explanation_snapshot 携带研究 breakdown 与统一输出信封；
  * 修改画像 -> 新运行与旧运行的指纹/画像版本不同（旧推荐不失效但可区分）；
  * 并发/重复推荐幂等（无幂等键自然去重；同 Key 语义不同 409）；
  * 反馈闭环：反馈是业务反馈，明确不是 Gold 标签。
"""
from __future__ import annotations

import unittest

from _util import (BusinessHarness, RESEARCH_MODEL_ID, SYNTHETIC_JOB_TEXT,
                   SYNTHETIC_JOB_TEXT_2, reset_research_caches)

M1_MODE = "experimental_model"


class M5RecommendationPersistence(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        reset_research_caches()
        cls.h = BusinessHarness()
        cls.h.make_admin("m5_admin")
        _u, cls.admin_token = cls.h.login("m5_admin", "Adm1n!2026pass")
        cls.job_ids = [
            cls.h.create_parsed_job(cls.admin_token, title="Java 开发工程师",
                                    job_description=SYNTHETIC_JOB_TEXT),
            cls.h.create_parsed_job(cls.admin_token, title="Python 数据开发",
                                    job_description=SYNTHETIC_JOB_TEXT_2),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.h.close()
        reset_research_caches()

    def _recommend(self, token: str, **kw):
        body = {"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID, "top_k": 2}
        body.update(kw)
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json=body)
        self.assertEqual(200, r.status_code, r.text)
        return r.json()["data"]

    def test_model_version_persisted_in_db(self):
        """模型版本写入数据库：runs.model_version / items.explanation_snapshot。"""
        from job_matching.infra.persistence import (RecommendationItem,
                                                    RecommendationRun)
        token = self.h.student("m5_p1")
        data = self._recommend(token)
        run_id = data["run"]["id"]
        # 用 harness 显式注入的 session_factory（默认全局工厂指向别的库）
        session = self.h.biz.students._session_factory()
        try:
            run = session.query(RecommendationRun).filter_by(id=run_id).one()
            self.assertEqual("zh_research_v1-20261031", run.model_version)
            self.assertEqual("research_fusion.zh_research_retrieval_v1",
                             run.scoring_method)
            self.assertEqual("research_scoring_config_v1", run.scoring_config_version)
            items = (session.query(RecommendationItem)
                     .filter_by(run_id=run_id).order_by(RecommendationItem.rank).all())
            self.assertEqual(2, len(items))
            snap = items[0].explanation_snapshot
            self.assertEqual(RESEARCH_MODEL_ID, snap["research"]["model_id"])
            self.assertEqual("research_scoring_config_v1",
                             snap["research"]["scoring_config_version"])
        finally:
            session.close()

    def test_explanation_replayable_from_history(self):
        """历史解释可回放：快照自带 breakdown / envelope / 版本三元组。"""
        token = self.h.student("m5_p2")
        run_id = self._recommend(token)["run"]["id"]
        detail = self.h.client.get(f"/api/v1/recommendations/{run_id}",
                                   headers=self.h.auth(token)).json()["data"]["run"]
        for it in detail["items"]:
            snap = it["explanation_snapshot"]
            self.assertIn("evidence", snap)          # 业务解释（技能证据等）
            research = snap["research"]
            self.assertIn("breakdown", research)     # 研究层评分明细
            self.assertIn("envelope", research)      # 统一模型输出信封
            self.assertIn("constraints", research["breakdown"])
            self.assertEqual("research_only_zh", research["evaluation_status"])

    def test_profile_change_produces_distinct_run(self):
        """修改画像后重推 -> 指纹与画像内容哈希变化（旧历史保留、可区分）。"""
        token = self.h.student("m5_p3")
        d1 = self._recommend(token)
        # 重新上传简历并确认 -> 画像内容变化
        self.h.upload_resume(token)
        self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(token),
                          json={"confirm": True})
        d2 = self._recommend(token)
        self.assertNotEqual(d1["run"]["id"], d2["run"]["id"])
        self.assertNotEqual(d1["run"]["profile_content_hash"],
                            d2["run"]["profile_content_hash"])
        self.assertNotEqual(d1["run"]["request_fingerprint"],
                            d2["run"]["request_fingerprint"])

    def test_job_update_produces_distinct_run(self):
        """岗位内容更新 -> 岗位集快照变化 -> 不复用旧运行。"""
        token = self.h.student("m5_p4")
        d1 = self._recommend(token)
        jid = self.job_ids[0]
        r = self.h.client.patch(f"/api/v1/jobs/{jid}", headers=self.h.auth(self.admin_token),
                                json={"job_description": SYNTHETIC_JOB_TEXT + "\n新增岗位职责：负责架构设计。"})
        self.assertEqual(200, r.status_code, r.text)
        rp = self.h.client.post(f"/api/v1/jobs/{jid}/parse",
                                headers=self.h.auth(self.admin_token))
        self.assertEqual(200, rp.status_code, rp.text)
        d2 = self._recommend(token)
        self.assertNotEqual(d1["run"]["id"], d2["run"]["id"])

    def test_repeat_request_naturally_deduped(self):
        """无幂等键：完全相同请求自然去重（复用既有运行，不重复落库）。"""
        token = self.h.student("m5_p5")
        d1 = self._recommend(token)
        d2 = self._recommend(token)
        self.assertEqual(d1["run"]["id"], d2["run"]["id"])
        self.assertFalse(d2["created"])

    def test_idempotency_key_semantic_conflict(self):
        """同 Idempotency-Key 不同语义 -> 409，绝不静默合并。"""
        token = self.h.student("m5_p6")
        key = "m5-key-1"
        r1 = self.h.client.post("/api/v1/recommendations", headers={
            **self.h.auth(token), "Idempotency-Key": key},
            json={"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID, "top_k": 2})
        self.assertEqual(200, r1.status_code, r1.text)
        r2 = self.h.client.post("/api/v1/recommendations", headers={
            **self.h.auth(token), "Idempotency-Key": key},
            json={"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID, "top_k": 1})
        self.assertEqual(409, r2.status_code, r2.text)
        r3 = self.h.client.post("/api/v1/recommendations", headers={
            **self.h.auth(token), "Idempotency-Key": key},
            json={"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID, "top_k": 2})
        self.assertEqual(200, r3.status_code)
        self.assertEqual(r1.json()["data"]["run"]["id"], r3.json()["data"]["run"]["id"])

    def test_feedback_loop_not_gold(self):
        """反馈闭环可用，且明确声明不是人工 Gold 标签。"""
        token = self.h.student("m5_p7")
        data = self._recommend(token)
        run_id = data["run"]["id"]
        detail = self.h.client.get(f"/api/v1/recommendations/{run_id}",
                                   headers=self.h.auth(token)).json()["data"]["run"]
        item_id = detail["items"][0]["id"]
        r = self.h.client.post(f"/api/v1/recommendations/{run_id}/feedback",
                               headers=self.h.auth(token),
                               json={"item_id": item_id, "feedback_type": "interested",
                                     "note": "合成测试反馈"})
        self.assertEqual(200, r.status_code, r.text)
        fb = r.json()["data"]["feedback"]
        self.assertIn("不是人工 Gold 标签", fb["gold_label_note"])
        listed = self.h.client.get("/api/v1/recommendations/feedback",
                                   headers=self.h.auth(token)).json()["data"]["items"]
        self.assertIn(fb["id"], [x["id"] for x in listed])


if __name__ == "__main__":
    unittest.main(verbosity=2)
