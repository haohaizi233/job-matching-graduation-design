# -*- coding: utf-8 -*-
"""P8 场景 10：独立评估排序指标正确性（协议第六节）。

口径：查询组 = 简历；增益 = 人工有序标签 {0,1,2}；相关阈值 = 1；
unjudgeable 不进增益、不进分母；Precision@K 分母 = min(K, 组内候选数)。
"""
from __future__ import annotations

import math
import unittest

from job_matching.independent_eval.metrics import (
    evaluate_ranking_human, prepare_human_labels,
)
from job_matching.metrics_ranking import evaluate_ranking


def dcg(gains, k):
    g = list(gains)[:k]
    return sum(v / math.log2(i + 2) for i, v in enumerate(g))


def ndcg_ref(ranked, ideal, k):
    return dcg(ranked, k) / dcg(sorted(ideal, reverse=True), k)


class P8TestMetricValues(unittest.TestCase):
    def test_p8_perfect_ranking(self):
        out = evaluate_ranking_human(["r1", "r1", "r1"], [0.9, 0.8, 0.7], ["2", "1", "0"])
        self.assertEqual(out["label_source"], "human_gold")
        self.assertEqual(out["gain_mode"], "human_ordinal_0_1_2")
        self.assertEqual(out["relevance_threshold"], 1)
        self.assertEqual(out["precision_denominator"], "min(k, group_size)")
        self.assertEqual(out["all"]["ndcg@5"], 1.0)
        self.assertEqual(out["all"]["ndcg@10"], 1.0)
        self.assertEqual(out["all"]["mrr@5"], 1.0)
        self.assertEqual(out["all"]["recall@5"], 1.0)
        self.assertAlmostEqual(out["all"]["precision@5"], 2 / 3, places=6)
        self.assertAlmostEqual(out["all"]["precision@5_with_zero_rel_groups"], 2 / 3, places=6)
        self.assertEqual(out["effective_query_count"], 1)
        self.assertEqual(out["queries_evaluated"], 1)
        self.assertEqual(out["queries_skipped_zero_relevance"], 0)

    def test_p8_inverted_ranking_values(self):
        out = evaluate_ranking_human(["r1", "r1", "r1"], [0.1, 0.2, 0.9], ["2", "1", "0"])
        want = ndcg_ref([0, 1, 2], [2, 1, 0], 5)
        self.assertAlmostEqual(out["all"]["ndcg@5"], round(want, 6), places=6)
        self.assertAlmostEqual(out["all"]["ndcg@5"], 0.619906, places=6)
        self.assertAlmostEqual(out["all"]["ndcg@10"], round(want, 6), places=6)
        self.assertEqual(out["all"]["mrr@5"], 0.5, "首个相关项在第 2 位")
        self.assertEqual(out["all"]["recall@5"], 1.0)
        self.assertAlmostEqual(out["all"]["precision@5"], 2 / 3, places=6)

    def test_p8_relevance_threshold_one(self):
        """relevance=1 计为相关，0 不计入相关项。"""
        out = evaluate_ranking_human(["r1", "r1"], [0.9, 0.8], ["1", "0"])
        self.assertEqual(out["all"]["recall@5"], 1.0)
        self.assertAlmostEqual(out["all"]["precision@5"], 0.5, places=6)

    def test_p8_unjudgeable_excluded_not_zero(self):
        out = evaluate_ranking_human(["r1", "r1", "r1"], [0.9, 0.5, 0.1],
                                     ["2", "unjudgeable", "0"])
        self.assertEqual(out["label_filter_stats"]["unjudgeable"], 1)
        self.assertEqual(out["label_filter_stats"]["judgeable"], 2)
        self.assertEqual(out["queries_total"], 1)
        self.assertEqual(out["all"]["ndcg@5"], 1.0)
        self.assertAlmostEqual(out["all"]["precision@5"], 0.5, places=6)
        self.assertEqual(out["all"]["recall@5"], 1.0)
        self.assertEqual(out["unjudgeable_policy"], "excluded_from_gain_and_denominator")

    def test_p8_precision_denominator_is_min_k_and_group_size(self):
        out = evaluate_ranking_human(["r1"] * 3, [0.9, 0.8, 0.7], ["2", "1", "0"], ks=(5,))
        self.assertAlmostEqual(out["all"]["precision@5"], 2 / 3, places=6,
                               msg="分母应是 min(5, 3) = 3")
        out10 = evaluate_ranking_human(["r1"] * 3, [0.9, 0.8, 0.7], ["2", "1", "0"], ks=(10,))
        self.assertAlmostEqual(out10["all"]["precision@10"], 2 / 3, places=6)

    def test_p8_tie_breaking_is_stable(self):
        """分数相同时按原始行序稳定排序（与 metrics_ranking 一致）。"""
        out = evaluate_ranking_human(["r1"] * 3, [0.5, 0.5, 0.5], ["2", "1", "0"])
        self.assertEqual(out["all"]["ndcg@5"], 1.0)
        out2 = evaluate_ranking_human(["r1"] * 3, [0.5, 0.5, 0.5], ["0", "1", "2"])
        self.assertAlmostEqual(out2["all"]["ndcg@5"], round(ndcg_ref([0, 1, 2], [0, 1, 2], 5), 6),
                               places=6)

    def test_p8_matches_metrics_ranking_implementation(self):
        """不另立计算口径：NDCG/MRR/Recall 必须与 metrics_ranking 同源，
        同时与本文件内独立实现的 ndcg_ref 交叉验证。"""
        groups = ["r1", "r1", "r1", "r2", "r2", "r2"]
        scores = [0.1, 0.2, 0.9, 0.9, 0.8, 0.7]
        labels = ["2", "1", "0", "2", "0", "1"]
        got = evaluate_ranking_human(groups, scores, labels)

        # 独立复算（不复用被测代码）
        r1_ranked, r1_ideal = [0, 1, 2], [2, 1, 0]
        r2_ranked, r2_ideal = [2, 0, 1], [2, 1, 0]
        want_ndcg = (ndcg_ref(r1_ranked, r1_ideal, 5) + ndcg_ref(r2_ranked, r2_ideal, 5)) / 2
        self.assertAlmostEqual(got["all"]["ndcg@5"], round(want_ndcg, 6), places=6)
        self.assertAlmostEqual(got["all"]["ndcg@5"], 0.785070, places=6)
        self.assertAlmostEqual(got["all"]["mrr@5"], (0.5 + 1.0) / 2, places=6)
        self.assertAlmostEqual(got["all"]["recall@5"], 1.0, places=6)
        self.assertAlmostEqual(got["all"]["precision@5"], 2 / 3, places=6)

        # 口径同源校验
        gains = [float(x) for x in labels]
        binary = [1 if x >= 1 else 0 for x in gains]
        base = evaluate_ranking(groups, scores, gains, binary_relevant=binary,
                                ks=(5, 10), gain_mode="score", min_group_size=2)
        for k in (5, 10):
            self.assertEqual(got["all"][f"ndcg@{k}"], base["all"][f"ndcg@{k}"])
            self.assertEqual(got["all"][f"mrr@{k}"], base["all"][f"mrr@{k}"])
            self.assertEqual(got["all"][f"recall@{k}"], base["all"][f"recall@{k}"])
        self.assertEqual(got["queries_total"], base["queries_total"])


