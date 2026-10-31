# -*- coding: utf-8 -*-
"""Phase6-R / R1：Cross-Encoder（精排）实际推理路径契约与 Logits 融合正确性。

背景缺陷（先复现后修复）
----------------------
`research_strategy.py` 原实现：

    rr = reranker.score(queries, documents)
    rr_scores = list(getattr(rr, "scores", []) or [])

当 `rr.scores` 是含多个元素的 NumPy 数组时，`arr or []` 会先求 `bool(arr)`，
触发「truth value of an array with more than one element is ambiguous」，
随后被宽泛 `except Exception` 吞掉并伪装成 `MODEL_CORRUPT`（权重损坏），
导致真实 Cross-Encoder 结果被误分类。

本文件用两类夹具分别隔离：
  * NumPy 数组返回值 -> 复现 `or []` 布尔歧义；
  * 纯 Python 列表返回值 -> 隔离 Logits 归一化/融合逻辑（跳过 numpy 缺陷）。

`ResearchRetrievalScorer.rank()` 返回项结构（顶层键）：
  pos / score / breakdown / filtered / filter_reason / rerank_score /
  rerank_norm / rerank_truncated / envelope / index_version / ...

纪律：夹具为合成数据，无真实简历/真人信息，不进入 Gold。
真实 BGE-Reranker 权重存在时执行一次业务级推理，否则显式 NOT_RUN（不冒充）。
"""
from __future__ import annotations

import math
import unittest

import numpy as np

from _util import make_research_scorer, reset_research_caches
from job_matching.models.reranker import RerankResult
from job_matching.service.contracts import JobProfile, StudentProfile
from job_matching.service.errors import ServiceError

RERANK_MODEL_ID = "zh_research_rerank_v1"          # use_reranker=True, use_embedding=False
NO_RERANK_MODEL_ID = "zh_research_retrieval_v1"    # 对照：无精排
SCORING_V2 = "research_scoring_config_v2"
SCORING_V1 = "research_scoring_config_v1"


class FakeReranker:
    """可控精排器：直接把 raw 返回值塞进 RerankResult，用于复现契约边界。"""

    reranker_id = "fake_reranker"

    def __init__(self, raw_scores, truncated=0, raise_exc=None):
        self._raw = raw_scores
        self._truncated = truncated
        self._raise_exc = raise_exc
        self.calls: list[int] = []          # 记录每次调用收到的文档数（top50 边界验证）

    def score(self, queries, documents):
        self.calls.append(len(documents))
        if self._raise_exc is not None:
            raise self._raise_exc
        return RerankResult(scores=self._raw, truncated=self._truncated, note="fake")

    def describe(self):
        return {"reranker_id": self.reranker_id}

    def stats(self):
        return {}


def _student() -> StudentProfile:
    return StudentProfile.from_dict({
        "profile_id": "p1",
        "employment_intention": {"value": "Java开发工程师", "status": "ok"},
        "education_level": {"value": "本科", "status": "ok"},
        "skills": [{"skill_id": "s1", "canonical_name": "Java"}],
    })


def _identical_jobs(n: int) -> list[JobProfile]:
    """n 个除 id 外完全相同的岗位：非语义融合分量恒定，便于隔离 Logits 单调性。"""
    return [JobProfile.from_dict({
        "job_id": f"j{i}",
        "job_title": {"value": "Java开发工程师", "status": "ok"},
        "required_skills": [{"skill_id": f"k{i}", "canonical_name": "Java"}],
    }) for i in range(n)]


def _run_with_reranker(raw_scores, n_jobs, *, truncated=0, raise_exc=None, top_k=None):
    reset_research_caches()
    fake = FakeReranker(raw_scores, truncated=truncated, raise_exc=raise_exc)
    scorer = make_research_scorer(RERANK_MODEL_ID, reranker_factory=lambda: fake)
    result = scorer.rank(_student(), _identical_jobs(n_jobs), top_k=top_k)
    return fake, result


def _sem(it) -> float:
    return it["breakdown"]["contributions"]["semantic"]


