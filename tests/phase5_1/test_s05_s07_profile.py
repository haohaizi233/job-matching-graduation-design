# -*- coding: utf-8 -*-
"""S05~S07：技能归一化 / 字段证据溯源 / 必备与加分技能区分。"""
from __future__ import annotations

import unittest

from _util import RESUME_TEXT, make_jd

from job_matching.service import parse_resume_text, parse_job_text
from job_matching.service.contracts import CONFIDENCE_MEANING, FACT_SOURCES, SkillEntry
from job_matching.service.job_parser import JobEducationResolver
from job_matching.service.skills_normalize import (match_skill_sets,
                                                   normalize_skill_terms,
                                                   skills_from_segment,
                                                   split_skill_terms)


class S05SkillNormalization(unittest.TestCase):
    """场景 5：技能归一化（别名精确映射，禁止子串包含）。"""

    def test_alias_mapping(self):
        entries = normalize_skill_terms(["Java", "java", "JS", "C++", "C#", "Golang"],
                                        evidence_text="技能：Java、JS",
                                        evidence_source="stated_in_source",
                                        verification_status="self_reported")
        names = [e.canonical_name for e in entries]
        self.assertEqual(names, ["java", "javascript", "c++", "c#", "go"])

    def test_dangerous_pairs_stay_distinct(self):
        entries = normalize_skill_terms(["Java", "JavaScript", "C", "C++", "SQL", "MySQL"],
                                        evidence_text="x", verification_status="self_reported")
        names = [e.canonical_name for e in entries]
        self.assertEqual(len(set(names)), 6)
        self.assertIn("java", names)
        self.assertIn("javascript", names)
        self.assertIn("c", names)
        self.assertIn("c++", names)
        self.assertIn("sql", names)
        self.assertIn("mysql", names)

    def test_unmapped_kept_with_needs_review(self):
        entries = normalize_skill_terms(["量子计算调参"], evidence_text="技能：量子计算调参",
                                        verification_status="self_reported")
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertTrue(e.needs_review)
        self.assertEqual(e.raw_form, "量子计算调参")

    def test_confidence_meaning_declared(self):
        entries = normalize_skill_terms(["Java"], verification_status="self_reported")
        self.assertEqual(entries[0].confidence_meaning, CONFIDENCE_MEANING)
        self.assertIn("不是技能掌握概率", CONFIDENCE_MEANING)
        self.assertIsNotNone(entries[0].confidence)
        self.assertGreaterEqual(entries[0].confidence, 0.0)
        self.assertLessEqual(entries[0].confidence, 1.0)

    def test_segment_filters_non_skill_fragments(self):
        self.assertEqual(split_skill_terms("熟悉 Java、MySQL\n2. 本科及以上学历"),
                         ["Java", "MySQL"])
        skills = skills_from_segment("2. 本科及以上学历，计算机相关专业\n熟悉 Java、MySQL")
        names = [s.canonical_name for s in skills]
        self.assertIn("java", names)
        self.assertIn("mysql", names)
        self.assertNotIn("本科及以上学历", names)

    def test_verification_status_vocabulary(self):
        from job_matching.service.contracts import VERIFICATION_STATUSES
        entry = SkillEntry(skill_id="skill_x", canonical_name="java",
                           verification_status="self_reported")
        self.assertIn(entry.verification_status, VERIFICATION_STATUSES)
        with self.assertRaises(ValueError):
            from job_matching.service.contracts import check_verification_status
            check_verification_status("expert")


class S06EvidenceTrace(unittest.TestCase):
    """场景 6：简历字段证据溯源。"""

    def test_every_field_carries_evidence_and_source(self):
        profile = parse_resume_text(RESUME_TEXT, profile_id="stu_s06", is_synthetic=True)
        for name in ("education_level", "major", "graduation_year",
                     "employment_intention"):
            fld = getattr(profile, name)
            self.assertIn(fld.fact_source, FACT_SOURCES, name)
            if fld.status == "ok":
                self.assertTrue(fld.evidence_text, f"{name} 缺少原文证据")
                self.assertTrue(fld.extraction_method, f"{name} 缺少抽取手段")

    def test_evidence_substring_traced_to_source(self):
        profile = parse_resume_text(RESUME_TEXT, profile_id="stu_s06b", is_synthetic=True)
        self.assertIn("Java", profile.employment_intention.evidence_text)
        self.assertIn("2027", profile.graduation_year.evidence_text)
        skill_ev = {s.canonical_name: s.evidence_text for s in profile.skills}
        self.assertTrue(any("Java" in v for v in skill_ev.values()))
        self.assertEqual(profile.profile_version, "phase5-1-profile-v1")

    def test_structured_self_report_and_rule_split(self):
        profile = parse_resume_text("求职意向：数据分析实习生\n",
                                    profile_id="stu_s06c", is_synthetic=True)
        self.assertEqual(profile.employment_intention.fact_source, "stated_in_source")
        self.assertEqual(profile.education_level.status, "unknown",
                         "无证据字段不得凭空补齐")

    def test_experience_never_fabricates_achievements(self):
        profile = parse_resume_text(RESUME_TEXT, profile_id="stu_s06d", is_synthetic=True)
        self.assertEqual(len(profile.project_experiences), 2)
        for e in profile.project_experiences:
            self.assertEqual(e.fact_source, "stated_in_source")
            self.assertTrue(e.excerpt)
            for q in e.quantified_achievements:
                self.assertTrue(any(ch.isdigit() for ch in q))


class S07RequiredVsPreferredSkills(unittest.TestCase):
    """场景 7：岗位必要技能与加分技能区分。"""

    def setUp(self):
        self.resolver = JobEducationResolver(None)

    def test_required_and_preferred_split(self):
        jd = make_jd(required="熟悉 Java、MySQL、Spring Boot",
                     preferred="1. 熟悉 Redis、Docker 者优先",
                     edu="1. 本科及以上学历")
        job = parse_job_text(jd, job_id="job_s07", resolver=self.resolver, is_synthetic=True)
        req = {s.canonical_name for s in job.required_skills}
        pref = {s.canonical_name for s in job.preferred_skills}
        self.assertEqual(req & {"java", "mysql", "spring boot"}, {"java", "mysql", "spring boot"})
        self.assertIn("redis", pref)
        self.assertIn("docker", pref)
        self.assertFalse(req & pref, "加分技能不得混入必要技能")

    def test_preferred_marker_moves_requirement_to_preferred(self):
        jd = ("职位名称：测试工程师\n任职要求：\n"
              "1. 熟悉 Python\n2. 熟悉 Selenium 者优先\n岗位职责：\n1. 负责自动化测试\n")
        job = parse_job_text(jd, job_id="job_s07b", resolver=self.resolver, is_synthetic=True)
        req = {s.canonical_name for s in job.required_skills}
        self.assertIn("python", req)
        self.assertNotIn("selenium", req)

    def test_match_skill_sets_reports_evidence_missing_not_incompetence(self):
        student = parse_resume_text(RESUME_TEXT, profile_id="stu_s07", is_synthetic=True)
        job = parse_job_text(make_jd(required="熟悉 Java、MySQL、Spring Boot"),
                             job_id="job_s07c", resolver=self.resolver, is_synthetic=True)
        matched, missing = match_skill_sets(job.required_skills, student.skills)
        matched_names = {m["canonical_name"] for m in matched}
        self.assertLessEqual({"java", "mysql"}, matched_names)
        for m in missing:
            self.assertEqual(m["status"], "evidence_missing")
            self.assertIn("不代表候选人不具备", m["note"])


if __name__ == "__main__":
    unittest.main()
