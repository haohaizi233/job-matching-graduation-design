# -*- coding: utf-8 -*-
"""可解释匹配结果（模块 D）。

硬性约束：
  * 解释内容只能来自实际技能匹配、岗位规则与可追溯证据；
  * 技能四态：satisfied（已满足）/ not_satisfied（未满足）/
    insufficient_evidence（证据不足）/ requirement_unclear（要求不明确）；
    简历未命中技能一律记 evidence_missing -> insufficient_evidence，
    **绝不表述为"用户不会该技能"**；
  * 学历 / 经验 / 毕业届别结论一律带 needs_human_review=True，
    不做硬编码资格判定；
  * 不返回"录用成功概率"；score_type ∈ {heuristic_score, model_raw_score,
    calibrated_score}，calibrated_score 仅在校准验证完成后允许（本轮禁用）。
"""
from __future__ import annotations

import re

from ..pair_features import title_tokens
from ..preprocess_skills import jaccard
from .contracts import (CohortRequirement, ExperienceRequirement, Field, JobProfile,
                        StudentProfile)
from .requirements import extract_cohort_clause, parse_cohort_requirement
from .skills_normalize import match_skill_sets

SCORE_TYPES = ("heuristic_score", "model_raw_score", "calibrated_score")
CONSTRAINT_STATUSES = ("satisfied", "not_satisfied", "insufficient_evidence",
                       "requirement_unclear")

_DEGREE_RANK = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}


# ------------------------------------------------------------------ 技能证据
def skill_evidence(student: StudentProfile, job: JobProfile) -> dict:
    matched_req, missing_req = match_skill_sets(job.required_skills, student.skills)
    matched_pref, missing_pref = match_skill_sets(job.preferred_skills, student.skills)
    out = {
        "matched_skills": matched_req + matched_pref,
        "missing_required_skills": missing_req,
        "preferred_skills_missing": missing_pref,
    }
    if not job.required_skills and not job.preferred_skills:
        out["note"] = "JD 未声明技能要求，技能维度按 requirement_unclear 处理"
    return out


def skill_status_summary(skill_ev: dict, job: JobProfile) -> str:
    if not job.required_skills and not job.preferred_skills:
        return "requirement_unclear"
    if skill_ev["missing_required_skills"]:
        return "insufficient_evidence"
    return "satisfied"


# ------------------------------------------------------------------ 约束
def education_constraint(student: StudentProfile, job: JobProfile) -> dict:
    edu = job.education_requirement
    stu = student.education_level
    base = {
        "job_requirement": edu.to_dict(),
        "student_education": stu.to_dict(),
        "needs_human_review": True,
        "note": "学历适配仅为倾向提示，最终资格结论必须人工确认",
    }
    if not edu.tokens or edu.status in ("unknown", "rejected") or "学历不明" in edu.tokens:
        base["status"] = "requirement_unclear"
        base["note"] = "岗位学历要求不明确或解析失败，无法自动判断"
        return base
    if "学历不限" in edu.tokens:
        base["status"] = "satisfied"
        base["note"] = "岗位标注学历不限；仍需人工确认其它资格条件"
        return base
    if stu.status != "ok" or not stu.value:
        base["status"] = "insufficient_evidence"
        base["note"] = "简历未提供明确学历证据，无法自动判断"
        return base
    stu_rank = _DEGREE_RANK.get(str(stu.value))
    req_ranks = [_DEGREE_RANK[t] for t in edu.tokens if t in _DEGREE_RANK]
    if stu_rank is None or not req_ranks:
        base["status"] = "insufficient_evidence"
        return base
    base["status"] = "satisfied" if stu_rank >= min(req_ranks) else "not_satisfied"
    base["note"] = ("学历倾向满足岗位要求（自动推断，需人工确认）"
                    if base["status"] == "satisfied"
                    else "学历证据低于岗位要求（自动推断，需人工确认，不做资格否决）")
    return base


def experience_constraint(student: StudentProfile, job: JobProfile) -> dict:
    exp: ExperienceRequirement = job.experience_requirement
    base = {
        "job_requirement": exp.to_dict(),
        "student_experience_evidence": {
            "internship_count": len(student.internship_experiences),
            "project_count": len(student.project_experiences),
            "note": "本阶段不推断工作年限，仅登记原文证据条目数；"
                    "禁止把项目/实习经历条数等同于工作年限",
        },
        "needs_human_review": True,
        "note": "经验适配需人工确认，不做硬性资格结论",
    }
    # Phase5-1R F-006：先处理语义明确的特殊状态，再处理缺失值。
    # 历史缺陷：先判 years_min is None 提前返回 requirement_unclear，
    # 导致 none_required + years_min=None 的合法表示被误判。
    if exp.status == "none_required":
        base["status"] = "satisfied"
        base["note"] = "岗位标注经验不限/无经验要求/接受应届；仍需人工确认"
        return base
    if exp.status == "preference_only":
        base["status"] = "requirement_unclear"
        base["note"] = ("JD 仅表述偏好（如实习/项目经验优先），未给出硬性年限要求，"
                        "不构成资格判断依据，需人工确认")
        return base
    if exp.status == "ok" and exp.years_min is not None:
        base["status"] = "insufficient_evidence"
        base["note"] = ("简历侧工作年限未提供（禁止凭项目/实习条数推断年限），"
                        f"无法自动判断是否满足 {exp.raw or str(exp.years_min) + ' 年'}，"
                        "转人工确认")
        return base
    base["status"] = "requirement_unclear"
    base["note"] = "JD 经验要求缺失或无法解析，无法自动判断"
    return base


