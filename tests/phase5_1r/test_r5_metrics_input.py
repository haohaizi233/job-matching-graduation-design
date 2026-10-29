# -*- coding: utf-8 -*-
"""R5：独立评估输入处理回归（Phase5-1R F-009 evaluate_ranking_human 迭代器）。

业务不变量：
  * group_ids / pred_scores / relevance_labels 任意一侧传入一次性生成器，
    结果必须与传入列表**完全一致**（入口统一物化一次）；
  * 历史缺陷：函数内多次 list(relevance_labels)，生成器被提前消费，
    后续迭代得到空数据 -> 长度校验误判或样本静默丢失；
  * 输入长度不一致 / NaN/Inf 分数 / 非法标签 一律显式报错，不静默吞掉；
  * unjudgeable 不进入增益与分母；缺失标签不填补；
  * 全零相关性组跳过、组大小不足跳过、同分排序确定性；
  * 归档指标口径不得改变：gain_mode/label_source/unjudgeable_policy 字段保持一致。
"""
from __future__ import annotations

import math
import unittest

import _util as U  # noqa: F401

from job_matching.independent_eval.metrics import (evaluate_ranking_human,
                                                   prepare_human_labels)

# 与历史归档口径一致的契约字段（改变即视为口径变更，需版本化）
ARCHIVED_CONTRACT = {
    "label_source": "human_gold",
    "gain_mode": "human_ordinal_0_1_2",
    "unjudgeable_policy": "excluded_from_gain_and_denominator",
    "precision_denominator": "min(k, group_size)",
}


def sample_rows():
    """3 个查询组、12 条样本（含 unjudgeable / 缺失标签 / 全零组）。"""
    groups = ["q1"] * 4 + ["q2"] * 4 + ["q3"] * 4
    scores = [0.9, 0.8, 0.7, 0.6,
              0.95, 0.55, 0.35, 0.15,
              0.5, 0.4, 0.3, 0.2]
    labels = ["2", "1", "0", "unjudgeable",
              "2", "0", "1", "",
              "0", "0", "0", "0"]
    return groups, scores, labels


class R9GeneratorMaterialization(unittest.TestCase):
    """F-009 核心：生成器输入与列表输入等价。"""

    def test_all_three_generators_equal_lists(self):
        g, s, lab = sample_rows()
        by_list = evaluate_ranking_human(g, s, lab)
        by_gen = evaluate_ranking_human(iter(g), iter(s), iter(lab))
        self.assertEqual(by_list, by_gen)

    def test_generator_of_relevance_not_consumed_twice(self):
        """历史缺陷复现：labels 传生成器时，二次 list() 只能得到空序列。"""
        g, s, lab = sample_rows()
        res = evaluate_ranking_human(g, s, (x for x in lab))
        self.assertEqual(res["label_filter_stats"]["judgeable"],
                         sum(1 for x in lab if x in ("0", "1", "2")))
        self.assertGreater(res["queries_evaluated"], 0)

    def test_lazy_generator_with_maps(self):
        g, s, lab = sample_rows()
        res = evaluate_ranking_human(
            (x for x in g), (float(x) for x in s), (str(x) for x in lab))
        self.assertEqual(res["queries_evaluated"], 2)   # q3 全零相关性被跳过

    def test_result_reproducible(self):
        g, s, lab = sample_rows()
        r1 = evaluate_ranking_human(g, s, lab)
        r2 = evaluate_ranking_human(list(g), list(s), list(lab))
        self.assertEqual(r1, r2)


class R9InputValidation(unittest.TestCase):
    """非法输入显式报错（不静默吞掉）。"""

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["q1", "q1"], [0.5], ["1", "0"])
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["q1"], [0.5, 0.4], ["1"])

    def test_length_mismatch_with_generators_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(iter(["q1", "q1"]), iter([0.5]), iter(["1"]))

    def test_nan_score_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["q1", "q1"], [0.5, float("nan")], ["1", "0"])

    def test_inf_score_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["q1", "q1"], [0.5, float("inf")], ["1", "0"])

    def test_invalid_label_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["q1", "q1"], [0.5, 0.4], ["3", "0"])
        with self.assertRaises(ValueError):
            evaluate_ranking_human(["q1", "q1"], [0.5, 0.4], ["good", "0"])

    def test_prepare_human_labels_contract(self):
        gains, stats = prepare_human_labels(["2", "1", "0", "unjudgeable", ""])
        self.assertEqual(list(gains), [2.0, 1.0, 0.0])
        self.assertEqual(stats["unjudgeable"], 1)
        self.assertEqual(stats["unlabeled"], 1)
        self.assertEqual(stats["judgeable"], 3)


