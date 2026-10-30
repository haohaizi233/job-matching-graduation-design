# -*- coding: utf-8 -*-
"""P8 评价指标：排序指标正确性 / 小样本与空样本 / 指标适用性登记。

口径纪律：只有正例、全零相关、组过小必须被单独计数，不得强行输出误导性指标。
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.evaluation.retrieval import (  # noqa: E402
    RelevanceSpec, evaluate_groups, mrr_at_k, ndcg_at_k, pairwise_accuracy,
    precision_at_k, recall_at_k, relevance_from_labels)


class P8EvaluationMetrics(unittest.TestCase):
    def test_ndcg_perfect_ranking_is_one(self):
        y = np.array([3.0, 2.0, 1.0, 0.0])
        s = np.array([0.9, 0.7, 0.4, 0.1])
        self.assertAlmostEqual(1.0, ndcg_at_k(y, s, 4), places=6)

    def test_ndcg_worst_ranking_below_perfect(self):
        y = np.array([3.0, 2.0, 1.0, 0.0])
        perfect = ndcg_at_k(y, np.array([0.9, 0.7, 0.4, 0.1]), 4)
        reversed_ = ndcg_at_k(y, np.array([0.1, 0.4, 0.7, 0.9]), 4)
        self.assertLess(reversed_, perfect)
        self.assertGreater(reversed_, 0.0)

    def test_ndcg_ideal_gain_at_cutoff(self):
        y = np.array([0.0, 0.0, 3.0])
        s = np.array([0.9, 0.8, 0.1])
        self.assertLess(ndcg_at_k(y, s, 2), 1e-9, "理想位置在 K 外时 NDCG@K 应接近 0")

    def test_ndcg_binary_gain_mode(self):
        y = np.array([3.0, 1.0, 0.0])
        s = np.array([0.9, 0.8, 0.7])
        self.assertAlmostEqual(1.0, ndcg_at_k(y, s, 3, gain_mode="binary"), places=6)

    def test_ndcg_empty_and_all_zero(self):
        self.assertTrue(math.isnan(ndcg_at_k(np.array([]), np.array([]), 5)))
        self.assertTrue(math.isnan(ndcg_at_k(np.zeros(3), np.array([.9, .8, .7]), 5)),
                        "全零相关时 IDCG=0，指标不可评估应记 NaN 而非伪造数值")

    def test_mrr_recall_precision_basic(self):
        y = np.array([0.0, 1.0, 0.0, 1.0])
        s = np.array([0.9, 0.8, 0.7, 0.6])
        self.assertAlmostEqual(0.5, mrr_at_k(y, s, 4), places=6)  # 首个相关在第 2 位
        self.assertAlmostEqual(1.0, recall_at_k(y, s, 4), places=6)
        self.assertAlmostEqual(0.0, recall_at_k(y, s, 1), places=6)  # Top1 无相关
        self.assertAlmostEqual(0.5, recall_at_k(y, s, 2), places=6)  # Top2 命中 1/2
        self.assertAlmostEqual(0.5, precision_at_k(y, s, 2), places=6)

    def test_mrr_no_hit_is_zero_recall_no_positive_is_nan(self):
        y = np.array([0.0, 0.0, 0.0])
        s = np.array([0.9, 0.8, 0.7])
        self.assertEqual(0.0, mrr_at_k(y, s, 3))
        self.assertTrue(math.isnan(recall_at_k(y, s, 3)),
                        "没有正例的查询组 Recall 不可评估")

    def test_metrics_on_short_groups_use_actual_size(self):
        y = np.array([1.0, 0.0])
        s = np.array([0.9, 0.1])
        self.assertAlmostEqual(1.0, ndcg_at_k(y, s, 10), places=6, msg="K 大于组大小按实际截断")
        self.assertAlmostEqual(1.0, recall_at_k(y, s, 10), places=6)

    def test_pairwise_accuracy_ties_excluded(self):
        y = np.array([2.0, 1.0])
        s = np.array([0.5, 0.5])
        self.assertTrue(math.isnan(pairwise_accuracy(y, s)),
                        "唯一可比较对预测并列 -> 不计入 -> 不可评估")

    def test_pairwise_accuracy_basic(self):
        y = np.array([2.0, 1.0, 0.0])
        s = np.array([0.9, 0.5, 0.1])
        self.assertAlmostEqual(1.0, pairwise_accuracy(y, s), places=6)
        s_bad = np.array([0.1, 0.5, 0.9])
        self.assertAlmostEqual(0.0, pairwise_accuracy(y, s_bad), places=6)

    def test_relevance_from_labels_marks_unjudgeable(self):
        rel = relevance_from_labels(["2", "unjudgeable", "", "1"], RelevanceSpec(kind="graded"))
        self.assertEqual(2.0, rel[0])
        self.assertTrue(math.isnan(rel[1]))
        self.assertTrue(math.isnan(rel[2]))
        self.assertEqual(1.0, rel[3])

    def test_evaluate_groups_skips_and_counts_edge_cases(self):
        gid = np.array(["q1", "q1", "q1", "q2", "q2", "q3", "q3", "q3"])
        scores = np.array([.9, .8, .7, .6, .5, .4, .3, .2])
        rel = np.array([2.0, 0.0, 1.0,      # q1 正常
                        0.0, 0.0,            # q2 全零相关
                        2.0, np.nan, 1.0])   # q3 含 unjudgeable
        out = evaluate_groups(gid, scores, rel, ks=(2, 3),
                              spec=RelevanceSpec(kind="graded", label_source="unit_test"))
        s = out["summary"]
        self.assertEqual(3, s["queries_total"])
        self.assertEqual(1, s["queries_skipped"]["all_zero_relevance"])
        self.assertEqual(1, s["queries_skipped"]["nan_relevance_dropped"])
        self.assertEqual(2, s["queries_evaluated"], "q1 与 q3 在剔除 NaN 后可评估")
        self.assertIn("relevance_spec", s)
        self.assertEqual("unit_test", s["relevance_spec"]["label_source"],
                         "相关性来源必须显式写入结果元数据")

    def test_evaluate_groups_too_small_recorded(self):
        gid = np.array(["q1", "q2", "q2"])
        scores = np.array([.9, .8, .7])
        rel = np.array([1.0, 1.0, 0.0])
        out = evaluate_groups(gid, scores, rel, ks=(2,))
        self.assertGreaterEqual(out["summary"]["queries_skipped"]["too_small"], 1)

    def test_evaluate_groups_rejects_length_mismatch(self):
        with self.assertRaises(ValueError):
            evaluate_groups(np.array(["a"]), np.array([1.0, 2.0]), np.array([1.0]))

    def test_group_macro_average_not_pair_micro(self):
        """per-query 宏平均：防止高频查询主导（与 metrics.pairwise_accuracy 口径一致）。"""
        from job_matching.evaluation.metrics import pairwise_accuracy as group_pa
        gid = np.array(["a", "a", "b", "b", "b", "b"])
        pred = np.array([0.9, 0.1, 0.4, 0.3, 0.2, 0.1])
        rel = np.array([1.0, 0.0, 3.0, 2.0, 1.0, 0.0])
        res = group_pa(gid, pred, rel)
        self.assertEqual("per_query_macro_average", res["weighting"])
        self.assertAlmostEqual(1.0, res["pairwise_accuracy"], places=6)
        self.assertEqual(2, res["queries_used"])

    def test_per_query_corr_marks_not_evaluable(self):
        from job_matching.evaluation.metrics import per_query_corr
        gid = np.array(["a", "a", "a", "b", "b", "b"])
        pred = np.array([0.9, 0.5, 0.1, 0.4, 0.4, 0.4])   # b 组零方差
        rel = np.array([1.0, 2.0, 3.0, 3.0, 2.0, 1.0])
        res = per_query_corr(gid, pred, rel)
        self.assertEqual(1, res["queries_used"])
        self.assertGreaterEqual(res["queries_not_evaluable"], 1)

    def test_selection_value_rejects_unregistered_key(self):
        from job_matching.evaluation.metrics import selection_value
        with self.assertRaises(KeyError):
            selection_value({}, "not_a_registered_metric")

    def test_binary_relevance_rule(self):
        from job_matching.evaluation.metrics import binary_relevance
        out = binary_relevance(["strong_positive", "medium_positive", "weak_positive"])
        self.assertEqual([1, 1, 0], out.tolist())


if __name__ == "__main__":
    unittest.main()