def _student_graduation_year(student: StudentProfile) -> int | None:
    """学生毕业年份 -> 合法整数年份；缺失/非法一律 None（绝不猜测）。"""
    fld = student.graduation_year
    if fld.status != "ok":
        return None
    m = re.search(r"(?<!\d)(20\d{2})(?!\d)", str(fld.value or ""))
    if not m:
        return None
    y = int(m.group(1))
    return y if 2000 <= y <= 2100 else None


def cohort_constraint(student: StudentProfile, job: JobProfile) -> dict:
    """毕业届别约束判定（Phase5-1R F-005）：真正比较届别，而非见值即 satisfied。"""
    req: CohortRequirement = job.cohort_requirement
    if req.rule == "unclear" and not req.raw:
        # 兼容旧契约（无 cohort_requirement）：从 graduation_cohort 字段回退解析
        fld = job.graduation_cohort
        req = parse_cohort_requirement(
            extract_cohort_clause(fld.evidence_text or fld.value or ""),
            source=str(fld.fact_source or "rule_parsed"),
            evidence_text=str(fld.evidence_text or ""))
    year = _student_graduation_year(student)
    status = req.match_year(year)

    notes = {
        "satisfied": "毕业届别倾向匹配（自动推断，需人工确认）",
        "not_satisfied": "毕业届别与岗位要求不一致（自动推断，需人工确认，不做资格否决）",
        "insufficient_evidence": (
            "学生毕业年份缺失或 JD 届别为应届/往届等政策性表述，"
            "证据不足，需人工复核（禁止只凭毕业年份推断校招身份）"),
        "requirement_unclear": "JD 毕业届别要求不明确或无法解析，需人工复核",
    }
    base = {
        "job_requirement": req.to_dict(),
        "student_graduation_year": student.graduation_year.to_dict(),
        "student_graduation_year_resolved": year,
        "needs_human_review": True,
        "status": status,
        "note": notes.get(status, ""),
    }
    return base


# ------------------------------------------------------------------ 组装
def build_match_result(student: StudentProfile, job: JobProfile, *,
                       rank: int, score: float, score_type: str,
                       scoring_method: str, model_version: str,
                       warnings: list[str] | None = None) -> dict:
    """单条推荐结果：排序值 + 可解释证据（全部可追溯到原文/规则）。"""
    if score_type not in SCORE_TYPES:
        raise ValueError(f"非法 score_type: {score_type}，合法值 {SCORE_TYPES}")
    skill_ev = skill_evidence(student, job)
    edu_c = education_constraint(student, job)
    exp_c = experience_constraint(student, job)
    coh_c = cohort_constraint(student, job)

    evidence = []
    for m in skill_ev["matched_skills"]:
        evidence.append({
            "type": "skill_matched",
            "skill": m["canonical_name"],
            "student_evidence_text": m["evidence_text"],
            "jd_evidence_text": m.get("jd_evidence_text", ""),
        })
    for m in skill_ev["missing_required_skills"]:
        evidence.append({
            "type": "skill_evidence_missing",
            "skill": m["canonical_name"],
            "jd_evidence_text": m.get("jd_evidence_text", ""),
            "note": m["note"],
        })
    if job.responsibilities.status == "ok":
        evidence.append({"type": "job_responsibilities",
                         "excerpt": str(job.responsibilities.value)[:200]})

    warns = list(warnings or [])
    if not job.required_skills:
        warns.append("job_required_skills_unspecified")
    if job.education_requirement.needs_human_review:
        warns.append("education_constraint_needs_human_review")
    if exp_c["status"] == "insufficient_evidence":
        warns.append("experience_evidence_insufficient")

    return {
        "job_id": job.job_id,
        "rank": rank,
        "score": round(float(score), 8),
        "score_type": score_type,
        "scoring_method": scoring_method,
        "model_version": model_version,
        "matched_skills": skill_ev["matched_skills"],
        "missing_required_skills": skill_ev["missing_required_skills"],
        "preferred_skills_missing": skill_ev["preferred_skills_missing"],
        "education_constraint": edu_c,
        "experience_constraint": exp_c,
        "graduation_cohort_constraint": coh_c,
        "skill_constraint_status": skill_status_summary(skill_ev, job),
        "evidence": evidence,
        "warnings": warns,
    }
