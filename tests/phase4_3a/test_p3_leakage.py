# -*- coding: utf-8 -*-
"""P3 场景 4：训练数据与评估数据交叉 / 泄漏检查（任务书 5.3）。"""
from __future__ import annotations

import unittest
from pathlib import Path

from _util import ROOT, make_job, make_pair

import leakage_check as lc  # scripts/phase4_3a/leakage_check.py

from job_matching.annotation import dedup as d

GOLD_HOLDOUT = ROOT / "data" / "splits" / "education" / "gold_holdout.csv"


def long_cjk(n: int = 200, shift: int = 0) -> str:
    return "".join(chr(0x4E00 + ((i * 719 + shift) % 900)) for i in range(n))


def variant_one_char(base: str, pos: int = 100) -> str:
    repl = chr(0x4E00 + 850) if base[pos] != chr(0x4E00 + 850) else chr(0x4E00 + 851)
    return base[:pos] + repl + base[pos + 1:]


class P3TestPoolInternalDuplicates(unittest.TestCase):
    def test_p3_exact_duplicate_pairs_detected(self):
        pairs = [
            make_pair(0, pid="pair-0000", resume_text="简历甲", job_text="岗位甲"),
            make_pair(1, pid="pair-0001", resume_text="简历甲", job_text="岗位甲"),
        ]
        res = lc.check_pool_internal([], pairs)
        self.assertEqual(res["pair_level"]["exact_duplicates"], 1)
        self.assertEqual(res["pair_level"]["pairs_checked"], 2)
        self.assertEqual(res["pair_level"]["exact_duplicate_pairs"],
                         [["pair-0000", "pair-0001"]])

    def test_p3_near_duplicate_pairs_detected(self):
        base = long_cjk(200)
        pairs = [
            make_pair(0, pid="pair-0000", resume_text="简历甲", job_text=base),
            make_pair(1, pid="pair-0001", resume_text="简历乙", job_text=variant_one_char(base)),
        ]
        res = lc.check_pool_internal([], pairs)
        self.assertEqual(res["pair_level"]["exact_duplicates"], 0)
        self.assertGreaterEqual(res["pair_level"]["near_duplicates"], 1)
        self.assertEqual(res["pair_level"]["near_threshold"], 0.90)

    def test_p3_same_resume_different_id(self):
        pairs = [
            make_pair(0, pid="pair-0000", rid="resume_A", resume_text="同一份简历文本"),
            make_pair(1, pid="pair-0001", rid="resume_B", resume_text="同一份简历文本"),
        ]
        res = lc.check_pool_internal([], pairs)
        self.assertEqual(res["resume_level"]["same_resume_different_id"], 1)
        self.assertEqual(res["resume_level"]["detail"], [["resume_A", "resume_B"]])

    def test_p3_same_job_different_id(self):
        jobs = [
            make_job(0, jid="job_A", text="完全相同的岗位描述文本"),
            make_job(1, jid="job_B", text="完全相同的岗位描述文本"),
        ]
        res = lc.check_pool_internal(jobs, [])
        self.assertEqual(res["job_level"]["same_job_different_id"], 1)
        self.assertEqual(res["job_level"]["detail"], [["job_A", "job_B"]])

    def test_p3_no_duplicates_reports_zero(self):
        pairs = [
            make_pair(0, pid="pair-0000", rid="resume_A", resume_text="简历甲", job_text="岗位甲"),
            make_pair(1, pid="pair-0001", rid="resume_B", resume_text="简历乙", job_text="岗位乙"),
        ]
        res = lc.check_pool_internal([], pairs)
        self.assertEqual(res["pair_level"]["exact_duplicates"], 0)
        self.assertEqual(res["pair_level"]["near_duplicates"], 0)
        self.assertEqual(res["resume_level"]["same_resume_different_id"], 0)


