# -*- coding: utf-8 -*-
"""Phase7 样本规模规划的确定性与统计口径测试。"""
from __future__ import annotations

import json
import math
import unittest

from _util import ROOT

import sample_size_planning as ssp  # noqa: E402


class TestSampleSizePlanning(unittest.TestCase):
    def test_mde_decreases_with_groups(self):
        m_small = ssp.mde(9)
        m_mid = ssp.mde(21)
        m_large = ssp.mde(36)
        self.assertGreater(m_small, m_mid)
        self.assertGreater(m_mid, m_large)

    def test_mde_formula_consistency(self):
        n = 25
        expect = ssp.Z_SUM * ssp.ASSUMED_SD_DIFF / math.sqrt(n)
        self.assertAlmostEqual(expect, ssp.mde(n), places=12)

    def test_required_groups_inverse_of_mde(self):
        for target in (0.20, 0.15, 0.10, 0.05):
            n = ssp.required_groups(target)
            self.assertLessEqual(ssp.mde(n), target + 1e-9,
                                 f"n={n} 时 MDE 应 ≤ 目标 {target}")

    def test_mde_zero_groups_is_none(self):
        self.assertIsNone(ssp.mde(0))

    def test_split_groups_sums_to_total(self):
        for total in (1, 2, 3, 30, 70, 120, 137):
            g = ssp.split_groups(total)
            self.assertEqual(total, g["dev_validation_groups"] + g["blind_test_groups"])

    def test_split_is_group_level_not_pair_level(self):
        s = ssp.plan_scenario({"id": "T", "name": "t", "resume_count": 50,
                               "pairs_per_resume": 8, "note": ""})
        self.assertEqual(50, s["inputs"]["real_resumes"])
        self.assertEqual(50, s["query_group_split"]["dev_validation_groups"]
                         + s["query_group_split"]["blind_test_groups"])

    def test_scenario_a_blind_groups_below_stability_threshold(self):
        a = ssp.plan_scenario(ssp.SCENARIOS[0])
        self.assertLess(a["query_group_split"]["blind_test_groups"],
                        ssp.MIN_GROUPS_FOR_STABILITY)
        self.assertFalse(a["statistical_stability"]["blind_groups_stable"])

    def test_scenario_b_meets_stability_threshold(self):
        b = ssp.plan_scenario(ssp.SCENARIOS[1])
        self.assertGreaterEqual(b["query_group_split"]["blind_test_groups"],
                                ssp.MIN_GROUPS_FOR_STABILITY)
        self.assertGreaterEqual(b["inputs"]["total_pairs"], ssp.PAIRS_GATE_MIN)

    def test_scenario_c_has_smallest_mde(self):
        c = ssp.plan_scenario(ssp.SCENARIOS[2])
        a = ssp.plan_scenario(ssp.SCENARIOS[0])
        self.assertLess(c["statistical_stability"]["mde_blind_test"],
                        a["statistical_stability"]["mde_blind_test"])

    def test_unjudgeable_sensitivity_monotone(self):
        s = ssp.plan_scenario(ssp.SCENARIOS[1])
        eff = [u["effective_judgeable_pairs"] for u in s["unjudgeable_sensitivity"]]
        self.assertEqual(sorted(eff, reverse=True), eff)

    def test_all_planning_values_marked_as_assumptions(self):
        s = ssp.plan_scenario(ssp.SCENARIOS[0])
        self.assertEqual("ASSUMPTION", s["annotation_workload"]["status"])
        self.assertEqual("ASSUMPTION", s["post_dedup"]["status"])
        self.assertIn("ASSUMPTION",
                      s["statistical_stability"]["assumed_sd_diff_status"])

    def test_deterministic_output(self):
        p1 = [ssp.plan_scenario(s) for s in ssp.SCENARIOS]
        p2 = [ssp.plan_scenario(s) for s in ssp.SCENARIOS]
        self.assertEqual(json.dumps(p1, sort_keys=True), json.dumps(p2, sort_keys=True))

    def test_report_payload_is_planning_not_fact(self):
        """纪律：规划报告必须显式声明不是已采集/已标注事实。"""
        text = (ROOT / "reports" / "phase7" / "sample-size-planning.json").read_text(
            encoding="utf-8")
        payload = json.loads(text)
        self.assertEqual("PLANNING_ASSUMPTIONS_NOT_COLLECTED_FACTS", payload["status"])


if __name__ == "__main__":
    unittest.main()
