# -*- coding: utf-8 -*-
"""P15 场景 13：PII 字段不得进入公开导出（Phase4-3A-2 模块 A/D）。

纪律：导出白名单 + PII 字段名拦截 + 文本残留检测三重门禁；
脱敏是掩码删除，白名单不得覆盖 PII 字段拦截；标注视图同样禁止 PII 字段。
"""
from __future__ import annotations

import unittest

from job_matching.annotation import blind_guard
from job_matching.annotation.pii import (
    check_export, detect_pii, mask_matches, pii_field_violations, scrub_record,
)

CLEAN_TEXT = "求职意向：数据分析师。技能：python、sql、数据分析。"
PII_TEXT = "联系人张三，手机 13812345678，邮箱 zhangsan@example.com。"
ALLOWED = ("pair_id", "resume_text", "job_text", "job_title")


class P15TestExportGate(unittest.TestCase):
    """场景 13：PII 字段不得进入公开导出。"""

    def test_p15_pii_column_blocked_even_in_whitelist(self):
        rec = {"pair_id": "pair-0001", "resume_text": CLEAN_TEXT,
               "phone": "13812345678"}
        problems = check_export(rec, ["resume_text"],
                                allowed_columns=["pair_id", "resume_text", "phone"])
        self.assertTrue(any("个人信息字段" in p for p in problems),
                        "PII 字段名拦截不得被白名单覆盖")

    def test_p15_raw_pii_in_text_blocks_export(self):
        rec = {"pair_id": "pair-0001", "resume_text": PII_TEXT}
        problems = check_export(rec, ["resume_text"], allowed_columns=ALLOWED)
        self.assertTrue(any("残留个人信息" in p for p in problems))

    def test_p15_scrubbed_record_passes_export(self):
        rec, hits = scrub_record({"pair_id": "pair-0001", "resume_text": PII_TEXT},
                                 ["resume_text"])
        self.assertTrue(hits, "PII 命中必须被统计（只记数量不记原文）")
        problems = check_export(rec, ["resume_text"], allowed_columns=ALLOWED)
        self.assertEqual(problems, [])
        self.assertNotIn("13812345678", rec["resume_text"])

    def test_p15_whitelist_enforced_for_extra_columns(self):
        rec = {"pair_id": "pair-0001", "resume_text": CLEAN_TEXT,
               "internal_score": 0.9}
        problems = check_export(rec, ["resume_text"], allowed_columns=ALLOWED)
        self.assertTrue(any("不在导出白名单内" in p for p in problems))

    def test_p15_pii_structured_fields_detected(self):
        rec = {"pair_id": "p", "name": "张三", "id_card_no": "110101199901011234",
               "address": "某市某区某街道 1 号"}
        bad = pii_field_violations(rec)
        self.assertIn("name", bad)
        self.assertIn("id_card_no", bad)
        self.assertIn("address", bad)
        self.assertNotIn("pair_id", bad)

    def test_p15_annotation_view_rejects_pii_fields(self):
        problems = blind_guard.check_annotation_view(
            {"pair_id": "pair-0001", "resume_text": CLEAN_TEXT, "mobile": "13812345678"})
        self.assertTrue(any("个人信息字段" in p for p in problems))

    def test_p15_detection_reports_counts_not_raw_values(self):
        hits = detect_pii(PII_TEXT)
        self.assertGreater(hits.get("mobile_cn", 0), 0)
        self.assertGreater(hits.get("email", 0), 0)
        # 只报类型与数量，不落原文
        self.assertEqual(set(hits.values()) - set(map(int, hits.values())), set())
        masked = mask_matches(PII_TEXT)
        self.assertNotIn("13812345678", masked)
        self.assertNotIn("zhangsan@example.com", masked)


if __name__ == "__main__":
    unittest.main()
