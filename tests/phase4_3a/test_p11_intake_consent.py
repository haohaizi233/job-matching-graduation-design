# -*- coding: utf-8 -*-
"""P11 场景 1–3：授权门禁 / 中文简历判定 / 合成数据冒充真实数据防护（Phase4-3A-2 模块 A）。

纪律：未授权真实简历拒绝进入 Gold；英文简历不得充当中文简历；
合成简历（C_synthetic）只能用于工具测试，不得冒充真实人工数据、不计入真实 Gold 数量。
"""
from __future__ import annotations

import unittest

from job_matching.annotation.consent import ConsentError, consent_index, gold_eligibility
from job_matching.annotation.gold_gate import count_real_gold, is_real_gold_record
from job_matching.annotation.resume_intake import (
    ResumeIntakeError, assign_resume_id, intake_resumes,
)

ZH_TEXT = ("求职意向：数据分析师。教育背景：本科，2027 届。"
           "项目经历：参与数据平台建设，负责核心模块。技能：python、sql、数据分析。")
EN_TEXT = ("Objective: Data Analyst. Education: B.S. 2027. "
           "Project: built data platform core modules. Skills: python, sql.")


def consent_row(resume_id: str, *, status: str = "granted",
                source_class: str = "A_consented_individual",
                consent_id: str = "consent_0001", **extra) -> dict:
    row = {
        "consent_id": consent_id,
        "resume_id": resume_id,
        "source_class": source_class,
        "subject_pseudo_id": "subj_k7p2x9",
        "consent_status": status,
        "purpose": "毕业设计人工Gold评估集建设",
        "data_categories": "教育背景;求职意向;技能与经历",
        "storage_note": "本地 data/private/ 非公开目录",
        "access_scope": "研究者与标注员",
        "withdrawal_method": "邮件联系研究者，7日内删除",
        "granted_at": "2026-10-29",
        "license": "",
        "license_evidence": "",
    }
    row.update(extra)
    return row


def row_item(resume_id: str, text: str) -> dict:
    return {"row": {"resume_id": resume_id, "resume_text": text,
                    "target_position": "数据分析师", "skills": "python,sql"}}


class P11TestConsentGate(unittest.TestCase):
    """场景 1：未经授权的数据拒绝进入 Gold。"""

    def test_p11_missing_consent_rejected(self):
        with self.assertRaises(ResumeIntakeError):
            intake_resumes([row_item("resume_a", ZH_TEXT)],
                           source_class="A_consented_individual",
                           consent_records=[], require_consent=True)

    def test_p11_withdrawn_consent_rejected(self):
        # 撤回/拒绝的授权记录本身即非法：不得登记为可用授权
        with self.assertRaises(ConsentError) as ctx:
            consent_index([consent_row("resume_a", status="withdrawn")])
        self.assertEqual(ctx.exception.code, "consent_not_granted")

    def test_p11_denied_record_not_gold(self):
        rec = {"is_synthetic": False, "consent_status": "denied",
               "source_class": "A_consented_individual", "language": "zh"}
        ok, reason = gold_eligibility(rec)
        self.assertFalse(ok)
        self.assertEqual(reason, "consent_not_granted")
        self.assertFalse(is_real_gold_record(rec))

    def test_p11_granted_real_chinese_accepted(self):
        result = intake_resumes(
            [row_item("resume_a", ZH_TEXT)],
            source_class="A_consented_individual",
            consent_records=[consent_row("resume_a")], require_consent=True)
        self.assertEqual(len(result["accepted"]), 1)
        rec = result["accepted"][0]
        self.assertTrue(rec["eligible_for_gold"])
        self.assertEqual(rec["consent_status"], "granted")
        self.assertTrue(is_real_gold_record(rec))

    def test_p11_missing_withdrawal_method_rejected(self):
        row = consent_row("resume_a")
        row["withdrawal_method"] = ""
        with self.assertRaises(ConsentError) as ctx:
            consent_index([row])
        self.assertEqual(ctx.exception.code, "missing_withdrawal_method")


class P11TestChineseResumeGate(unittest.TestCase):
    """场景 2：英文简历不能充当中文简历。"""

    def test_p11_english_resume_quarantined(self):
        result = intake_resumes(
            [row_item("resume_en", EN_TEXT)],
            source_class="A_consented_individual",
            consent_records=[consent_row("resume_en")], require_consent=True)
        self.assertEqual(result["accepted"], [], "英文简历不得进入中文 Gold")
        reasons = [q["reason"] for q in result["quarantined"]]
        self.assertIn("non_chinese_resume", reasons)

    def test_p11_english_resume_not_real_gold(self):
        result = intake_resumes(
            [row_item("resume_en", EN_TEXT)],
            source_class="A_consented_individual",
            consent_records=[consent_row("resume_en")], require_consent=True)
        self.assertEqual(result["report"]["real_in_accepted"], 0)

    def test_p11_mixed_language_allowed(self):
        text = ZH_TEXT + " Skills: python, sql, tableau."
        result = intake_resumes(
            [row_item("resume_m", text)],
            source_class="A_consented_individual",
            consent_records=[consent_row("resume_m")], require_consent=True)
        self.assertEqual(len(result["accepted"]), 1)


class P11TestSyntheticIsolation(unittest.TestCase):
    """场景 3：合成简历不能冒充真实人工数据。"""

    def test_p11_synthetic_source_quarantined_never_gold(self):
        result = intake_resumes(
            [row_item("syn_resume_001", ZH_TEXT)],
            source_class="C_synthetic", consent_records=[], require_consent=True)
        self.assertEqual(result["accepted"], [])
        reasons = [q["reason"] for q in result["quarantined"]]
        self.assertIn("synthetic_not_gold", reasons)
        self.assertEqual(result["report"]["synthetic_in_accepted"], 0)
        self.assertEqual(result["report"]["real_in_accepted"], 0)

    def test_p11_synthetic_claiming_real_source_rejected(self):
        # 合成来源冒充真实来源（授权记录声称 A 类）：来源类别不一致直接报错
        with self.assertRaises(ResumeIntakeError):
            intake_resumes(
                [row_item("syn_resume_001", ZH_TEXT)],
                source_class="C_synthetic",
                consent_records=[consent_row("syn_resume_001",
                                             source_class="A_consented_individual")],
                require_consent=True)

    def test_p11_synthetic_consent_status_must_be_not_applicable(self):
        with self.assertRaises(ConsentError):
            consent_index([consent_row("syn_resume_001", status="granted",
                                       source_class="C_synthetic")])

    def test_p11_synthetic_never_counted_in_real_gold(self):
        records = [
            {"is_synthetic": True, "consent_status": "granted", "language": "zh",
             "eligible_for_gold": True},
            {"is_synthetic": False, "consent_status": "granted", "language": "zh",
             "eligible_for_gold": True},
        ]
        counts = count_real_gold(records)
        self.assertEqual(counts["real_gold"], 1)
        self.assertEqual(counts["synthetic_excluded"], 1)


class P11TestStableResumeId(unittest.TestCase):
    def test_p11_resume_id_deterministic_and_unnamed(self):
        h = "abc123"
        a = assign_resume_id(h, seed=20261212)
        b = assign_resume_id(h, seed=20261212)
        c = assign_resume_id(h, seed=1)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("resume_"))
        self.assertNotIn("张", a)


if __name__ == "__main__":
    unittest.main()
