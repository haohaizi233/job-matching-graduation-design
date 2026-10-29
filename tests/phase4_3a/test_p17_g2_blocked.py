# -*- coding: utf-8 -*-
"""P17 场景 16–17：无真实数据时 G2 必须 BLOCKED / 合成数据不计入真实 Gold（模块 E）。

纪律：缺少真实简历、真实配对、双人标注、授权或冻结复验时 G2 一律 BLOCKED；
合成样本（is_synthetic）永不计入真实 Gold 数量与规模门槛。
"""
from __future__ import annotations

import unittest

from job_matching.annotation.gold_gate import (
    H2_MIN_REAL_PAIRS, count_real_gold, evaluate_g2_status, is_real_gold_record,
)


def _record(**kw) -> dict:
    base = {"is_synthetic": False, "consent_status": "granted",
            "source_class": "A_consented_individual", "language": "zh",
            "eligible_for_gold": True, "quarantine_reason": ""}
    base.update(kw)
    return base


def _ready_facts(**kw) -> dict:
    base = {
        "real_resumes": 40, "real_pairs": 360, "synthetic_pairs": 75,
        "dual_annotation_complete": True, "open_disagreements": 0,
        "unjudgeable_forced": 0, "consent_complete": True,
        "leakage_blocking_findings": [], "split_isolation_ok": True,
        "freeze_verified": True,
    }
    base.update(kw)
    return base


class P17TestG2Blocked(unittest.TestCase):
    """场景 16：无真实简历或真实标注时 G2 必须返回 BLOCKED。"""

    def test_p17_no_real_data_blocked(self):
        g2 = evaluate_g2_status({
            "real_resumes": 0, "real_pairs": 0, "synthetic_pairs": 75,
            "dual_annotation_complete": False, "consent_complete": False,
            "split_isolation_ok": False, "freeze_verified": False})
        self.assertEqual(g2["status"], "blocked")
        joined = "；".join(g2["reasons"])
        self.assertIn("真实中文简历 0 份", joined)
        self.assertIn("真实有效配对 0 组", joined)

    def test_p17_no_real_annotation_blocked(self):
        g2 = evaluate_g2_status(_ready_facts(dual_annotation_complete=False))
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any("双人独立标注未完成" in r for r in g2["reasons"]))

    def test_p17_open_disagreements_block(self):
        g2 = evaluate_g2_status(_ready_facts(open_disagreements=3))
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any("分歧未仲裁" in r for r in g2["reasons"]))

    def test_p17_unverified_freeze_blocks(self):
        g2 = evaluate_g2_status(_ready_facts(freeze_verified=False))
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any("未冻结" in r or "复验" in r for r in g2["reasons"]))

    def test_p17_leakage_findings_block(self):
        g2 = evaluate_g2_status(_ready_facts(leakage_blocking_findings=["导出 PII 残留"]))
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any("泄漏" in r for r in g2["reasons"]))

    def test_p17_real_scale_below_target_blocks(self):
        g2 = evaluate_g2_status(_ready_facts(real_pairs=120))
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any(str(H2_MIN_REAL_PAIRS) in r for r in g2["reasons"]))

    def test_p17_ready_only_when_all_conditions_met(self):
        g2 = evaluate_g2_status(_ready_facts())
        self.assertEqual(g2["status"], "ready")
        self.assertEqual(g2["reasons"], [])


class P17TestSyntheticNeverRealGold(unittest.TestCase):
    """场景 17：合成数据不得计入真实 Gold 数量。"""

    def test_p17_synthetic_record_not_real_gold(self):
        self.assertFalse(is_real_gold_record(_record(is_synthetic=True)))

    def test_p17_synthetic_do_not_inflate_counts(self):
        records = [_record(is_synthetic=True) for _ in range(20)] + \
                  [_record() for _ in range(5)]
        counts = count_real_gold(records)
        self.assertEqual(counts["real_gold"], 5)
        self.assertEqual(counts["synthetic_excluded"], 20)
        self.assertEqual(counts["total_records"], 25)

    def test_p17_synthetic_pairs_do_not_satisfy_scale(self):
        # 合成配对数量再大也不能替代真实配对规模
        g2 = evaluate_g2_status(_ready_facts(real_pairs=0, synthetic_pairs=500))
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any("真实有效配对 0 组" in r for r in g2["reasons"]))
        self.assertEqual(g2["facts"]["synthetic_pairs"], 500)
        self.assertEqual(g2["facts"]["real_pairs"], 0)

    def test_p17_unconsented_or_non_chinese_not_real_gold(self):
        records = [
            _record(consent_status="denied"),
            _record(consent_status="withdrawn"),
            _record(language="en"),
            _record(eligible_for_gold=False),
            _record(quarantine_reason="near_duplicate_pair"),
        ]
        counts = count_real_gold(records)
        self.assertEqual(counts["real_gold"], 0)
        self.assertEqual(counts["non_gold_excluded"], 5)


if __name__ == "__main__":
    unittest.main()
