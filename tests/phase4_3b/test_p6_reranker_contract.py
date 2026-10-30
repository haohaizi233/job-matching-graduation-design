# -*- coding: utf-8 -*-
"""P6 精排（Cross-Encoder / 词法基线）契约：批量 / 截断 / 缺模型显式失败 / 权重只读。"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.models.reranker import (  # noqa: E402
    LexicalReranker, RerankError, build_reranker)

QUERIES = ["Python 后端开发 三年经验", "财务专员 报表编制"]
DOCS = ["招聘 Python 后端开发工程师，熟悉 Django",
        "财务专员，负责账务处理与报表编制"]


class P6RerankerContract(unittest.TestCase):
    def test_length_mismatch_raises(self):
        rr = LexicalReranker()
        with self.assertRaises(RerankError):
            rr.score(["只有一条"], ["a", "b"])

    def test_empty_batch_returns_empty_scores(self):
        rr = LexicalReranker()
        res = rr.score([], [])
        self.assertEqual((0,), res.scores.shape)

    def test_scores_finite_and_bounded(self):
        rr = LexicalReranker()
        res = rr.score(QUERIES, DOCS)
        self.assertEqual((2,), res.scores.shape)
        for s in res.scores:
            self.assertTrue(np.isfinite(s), "不得输出 NaN/Inf 分数")
            self.assertGreaterEqual(float(s), 0.0)
            self.assertLessEqual(float(s), 1.0)

    def test_matching_pair_scores_higher(self):
        rr = LexicalReranker()
        res = rr.score([QUERIES[0], QUERIES[0]], [DOCS[0], DOCS[1]])
        self.assertGreater(float(res.scores[0]), float(res.scores[1]),
                           "相关文本对得分应高于不相关文本对")

    def test_truncation_recorded_for_long_inputs(self):
        rr = LexicalReranker(max_length=20)
        res = rr.score(["超长文本" * 100], ["同样超长的岗位描述" * 100])
        self.assertGreater(res.truncated, 0)
        self.assertGreater(rr.stats()["truncated_pairs"], 0)

    def test_describe_declares_not_finetuned(self):
        d = LexicalReranker().describe()
        self.assertFalse(d["finetuned"], "无监督数据前不得微调")
        self.assertIn("license", d)

    def test_build_reranker_rejects_unknown(self):
        with self.assertRaises(RerankError):
            build_reranker("not-a-registered-reranker")

    def test_build_reranker_lexical_alias(self):
        rr = build_reranker("lexical")
        self.assertEqual("lexical_v1", rr.reranker_id)

    def test_bge_reranker_conditional(self):
        """有条件：BGE reranker 权重本地可用才执行，否则显式 SKIP。"""
        try:
            rr = build_reranker("bge_reranker_base", local_files_only=True,
                                max_length=64, batch_size=2)
        except Exception as e:  # noqa: BLE001 - 依赖/权重缺失的显式跳过
            self.skipTest(f"ENV_INCOMPATIBLE/模型不可用，BGE 精排测试显式跳过: {e}")
        d = rr.describe()
        self.assertEqual("BAAI/bge-reranker-base", d["model_id"])
        self.assertTrue(d["revision"], "必须固定精确 revision")
        self.assertEqual("MIT", d["license"])
        self.assertFalse(d["finetuned"])

        def _state_digest(model) -> str:
            h = hashlib.sha256()
            for name, t in sorted(model.state_dict().items()):
                h.update(name.encode("utf-8"))
                h.update(t.detach().cpu().numpy().tobytes())
            return h.hexdigest()

        before = _state_digest(rr.model)
        res = rr.score([QUERIES[0], QUERIES[0]], [DOCS[0], DOCS[1]])
        after = _state_digest(rr.model)
        self.assertEqual(before, after, "推理过程不得修改模型权重")
        self.assertEqual((2,), res.scores.shape)
        for s in res.scores:
            self.assertTrue(np.isfinite(s))
        self.assertGreater(float(res.scores[0]), float(res.scores[1]),
                           "同一查询下相关文本对得分应高于不相关文本对")


if __name__ == "__main__":
    unittest.main()
