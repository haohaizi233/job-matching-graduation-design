# -*- coding: utf-8 -*-
"""岗位资格要求规范化层（Phase5-1R F-005 / F-006）。

职责：把 JD 原文中的「毕业届别」「工作经验」表述解析为规范化约束对象
（`CohortRequirement` / `ExperienceRequirement`），供 `explanations` 做
真正的约束比较；**不**在解析层给出资格结论。

硬性口径：
  * 毕业届别支持：仅限某届 / 多届集合 / 届别区间 / 某届及以后 /
    应届 / 往届 / 不限届别 / 要求不明确；禁止用字符串相等覆盖所有情况；
  * 工作经验：先处理语义明确的特殊状态（经验不限/无经验要求/接受应届），
    再处理年限缺失；数值年限只从「经验语境子句」解析，"学历不限" 不得被
    误读为 "经验不限"；"实习经验优先/项目经验优先" 是偏好表述，不是年限要求；
  * 禁止把项目/实习经历条数等同于工作年限（经验侧证据不足一律转人工）。
"""
from __future__ import annotations

import re

from .contracts import CohortRequirement, ExperienceRequirement

# ------------------------------------------------------------------ 毕业届别
_COHORT_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_RANGE_RE = re.compile(
    r"(?<!\d)(20\d{2})\s*届?\s*(?:[-—~－—~至到]|--)\s*(?<!\d)(20\d{2})\s*届?")
_AND_AFTER_RE = re.compile(
    r"(?<!\d)(20\d{2})\s*届?\s*(?:及以后|及以上|以后|之后|起|以上)")
_UNRESTRICTED_RES = (
    re.compile(r"(?:毕业)?届别\s*不限"),
    re.compile(r"不限\s*(?:毕业)?\s*届别"),
    re.compile(r"应\s*往\s*届\s*(?:均|都)?(?:可|不限|欢迎)"),
    re.compile(r"届\s*别\s*不\s*限"),
)
_FRESH_RE = re.compile(r"应\s*届")
_PAST_RE = re.compile(r"往\s*届")
_COHORT_HINT_RE = re.compile(r"届|毕业|应届|往届")


def extract_cohort_clause(text: str, max_chars: int = 200) -> str:
    """抽取含毕业届别语义的子句（，,。；;、/换行 切分），供 CohortRequirement 解析。"""
    s = "" if text is None else str(text)
    parts = [c.strip() for c in re.split(r"[，,。；;、\n]", s)]
    hit = [c for c in parts if c and _COHORT_HINT_RE.search(c)]
    return "；".join(hit)[:max_chars]


def _year_ok(y: int) -> bool:
    return 2000 <= int(y) <= 2100


def parse_cohort_requirement(raw: str, *, source: str = "rule_parsed",
                             evidence_text: str = "") -> CohortRequirement:
    """原文表述 -> CohortRequirement（唯一实现，禁止在调用方各自解析）。"""
    s = ("" if raw is None else str(raw)).strip()
    base = {"raw": s[:200], "source": source,
            "evidence_text": evidence_text or s[:200]}
    if not s:
        return CohortRequirement(**base, rule="unclear", status="unclear",
                                 note="JD 未提供毕业届别要求（requirement_unclear）")

    # ---- 不限届别（必须先于年份规则，且不与具体年份混用）
    if not _COHORT_YEAR_RE.search(s):
        for rx in _UNRESTRICTED_RES:
            if rx.search(s):
                return CohortRequirement(**base, rule="unrestricted", status="ok",
                                         note="JD 明确不限毕业届别")
        if _FRESH_RE.search(s) and _PAST_RE.search(s):
            return CohortRequirement(**base, rule="unrestricted", status="ok",
                                     note="JD 同时接受应届/往届（应往届不限）")
        if _PAST_RE.search(s):
            return CohortRequirement(**base, rule="past_graduate", status="ok",
                                     note="JD 表述往届毕业生；毕业年份只能佐证，"
                                          "往届身份受招聘年度与政策影响，需人工确认")
        if _FRESH_RE.search(s):
            return CohortRequirement(**base, rule="fresh_graduate", status="ok",
                                     note="JD 表述应届毕业生但未说明具体年度；"
                                          "应届身份受招聘年度与政策影响，"
                                          "禁止只凭毕业年份推断校招资格，需人工确认")
        return CohortRequirement(**base, rule="unclear", status="unclear",
                                 note="JD 届别要求不明确或年份不合法，无法自动判断")

    # ---- 具体年份规则
    years_all = [int(y) for y in _COHORT_YEAR_RE.findall(s)]
    bad_years = [y for y in years_all if not _year_ok(y)]
    if bad_years:
        return CohortRequirement(**base, rule="unclear", status="unclear",
                                 note=f"届别年份不合法: {bad_years}，转人工复核")

    m = _RANGE_RE.search(s)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        lo, hi = min(y1, y2), max(y1, y2)
        return CohortRequirement(**base, rule="year_range", status="ok",
                                 year_min=lo, year_max=hi,
                                 note=f"届别区间 {lo}–{hi} 届")
    m = _AND_AFTER_RE.search(s)
    if m:
        return CohortRequirement(**base, rule="year_and_after", status="ok",
                                 year_min=int(m.group(1)),
                                 note=f"{m.group(1)} 届及以后")
    years = sorted(set(years_all))
    if len(years) >= 2:
        return CohortRequirement(**base, rule="year_set", status="ok", years=years,
                                 note=f"指定届别集合 {years}")
    return CohortRequirement(**base, rule="exact_year", status="ok", years=years,
                             note=f"仅限 {years[0]} 届" if years else "")


