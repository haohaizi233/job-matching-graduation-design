# -*- coding: utf-8 -*-
"""R3：业务资格约束判定回归（Phase5-1R F-005 毕业届别 / F-006 经验判断顺序）。

业务不变量：
  * 毕业届别必须**真正比较**年份/规则，禁止「两个字段都存在即 satisfied」；
  * 应届/往届是政策性身份，禁止只凭毕业年份推断 -> insufficient_evidence；
  * 经验判断先处理语义明确状态（none_required / preference_only），再处理缺失值；
    历史缺陷：none_required + years_min=None 被提前判为 requirement_unclear；
  * 项目/实习经历条数**不得**等同工作年限；
  * "学历不限" 不得被误读为 "经验不限"；
  * 状态四分类严格：satisfied / not_satisfied / insufficient_evidence / requirement_unclear。
"""
from __future__ import annotations

import unittest

import _util as U  # noqa: F401  （确保 src 进 sys.path，与其余 phase5_1r 测试一致）

from job_matching.service.contracts import (CohortRequirement, ExperienceRequirement,
                                            Field, JobProfile, StudentProfile)
from job_matching.service.explanations import cohort_constraint, experience_constraint
from job_matching.service.requirements import (extract_cohort_clause,
                                               parse_cohort_requirement,
                                               parse_experience_requirement_detail)

STATUSES = {"satisfied", "not_satisfied", "insufficient_evidence", "requirement_unclear"}


def student_with_year(year: str | None, *, profile_id: str = "stu_r3") -> StudentProfile:
    fld = (Field(value=year, status="ok", fact_source="stated_in_source",
                 evidence_text=f"毕业年份：{year}") if year is not None
           else Field.unknown(note="简历未提供毕业年份"))
    return StudentProfile(profile_id=profile_id, graduation_year=fld)


def job_with_cohort(raw: str, *, job_id: str = "job_r3") -> JobProfile:
    return JobProfile(job_id=job_id, cohort_requirement=parse_cohort_requirement(raw))


def job_with_exp(raw: str, *, job_id: str = "job_r3e") -> JobProfile:
    return JobProfile(job_id=job_id,
                      experience_requirement=parse_experience_requirement_detail(raw))


def constraint_status(constraint_fn, student, job) -> str:
    res = constraint_fn(student, job)
    st = res["status"]
    assert st in STATUSES, f"非法状态 {st!r}"
    return st


class R3CohortParsing(unittest.TestCase):
    """F-005：中文届别表述 -> CohortRequirement 规则解析。"""

    def test_exact_year(self):
        for raw in ("仅限2027届", "2027届", "限2027届毕业生", "毕业年份：2027",
                    "2027年毕业", "招聘2027届"):
            req = parse_cohort_requirement(raw)
            self.assertEqual(req.rule, "exact_year", raw)
            self.assertEqual(req.years, [2027], raw)

    def test_year_set(self):
        req = parse_cohort_requirement("2026届及2027届")
        self.assertEqual(req.rule, "year_set")
        self.assertEqual(req.years, [2026, 2027])

    def test_year_range_variants(self):
        for raw in ("2026届—2028届", "2026—2028届", "2026-2028届", "2026至2028届"):
            req = parse_cohort_requirement(raw)
            self.assertEqual(req.rule, "year_range", raw)
            self.assertEqual((req.year_min, req.year_max), (2026, 2028), raw)

    def test_range_reversed_normalized(self):
        req = parse_cohort_requirement("2028届—2026届")
        self.assertEqual(req.rule, "year_range")
        self.assertEqual((req.year_min, req.year_max), (2026, 2028))

    def test_year_and_after(self):
        for raw in ("2027届及以后", "2027届及以上", "2027届起"):
            req = parse_cohort_requirement(raw)
            self.assertEqual(req.rule, "year_and_after", raw)
            self.assertEqual(req.year_min, 2027, raw)

    def test_unrestricted(self):
        for raw in ("毕业届别不限", "不限毕业届别", "届别不限", "应往届均可"):
            req = parse_cohort_requirement(raw)
            self.assertEqual(req.rule, "unrestricted", raw)

    def test_fresh_and_past_graduate(self):
        self.assertEqual(parse_cohort_requirement("应届毕业生").rule, "fresh_graduate")
        self.assertEqual(parse_cohort_requirement("往届毕业生").rule, "past_graduate")

    def test_unclear_cases(self):
        for raw in ("", "要求不明确", "仅限25届", "1999届", "优秀者优先"):
            req = parse_cohort_requirement(raw)
            self.assertEqual(req.rule, "unclear", raw)

    def test_extract_cohort_clause(self):
        clause = extract_cohort_clause("岗位职责：开发；任职要求：仅限2027届；五险一金")
        self.assertIn("2027届", clause)
        self.assertNotIn("五险一金", clause)