class R9FilteringSemantics(unittest.TestCase):
    """unjudgeable / 缺失 / 全零组 / 组大小 过滤语义。"""

    def test_empty_inputs_not_filled(self):
        res = evaluate_ranking_human([], [], [])
        self.assertEqual(res["queries_evaluated"], 0)
        self.assertIsNone(res["precision@5"])
        self.assertIsNone(res["ndcg@5"])
        self.assertIn("不填充数值", res["note"])

    def test_unjudgeable_excluded_from_denominator(self):
        g = ["q1"] * 3
        s = [0.9, 0.8, 0.7]
        lab = ["2", "unjudgeable", "unjudgeable"]
        res = evaluate_ranking_human(g, s, lab)
        self.assertEqual(res["label_filter_stats"]["unjudgeable"], 2)
        self.assertEqual(res["label_filter_stats"]["judgeable"], 1)
        # 仅剩 1 条 -> 组大小不足 min_group_size=2，不评估而非填补
        self.assertEqual(res["queries_evaluated"], 0)

    def test_unlabeled_excluded(self):
        g = ["q1"] * 3
        s = [0.9, 0.8, 0.7]
        lab = ["2", "", "1"]
        res = evaluate_ranking_human(g, s, lab)
        self.assertEqual(res["label_filter_stats"]["unlabeled"], 1)
        self.assertEqual(res["label_filter_stats"]["judgeable"], 2)
        self.assertEqual(res["queries_evaluated"], 1)

    def test_label_filter_stats_sum(self):
        g, s, lab = sample_rows()
        res = evaluate_ranking_human(g, s, lab)
        st = res["label_filter_stats"]
        self.assertEqual(st["judgeable"] + st["unjudgeable"] + st["unlabeled"], len(lab))

    def test_zero_relevance_group_skipped(self):
        g, s, lab = sample_rows()
        res = evaluate_ranking_human(g, s, lab)
        self.assertGreaterEqual(res["queries_skipped_zero_relevance"], 1)

    def test_min_group_size_filter(self):
        g = ["q1", "q2", "q2"]
        s = [0.9, 0.8, 0.7]
        lab = ["2", "2", "1"]
        res = evaluate_ranking_human(g, s, lab, min_group_size=2)
        self.assertEqual(res["queries_evaluated"], 1)   # q1 只有 1 条被过滤

    def test_single_item_group_can_be_evaluated_when_min_size_1(self):
        g = ["q1", "q2", "q2"]
        s = [0.9, 0.8, 0.7]
        lab = ["2", "2", "1"]
        res = evaluate_ranking_human(g, s, lab, min_group_size=1)
        self.assertEqual(res["queries_evaluated"], 2)


class R9DeterminismAndContract(unittest.TestCase):
    """同分排序确定性 + 归档指标口径不变。"""

    def test_tie_scores_deterministic(self):
        g = ["q1"] * 4
        s = [0.5, 0.5, 0.5, 0.5]
        lab = ["2", "0", "1", "0"]
        r1 = evaluate_ranking_human(g, s, lab, ks=(2,))
        r2 = evaluate_ranking_human(list(g), list(s), list(lab), ks=(2,))
        self.assertEqual(r1["all"]["precision@2"], r2["all"]["precision@2"])
        self.assertEqual(r1["all"]["ndcg@2"], r2["all"]["ndcg@2"])
        # 稳定 tie-breaking：同分按原始行序 -> 首两位为 2/0 -> precision@2 = 0.5
        self.assertEqual(r1["all"]["precision@2"], 0.5)

    def test_archived_contract_fields_unchanged(self):
        g, s, lab = sample_rows()
        res = evaluate_ranking_human(g, s, lab)
        for key, want in ARCHIVED_CONTRACT.items():
            self.assertEqual(res[key], want, key)

    def test_scope_fields_present(self):
        g, s, lab = sample_rows()
        res = evaluate_ranking_human(g, s, lab, ks=(2, 5))
        for scope in ("all", "size_ge_2", "size_ge_maxk"):
            self.assertIn(scope, res)
        self.assertEqual(res["ks"], [2, 5])
        self.assertIn("effective_query_count", res)


if __name__ == "__main__":
    unittest.main(verbosity=2)
