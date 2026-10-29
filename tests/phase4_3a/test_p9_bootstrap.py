# -*- coding: utf-8 -*-
"""P9 场景 11：配对 Bootstrap 的确定性与稳定性（协议第七节）。

纪律：重采样单位 = 查询组（简历）；同一次 Bootstrap 中所有模型共享同一批重采样组；
有效查询组 < 20 时必须报告 statistical_stability="unstable"。
"""
from __future__ import annotations

import unittest

import numpy as np

from job_matching.evaluation.statistical_tests import bootstrap_diff
from job_matching.independent_eval.bootstrap import (
    DEFAULT_N_BOOT, DEFAULT_SEED, MIN_GROUPS_FOR_STABILITY,
    paired_bootstrap_vs_baseline, per_query_metric,
)


def per_query(ndcg=0.7, n=25, start=0, tag="q"):
    return {f"{tag}-{i:03d}": ndcg + (i % 5) * 0.01 for i in range(start, start + n)}


class P9TestPerQueryMetric(unittest.TestCase):
    def test_p9_per_query_ndcg_values(self):
        out = per_query_metric(["r1", "r1", "r1"], [0.9, 0.8, 0.7], ["2", "1", "0"],
                               metric="ndcg", k=5)
        self.assertEqual(out, {"r1": 1.0})

    def test_p9_per_query_precision_recall_mrr(self):
        g = ["r1", "r1", "r1"]
        s = [0.9, 0.8, 0.7]
        lab = ["2", "1", "0"]
        self.assertAlmostEqual(per_query_metric(g, s, lab, metric="precision", k=5)["r1"],
                               2 / 3, places=6)
        self.assertEqual(per_query_metric(g, s, lab, metric="recall", k=5)["r1"], 1.0)
        self.assertEqual(per_query_metric(g, s, lab, metric="mrr", k=5)["r1"], 1.0)

    def test_p9_per_query_skips_unjudgeable_and_small_and_zero(self):
        # r1：1 条 unjudgeable 剔除后仍 >=2 候选 -> 保留
        # r2：2 条候选但全零相关 -> 剔除
        # r3：仅 1 条候选 -> 组内候选不足剔除
        out = per_query_metric(["r1", "r1", "r1", "r2", "r2", "r3"],
                               [0.9, 0.8, 0.7, 0.1, 0.2, 0.5],
                               ["unjudgeable", "1", "2", "0", "0", "2"],
                               metric="ndcg", k=5)
        self.assertEqual(set(out), {"r1"})
        stats = per_query_metric.last_stats
        self.assertEqual(stats["unjudgeable_or_unlabeled"], 1)
        self.assertEqual(stats["skipped_small_groups"], 1)
        self.assertEqual(stats["skipped_zero_relevance_groups"], 1)

    def test_p9_per_query_unknown_metric(self):
        with self.assertRaises(ValueError):
            per_query_metric(["r1", "r1"], [0.9, 0.8], ["2", "1"], metric="auc")

    def test_p9_per_query_empty(self):
        self.assertEqual(per_query_metric([], [], [], metric="ndcg"), {})