class R3CohortConstraint(unittest.TestCase):
    """F-005：毕业届别约束判定（修复「见值即 satisfied」）。"""

    def test_2027_matches_2027(self):
        st = constraint_status(cohort_constraint, student_with_year("2027"),
                               job_with_cohort("仅限2027届"))
        self.assertEqual(st, "satisfied")

    def test_2027_rejects_only_2026(self):
        """历史缺陷 F-005 复现：学生2027届 + 岗位仅限2026届，旧逻辑误判 satisfied。"""
        st = constraint_status(cohort_constraint, student_with_year("2027"),
                               job_with_cohort("仅限2026届"))
        self.assertEqual(st, "not_satisfied")

    def test_2027_in_range_2026_2028(self):
        st = constraint_status(cohort_constraint, student_with_year("2027"),
                               job_with_cohort("2026届—2028届"))
        self.assertEqual(st, "satisfied")

    def test_2027_out_of_range(self):
        st = constraint_status(cohort_constraint, student_with_year("2027"),
                               job_with_cohort("2024届—2026届"))
        self.assertEqual(st, "not_satisfied")

    def test_2027_and_after(self):
        self.assertEqual(constraint_status(cohort_constraint, student_with_year("2027"),
                                           job_with_cohort("2027届及以后")), "satisfied")
        self.assertEqual(constraint_status(cohort_constraint, student_with_year("2026"),
                                           job_with_cohort("2027届及以后")), "not_satisfied")

    def test_year_set_membership(self):
        self.assertEqual(constraint_status(cohort_constraint, student_with_year("2027"),
                                           job_with_cohort("2026届及2027届")), "satisfied")
        self.assertEqual(constraint_status(cohort_constraint, student_with_year("2028"),
                                           job_with_cohort("2026届及2027届")), "not_satisfied")

    def test_missing_student_year_insufficient(self):
        st = constraint_status(cohort_constraint, student_with_year(None),
                               job_with_cohort("仅限2027届"))
        self.assertEqual(st, "insufficient_evidence")

    def test_missing_jd_cohort_unclear(self):
        st = constraint_status(cohort_constraint, student_with_year("2027"),
                               job_with_cohort(""))
        self.assertEqual(st, "requirement_unclear")

    def test_fresh_graduate_policy_is_insufficient(self):
        """“应届”但未说明年度：禁止只凭毕业年份推断校招资格。"""
        st = constraint_status(cohort_constraint, student_with_year("2027"),
                               job_with_cohort("应届毕业生"))
        self.assertEqual(st, "insufficient_evidence")

    def test_unrestricted_always_satisfied(self):
        self.assertEqual(constraint_status(cohort_constraint, student_with_year("2027"),
                                           job_with_cohort("毕业届别不限")), "satisfied")
        self.assertEqual(constraint_status(cohort_constraint, student_with_year(None),
                                           job_with_cohort("毕业届别不限")), "satisfied")

    def test_invalid_year_treated_as_unclear(self):
        st = constraint_status(cohort_constraint, student_with_year("25届"),
                               job_with_cohort("仅限2027届"))
        self.assertEqual(st, "insufficient_evidence")   # 学生年份非法 -> 无法判定，绝不猜测
        st2 = constraint_status(cohort_constraint, student_with_year("2027"),
                                job_with_cohort("仅限1999届"))
        self.assertEqual(st2, "requirement_unclear")

    def test_chinese_variants(self):
        for raw in ("2027届", "2027年毕业", "仅限2027届毕业生", "招聘对象：2027届"):
            st = constraint_status(cohort_constraint, student_with_year("2027"),
                                   job_with_cohort(raw))
            self.assertEqual(st, "satisfied", raw)

    def test_legacy_field_fallback(self):
        """旧契约（只有 graduation_cohort 字段）也能得到正确比较，而不是见值即满足。"""
        job = JobProfile(job_id="job_legacy",
                         graduation_cohort=Field(value="2026", status="ok",
                                                 fact_source="stated_in_source",
                                                 evidence_text="仅限2026届"))
        self.assertEqual(constraint_status(cohort_constraint,
                                           student_with_year("2027"), job),
                         "not_satisfied")

    def test_no_auto_veto_but_status_accurate(self):
        res = cohort_constraint(student_with_year("2027"), job_with_cohort("仅限2026届"))
        self.assertTrue(res["needs_human_review"])   # 自动结论一律标注需人工确认
        self.assertEqual(res["student_graduation_year_resolved"], 2027)


