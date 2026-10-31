# -*- coding: utf-8 -*-
"""Phase6-R / R2 推荐引擎正确性与索引生命周期契约。

覆盖 R2 审计项（先构造可失败的回归，再修复）：
  * 索引缓存键：检索配置（rrf_k 等）/ 编码器标识 / 策略版本 / 索引 schema 版本
    变化必须失效（不只是岗位文本哈希）；
  * 并发请求不得重复建索引（check-then-act 竞态）；
  * 被硬约束过滤（filtered=True）的岗位**不得**以零分形式进入最终推荐结果；
  * Top-K 不足时显式声明（shortfall）；top_k=0 返回空；重复 job_id 去重；
  * 同分排序稳定（score 降序 -> 输入顺序）；
  * 协作式 deadline 检查覆盖索引构建阶段。

夹具全部为合成数据（无真实简历/真人信息/PII），不进入 Gold 评估集。
"""
from __future__ import annotations

import threading
import time
import unittest

from _util import RESEARCH_MODEL_ID, reset_research_caches, synthetic_job_pool

from job_matching.service.contracts import JobProfile, StudentProfile
from job_matching.service.errors import ServiceError
from job_matching.service.matching import MatchingService, RankOptions
from job_matching.service.model_registry import ModelRegistry, register_builtin_models
from job_matching.service.research_strategy import (INDEX_SCHEMA_VERSION,
                                                    RecallIndexCache,
                                                    ResearchRetrievalScorer,
                                                    RESEARCH_STRATEGY_SPECS)


def _student(profile_id: str = "p", *, edu: str = "本科") -> StudentProfile:
    return StudentProfile.from_dict({
        "profile_id": profile_id,
        "employment_intention": {"value": "Java开发工程师", "status": "ok"},
        "education_level": {"value": edu, "status": "ok"},
        "skills": [{"skill_id": "s1", "canonical_name": "Java"}]})


def _job(job_id: str, *, edu_tokens: list[str] | None = None) -> JobProfile:
    d = {
        "job_id": job_id, "job_title": {"value": "Java开发工程师", "status": "ok"},
        "required_skills": [{"skill_id": "k", "canonical_name": "Java"}]}
    if edu_tokens:
        d["education_requirement"] = {
            "raw": "/".join(edu_tokens), "tokens": list(edu_tokens), "status": "ok"}
    return JobProfile.from_dict(d)


def _svc() -> MatchingService:
    return MatchingService(register_builtin_models(ModelRegistry()))


def _opts(top_k: int | None = 3) -> dict:
    return {"mode": "experimental_model", "model_id": RESEARCH_MODEL_ID,
            "top_k": top_k, "allow_fallback": False}