# ------------------------------------------------------------------ 工作经验
_EXP_HINT_RE = re.compile(r"经验|年限|工作经历|实习|应届|校招")
# 数值年限表达式本身也视为经验语境（如单独一句“3年以上”）
_EXP_NUMERIC_HINT_RE = re.compile(
    r"(?<![\d.])(\d{1,2})\s*[-~—至到]\s*(\d{1,2})\s*年"
    r"|(?:至少|不少于|不低于|大于|超过)\s*\d{1,2}\s*年"
    r"|(?<![\d.])\d{1,2}\s*年\s*(?:及\s*以上|以上|及以上)")
_EXP_YEARS_RES = (
    re.compile(r"(?<![\d.])(\d{1,2})\s*[-~—至到]\s*(\d{1,2})\s*年"),
    re.compile(r"(?:至少|不少于|不低于|大于|超过)\s*(\d{1,2})\s*年"),
    re.compile(r"(?<![\d.])(\d{1,2})\s*年\s*(?:及\s*以上|以上|及以上|以上工作经验)?"),
)
_EXP_NONE_RES = (
    re.compile(r"经验\s*不\s*限"),
    re.compile(r"无\s*(?:工作)?\s*经验\s*要求"),
    re.compile(r"无需\s*(?:工作)?\s*经验"),
    re.compile(r"无\s*(?:工作)?\s*经验"),
    re.compile(r"(?:可)?接受\s*应届"),
    re.compile(r"应\s*届\s*(?:毕业生?|生)?\s*(?:均可|可|欢迎)"),
)
_EXP_PREF_RE = re.compile(r"优先|加分|更佳|尤佳")


def parse_experience_requirement_detail(raw: str) -> ExperienceRequirement:
    """JD 经验表述 -> ExperienceRequirement（服务层口径，F-006）。

    与 `annotation/pool.parse_experience_requirement`（数据工程口径）刻意分离：
    服务层只从**经验语境子句**解析，避免 "学历不限" 被误读为 "经验不限"。
    """
    s = "" if raw is None else str(raw)
    clauses = [c.strip() for c in re.split(r"[，,。；;、\n]", s) if c.strip()]
    exp_clauses = [c for c in clauses
                   if _EXP_HINT_RE.search(c) or _EXP_NUMERIC_HINT_RE.search(c)]
    if not exp_clauses:
        return ExperienceRequirement(raw="", years_min=None, status="unknown",
                                     source="absent",
                                     note="JD 未提供经验要求，保留 unknown")
    joined = "；".join(exp_clauses)[:120]

    # 1) 数值年限（明确要求优先于偏好/缺失）
    for c in exp_clauses:
        for rx in _EXP_YEARS_RES:
            m = rx.search(c)
            if not m:
                continue
            years_min = float(m.group(1))
            pref = bool(_EXP_PREF_RE.search(c))
            return ExperienceRequirement(
                raw=m.group(0)[:60], years_min=years_min, status="ok",
                source="heuristic_pattern_v1",
                note=("年限为规则解析结果；同句含『优先』属偏好表述，"
                      "是否满足需人工确认" if pref else
                      "年限为规则解析结果；简历侧不采集工作年限，禁止以项目/"
                      "实习经历条数等同工作年限"))

    # 2) 明确的无经验要求（语义明确的特殊状态先于缺失值处理）
    for c in exp_clauses:
        for rx in _EXP_NONE_RES:
            m = rx.search(c)
            if m:
                return ExperienceRequirement(
                    raw=m.group(0)[:60], years_min=0.0, status="none_required",
                    source="heuristic_keyword_v1",
                    note="JD 明确经验不限/无经验要求/接受应届；仍需人工确认其它资格")

    # 3) 仅偏好表述（实习经验优先 / 项目经验优先）
    for c in exp_clauses:
        if _EXP_PREF_RE.search(c):
            return ExperienceRequirement(
                raw=c[:60], years_min=None, status="preference_only",
                source="heuristic_keyword_v1",
                note="JD 仅表述偏好（实习/项目经验优先），无硬性年限要求，"
                     "不构成资格判断依据，需人工确认")

    # 4) 兜底：有经验语境但无法解析
    return ExperienceRequirement(raw=joined, years_min=None, status="unknown",
                                 source="rule",
                                 note="存在经验相关表述但无法解析出明确要求，保留 unknown")
