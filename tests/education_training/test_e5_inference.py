# -*- coding: utf-8 -*-
"""E5：推理接口（异常输入 / 稳定性 / 无监督目标依赖）。"""
from __future__ import annotations

import unittest
from pathlib import Path

from _util import ROOT, label_access_hits, latest_run_dir

RUN_DIR = latest_run_dir()


class E5Inference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RUN_DIR is None:
            raise unittest.SkipTest("尚无已训练模型目录")
        from job_matching.education.predictor import EducationNormalizer
        cls.nz = EducationNormalizer.from_model_dir(RUN_DIR, fallback_to_rules=True)

    def test_single_pair_independent_prediction(self):
        r = self.nz.normalize("本科及以上")
        self.assertIn("labels", r)
        self.assertTrue(len(r["labels"]) >= 1)
        self.assertIn("confidence_meaning", r)

    def test_batch_equals_single(self):
        texts = ["本科", "硕士及以上", "大专", "不限", "火星文"]
        single = [self.nz.normalize(t)["labels"] for t in texts]
        batch = [r["labels"] for r in self.nz.batch(texts)]
        self.assertEqual(single, batch)

    def test_repeat_stability(self):
        texts = ["本科", "博士", "学历不限", "专科及以上"]
        a = [r["labels"] for r in self.nz.batch(texts)]
        b = [r["labels"] for r in self.nz.batch(texts)]
        self.assertEqual(a, b)

    def test_empty_input_handled(self):
        r = self.nz.normalize("")
        self.assertEqual(r["labels"], ["学历不明"])
        r2 = self.nz.normalize(None)
        self.assertEqual(r2["labels"], ["学历不明"])
        r3 = self.nz.normalize("   ")
        self.assertEqual(r3["labels"], ["学历不明"])

    def test_unknown_expression_no_crash(self):
        for t in ["火星文学历", "985", "🎓硕士", "博士" * 100, "本科/硕士、博士；及以上?"]:
            r = self.nz.normalize(t)
            self.assertIsInstance(r["labels"], list)
            self.assertGreaterEqual(len(r["labels"]), 1)

    def test_unicode_and_whitespace_normalization(self):
        a = self.nz.normalize("本科")
        b = self.nz.normalize("  本科  ")          # 首尾空白
        c = self.nz.normalize("\u3000本科\u3000")   # 全角空格（NFKC 归一）
        self.assertEqual(a["normalized_input"], b["normalized_input"])
        self.assertEqual(a["normalized_input"], c["normalized_input"])

    def test_inference_has_no_label_dependency(self):
        hits = label_access_hits(ROOT / "src" / "job_matching" / "education" / "predictor.py")
        self.assertEqual(hits, [], f"推理代码引用监督目标字段: {hits}")

    def test_predictor_works_without_dataset_files(self):
        """推理只需要模型目录；不加载任何 data/ 表即可工作。"""
        from job_matching.education.predictor import EducationNormalizer
        nz = EducationNormalizer.from_model_dir(RUN_DIR, fallback_to_rules=True)
        r = nz.normalize("硕士")
        self.assertIn("labels", r)

    def test_output_matches_label_vocabulary(self):
        from job_matching.education.labels import LABEL_ORDER
        for t in ["本科", "硕士及以上", "学历不限", "大专", "火星文"]:
            for lab in self.nz.normalize(t)["labels"]:
                self.assertIn(lab, LABEL_ORDER)


if __name__ == "__main__":
    unittest.main()
