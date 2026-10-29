# -*- coding: utf-8 -*-
"""P10 场景 15：个人信息（PII）检测、脱敏与导出检查（协议第十节）。

纪律：检测结果只含命中类型与数量，绝不回显原始号码；导出前必须过
scrub_record / check_export，违规显式报错而不是静默放行。
"""
from __future__ import annotations

import unittest

from job_matching.annotation.pii import (
    check_export, detect_pii, mask_matches, pii_field_violations, scrub_record,
)

CLEAN_TEXT = "求职意向：数据分析师。技能：python、sql、数据分析。项目经历：参与数据平台建设。"


class P10TestPiiDetection(unittest.TestCase):
    def test_p10_detect_counts_by_kind(self):
        text = "邮箱 hr@example.com，手机 13812345678，电话 021-12345678，" \
               "身份证 11010519491231002X"
        hits = detect_pii(text)
        self.assertEqual(hits["email"], 1)
        self.assertEqual(hits["mobile_cn"], 1)
        self.assertEqual(hits["landline"], 1)
        self.assertEqual(hits["id_card_cn"], 1)

    def test_p10_detect_output_contains_no_raw_pii(self):
        text = "手机 13812345678，邮箱 a.b+c@d-ef.com"
        out = str(detect_pii(text))
        self.assertNotIn("13812345678", out)
        self.assertNotIn("a.b+c@d-ef.com", out)

    def test_p10_clean_text_has_no_hits(self):
        self.assertEqual(detect_pii(CLEAN_TEXT), {})
        self.assertEqual(detect_pii(None), {})


class P10TestPiiMasking(unittest.TestCase):
    def test_p10_mask_matches_removes_raw_values(self):
        text = "联系方式：13812345678 / hr@example.com"
        masked = mask_matches(text)
        self.assertNotIn("13812345678", masked)
        self.assertNotIn("hr@example.com", masked)
        self.assertIn("***", masked)
        self.assertEqual(detect_pii(masked), {}, "脱敏后不得再命中")

    def test_p10_scrub_record_masks_text_fields(self):
        rec = {"pair_id": "p1", "resume_text": "手机 13900001111",
               "job_text": CLEAN_TEXT}
        out, hits = scrub_record(rec, ("resume_text", "job_text"))
        self.assertEqual(hits.get("mobile_cn"), 1)
        self.assertNotIn("13900001111", out["resume_text"])
        self.assertEqual(out["job_text"], CLEAN_TEXT)
        self.assertEqual(rec["resume_text"], "手机 13900001111", "原记录不得被就地修改")

    def test_p10_scrub_ignores_missing_fields(self):
        out, hits = scrub_record({"a": "x"}, ("nope",))
        self.assertEqual(out, {"a": "x"})
        self.assertEqual(hits, {})


class P10TestPiiExportCheck(unittest.TestCase):
    def test_p10_export_check_passes_after_scrub(self):
        rec, _ = scrub_record({"pair_id": "p1", "resume_text": "手机 13900001111"},
                              ("resume_text",))
        self.assertEqual(check_export(rec, ("resume_text",)), [])

    def test_p10_export_check_blocks_raw_pii(self):
        rec = {"pair_id": "p1", "resume_text": "邮箱 hr@example.com"}
        problems = check_export(rec, ("resume_text",))
        self.assertGreaterEqual(len(problems), 1)
        self.assertTrue(any("email" in p for p in problems))
        for p in problems:
            self.assertIn("个人信息", p)
            self.assertNotIn("hr@example.com", p, "违规描述不得回显原文")

    def test_p10_pii_structured_fields_flagged(self):
        self.assertEqual(pii_field_violations({"phone": "1"}),
                         ["phone"])
        self.assertIn("candidate_name", pii_field_violations({"candidate_name": "张三"}))
        self.assertIn("联系方式", pii_field_violations({"联系方式": "1"}))
        self.assertIn("id_card_no", pii_field_violations({"id_card_no": "1"}))

    def test_p10_non_pii_columns_not_flagged(self):
        for key in ("job_name", "company_name", "job_id", "resume_id", "pair_id"):
            self.assertEqual(pii_field_violations({key: "x"}), [], key)

    def test_p10_export_whitelist_enforced(self):
        rec = {"pair_id": "p1", "resume_text": CLEAN_TEXT, "internal_score": "0.9"}
        problems = check_export(rec, ("resume_text",),
                                allowed_columns=("pair_id", "resume_text"))
        self.assertTrue(any("不在导出白名单内" in p for p in problems))
        self.assertEqual(check_export(rec, ("resume_text",),
                                      allowed_columns=("pair_id", "resume_text",
                                                       "internal_score")), [])

    def test_p10_export_blocks_pii_column_even_in_whitelist(self):
        rec = {"pair_id": "p1", "phone": "1"}
        problems = check_export(rec, (), allowed_columns=("pair_id", "phone"))
        self.assertTrue(any("禁止导出" in p for p in problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