class RerankerContract(unittest.TestCase):
    maxDiff = None

    # -------------------------------------------- 复现缺陷：NumPy 数组返回值
    def test_reranker_numpy_scores(self):
        """多元素 NumPy 数组 scores 不得触发布尔歧义、不得被误判 MODEL_CORRUPT。"""
        raw = np.array([3.0, 1.0, 2.0])
        fake, result = _run_with_reranker(raw, 3)
        self.assertEqual(3, len(result))
        self.assertTrue(all(it["envelope"]["extra"]["rerank_applied"] for it in result))
        # rerank_score 保留原始 logit，并与候选一一对应
        rerank_scores = [it["rerank_score"] for it in result]
        self.assertEqual([1.0, 2.0, 3.0], sorted(rerank_scores))
        for it in result:
            self.assertIsNotNone(it["rerank_score"])

    def test_reranker_numpy_scores_order_preserved(self):
        """候选 job_id 与 rerank 分数严格对齐（按输入顺序映射，最高分居首）。"""
        raw = np.array([1.0, 5.0, 2.0])
        fake, result = _run_with_reranker(raw, 3, top_k=3)
        self.assertEqual(5.0, result[0]["rerank_score"])

    # -------------------------------------------- Logits 归一化（纯列表隔离）
    def test_reranker_negative_logits(self):
        """全为负 logits：必须仍然施加精排且归一化严格单调（旧逻辑静默跳过）。"""
        raw = [-5.0, -1.0, -3.0]           # 越大越相关
        fake, result = _run_with_reranker(raw, 3)
        order = sorted(result, key=lambda x: x["rerank_score"], reverse=True)
        sems = [_sem(it) for it in order]
        for a, b in zip(sems, sems[1:]):
            self.assertGreaterEqual(a, b)
        self.assertGreater(sems[0], sems[-1])
        for it in result:
            self.assertFalse(it["filtered"])

    def test_reranker_zero_logits(self):
        """最大 logit 为 0（含负值）：不得因 `m > 0` 判定而静默跳过精排。"""
        raw = [0.0, -2.0, -1.0]
        fake, result = _run_with_reranker(raw, 3)
        self.assertEqual([-2.0, -1.0, 0.0], sorted(it["rerank_score"] for it in result))
        sems = {it["rerank_score"]: _sem(it) for it in result}
        self.assertGreater(sems[-1.0], sems[-2.0])   # -1 优于 -2

    def test_reranker_equal_logits(self):
        """全部 logit 相等：归一化退化为中性值（不得除零、不得 NaN）。"""
        raw = [2.5, 2.5, 2.5]
        fake, result = _run_with_reranker(raw, 3)
        sems = {round(_sem(it), 6) for it in result}
        self.assertEqual(1, len(sems))
        val = sems.pop()
        self.assertTrue(math.isfinite(val))
        # 中性：单批 min==max -> 归一化语义信号 0.5 -> 贡献 = 0.30 * 0.5
        self.assertAlmostEqual(0.30 * 0.5, val, places=6)

    def test_reranker_mixed_signs_strictly_monotonic(self):
        """正负混合 + 极端值：归一化严格单调、数值稳定、语义信号有界。"""
        raw = [1e6, -1e6, 0.0, 5.0]
        fake, result = _run_with_reranker(raw, 4)
        sems = {it["rerank_score"]: _sem(it) for it in result}
        self.assertTrue(all(math.isfinite(v) for v in sems.values()))
        for v in sems.values():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 0.30 + 1e-9)     # 语义贡献不超过其权重
        self.assertGreater(sems[1e6], sems[5.0])
        self.assertGreater(sems[5.0], sems[0.0])
        self.assertGreater(sems[0.0], sems[-1e6])

    def test_reranker_nonfinite_scores(self):
        """NaN/Inf 分数必须显式拒绝，且不得伪装成权重损坏 MODEL_CORRUPT。"""
        for bad in ([float("nan"), 1.0, 2.0], [float("inf"), 1.0, 2.0]):
            with self.assertRaises(ServiceError) as ctx:
                _run_with_reranker(bad, 3)
            self.assertNotEqual("MODEL_CORRUPT", ctx.exception.code)
            self.assertEqual("rerank_output_contract_violation",
                             ctx.exception.detail.get("failure_kind"))

    def test_reranker_length_mismatch(self):
        """返回条数与候选数不一致：契约违规，非 MODEL_CORRUPT。"""
        with self.assertRaises(ServiceError) as ctx:
            _run_with_reranker([1.0, 2.0], 3)      # 2 != 3
        self.assertNotEqual("MODEL_CORRUPT", ctx.exception.code)
        self.assertEqual("rerank_output_contract_violation",
                         ctx.exception.detail.get("failure_kind"))

    def test_reranker_none_scores(self):
        """scores 为 None：显式契约违规，不得走 `or []` 静默成空。"""
        with self.assertRaises(ServiceError) as ctx:
            _run_with_reranker(None, 3)
        self.assertNotEqual("MODEL_CORRUPT", ctx.exception.code)
        self.assertEqual("rerank_output_contract_violation",
                         ctx.exception.detail.get("failure_kind"))

    # -------------------------------------------- Top-50 边界
    def test_reranker_top50_boundary(self):
        """精排只作用于前 50 候选；50 之外不得伪造 rerank 分数，且截断数被保留。"""
        n = 60
        raw = [float(i) for i in range(50)]        # 仅前 50 条返回
        fake, result = _run_with_reranker(np.asarray(raw), n, truncated=7, top_k=n)
        self.assertEqual([50], fake.calls)         # 精排器只收到 50 条文档
        scored = [it for it in result if it["rerank_score"] is not None]
        self.assertEqual(50, len(scored))
        # 截断数量被记录（与截断相关联的候选项均登记同一截断数）
        self.assertEqual(7, result[0]["rerank_truncated"])

    # -------------------------------------------- 确定性
    def test_reranker_stable_order_same_input(self):
        """同输入 -> 同排序（确定性、稳定 tie-breaking）。"""
        raw = [2.0, 2.0, 1.0]
        _, r1 = _run_with_reranker(list(raw), 3)
        _, r2 = _run_with_reranker(list(raw), 3)
        self.assertEqual([(x["pos"], x["score"]) for x in r1],
                         [(x["pos"], x["score"]) for x in r2])

    # -------------------------------------------- 推理异常仍归 MODEL_CORRUPT
    def test_reranker_inference_exception_is_corrupt(self):
        """真实推理异常（如加载失败）仍应归 MODEL_CORRUPT（与契约违规区分）。"""
        with self.assertRaises(ServiceError) as ctx:
            _run_with_reranker([1.0, 2.0, 3.0], 3,
                               raise_exc=RuntimeError("torch boom"))
        self.assertEqual("MODEL_CORRUPT", ctx.exception.code)

    # -------------------------------------------- 版本口径
    def test_reranker_scoring_version(self):
        """精排策略评分配置版本升级为 v2，无精排保持 v1（历史结果可解释）。"""
        from job_matching.service.research_strategy import RESEARCH_STRATEGY_SPECS as S
        self.assertEqual(SCORING_V2, S[RERANK_MODEL_ID].scoring_config_version)
        self.assertEqual(SCORING_V2, S["zh_research_bge_rerank_v1"].scoring_config_version)
        self.assertEqual(SCORING_V1, S[NO_RERANK_MODEL_ID].scoring_config_version)
        self.assertEqual(SCORING_V1, S["zh_research_bge_recall_v1"].scoring_config_version)

    # -------------------------------------------- 真实模型推理（条件化）
    def test_reranker_real_model_inference(self):
        """真实 BGE-Reranker 业务级推理；权重/依赖缺失则显式 NOT_RUN，不冒充。"""
        try:
            from job_matching.models.reranker import build_reranker
            rr = build_reranker("bge_reranker_base", local_files_only=True)
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"NOT_RUN: BGE-Reranker 权重/依赖不可用（{type(e).__name__}: {e}）")
        out = rr.score(["Java 后端开发"], ["Java Spring Boot 后端开发工程师"])
        self.assertEqual(1, len(out.scores))
        self.assertTrue(math.isfinite(float(np.asarray(out.scores).ravel()[0])))
        # 真实权重下走完整研究链路（至少不抛契约异常）
        reset_research_caches()
        scorer = make_research_scorer(RERANK_MODEL_ID, reranker_factory=lambda: rr)
        res = scorer.rank(_student(), _identical_jobs(3))
        self.assertEqual(3, len(res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