class R2CacheKeyContract(unittest.TestCase):
    """缓存键必须覆盖全部影响索引内容/语义的输入（任务 4.1）。"""

    def setUp(self):
        reset_research_caches()

    def test_cache_key_includes_retrieval_config(self):
        docs = synthetic_job_pool(5)
        k1 = RecallIndexCache.content_key("m", docs, config={"rrf_k": 60})
        k2 = RecallIndexCache.content_key("m", docs, config={"rrf_k": 10})
        self.assertNotEqual(k1, k2, "检索配置（rrf_k）变化必须产生新键")

    def test_cache_key_includes_encoder_tag(self):
        docs = synthetic_job_pool(5)
        k1 = RecallIndexCache.content_key("m", docs, config={"encoder_tag": "encA"})
        k2 = RecallIndexCache.content_key("m", docs, config={"encoder_tag": "encB"})
        self.assertNotEqual(k1, k2, "Embedding 版本（编码器标识）变化必须产生新键")

    def test_cache_key_includes_strategy_and_schema_version(self):
        docs = synthetic_job_pool(5)
        base = RecallIndexCache.content_key("m", docs, config={"v": 1})
        self.assertNotEqual(
            base, RecallIndexCache.content_key("m", docs, config={"v": 2}),
            "策略/评分版本变化必须产生新键")
        self.assertNotEqual(
            base,
            RecallIndexCache.content_key("m", docs,
                                         config={"v": 1, "schema": INDEX_SCHEMA_VERSION + 1}),
            "索引 schema 版本变化必须产生新键")

    def test_cache_key_stable_for_identical_inputs(self):
        docs = synthetic_job_pool(4)
        cfg = {"rrf_k": 60, "encoder_tag": "x"}
        self.assertEqual(RecallIndexCache.content_key("m", docs, config=cfg),
                         RecallIndexCache.content_key("m", docs, config=cfg))

    def test_different_rrf_k_scorers_do_not_share_index(self):
        """回归：不同 rrf_k 的 scorer 共用进程缓存时不得复用错误融合参数的索引。"""
        from job_matching.service.contracts import JobProfile as JP
        cache = RecallIndexCache(max_entries=4)
        jobs = [_job(f"j{i}") for i in range(4)]
        spec = RESEARCH_STRATEGY_SPECS[RESEARCH_MODEL_ID]
        s1 = ResearchRetrievalScorer(spec, cache=cache, rrf_k=60)
        s2 = ResearchRetrievalScorer(spec, cache=cache, rrf_k=1)
        s1.rank(_student(), jobs, top_k=2)
        s2.rank(_student(), jobs, top_k=2)
        self.assertEqual(2, cache.stats()["builds"],
                         "rrf_k 不同必须各建一次索引（缓存键含检索配置）")

    def test_encoder_tag_respects_encoderinfo_contract(self):
        """回归：describe() 返回 EncoderInfo（dataclass，非 dict）时不得报错。

        曾因 `info.get(...)` 对 dataclass 调用 .get 触发
        `'EncoderInfo' object has no attribute 'get'`，被外层包装成
        INTERNAL_ERROR，BGE 推理 500。
        """
        from job_matching.models.text_encoder import EncoderInfo

        class _Enc:
            def describe(self):
                return EncoderInfo(encoder_id="e", model_id="m/x", revision="rev1",
                                   license="MIT", dim=4, normalization="l2",
                                   max_length=128, device="cpu",
                                   backend="test", offline=True)

        spec = RESEARCH_STRATEGY_SPECS["zh_research_bge_recall_v1"]
        scorer = ResearchRetrievalScorer(spec, encoder_factory=lambda: _Enc())
        scorer._get_encoder()   # 触发加载
        tag = scorer._encoder_tag()
        self.assertEqual("m/x@rev1", tag)

    def test_encoder_tag_dict_form_supported(self):
        class _Enc:
            def describe(self):
                return {"model_id": "m/y", "revision": "rev2"}

        spec = RESEARCH_STRATEGY_SPECS["zh_research_bge_recall_v1"]
        scorer = ResearchRetrievalScorer(spec, encoder_factory=lambda: _Enc())
        scorer._get_encoder()
        self.assertEqual("m/y@rev2", scorer._encoder_tag())

    def test_concurrent_get_or_build_builds_once(self):
        """并发请求不得重复建索引（check-then-act 竞态回归）。"""
        cache = RecallIndexCache(max_entries=4)
        key = cache.content_key("m", synthetic_job_pool(3))
        builds = {"n": 0}
        barrier = threading.Barrier(8)

        def builder():
            builds["n"] += 1
            time.sleep(0.05)   # 放大竞态窗口
            return {"ok": True}

        def worker():
            barrier.wait()
            cache.get_or_build(key, builder)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(1, builds["n"], "同一键并发只允许构建一次索引")
        self.assertEqual(1, cache.stats()["builds"])
        self.assertEqual(7, cache.stats()["hits"])


class R2TopKAndHardConstraint(unittest.TestCase):
    """硬约束过滤 / Top-K 边界 / 去重 / 稳定排序（任务 4.2）。"""

    def setUp(self):
        reset_research_caches()

    def test_hard_filtered_job_not_in_final_results(self):
        """被硬约束过滤的岗位不得以零分形式进入最终推荐（回归）。"""
        svc = _svc()
        jobs = [_job("j_ok", edu_tokens=["本科"]),
                _job("j_filtered", edu_tokens=["硕士"])]
        result = svc.rank(_student(), jobs, _opts(top_k=10))
        ids = [r["job_id"] for r in result["results"]]
        self.assertIn("j_ok", ids)
        self.assertNotIn("j_filtered", ids, "硬约束过滤岗位不得出现在最终推荐结果")
        # 但必须显式登记被过滤项及原因（可解释，不静默丢弃）
        filtered_out = result.get("filtered_out") or []
        self.assertEqual(["j_filtered"], [f["job_id"] for f in filtered_out])
        self.assertTrue(filtered_out[0]["filter_reason"])
        self.assertTrue(any("hard_filtered_excluded" in w for w in result["warnings"]))

    def test_top_k_shortfall_declared(self):
        """合格候选不足 top_k 时必须显式声明 shortfall，不得拿零分/过滤项凑数。"""
        svc = _svc()
        jobs = [_job("j_ok", edu_tokens=["本科"]),
                _job("j_f1", edu_tokens=["硕士"]),
                _job("j_f2", edu_tokens=["博士"])]
        result = svc.rank(_student(), jobs, _opts(top_k=3))
        self.assertEqual(["j_ok"], [r["job_id"] for r in result["results"]])
        self.assertTrue(any("top_k_shortfall" in w for w in result["warnings"]),
                        result["warnings"])

    def test_top_k_zero_returns_empty(self):
        svc = _svc()
        result = svc.rank(_student(), [_job("j1"), _job("j2")], _opts(top_k=0))
        self.assertEqual([], result["results"])

    def test_top_k_negative_treated_as_zero(self):
        svc = _svc()
        result = svc.rank(_student(), [_job("j1")], _opts(top_k=-5))
        self.assertEqual([], result["results"])

    def test_duplicate_job_ids_deduped_with_warning(self):
        svc = _svc()
        jobs = [_job("j1"), _job("j1"), _job("j2")]
        result = svc.rank(_student(), jobs, _opts(top_k=5))
        ids = [r["job_id"] for r in result["results"]]
        self.assertEqual(sorted(set(ids)), sorted(ids), "重复 job_id 必须去重")
        self.assertTrue(any("duplicate_job_ids_dropped" in w
                            for w in result["warnings"]))

    def test_same_score_stable_order(self):
        """同分候选按输入顺序稳定排序（score 降序 -> pos 升序）。"""
        scorer = ResearchRetrievalScorer(RESEARCH_STRATEGY_SPECS[RESEARCH_MODEL_ID])
        # 两个完全同构岗位（同文本同技能）+ 相同学生 -> 融合分必然相等
        jobs = [_job("a"), _job("b"), _job("c")]
        out = scorer.rank(_student(), jobs, top_k=3)
        pairs = [(x["score"], x["pos"]) for x in out]
        self.assertEqual(sorted(pairs, key=lambda t: (-t[0], t[1])), pairs)

    def test_filtered_rows_sorted_after_qualified_in_rank(self):
        """scorer.rank 全量契约：filtered 行排在合格行之后且保留原因。"""
        scorer = ResearchRetrievalScorer(RESEARCH_STRATEGY_SPECS[RESEARCH_MODEL_ID])
        jobs = [_job("f1", edu_tokens=["硕士"]), _job("ok", edu_tokens=["本科"]),
                _job("f2", edu_tokens=["博士"])]
        out = scorer.rank(_student(), jobs, top_k=3)
        flags = [x["filtered"] for x in out]
        self.assertEqual(sorted(flags), flags, "filtered 行必须整体排后")
        for x in out:
            if x["filtered"]:
                self.assertTrue(x["filter_reason"])
                self.assertEqual(0.0, x["score"])