class R3ExperienceParsing(unittest.TestCase):
    """F-006：JD 经验表述 -> ExperienceRequirement。"""

    def test_none_required(self):
        for raw in ("工作经验不限", "无经验要求", "无需工作经验", "接受应届毕业生",
                    "应届毕业生均可"):
            req = parse_experience_requirement_detail(raw)
            self.assertEqual(req.status, "none_required", raw)

    def test_years_min(self):
        cases = {"至少1年工作经验": 1.0, "至少3年工作经验": 3.0, "3年以上": 3.0,
                 "1-3年工作经验": 1.0, "2年及以上": 2.0}
        for raw, years in cases.items():
            req = parse_experience_requirement_detail(raw)
            self.assertEqual(req.status, "ok", raw)
            self.assertEqual(req.years_min, years, raw)

    def test_preference_only(self):
        for raw in ("实习经验优先", "项目经验优先", "有项目经验者加分"):
            req = parse_experience_requirement_detail(raw)
            self.assertEqual(req.status, "preference_only", raw)

    def test_missing_is_unknown(self):
        req = parse_experience_requirement_detail("岗位职责：负责后端开发")
        self.assertEqual(req.status, "unknown")
        self.assertIsNone(req.years_min)

    def test_education_unlimited_not_experience(self):
        """“学历不限”是学历口径，不得被误读为“经验不限”。"""
        req = parse_experience_requirement_detail("学历不限")
        self.assertNotEqual(req.status, "none_required")
        self.assertEqual(req.status, "unknown")

    def test_mixed_clauses_isolated(self):
        req = parse_experience_requirement_detail("学历不限，3年以上工作经验")
        self.assertEqual(req.status, "ok")
        self.assertEqual(req.years_min, 3.0)

    def test_project_count_never_years(self):
        """禁止以项目/实习条数充当年限：解析结果不得凭条目生成年限。"""
        req = parse_experience_requirement_detail("有3个项目经历")
        self.assertNotEqual(req.status, "ok")


class R3ExperienceConstraint(unittest.TestCase):
    """F-006：经验判断顺序（先语义明确状态，后缺失值）。"""

    def test_none_required_with_null_years_is_satisfied(self):
        """F-006 核心回归：none_required + years_min=None 不得提前返回 requirement_unclear。"""
        job = JobProfile(job_id="j1", experience_requirement=ExperienceRequirement(
            raw="经验不限", years_min=None, status="none_required"))
        res = experience_constraint(student_with_year("2027"), job)
        self.assertEqual(res["status"], "satisfied")

    def test_accept_fresh_graduate(self):
        res = experience_constraint(student_with_year("2027"),
                                    job_with_exp("接受应届毕业生"))
        self.assertEqual(res["status"], "satisfied")

    def test_years_required_insufficient_evidence(self):
        """简历侧不采集工作年限 -> 不能自动判满足，转人工（证据不足）。"""
        for raw in ("至少1年工作经验", "至少3年工作经验", "3年以上"):
            res = experience_constraint(student_with_year("2027"), job_with_exp(raw))
            self.assertEqual(res["status"], "insufficient_evidence", raw)
            self.assertNotIn("项目", res["note"].replace("项目/实习", ""))  # 不得用条目数给结论

    def test_preference_only_unclear(self):
        res = experience_constraint(student_with_year("2027"), job_with_exp("实习经验优先"))
        self.assertEqual(res["status"], "requirement_unclear")

    def test_missing_requirement_unclear(self):
        res = experience_constraint(student_with_year("2027"), job_with_exp("岗位职责：开发"))
        self.assertEqual(res["status"], "requirement_unclear")

    def test_unknown_status_with_years_is_unclear(self):
        """status=unknown 即使带 years_min 也不得直接判满足。"""
        job = JobProfile(job_id="j2", experience_requirement=ExperienceRequirement(
            raw="3年", years_min=3.0, status="unknown"))
        res = experience_constraint(student_with_year("2027"), job)
        self.assertEqual(res["status"], "requirement_unclear")

    def test_evidence_only_counts_entries(self):
        job = JobProfile(job_id="j3", experience_requirement=ExperienceRequirement(
            raw="", status="unknown"))
        res = experience_constraint(student_with_year("2027"), job)
        ev = res["student_experience_evidence"]
        self.assertEqual(ev["project_count"], 0)
        self.assertEqual(ev["internship_count"], 0)
        self.assertIn("禁止", ev["note"])


class R3StatusContract(unittest.TestCase):
    """结果契约一致性：四分类状态、人工复核标记。"""

    def test_all_paths_human_review(self):
        combos = [
            (student_with_year("2027"), job_with_cohort("仅限2027届")),
            (student_with_year("2027"), job_with_cohort("仅限2026届")),
            (student_with_year(None), job_with_cohort("仅限2027届")),
            (student_with_year("2027"), job_with_cohort("")),
        ]
        for stu, job in combos:
            for fn in (cohort_constraint, experience_constraint):
                res = fn(stu, job)
                self.assertIn(res["status"], STATUSES)
                self.assertTrue(res["needs_human_review"])

    def test_requirement_serialized(self):
        res = cohort_constraint(student_with_year("2027"), job_with_cohort("2026届—2028届"))
        self.assertEqual(res["job_requirement"]["rule"], "year_range")
        self.assertIn("raw", res["job_requirement"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
