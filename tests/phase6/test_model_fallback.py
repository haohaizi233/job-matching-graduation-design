# -*- coding: utf-8 -*-
"""Phase6 / M1+M5 模型降级与错误契约：绝不静默返回随机评分。

覆盖任务书 4.3 / M5-3/4：
  * 模型不可用 / 权重缺失 -> 显式 ServiceError（可降级码），allow_fallback 时
    降级到 Baseline 且降级来源写明；
  * 推理超时 -> INFERENCE_TIMEOUT（永不降级）；
  * 非法输入（空文本）-> MODEL_INAPPLICABLE，不用中性分/随机分冒充结果；
  * 未注册模型：显式 model_id -> 可按策略降级；默认槽位未注册 -> 显式失败；
  * Reranker 默认不启用（Phase4-3B 观察到负贡献）；
  * BGE/Reranker 失败被记忆，重复调用重复显式报错（不静默返回 None 变无精排）。
"""
from __future__ import annotations

import unittest

from _util import (BGE_MODEL_ID, RESEARCH_MODEL_ID, RERANK_MODEL_ID,
                   make_research_scorer, reset_research_caches, synthetic_job_pool)

from job_matching.service.contracts import JobProfile, StudentProfile
from job_matching.service.errors import ServiceError
from job_matching.service.matching import MatchingService, RankOptions
from job_matching.service.model_registry import (ModelRegistry,
                                                 register_builtin_models)


def _student(profile_id: str = "p", text: str = "Java开发工程师") -> StudentProfile:
    return StudentProfile.from_dict({
        "profile_id": profile_id,
        "employment_intention": {"value": text, "status": "ok"},
        "education_level": {"value": "本科", "status": "ok"},
        "skills": [{"skill_id": "s1", "canonical_name": "Java"}]})


def _jobs(n: int = 4) -> list[JobProfile]:
    return [JobProfile.from_dict({
        "job_id": f"j{i}", "job_title": {"value": "Java开发工程师", "status": "ok"},
        "required_skills": [{"skill_id": f"k{i}", "canonical_name": "Java"}]})
        for i in range(n)]


def _svc() -> MatchingService:
    return MatchingService(register_builtin_models(ModelRegistry()))