class R2DeadlineContract(unittest.TestCase):
    """协作式 deadline 覆盖索引构建等耗时阶段（任务 4.3）。"""

    def setUp(self):
        reset_research_caches()

    def test_deadline_checked_before_index_build(self):
        scorer = ResearchRetrievalScorer(RESEARCH_STRATEGY_SPECS[RESEARCH_MODEL_ID],
                                         cache=RecallIndexCache(max_entries=2))
        calls = {"n": 0}

        def deadline_check():
            calls["n"] += 1
            if calls["n"] >= 1:
                raise ServiceError("INFERENCE_TIMEOUT", "推理超过时间预算",
                                   {"timeout_exceeded": True})

        with self.assertRaises(ServiceError) as ctx:
            scorer.rank(_student(), [_job("j1"), _job("j2")],
                        deadline_check=deadline_check)
        self.assertEqual("INFERENCE_TIMEOUT", ctx.exception.code)

    def test_deadline_checked_per_candidate(self):
        """逐候选融合阶段也必须检查 deadline（不限于索引构建）。"""
        scorer = ResearchRetrievalScorer(RESEARCH_STRATEGY_SPECS[RESEARCH_MODEL_ID],
                                         cache=RecallIndexCache(max_entries=2))
        calls = {"n": 0}

        def deadline_check():
            calls["n"] += 1
            if calls["n"] > 2:
                raise ServiceError("INFERENCE_TIMEOUT", "推理超过时间预算",
                                   {"timeout_exceeded": True})

        with self.assertRaises(ServiceError):
            scorer.rank(_student(), [_job(f"j{i}") for i in range(5)],
                        deadline_check=deadline_check)
        self.assertGreater(calls["n"], 2, "每个候选都要检查 deadline")

    def test_warmup_preloads_heavy_resources(self):
        """warmup() 把编码器/精排器冷加载移出请求 deadline 预算（冷加载不可中断）。

        背景缺陷：BGE 冷加载发生在首个请求 rank() 内，请求默认 30s deadline
        从进服务开始计时，冷加载（实测 30–50s）完成后的下一检查点会被误判
        INFERENCE_TIMEOUT。warmup 后同请求不再触发加载。
        """
        loaded = {"n": 0}

        class _Enc:
            def describe(self):
                return {"model_id": "m/w", "revision": "r"}

            def encode(self, texts):
                import numpy as _np
                return _np.ones((len(texts), 3), dtype="float64")

        def factory():
            loaded["n"] += 1
            return _Enc()

        spec = RESEARCH_STRATEGY_SPECS["zh_research_bge_recall_v1"]
        scorer = ResearchRetrievalScorer(spec, encoder_factory=factory)
        info = scorer.warmup()
        self.assertEqual(["bge_encoder"], info["preloaded"])
        self.assertEqual(1, loaded["n"])
        # 预热后推理不再触发加载（冷加载已移出请求路径）
        scorer.rank(_student(), [_job("j1"), _job("j2")], top_k=2)
        self.assertEqual(1, loaded["n"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