class P9TestPairedBootstrap(unittest.TestCase):
    def test_p9_shared_resampling_groups_enforced(self):
        base = per_query(ndcg=0.5, n=25, tag="q")
        m1 = per_query(ndcg=0.7, n=25, tag="q")
        m2 = {k: 0.6 for k in list(base)[:24]}      # 少一个查询组
        with self.assertRaises(ValueError) as ctx:
            paired_bootstrap_vs_baseline({"base": base, "m1": m1, "m2": m2}, "base")
        self.assertIn("有效查询组与基线不一致", str(ctx.exception))

    def test_p9_unknown_baseline_rejected(self):
        base = per_query(ndcg=0.5, n=25, tag="q")
        with self.assertRaises(ValueError):
            paired_bootstrap_vs_baseline({"base": base}, "nope")

    def test_p9_stable_when_enough_groups(self):
        base = per_query(ndcg=0.5, n=25, tag="q")
        m1 = per_query(ndcg=0.7, n=25, tag="q")
        res = paired_bootstrap_vs_baseline({"base": base, "m1": m1}, "base",
                                           metric="ndcg", k=5, n_boot=200, seed=1)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["queries"], 25)
        self.assertEqual(res["unit"], "query(resume_id)")
        self.assertEqual(res["statistical_stability"], "stable")
        self.assertEqual(res["stability_note"], "")
        self.assertIn("m1", res["comparisons"])
        cmp = res["comparisons"]["m1"]
        self.assertEqual(cmp["baseline"], "base")
        self.assertAlmostEqual(cmp["mean_diff"], 0.2, places=6)
        self.assertGreater(cmp["ci_low"], 0.0)
        self.assertTrue(cmp["significant_at_95"])
        self.assertEqual(cmp["interpretation"], "significant")

    def test_p9_unstable_when_few_groups(self):
        self.assertEqual(MIN_GROUPS_FOR_STABILITY, 20)
        base = per_query(ndcg=0.5, n=12, tag="q")
        m1 = per_query(ndcg=0.7, n=12, tag="q")
        res = paired_bootstrap_vs_baseline({"base": base, "m1": m1}, "base",
                                           n_boot=200, seed=1)
        self.assertEqual(res["statistical_stability"], "unstable")
        self.assertIn("禁止声明显著优于 Baseline", res["stability_note"])
        self.assertEqual(res["queries"], 12)

    def test_p9_no_effective_queries_not_computable(self):
        res = paired_bootstrap_vs_baseline({"base": {}, "m1": {}}, "base")
        self.assertEqual(res["status"], "not_computable")
        self.assertEqual(res["reason"], "no_effective_queries")

    def test_p9_baseline_excluded_from_comparisons(self):
        base = per_query(ndcg=0.5, n=25, tag="q")
        res = paired_bootstrap_vs_baseline({"base": dict(base)}, "base", n_boot=50, seed=1)
        self.assertEqual(res["comparisons"], {})

    def test_p9_deterministic_across_calls(self):
        base = per_query(ndcg=0.5, n=25, tag="q")
        m1 = per_query(ndcg=0.7, n=25, tag="q")
        m2 = per_query(ndcg=0.65, n=25, tag="q")
        kw = dict(metric="ndcg", k=5, n_boot=300, seed=DEFAULT_SEED, ci=0.95)
        a = paired_bootstrap_vs_baseline({"base": base, "m1": m1, "m2": m2}, "base", **kw)
        b = paired_bootstrap_vs_baseline({"base": base, "m1": m1, "m2": m2}, "base", **kw)
        self.assertEqual(a, b)

    def test_p9_defaults_match_protocol(self):
        self.assertEqual(DEFAULT_N_BOOT, 1000)
        self.assertEqual(DEFAULT_SEED, 20261205)

    def test_p9_models_share_identical_resampling_indices(self):
        """手工重放 rng.integers(0, n, (n_boot, n))，证明两次对比用的是同一批重采样组。"""
        base = per_query(ndcg=0.5, n=25, tag="q")
        m1 = per_query(ndcg=0.7, n=25, tag="q")
        m2 = per_query(ndcg=0.8, n=25, tag="q")
        n_boot, seed = 300, 20261205
        r1 = bootstrap_diff(m1, base, n_boot=n_boot, seed=seed, ci=0.95)
        r2 = bootstrap_diff(m2, base, n_boot=n_boot, seed=seed, ci=0.95)
        self.assertEqual(r1["seed"], r2["seed"])
        self.assertEqual(r1["n_boot"], r2["n_boot"])
        self.assertEqual(r1["queries"], r2["queries"])

        keys = sorted(base)
        n = len(keys)
        diff1 = np.array([m1[k] - base[k] for k in keys])
        diff2 = np.array([m2[k] - base[k] for k in keys])
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, n, size=(n_boot, n))
        for diff, res in ((diff1, r1), (diff2, r2)):
            means = diff[idx].mean(axis=1)
            lo = float(np.quantile(means, 0.025))
            hi = float(np.quantile(means, 0.975))
            self.assertAlmostEqual(res["mean_diff"], round(float(diff.mean()), 6), places=6)
            self.assertAlmostEqual(res["ci_low"], round(lo, 6), places=6)
            self.assertAlmostEqual(res["ci_high"], round(hi, 6), places=6)
            self.assertEqual(res["significant_at_95"], bool(lo > 0 or hi < 0))

    def test_p9_no_common_queries(self):
        r = bootstrap_diff({"a-1": 1.0}, {"b-1": 1.0}, n_boot=10, seed=1)
        self.assertEqual(r["queries"], 0)
        self.assertIn("没有共同查询", r["note"])

    def test_p9_resampling_unit_is_query_group(self):
        base = per_query(ndcg=0.5, n=25, tag="q")
        m1 = per_query(ndcg=0.7, n=25, tag="q")
        res = paired_bootstrap_vs_baseline({"base": base, "m1": m1}, "base",
                                           n_boot=50, seed=1)
        self.assertEqual(res["unit"], "query(resume_id)")
        self.assertIn("查询组", res["shared_resampling_guarantee"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
