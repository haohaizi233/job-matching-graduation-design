# -*- coding: utf-8 -*-
"""Phase6 / M1 业务级集成验收：研究推荐策略真正接入业务推荐链路。

覆盖任务书 4.4 的 12 项验收点（不只检查 HTTP 200）：
  1. 注册用户；2. 上传并确认画像；3. 创建并解析岗位；4. 选择研究推荐策略；
  5. 发起推荐；6. **断言实际调用了指定研究模型**（scoring_method / model_id /
  research 明细），而非偷偷走旧 Baseline；7. 返回 Top-K；8. 展示评分明细；
  9. 记录运行快照；10. 回读推荐历史；11. 显式处理模型降级；12. 用户隔离。

夹具全部为合成数据（无真实简历/真人信息），不进入 Gold 评估集。
"""
from __future__ import annotations

import unittest

from _util import (BusinessHarness, RESEARCH_EVAL_STATUS, RESEARCH_MODEL_ID,
                   RESEARCH_SCORING_METHOD_PREFIX, RESEARCH_SCORE_TYPE,
                   reset_research_caches)

M1_MODE = "experimental_model"


class M1ModelIntegration(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        reset_research_caches()
        cls.h = BusinessHarness()
        # 1) 管理员 + 岗位池（2 个已解析岗位，合成文本）
        from _util import SYNTHETIC_JOB_TEXT, SYNTHETIC_JOB_TEXT_2
        cls.admin = cls.h.make_admin("m1_admin")
        _u, cls.admin_token = cls.h.login("m1_admin", "Adm1n!2026pass")
        cls.job_ids = [
            cls.h.create_parsed_job(cls.admin_token, title="Java 开发工程师",
                                    job_description=SYNTHETIC_JOB_TEXT),
            cls.h.create_parsed_job(cls.admin_token, title="Python 数据开发工程师",
                                    job_description=SYNTHETIC_JOB_TEXT_2),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.h.close()
        reset_research_caches()

    # ---------------------------------------------------------- 1/2 用户与画像
    def _student(self, name: str) -> str:
        return self.h.student(name)

    def test_01_profile_confirmed_and_jobs_parsed(self):
        """验收点 1-3：注册、上传并确认画像、岗位已解析可匹配。"""
        token = self._student("m1_s1")
        prof = self.h.profile(token)
        self.assertTrue(prof.get("confirmed"))
        self.assertTrue(prof.get("profile_version", 0) >= 1)
        for jid in self.job_ids:
            r = self.h.client.get(f"/api/v1/jobs/{jid}", headers=self.h.auth(self.admin_token))
            self.assertEqual(200, r.status_code)
            self.assertEqual("published", r.json()["data"]["job"]["status"])

    # ---------------------------------------------------------- 4-8 推荐主链路
    def test_02_research_strategy_really_called(self):
        """验收点 4-8：选择研究策略 -> 推荐 -> **断言真实调用研究模型**。"""
        token = self._student("m1_s2")
        r = self.h.client.post(
            "/api/v1/recommendations", headers=self.h.auth(token),
            json={"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID, "top_k": 2})
        self.assertEqual(200, r.status_code, r.text)
        data = r.json()["data"]
        summary = data["result_summary"]
        run = data["run"]

        # 6) 不是偷偷走旧 Baseline：评分方法 / 模型身份必须是研究策略
        self.assertEqual(RESEARCH_SCORING_METHOD_PREFIX + RESEARCH_MODEL_ID,
                         summary["scoring_method"])
        self.assertNotEqual("baseline_skill_text_v1", summary["scoring_method"])
        self.assertEqual(RESEARCH_EVAL_STATUS, summary["evaluation_status"])
        self.assertEqual("zh_research_v1-20261031", summary["model_version"])
        self.assertEqual(RESEARCH_SCORE_TYPE, summary["score_type"])
        self.assertFalse(summary["formal_evaluation"])

        # 7) Top-K 截断
        run_id = run["id"]
        detail = self.h.client.get(f"/api/v1/recommendations/{run_id}",
                                   headers=self.h.auth(token)).json()["data"]["run"]
        items = detail["items"]
        self.assertEqual(2, len(items))
        self.assertEqual([1, 2], [it["rank"] for it in items])

        # 8) 评分明细：每条结果带研究层可解释 breakdown 与统一输出信封
        first = items[0]["explanation_snapshot"]
        research = first["research"]
        self.assertEqual(RESEARCH_MODEL_ID, research["model_id"])
        self.assertEqual("zh_research_feature_v1", research["feature_version"])
        self.assertEqual("research_scoring_config_v1",
                         research["scoring_config_version"])
        self.assertEqual(RESEARCH_EVAL_STATUS, research["evaluation_status"])
        contributions = research["breakdown"]["contributions"]
        for comp in ("semantic", "skill", "education", "experience", "category", "intent"):
            self.assertIn(comp, contributions)
        self.assertIn("envelope", research)
        self.assertEqual(RESEARCH_MODEL_ID, research["envelope"]["model_id"])

        # 9) 运行快照：模型版本 / 评分配置版本写入持久化
        self.assertEqual("zh_research_v1-20261031", run["model_version"])
        self.assertTrue(str(run["scoring_method"]).startswith("research_fusion."))
        self.assertEqual("research_scoring_config_v1", run["scoring_config_version"])

        # 10) 回读推荐历史
        hist = self.h.client.get("/api/v1/recommendations", headers=self.h.auth(token))
        self.assertEqual(200, hist.status_code)
        ids = [x["id"] for x in hist.json()["data"]["items"]]
        self.assertIn(run_id, ids)

    def test_03_research_differs_from_baseline(self):
        """验收点 6 补充：研究策略与 Baseline 结果可区分（评分方法与分数语义不同）。"""
        token = self._student("m1_s3")
        rb = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json={"mode": "baseline", "top_k": 3}).json()["data"]
        rr = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json={"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID,
                                      "top_k": 3}).json()["data"]
        self.assertEqual("baseline_skill_text_v1", rb["result_summary"]["scoring_method"])
        self.assertEqual("heuristic_score", rb["result_summary"]["score_type"])
        self.assertEqual(RESEARCH_SCORING_METHOD_PREFIX + RESEARCH_MODEL_ID,
                         rr["result_summary"]["scoring_method"])
        # 两次运行基于同一份已确认画像 -> 画像版本一致；评分方法不同 -> 结果可区分
        self.assertEqual(rb["run"]["profile_version"], rr["run"]["profile_version"])
        self.assertNotEqual(rb["run"]["scoring_method"], rr["run"]["scoring_method"])
        self.assertEqual("scoring_config_v1", rb["run"]["scoring_config_version"])
        self.assertEqual("research_scoring_config_v1",
                         rr["run"]["scoring_config_version"])

    # ---------------------------------------------------------- 11 降级
    def test_04_model_missing_degrades_explicitly(self):
        """验收点 11：BGE 策略权重缺失 -> 显式降级记录，绝不伪造模型输出。"""
        token = self._student("m1_s4")
        r = self.h.client.post(
            "/api/v1/recommendations", headers=self.h.auth(token),
            json={"mode": M1_MODE, "model_id": "zh_research_bge_recall_v1",
                  "top_k": 2, "allow_fallback": True})
        self.assertEqual(200, r.status_code, r.text)
        data = r.json()["data"]
        deg = data["result_summary"]["degradation"]
        if deg is None:
            # 权重实际存在 -> 本用例验证目标不成立，显式登记而非假绿
            self.skipTest("BGE 权重在本机存在，降级路径未触发（登记 SKIP，不计 PASS）")
        self.assertTrue(deg["degraded"])
        self.assertIn(deg["reason_code"], ("MODEL_MISSING", "MODEL_CORRUPT",
                                           "MODEL_INAPPLICABLE"))
        self.assertEqual("zh_research_bge_recall_v1", deg["requested_model_id"])
        self.assertEqual("baseline_skill_text_v1", deg["actual_scoring_method"])
        self.assertIn("degraded_to_baseline",
                      " ".join(data["result_summary"]["warnings"]))

    def test_05_allow_fallback_false_refuses(self):
        """降级关闭：模型不可用必须显式失败，不允许静默换路径。"""
        token = self._student("m1_s5")
        r = self.h.client.post(
            "/api/v1/recommendations", headers=self.h.auth(token),
            json={"mode": M1_MODE, "model_id": "zh_research_bge_recall_v1",
                  "top_k": 2, "allow_fallback": False})
        if r.status_code == 200:
            deg = r.json()["data"]["result_summary"]["degradation"]
            if deg is None:
                self.skipTest("BGE 权重在本机存在，失败路径未触发（登记 SKIP，不计 PASS）")
        # 契约：MODEL_MISSING 在 errors.ERROR_CODES 登记为 503（模型能力缺失是服务侧
        # 问题，不是请求非法）。历史断言误写 400——本机权重存在时该用例走 skipTest
        # 从未真正执行，直到 CI 干净 checkout（无 torch/权重）才首次运行并暴露。
        self.assertEqual(503, r.status_code,
                         "MODEL_MISSING 登记 HTTP 状态为 503（见 errors.ERROR_CODES）")
        body = r.text
        self.assertIn("MODEL_MISSING", body)
        err = r.json().get("error", {})
        self.assertEqual("MODEL_MISSING", err.get("code"),
                         "显式失败必须携带稳定 error_code，不静默降级")

    def test_06_formal_mode_rejected(self):
        """正式模式门禁：research_only_zh 模型不允许 formal。"""
        from job_matching.service.matching import MatchingService, RankOptions
        from job_matching.service.model_registry import (ModelRegistry,
                                                         register_builtin_models)
        reg = register_builtin_models(ModelRegistry())
        svc = MatchingService(reg)
        with self.assertRaises(Exception) as ctx:
            svc.rank({"profile_id": "p", "employment_intention":
                      {"value": "Java", "status": "ok"}},
                     [{"job_id": "j", "job_title": {"value": "Java", "status": "ok"}}],
                     RankOptions(mode=M1_MODE, model_id=RESEARCH_MODEL_ID, formal=True))
        self.assertIn("MODEL_FORMAL_USE_FORBIDDEN", repr(ctx.exception))

    # ---------------------------------------------------------- 12 用户隔离
    def test_07_user_isolation(self):
        """验收点 12：不同用户推荐运行互相隔离（越权统一 404）。"""
        t1 = self._student("m1_u1")
        t2 = self._student("m1_u2")
        run_id = self.h.client.post(
            "/api/v1/recommendations", headers=self.h.auth(t1),
            json={"mode": M1_MODE, "model_id": RESEARCH_MODEL_ID, "top_k": 2}
        ).json()["data"]["run"]["id"]
        # 用户 2 不能读取用户 1 的运行
        r = self.h.client.get(f"/api/v1/recommendations/{run_id}",
                              headers=self.h.auth(t2))
        self.assertEqual(404, r.status_code)
        # 用户 2 的历史不含用户 1 的运行
        hist = self.h.client.get("/api/v1/recommendations", headers=self.h.auth(t2))
        self.assertNotIn(run_id, [x["id"] for x in hist.json()["data"]["items"]])

    # ---------------------------------------------------------- 确定性
    def test_08_deterministic_same_input(self):
        """同输入 + 同模型版本 => 确定性结果（稳定排序）。"""
        from _util import make_research_scorer
        from job_matching.service.contracts import JobProfile, StudentProfile
        reset_research_caches()
        scorer = make_research_scorer(RESEARCH_MODEL_ID)
        student = StudentProfile.from_dict({
            "profile_id": "p1",
            "employment_intention": {"value": "Java开发工程师", "status": "ok"},
            "education_level": {"value": "本科", "status": "ok"},
            "skills": [{"skill_id": "s1", "canonical_name": "Java"}]})
        jobs = [JobProfile.from_dict({
            "job_id": f"j{i}", "job_title": {"value": "Java开发工程师", "status": "ok"},
            "required_skills": [{"skill_id": f"k{i}", "canonical_name": "Java"}]})
            for i in range(5)]
        r1 = scorer.rank(student, jobs, top_k=5)
        r2 = scorer.rank(student, jobs, top_k=5)
        self.assertEqual([(x["pos"], x["score"]) for x in r1],
                         [(x["pos"], x["score"]) for x in r2])
        # 排序稳定：非过滤项按分数降序（同分按输入顺序），过滤项沉底
        non_filtered = [x for x in r1 if not x["filtered"]]
        keys = [(-x["score"], x["pos"]) for x in non_filtered]
        self.assertEqual(keys, sorted(keys))


if __name__ == "__main__":
    unittest.main(verbosity=2)
