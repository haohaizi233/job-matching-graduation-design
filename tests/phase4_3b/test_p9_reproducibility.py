# -*- coding: utf-8 -*-
"""P9 可复现性：同输入同输出 / 固定配置可复现 / 推理不修改权重。

有条件项（BGE 权重）不可用时显式 SKIP，不伪装 PASS。
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.models.fusion import FeatureFusion  # noqa: E402
from job_matching.models.retrieval import BM25Recall, TfidfRecall  # noqa: E402
from job_matching.models.text_encoder import (  # noqa: E402
    HashNgramEncoder, TextEncodeError, build_encoder)

DOCS = ["算法工程师 机器学习 Python", "前端开发 Vue", "财务 报表"]
QUERY = ["机器学习 Python"]


def _digest(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


class P9Reproducibility(unittest.TestCase):
    def test_encoder_same_input_same_output(self):
        enc = HashNgramEncoder(dim=128)
        a = enc.encode(DOCS)
        b = enc.encode(DOCS)
        self.assertEqual(_digest(a), _digest(b))

    def test_encoder_cross_instance_reproducible(self):
        self.assertEqual(_digest(HashNgramEncoder(dim=128).encode(DOCS)),
                         _digest(HashNgramEncoder(dim=128).encode(DOCS)))

    def test_retrieval_rebuild_reproducible(self):
        for cls in (TfidfRecall, BM25Recall):
            ix = cls()
            ix.build(DOCS)
            a = ix.search(QUERY, top_k=3)
            ix2 = cls()
            ix2.build(DOCS)
            b = ix2.search(QUERY, top_k=3)
            self.assertEqual(a, b, f"{cls.__name__} 结果必须可复现")

    def test_fusion_deterministic(self):
        resume = {"education_level": "本科", "skills": {"Python"}, "years_experience": 2.0,
                  "inferred_category": "IT", "city": "上海", "target_position": "算法"}
        job = {"education_tokens": ["本科"], "skills": {"Python"}, "years_min": 1.0,
               "category": "IT", "city": "上海", "job_title": "算法工程师"}
        f = FeatureFusion()
        self.assertEqual(f.score(resume, job, 0.6).to_dict(),
                         f.score(resume, job, 0.6).to_dict())

    def test_repeated_evaluation_same_metrics(self):
        from job_matching.evaluation.retrieval import (
            RelevanceSpec, evaluate_groups)
        gid = np.array(["q1", "q1", "q1"])
        scores = np.array([0.9, 0.5, 0.1])
        rel = np.array([2.0, 1.0, 0.0])
        spec = RelevanceSpec(kind="graded", label_source="unit_test")
        a = evaluate_groups(gid, scores, rel, spec=spec)["summary"]["metrics"]
        b = evaluate_groups(gid, scores, rel, spec=spec)["summary"]["metrics"]
        self.assertEqual(a, b)

    def test_inference_does_not_mutate_encoder_config(self):
        enc = HashNgramEncoder(dim=64)
        before = enc.describe().to_dict()
        enc.encode(["调用一次"])
        self.assertEqual(before, enc.describe().to_dict())

    def test_bge_inference_is_deterministic_and_read_only(self):
        """有条件：BGE 可用时验证同输入同输出 + 权重不被修改。"""
        try:
            enc = build_encoder("bge_small_zh_v15", local_files_only=True,
                                max_length=64, batch_size=2)
        except TextEncodeError as e:
            self.skipTest(f"ENV_INCOMPATIBLE/模型不可用，BGE 复现性测试显式跳过: {e}")

        def _state_digest(model) -> str:
            h = hashlib.sha256()
            for name, t in sorted(model.state_dict().items()):
                h.update(name.encode("utf-8"))
                h.update(t.detach().cpu().numpy().tobytes())
            return h.hexdigest()

        texts = ["中文简历复现性样例", "岗位描述复现性样例"]
        before = _state_digest(enc.model)
        a = enc.encode(texts)
        b = enc.encode(texts)
        after = _state_digest(enc.model)
        self.assertTrue(np.allclose(a, b, atol=1e-5), "BGE 同输入必须同输出")
        self.assertEqual(before, after, "推理不得修改模型权重")


if __name__ == "__main__":
    unittest.main()
