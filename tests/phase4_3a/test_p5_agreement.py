# -*- coding: utf-8 -*-
"""P5 场景 7：双人标注一致性（一致率 / Kappa / Weighted Kappa / 分歧统计）。

基准：sklearn.metrics.cohen_kappa_score（labels=[0,1,2]）作为外部真值。
"""
from __future__ import annotations

import unittest

from _util import ANNOTATOR_A, ANNOTATOR_B, annotation_row, paired

from job_matching.annotation.agreement import (
    MIN_SAMPLES_FOR_KAPPA, NOT_COMPUTABLE, agreement_report, cohens_kappa,
    disagreement_detail, paired_labels, raw_agreement, weighted_kappa,
)

try:
    from sklearn.metrics import cohen_kappa_score as _sk_kappa
    HAS_SK = True
except Exception:  # pragma: no cover
    HAS_SK = False


def pairs_from(labels_a, labels_b, prefix="pair"):
    a, b = paired(ANNOTATOR_A, labels_a, ANNOTATOR_B, labels_b, prefix=prefix)
    return paired_labels(a, b)


class P5TestRawAgreement(unittest.TestCase):
    def test_p5_perfect_agreement(self):
        p = pairs_from([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
        r = raw_agreement(p)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["agreements"], 10)
        self.assertEqual(r["value"], 1.0)
        self.assertEqual(r["n_judgeable"], 10)

    def test_p5_unjudgeable_excluded_from_judgeable(self):
        p = pairs_from(["2", "unjudgeable", "0", "unjudgeable", "1", "1"],
                       ["2", "unjudgeable", "1", "2", "1", "unjudgeable"])
        r = raw_agreement(p)
        self.assertEqual(r["n_paired"], 6)
        self.assertEqual(r["n_judgeable"], 3)   # (2,2) (1,1) 及 (0,1) 三对双方可判定
        self.assertEqual(r["both_unjudgeable"], 1)
        self.assertEqual(r["one_side_unjudgeable"], 2)
        self.assertAlmostEqual(r["value"], 2 / 3, places=6)

    def test_p5_no_judgeable_overlap_not_computable(self):
        p = pairs_from(["unjudgeable", "unjudgeable"], ["0", "1"])
        r = raw_agreement(p)
        self.assertEqual(r["status"], NOT_COMPUTABLE)
        self.assertEqual(r["reason"], "no_judgeable_overlap")
        self.assertIsNone(r["value"], "不可计算时禁止填充数值")

    def test_p5_paired_labels_sorted_and_deterministic(self):
        p = pairs_from(["1", "0", "2"], ["1", "1", "2"])
        self.assertEqual([x["pair_id"] for x in p], ["pair-000", "pair-001", "pair-002"])
        self.assertEqual(p[0]["annotator_a"], ANNOTATOR_A)
        self.assertEqual(p[0]["annotator_b"], ANNOTATOR_B)


class P5TestKappaAgainstSklearn(unittest.TestCase):
    CASES = {
        "perfect": ([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]),
        "reversal": ([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]),
        "asym": ([0, 0, 0, 0, 0, 0, 1, 1, 1, 1], [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]),
        "mixed3": ([0, 0, 1, 1, 2, 2, 0, 1, 2, 1, 0, 2], [0, 1, 1, 2, 2, 0, 1, 2, 2, 1, 1, 0]),
    }

    def test_p5_known_kappa_values(self):
        self.assertEqual(cohens_kappa(pairs_from(*self.CASES["perfect"]))["value"], 1.0)
        self.assertEqual(cohens_kappa(pairs_from(*self.CASES["reversal"]))["value"], -1.0)
        # 手算：po=0.8, pe=0.48 -> kappa = 0.32/0.52
        self.assertAlmostEqual(cohens_kappa(pairs_from(*self.CASES["asym"]))["value"],
                               0.32 / 0.52, places=6)

    @unittest.skipUnless(HAS_SK, "sklearn 不可用")
    def test_p5_kappa_matches_sklearn(self):
        for name, (a, b) in self.CASES.items():
            got = cohens_kappa(pairs_from(a, b))
            want = float(_sk_kappa(a, b, labels=[0, 1, 2]))
            self.assertEqual(got["status"], "ok", name)
            self.assertAlmostEqual(got["value"], round(want, 6), places=6, msg=name)

    @unittest.skipUnless(HAS_SK, "sklearn 不可用")
    def test_p5_weighted_kappa_matches_sklearn(self):
        for name, (a, b) in self.CASES.items():
            for w in ("linear", "quadratic"):
                got = weighted_kappa(pairs_from(a, b), w)
                want = float(_sk_kappa(a, b, labels=[0, 1, 2], weights=w))
                self.assertEqual(got["status"], "ok", f"{name}/{w}")
                self.assertAlmostEqual(got["value"], round(want, 6), places=6,
                                       msg=f"{name}/{w}")

    @unittest.skipUnless(HAS_SK, "sklearn 不可用")
    def test_p5_linear_and_quadratic_can_differ(self):
        a, b = self.CASES["mixed3"]
        lin = weighted_kappa(pairs_from(a, b), "linear")["value"]
        qua = weighted_kappa(pairs_from(a, b), "quadratic")["value"]
        self.assertNotAlmostEqual(lin, qua, places=6)
        self.assertAlmostEqual(lin, 0.129032, places=6)
        self.assertAlmostEqual(qua, 0.133333, places=6)

    def test_p5_perfect_weighted_kappa_is_one(self):
        p = pairs_from(*self.CASES["perfect"])
        self.assertEqual(weighted_kappa(p, "linear")["value"], 1.0)
        self.assertEqual(weighted_kappa(p, "quadratic")["value"], 1.0)

    def test_p5_reject_unknown_weight_type(self):
        with self.assertRaises(ValueError):
            weighted_kappa(pairs_from(*self.CASES["perfect"]), "cubic")


class P5TestNotComputable(unittest.TestCase):
    def test_p5_too_few_samples(self):
        p = pairs_from(["1", "0", "1"], ["1", "1", "1"])
        for fn in (cohens_kappa, lambda x: weighted_kappa(x, "linear")):
            r = fn(p)
            self.assertEqual(r["status"], NOT_COMPUTABLE)
            self.assertIn(f"judgeable_samples<{MIN_SAMPLES_FOR_KAPPA}", r["reason"])
            self.assertIsNone(r["value"])

    def test_p5_degenerate_distribution(self):
        p = pairs_from(["2"] * 10, ["2"] * 10)
        r = cohens_kappa(p)
        self.assertEqual(r["status"], NOT_COMPUTABLE)
        self.assertEqual(r["reason"], "degenerate_distribution")
        self.assertIsNone(r["value"])

    def test_p5_single_annotator(self):
        rows = [annotation_row("pair-000", "1", who=ANNOTATOR_A)]
        rep = agreement_report(rows, [], {})
        self.assertEqual(rep["status"], NOT_COMPUTABLE)
        self.assertEqual(rep["reason"], "single_annotator")
        self.assertNotIn("raw_agreement", rep, "不可计算时不得输出任何一致性数值")

    def test_p5_no_annotations(self):
        rep = agreement_report([], [], {})
        self.assertEqual(rep["status"], NOT_COMPUTABLE)
        self.assertEqual(rep["reason"], "no_annotations")

    def test_p5_no_overlapping_pairs(self):
        rows_a = [annotation_row("pair-000", "1", who=ANNOTATOR_A)]
        rows_b = [annotation_row("pair-999", "1", who=ANNOTATOR_B)]
        rep = agreement_report(rows_a, rows_b, {})
        self.assertEqual(rep["status"], NOT_COMPUTABLE)
        self.assertEqual(rep["reason"], "no_overlapping_pairs")


class P5TestAgreementReport(unittest.TestCase):
    def test_p5_full_report_shape_and_disagreements(self):
        a, b = paired(ANNOTATOR_A, ["2", "1", "0", "2", "1", "unjudgeable"],
                      ANNOTATOR_B, ["2", "0", "0", "1", "1", "unjudgeable"])
        meta = {f"pair-{i:03d}": {"job_category": ("FINANCE" if i < 3 else "HR")}
                for i in range(6)}
        rep = agreement_report(a, b, meta)
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["annotators"], sorted([ANNOTATOR_A, ANNOTATOR_B]))
        self.assertEqual(rep["n_paired"], 6)
        self.assertEqual(rep["n_judgeable"], 5)
        self.assertEqual(rep["n_disagreements"], 2)
        self.assertEqual(len(rep["disagreements"]), 2)
        self.assertIn("raw_agreement", rep)
        self.assertIn("weighted_kappa_quadratic", rep)
        self.assertEqual(rep["label_distribution_a"]["unjudgeable"], 1)

    def test_p5_per_category_insufficient_evidence(self):
        labels_a = ["2", "1", "0", "2", "1", "1", "0", "2", "2"]
        labels_b = ["2", "1", "1", "2", "1", "1", "0", "1", "2"]
        a, b = paired(ANNOTATOR_A, labels_a, ANNOTATOR_B, labels_b)
        meta = {f"pair-{i:03d}": {"job_category": ("FINANCE" if i < 6 else "HR")}
                for i in range(9)}
        rep = agreement_report(a, b, meta)
        self.assertEqual(rep["per_category"]["FINANCE"]["status"], "ok")
        self.assertIsNotNone(rep["per_category"]["FINANCE"]["cohens_kappa"])
        hr = rep["per_category"]["HR"]
        self.assertEqual(hr["status"], "insufficient_evidence")
        self.assertEqual(hr["n_paired"], 3)
        self.assertIsNone(hr["raw_agreement"])
        self.assertIsNone(hr["cohens_kappa"])
        self.assertIsNone(hr["weighted_kappa_linear"])

    def test_p5_unknown_category_bucket(self):
        a, b = paired(ANNOTATOR_A, ["2"] * 6, ANNOTATOR_B, ["2"] * 5 + ["1"])
        rep = agreement_report(a, b, {})
        self.assertIn("UNKNOWN", rep["per_category"])

    def test_p5_disagreement_detail_lists_both_sides(self):
        a, b = paired(ANNOTATOR_A, ["2", "1"], ANNOTATOR_B, ["1", "1"])
        det = disagreement_detail(paired_labels(a, b))
        self.assertEqual(len(det), 1)
        self.assertEqual(det[0]["pair_id"], "pair-000")
        self.assertEqual(det[0]["relevance_a"], "2")
        self.assertEqual(det[0]["relevance_b"], "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