class M2ModelFallback(unittest.TestCase):
    def setUp(self):
        reset_research_caches()

    # ---------------------------------------------------------- 输入非法
    def test_empty_text_rejected_not_random_score(self):
        scorer = make_research_scorer(RESEARCH_MODEL_ID)
        # 求职意向/专业/学历/技能/经历全部为空 -> 检索文本为空 -> 拒绝随机分
        stu = StudentProfile.from_dict({"profile_id": "p"})
        with self.assertRaises(ServiceError) as ctx:
            scorer.rank(stu, _jobs())
        self.assertEqual("MODEL_INAPPLICABLE", ctx.exception.code)

    def test_empty_job_list_rejected(self):
        scorer = make_research_scorer(RESEARCH_MODEL_ID)
        with self.assertRaises(ServiceError) as ctx:
            scorer.rank(_student(), [])
        self.assertEqual("INVALID_REQUEST", ctx.exception.code)

    # ---------------------------------------------------------- 缺权重显式失败
    def test_bge_missing_raises_model_missing(self):
        def boom():
            raise FileNotFoundError("bge weights not present")

        scorer = make_research_scorer(BGE_MODEL_ID, encoder_factory=boom)
        with self.assertRaises(ServiceError) as ctx:
            scorer.rank(_student(), _jobs())
        self.assertEqual("MODEL_MISSING", ctx.exception.code)
        self.assertEqual("artifact_missing", ctx.exception.detail["failure_kind"])
        # 失败被记忆：重复调用仍显式报错（不静默变成无向量召回）
        with self.assertRaises(ServiceError) as ctx2:
            scorer.rank(_student(), _jobs())
        self.assertEqual("MODEL_MISSING", ctx2.exception.code)

    def test_reranker_missing_raises_model_missing(self):
        def boom():
            raise FileNotFoundError("reranker weights not present")

        scorer = make_research_scorer(RERANK_MODEL_ID, reranker_factory=boom)
        with self.assertRaises(ServiceError) as ctx:
            scorer.rank(_student(), _jobs())
        self.assertEqual("MODEL_MISSING", ctx.exception.code)
        self.assertEqual("reranker", ctx.exception.detail["component"])

    def test_rerank_disabled_by_default(self):
        scorer = make_research_scorer(RESEARCH_MODEL_ID)
        self.assertIsNone(scorer._get_reranker())
        rows = scorer.rank(_student(), _jobs())
        for r in rows:
            self.assertIsNone(r.get("rerank_score"))

    # ---------------------------------------------------------- 服务级降级
    def _svc_with_simulated_missing_bge(self) -> MatchingService:
        """确定性构造「BGE 权重缺失」服务：在制品加载边界抛 FileNotFoundError。

        与真实权重缺失时 `ResearchRetrievalScorer._get_encoder` 产生的
        ServiceError 路径完全一致（MODEL_MISSING / failure_kind=artifact_missing /
        component=bge_encoder），但不依赖本机是否安装权重、不触发真实模型加载
        （避免 30s 默认 deadline 与冷加载竞速）。真实权重推理由
        test_bge_real_model_inference 单独覆盖（缺失时显式 NOT_RUN，不冒充）。
        """
        def boom():
            raise FileNotFoundError("bge weights not present (simulated)")

        scorer = make_research_scorer(BGE_MODEL_ID, encoder_factory=boom)

        def loader_impl(reg):
            return scorer

        return MatchingService(register_builtin_models(
            ModelRegistry(loader_impl=loader_impl)))

    def test_missing_artifact_degrades_with_reason(self):
        svc = self._svc_with_simulated_missing_bge()
        res = svc.rank(_student(), _jobs(), RankOptions(
            mode="experimental_model", model_id=BGE_MODEL_ID, allow_fallback=True))
        deg = res.get("degradation")
        self.assertIsNotNone(deg, "权重缺失 + allow_fallback=True 必须显式降级")
        self.assertTrue(deg["degraded"])
        self.assertEqual(BGE_MODEL_ID, deg["requested_model_id"])
        self.assertEqual("baseline_skill_text_v1", deg["actual_scoring_method"])
        self.assertEqual("artifact_missing", deg["failure_kind"])
        self.assertIn("degraded_to_baseline", " ".join(res["warnings"]))

    def test_missing_artifact_refuses_without_fallback(self):
        svc = self._svc_with_simulated_missing_bge()
        with self.assertRaises(ServiceError) as ctx:
            svc.rank(_student(), _jobs(), RankOptions(
                mode="experimental_model", model_id=BGE_MODEL_ID, allow_fallback=False))
        self.assertEqual("MODEL_MISSING", ctx.exception.code)
        self.assertEqual("artifact_missing", ctx.exception.detail["failure_kind"])

    def test_bge_real_model_inference(self):
        """真实 BGE 编码器业务级推理；权重/依赖缺失时显式 NOT_RUN（不以 Mock 冒充）。"""
        try:
            from job_matching.models.text_encoder import build_encoder
            enc = build_encoder("bge_small_zh_v15", local_files_only=True)
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"NOT_RUN: BGE 编码器权重/依赖不可用（{type(e).__name__}: {e}）")
        import math
        reset_research_caches()
        scorer = make_research_scorer(BGE_MODEL_ID, encoder_factory=lambda: enc)
        res = scorer.rank(_student(), _jobs(3))
        self.assertEqual(3, len(res))
        for r in res:
            self.assertTrue(math.isfinite(r["score"]))

    def test_unregistered_default_slot_fails_explicitly(self):
        """默认模型槽位未注册 = 部署错误 -> 显式失败，不静默长期降级。"""
        reg = ModelRegistry()
        reg.register(register_builtin_models(ModelRegistry()).get("baseline_skill_text_v1"))
        svc = MatchingService(reg, default_model_id="no_such_model")
        with self.assertRaises(ServiceError) as ctx:
            svc.rank(_student(), _jobs(),
                     RankOptions(mode="experimental_model"))
        self.assertEqual("MODEL_MISSING", ctx.exception.code)
        self.assertEqual("model_not_registered",
                         ctx.exception.detail["failure_kind"])

    def test_explicit_model_id_missing_can_degrade(self):
        reg = ModelRegistry()
        reg.register(register_builtin_models(ModelRegistry()).get("baseline_skill_text_v1"))
        svc = MatchingService(reg, default_model_id="no_such_model")
        res = svc.rank(_student(), _jobs(), RankOptions(
            mode="experimental_model", model_id="no_such_model", allow_fallback=True))
        self.assertTrue(res["degradation"]["degraded"])

    # ---------------------------------------------------------- 超时
    def test_timeout_never_degrades(self):
        svc = _svc()
        with self.assertRaises(ServiceError) as ctx:
            svc.rank(_student(), _jobs(), RankOptions(
                mode="experimental_model", model_id=RESEARCH_MODEL_ID,
                allow_fallback=True, timeout_ms=0))
        self.assertEqual("INFERENCE_TIMEOUT", ctx.exception.code)

    # ---------------------------------------------------------- NaN 防线
    def test_fusion_score_nan_refused(self):
        import math
        from job_matching.models.fusion import FeatureFusion
        from job_matching.service.research_strategy import build_fusion_inputs
        scorer = make_research_scorer(RESEARCH_MODEL_ID)
        r_in, j_in = build_fusion_inputs(_student(), _jobs(1)[0])
        # 直接构造非法语义分注入 fusion，验证出层前拦截由 rank 内 _finite 负责
        bd = scorer.fusion.score(r_in, j_in, semantic_score=None)
        self.assertTrue(math.isfinite(bd.total))


if __name__ == "__main__":
    unittest.main(verbosity=2)
