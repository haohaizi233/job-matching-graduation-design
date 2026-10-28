# -*- coding: utf-8 -*-
"""T5 独立推理与稳定排序（验收项 10、11）。

 10. 单个简历 + 单个岗位能独立生成预测分数（不查历史 matches、不依赖标签）。
 11. 多岗位排序稳定且可重复（同分保持输入顺序，重复调用结果一致）。
"""
from __future__ import annotations

import unittest

from _util import any_run_dir

from job_matching.inference.predictor import MatchPredictor

RESUME = {"candidate_id": "cand_test", "target_position_norm": "软件工程师",
          "skills_canonical_json": '["java", "spring", "mysql"]',
          "inferred_category": "INFORMATION-TECHNOLOGY", "years_experience": 3}
JOBS = [
    {"job_id": 1, "job_title_norm": "java 开发工程师",
     "category": "INFORMATION-TECHNOLOGY", "skills_canonical_json": '["java", "spring"]'},
    {"job_id": 2, "job_title_norm": "财务分析师", "category": "FINANCE",
     "skills_canonical_json": '["finance", "excel"]'},
    {"job_id": 3, "job_title_norm": "软件工程师", "category": "INFORMATION-TECHNOLOGY",
     "skills_canonical_json": '["java", "mysql"]'},
]


class T5Inference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = any_run_dir()
        if run is None:
            raise unittest.SkipTest("没有可用的已训练模型目录")
        cls.run_dir = run
        cls.predictor = MatchPredictor(run, device="cpu")

    def test_single_pair_prediction(self):
        s = self.predictor.predict_score(RESUME, JOBS[0])
        self.assertIsInstance(s, float)
        self.assertTrue(abs(s) < 1e6 and s == s, "预测分数非法")

    def test_prediction_without_labels(self):
        # 输入里即使携带标签字段，预测也必须与不带时一致（推理无标签依赖）
        base = self.predictor.predict_score(RESUME, JOBS[0])
        with_labels = self.predictor.predict_score(
            dict(RESUME, final_score=1.0, label_strength="strong_positive",
                 candidate_rank=1, candidate_rank_pct=0.0),
            dict(JOBS[0], final_score=1.0, label_strength="strong_positive"))
        self.assertAlmostEqual(base, with_labels, places=12)

    def test_rank_jobs_stable_and_repeatable(self):
        r1 = self.predictor.rank_jobs(RESUME, JOBS)
        r2 = self.predictor.rank_jobs(RESUME, JOBS)
        self.assertEqual([x["job_id"] for x in r1], [x["job_id"] for x in r2])
        self.assertEqual([x["score"] for x in r1], [x["score"] for x in r2])
        scores = [x["score"] for x in r1]
        self.assertEqual(scores, sorted(scores, reverse=True), "排序未按分数降序")
        self.assertEqual([x["rank"] for x in r1], [1, 2, 3])

        # 输入顺序打乱，分数多重集不变（稳定排序只影响同分顺序）
        r3 = self.predictor.rank_jobs(RESUME, list(reversed(JOBS)))
        self.assertEqual(sorted(x["score"] for x in r1),
                         sorted(x["score"] for x in r3))

    def test_input_validation(self):
        with self.assertRaises(Exception):
            self.predictor.predict_score({"target_position_norm": "x"}, JOBS[0])
        with self.assertRaises(Exception):
            self.predictor.rank_jobs(RESUME, "not-a-list")

    def test_info_declares_no_label_dependency(self):
        info = self.predictor.info()
        self.assertFalse(info["requires_labels"])
        self.assertTrue(info["supports_cpu"])


if __name__ == "__main__":
    unittest.main()
