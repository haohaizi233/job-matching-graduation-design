# -*- coding: utf-8 -*-
"""S08~S09：学历规则回退与异常拒识 / 缺字段与非法数据验证。"""
from __future__ import annotations

import unittest

from _util import StubEducationNormalizer, make_jd

from job_matching.service import JobEducationResolver, parse_job_text, parse_resume_text
from job_matching.service.contracts import EDU_CONFIDENCE_MEANING
from job_matching.service.errors import ServiceError
from job_matching.service.matching import RankOptions


class S08EducationFallbackAndRejection(unittest.TestCase):
    """场景 8：学历规则回退、模型记录、异常表达拒识。"""

    def test_rule_mode_parses_above_expression(self):
        resolver = JobEducationResolver(None)
        req = resolver.resolve("本科及以上学历")
        self.assertEqual(req.status, "rules_only")
        self.assertEqual(req.source, "rule")
        self.assertIsNone(req.model_version, "规则模式不得伪造模型版本")
        self.assertIsNone(req.confidence, "规则模式不得伪造模型置信度")
        self.assertEqual(set(req.tokens), {"本科", "硕士", "博士"})
        self.assertIn("rule_predict", req.rule)

    def test_rule_mode_declares_rules_only(self):
        resolver = JobEducationResolver(None)
        desc = resolver.describe()
        self.assertEqual(desc["mode"], "rules_only")
        self.assertIn("未生成任何模型输出", resolver.resolve("硕士学历").note)

    def test_anomalous_expression_rejected_for_human_review(self):
        resolver = JobEducationResolver(None)
        req = resolver.resolve("~~~***^^^###")
        self.assertEqual(req.status, "rejected")
        self.assertTrue(req.needs_human_review)
        self.assertEqual(req.tokens, [])

    def test_empty_input_yields_unknown_degree_token(self):
        req = JobEducationResolver(None).resolve("")
        self.assertEqual(req.tokens, ["学历不明"])
        self.assertEqual(req.rule, "empty_input")

    def test_model_record_mapping_and_rule_fallback(self):
        resolver = JobEducationResolver(None)
        resolver.normalizer = StubEducationNormalizer(labels=["本科"], fallback=False)
        req = resolver.resolve("本科学历")
        self.assertEqual(req.status, "model")
        self.assertEqual(req.source, "model")
        self.assertEqual(req.model_version, "stub-edu-v1")
        self.assertIs(req.expression_seen_in_train, True)
        self.assertEqual(req.confidence_meaning, EDU_CONFIDENCE_MEANING)

        resolver.normalizer = StubEducationNormalizer(labels=["硕士"], fallback=True)
        req2 = resolver.resolve("硕士学历")
        self.assertEqual(req2.status, "rules_only", "规则回退必须显式标注")
        self.assertEqual(req2.source, "rule")
        self.assertEqual(req2.rule, "stub_rule")

    def test_batch_supported(self):
        resolver = JobEducationResolver(None)
        resolver.normalizer = StubEducationNormalizer(labels=["大专"], fallback=False)
        reqs = resolver.resolve_batch(["大专学历", "博士学历", ""])
        self.assertEqual(reqs[0].tokens, ["大专"])
        self.assertEqual(reqs[2].rule, "empty_input")

    def test_missing_model_dir_degrades_to_rules_without_fake_output(self):
        resolver = JobEducationResolver("models/definitely/not/existing")
        self.assertEqual(resolver.mode, "rules_only")
        self.assertIsNotNone(resolver.load_error)
        req = resolver.resolve("本科学历")
        self.assertEqual(req.status, "rules_only")
        self.assertIsNone(req.model_version)

    def test_job_profile_education_flags_human_review(self):
        job = parse_job_text(make_jd(), job_id="job_s08",
                             resolver=JobEducationResolver(None), is_synthetic=True)
        self.assertTrue(job.education_requirement.needs_human_review or
                        job.education_requirement.tokens)
        self.assertEqual(job.education_requirement.confidence_meaning,
                         EDU_CONFIDENCE_MEANING)


class S09ValidationAndIllegalInput(unittest.TestCase):
    """场景 9：缺字段与非法数据验证。"""

    def test_rank_options_rejects_illegal_mode(self):
        with self.assertRaises(ServiceError) as ctx:
            RankOptions.from_dict({"mode": "magic"})
        self.assertEqual(ctx.exception.code, "INVALID_REQUEST")

    def test_student_profile_requires_profile_id(self):
        from job_matching.service import StudentProfile
        with self.assertRaises(ValueError):
            StudentProfile.from_dict({"education_level": {"value": "本科"}})

    def test_job_profile_requires_job_id(self):
        from job_matching.service import JobProfile
        with self.assertRaises(ValueError):
            JobProfile.from_dict({"job_title": {"value": "Java开发"}})

    def test_skill_entry_requires_identity(self):
        from job_matching.service.contracts import SkillEntry
        with self.assertRaises(ValueError):
            SkillEntry.from_dict({"canonical_name": ""})

    def test_empty_resume_text_yields_empty_status(self):
        profile = parse_resume_text("  ", profile_id="stu_s09", is_synthetic=True)
        self.assertEqual(profile.parse_status, "empty_text")

    def test_empty_job_text_yields_empty_status(self):
        job = parse_job_text(" ", job_id="job_s09", resolver=JobEducationResolver(None))
        self.assertEqual(job.parse_status, "empty_text")

    def test_unknown_field_kept_unknown_not_fabricated(self):
        job = parse_job_text(make_jd(edu=""), job_id="job_s09b",
                             resolver=JobEducationResolver(None), is_synthetic=True)
        self.assertEqual(job.employer.status, "unknown")
        self.assertIsNone(job.employer.value)
        self.assertEqual(job.experience_requirement.status, "unknown")


if __name__ == "__main__":
    unittest.main()