class P3TestTrainingEvalOverlap(unittest.TestCase):
    """评估池 vs 训练语料的文本交叉（哈希级 + 近似级）。"""

    def test_p3_hash_overlap_detected_between_train_and_pool(self):
        base = long_cjk(120)
        pool_desc = {"pool_1": base, "pool_2": "另一段完全不同的岗位描述"}
        train_desc = [("train_1", base), ("train_2", "第三段无关文本")]
        pool_hashes = {d.norm_hash(v) for v in pool_desc.values()}
        overlap = sum(1 for _k, v in train_desc if d.norm_hash(v) in pool_hashes)
        self.assertEqual(overlap, 1)

    def test_p3_near_overlap_detected_between_train_and_pool(self):
        base = long_cjk(200)
        pool_desc = {"pool_1": base}
        train_desc = [("train_1", variant_one_char(base))]
        found = d.cross_near_duplicate_pairs(pool_desc, train_desc, threshold=0.90)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["a"], "pool_1")

    def test_p3_disjoint_train_and_pool_has_no_overlap(self):
        pool_desc = {"pool_1": long_cjk(200, shift=0)}
        train_desc = [("train_1", long_cjk(200, shift=500))]
        pool_hashes = {d.norm_hash(v) for v in pool_desc.values()}
        self.assertEqual(sum(1 for _k, v in train_desc if d.norm_hash(v) in pool_hashes), 0)
        self.assertEqual(d.cross_near_duplicate_pairs(pool_desc, train_desc, threshold=0.90), [])


class P3TestProvenanceAndHistoricalGold(unittest.TestCase):
    def test_p3_historical_gold_cross_report_shape(self):
        jobs = [make_job(0, jid="job_A"), make_job(1, jid="job_B")]
        res = lc.check_historical_gold(jobs)
        self.assertIn("status", res)
        if res["status"] == "checked":
            self.assertGreaterEqual(res["gold_records"], 1)
            self.assertIsInstance(res["overlap_job_ids"], int)
            self.assertGreaterEqual(res["overlap_job_ids"], 0)
            self.assertIn("历史 Gold", res["policy"])
        else:
            self.assertEqual(res["status"], "not_available")

    def test_p3_historical_gold_file_if_present_is_not_silent(self):
        """历史 Gold 必须存在或显式登记为缺失，不允许"检查通过"的假象。"""
        if GOLD_HOLDOUT.exists():
            jobs = [make_job(0, jid="___no_such_job___")]
            res = lc.check_historical_gold(jobs)
            self.assertEqual(res["status"], "checked")
            self.assertEqual(res["overlap_job_ids"], 0)
        else:
            self.skipTest("gold_holdout.csv 不在本地，按 not_available 登记")

    def test_p3_unknown_license_is_flagged(self):
        jobs = [
            make_job(0, jid="job_A", source="job-education/annotated"),
            make_job(1, jid="job_B", source="other/all_df"),
        ]
        res = lc.check_license_and_provenance(jobs)
        self.assertEqual(res["pool_jobs_by_source"],
                         {"job-education/annotated": 1, "other/all_df": 1})
        self.assertEqual(res["jobs_with_unknown_license"], 1)
        self.assertIn("UNKNOWN", res["all_df_license"])
        self.assertIn("unverified", res["job_resume_matching_license"])

    def test_p3_english_resume_source_marked_unusable_for_chinese_eval(self):
        res = lc.check_license_and_provenance([])
        for _k, v in res["resume_sources"].items():
            self.assertFalse(v["usable_for_chinese_eval"],
                             "英文简历禁止充当中国大学生就业画像数据")

    def test_p3_pretraining_contamination_statement_is_honest(self):
        """泄漏报告只能声明『未发现已知泄漏』，不得宣称绝对无泄漏。"""
        src = Path(lc.__file__).read_text(encoding="utf-8")
        self.assertIn("无法完全排除", src)
        self.assertIn("不能声称绝对无泄漏", src)
        self.assertIn("not_checkable", src)
        self.assertNotIn("已证明无泄漏", src)
        self.assertNotIn("不存在任何泄漏", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
