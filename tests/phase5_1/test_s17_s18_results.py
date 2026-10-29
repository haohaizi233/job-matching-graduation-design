# -*- coding: utf-8 -*-
"""S17~S18：分数类型正确 / 匹配解释与实际证据一致。"""
from __future__ import annotations

import unittest

from _util import StubMatchPredictor, make_jd

from job_matching.service import (JobEducationResolver, MatchingService, ModelRegistration,
                                  ModelRegistry, parse_job_text, parse_resume_text,
                                  register_builtin_models)
from job_matching.service.explanations import CONSTRAINT_STATUSES, build_match_result

RESUME_PARTIAL = (
    "求职意向：Java开发工程师\n"
    "教育背景\n"
    "2027届 本科 计算机科学与技术\n"
    "专业技能\n"
    "Java、MySQL\n"
    "项目经历\n"
    "1. 学生选课系统：使用 Java 与 MySQL 开发\n"
)


def service_with_stub() -> MatchingService:
    reg = ModelRegistry(loader_impl=lambda r: StubMatchPredictor())
    reg.register(ModelRegistration(
        model_id="legacy_match_proxy_v1", model_version="stub-v1",
        task_type="match_ranking", training_data_version="stub",
        evaluation_status="research_only_proxy_labels", supported_languages=["en"],
        artifacts=[], checksum="stub", limitations=[], loader="legacy_match"))
    return MatchingService(reg)


class S17ScoreTypes(unittest.TestCase):
    """场景 17：score_type 明确且正确。"""

    def setUp(self):
        self.student = parse_resume_text(RESUME_PARTIAL, profile_id="stu_s17",
                                         is_synthetic=True)
        self.job = parse_job_text(make_jd(required="熟悉 Java、MySQL"),
                                  job_id="job_s17",
                                  resolver=JobEducationResolver(None), is_synthetic=True)

    def test_baseline_uses_heuristic_score(self):
        reg = ModelRegistry()
        register_builtin_models(reg)
        res = MatchingService(reg).rank(self.student, [self.job], {"mode": "baseline"})
        self.assertEqual(res["score_type"], "heuristic_score")
        for r in res["results"]:
            self.assertEqual(r["score_type"], "heuristic_score")

    def test_experimental_uses_model_raw_score(self):
        res = service_with_stub().rank(self.student, [self.job],
                                       {"mode": "experimental_model",
                                        "model_id": "legacy_match_proxy_v1"})
        self.assertEqual(res["score_type"], "model_raw_score")
        self.assertEqual(res["results"][0]["score_type"], "model_raw_score")

    def test_calibrated_score_forbidden_without_gold(self):
        with self.assertRaises(ValueError):
            build_match_result(self.student, self.job, rank=1, score=0.5,
                               score_type="probability_score", scoring_method="x",
                               model_version="v1")

    def test_no_hire_probability_fields(self):
        reg = ModelRegistry()
        register_builtin_models(reg)
        res = MatchingService(reg).rank(self.student, [self.job], {"mode": "baseline"})
        blob = str(res)
        for banned in ("hire_probability", "录用成功概率", "calibrated_score"):
            self.assertNotIn(banned, blob)


class S18ExplanationConsistency(unittest.TestCase):
    """场景 18：解释与实际证据一致（不臆断能力）。"""

    def setUp(self):
        self.student = parse_resume_text(RESUME_PARTIAL, profile_id="stu_s18",
                                         is_synthetic=True)
        self.job = parse_job_text(
            make_jd(required="熟悉 Java、MySQL、Spring Boot"),
            job_id="job_s18", resolver=JobEducationResolver(None), is_synthetic=True)
        reg = ModelRegistry()
        register_builtin_models(reg)
        self.result = MatchingService(reg).rank(
            self.student, [self.job], {"mode": "baseline"})["results"][0]

    def test_matched_skills_traceable_to_student_evidence(self):
        student_names = {s.canonical_name for s in self.student.skills}
        for m in self.result["matched_skills"]:
            self.assertIn(m["canonical_name"], student_names)
            self.assertTrue(m["evidence_text"], "匹配技能必须带简历证据")

    def test_missing_skill_is_evidence_missing_not_incompetence(self):
        missing = {m["canonical_name"]: m for m in self.result["missing_required_skills"]}
        self.assertIn("spring boot", missing)
        m = missing["spring boot"]
        self.assertEqual(m["status"], "evidence_missing")
        self.assertIn("不代表候选人不具备", m["note"])

    def test_explanation_counts_match_skill_sets(self):
        matched = {m["canonical_name"] for m in self.result["matched_skills"]}
        missing = {m["canonical_name"] for m in self.result["missing_required_skills"]}
        job_req = {s.canonical_name for s in self.job.required_skills}
        self.assertEqual(matched | missing, job_req)
        self.assertFalse(matched & missing)

    def test_constraints_never_assert_hard_qualification(self):
        for key in ("education_constraint", "experience_constraint",
                    "graduation_cohort_constraint"):
            c = self.result[key]
            self.assertIn(c["status"], CONSTRAINT_STATUSES)
            self.assertTrue(c["needs_human_review"], f"{key} 必须转人工确认")

    def test_skill_status_vocabulary(self):
        self.assertIn(self.result["skill_constraint_status"], CONSTRAINT_STATUSES)

    def test_evidence_section_is_traceable(self):
        for ev in self.result["evidence"]:
            self.assertIn(ev["type"], ("skill_matched", "skill_evidence_missing",
                                       "job_responsibilities"))


if __name__ == "__main__":
    unittest.main()