class P8TestZeroAndSmallGroups(unittest.TestCase):
    def test_p8_zero_relevance_group_skipped(self):
        out = evaluate_ranking_human(["r2", "r2"], [0.9, 0.1], ["0", "0"])
        self.assertEqual(out["all"]["queries_evaluated"], 0)
        self.assertEqual(out["all"]["queries_skipped_zero_relevance"], 1)
        self.assertIsNone(out["all"]["ndcg@5"])
        self.assertIsNone(out["all"]["precision@5"])
        self.assertEqual(out["all"]["precision@5_with_zero_rel_groups"], 0.0)
        self.assertEqual(out["effective_query_count"], 0)

    def test_p8_single_item_group_not_ranked(self):
        out = evaluate_ranking_human(["r1"], [0.9], ["2"])
        self.assertEqual(out["queries_total"], 1)
        self.assertEqual(out["queries_size_eq_1"], 1)
        self.assertEqual(out["queries_size_ge_2"], 0)
        self.assertEqual(out["all"]["queries_evaluated"], 0)
        self.assertEqual(out["effective_query_count"], 0)

    def test_p8_min_group_size_is_configurable(self):
        out = evaluate_ranking_human(["r1"], [0.9], ["2"], min_group_size=1)
        self.assertEqual(out["all"]["queries_evaluated"], 1)
        self.assertEqual(out["all"]["ndcg@5"], 1.0)

    def test_p8_empty_input_no_fake_numbers(self):
        out = evaluate_ranking_human([], [], [])
        self.assertEqual(out["queries_total"], 0)
        self.assertEqual(out["effective_query_count"], 0)
        for k in (5, 10):
            self.assertIsNone(out[f"precision@{k}"])
            self.assertIsNone(out[f"ndcg@{k}"])
            self.assertIsNone(out[f"mrr@{k}"])
            self.assertIsNone(out[f"recall@{k}"])
        self.assertIn("不可计算", out["note"])

    def test_p8_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["r1", "r1"], [0.9], ["2", "1"])
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["r1"], [0.9, 0.1], ["2"])

    def test_p8_invalid_label_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["r1", "r1"], [0.9, 0.8], ["3", "1"])
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["r1", "r1"], [0.9, 0.8], ["maybe", "1"])

    def test_p8_prepare_human_labels_filters(self):
        gains, stats = prepare_human_labels(["2", "1", "0", "unjudgeable", ""])
        self.assertEqual(list(gains), [2.0, 1.0, 0.0])
        self.assertEqual(stats, {"unjudgeable": 1, "unlabeled": 1, "judgeable": 3,
                                 "invalid": 0})

    def test_p8_scope_variants_present(self):
        out = evaluate_ranking_human(["r1"] * 3, [0.9, 0.8, 0.7], ["2", "1", "0"])
        for scope in ("all", "size_ge_2", "size_ge_maxk"):
            self.assertIn("precision@5", out[scope])
            self.assertIn("ndcg@5", out[scope])
        self.assertEqual(out["ks"], [5, 10])
        self.assertEqual(out["min_group_size"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
