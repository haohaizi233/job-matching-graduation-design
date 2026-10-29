# -*- coding: utf-8 -*-
"""中文简历解析 -> StudentProfile（模块 A）。

能力：
  * 中文 TXT / PDF / DOCX 文本解析（text_extract）；
  * 基础字段识别：学历、专业、毕业年份、求职意向、期望城市、就业形式；
  * 技能词典归一化（skills_normalize，保留原文证据）；
  * 项目 / 实习 / 证书经历：只保留原文摘录与原文出现的量化表述，
    绝不凭空补充项目成果、工作年限、技能熟练度；
  * 每个字段带 fact_source / evidence_text / extraction_method，支持人工修正。

纪律：
  * 扫描版 PDF 返回 parse_status="ocr_required"，所有字段保持 unknown；
  * 非显式键值的抽取一律 fact_source="rule_parsed"，显式键值为 "stated_in_source"；
  * 自动流水线不产生 assessment_supported / manually_verified 状态。
"""
from __future__ import annotations

import re
from pathlib import Path

from ..annotation.pii import detect_pii, mask_matches
from ..core import norm_text, sha256_text
from .contracts import (ExperienceEntry, Field, StudentProfile)
from .skills_normalize import (normalize_skill_terms, skills_from_segment,
                               scan_skills_in_text)
from .text_extract import extract_document

PROFILE_VERSION = "phase5-1-profile-v1"

_DEGREE_TOKENS = ("博士", "硕士", "研究生", "本科", "学士", "大专", "专科", "高职", "高中")
_DEGREE_RANK = {"博士": 4, "硕士": 3, "本科": 2, "大专": 1}
_DEGREE_CANON = {"博士": "博士", "硕士": "硕士", "研究生": "硕士", "本科": "本科",
                 "学士": "本科", "大专": "大专", "专科": "大专", "高职": "大专",
                 "高中": "高中"}

_KV_RE = re.compile(
    r"^\s*(求职意向|意向岗位|目标岗位|应聘岗位|应聘职位|目标职位|求职岗位|"
    r"最高学历|学历|教育程度|专业|所学专业|毕业年份|毕业时间|预计毕业|"
    r"期望城市|意向城市|工作地点|期望工作地|城市|工作性质|求职状态|"
    r"姓名|联系方式|电话|手机|邮箱|身份证|住址|地址)\s*[:：]\s*(.+)$")

_INTENTION_KEYS = ("求职意向", "意向岗位", "目标岗位", "应聘岗位", "应聘职位", "目标职位", "求职岗位")
_EDU_KEYS = ("最高学历", "学历", "教育程度")
_MAJOR_KEYS = ("专业", "所学专业")
_YEAR_KEYS = ("毕业年份", "毕业时间", "预计毕业")
_CITY_KEYS = ("期望城市", "意向城市", "工作地点", "期望工作地", "城市")
_EMPLOYMENT_KEYS = ("工作性质", "求职状态")

_SECTION_HEADERS = (
    "教育背景", "教育经历", "项目经历", "项目经验", "实习经历", "实习经验",
    "工作经历", "工作经验", "专业技能", "技能特长", "技能", "证书", "资格证书",
    "获奖情况", "自我评价", "个人总结",
)
_SECTION_RE = re.compile(
    r"^\s*(教育背景|教育经历|项目经历|项目经验|实习经历|实习经验|工作经历|工作经验|"
    r"专业技能|技能特长|技能|证书|资格证书|获奖情况|自我评价|个人总结)\s*[:：]?\s*$")

_YEAR_RE = re.compile(r"(20\d{2})\s*年?\s*(?:毕业|应届|届)?")
_COHORT_RE = re.compile(r"(20\d{2})\s*届")
_MAJOR_RE = re.compile(r"([\u4e00-\u9fffA-Za-z0-9（）()]{2,16}?)(?:专业|系)\b|专业\s*[:：]\s*([\u4e00-\u9fffA-Za-z0-9（）()]{2,16})")
_QUANT_RE = re.compile(r"(?:提升|降低|增长|节省|减少|优化|覆盖|处理)?\s*\d+(?:\.\d+)?\s*[%％万倍]+")

_EMPLOYMENT_WORDS = ("校招", "社招", "实习", "兼职", "全职", "应届", "校园招聘")


def _split_sections(text: str) -> dict[str, str]:
    """按常见简历栏目标题切分正文 -> {栏目名: 正文}。"""
    sections: dict[str, list[str]] = {}
    current = "__head__"
    sections[current] = []
    for line in text.splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _first_kv(text: str, keys: tuple[str, ...]) -> tuple[str, str] | None:
    for line in text.splitlines():
        m = _KV_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if key in keys and value:
            return key, value
    return None


def _pick_degree(text: str) -> tuple[str | None, str, str]:
    """返回 (规范学历, 证据窗口, note)。多个不同层级 -> note 提示人工复核。"""
    found: list[tuple[str, int]] = []
    for tok in _DEGREE_TOKENS:
        for m in re.finditer(re.escape(tok), text):
            found.append((_DEGREE_CANON[tok], m.start()))
    if not found:
        return None, "", ""
    distinct = sorted({d for d, _ in found})
    pos = min(p for _, p in found)
    window = text[max(0, pos - 20): pos + 30].strip()
    if len(distinct) > 1:
        # 多个层级并存：取证据位置最早的，标记 needs_review 交人工判断
        first = min(found, key=lambda t: t[1])[0]
        return first, mask_matches(window), "multiple_degree_tokens:" + "/".join(distinct)
    return found[0][0], mask_matches(window), ""


def _bullet_chunks(section_text: str) -> list[str]:
    if not section_text:
        return []
    parts = re.split(r"\n\s*(?:[•●▪\-—*]|\d+[.、)])\s*", section_text)
    return [p.strip() for p in parts if p.strip()]


def _build_experiences(section_text: str, kind: str) -> list[ExperienceEntry]:
    out: list[ExperienceEntry] = []
    for i, chunk in enumerate(_bullet_chunks(section_text)[:20]):
        quant = [mask_matches(q.strip()) for q in _QUANT_RE.findall(chunk) if q.strip()]
        out.append(ExperienceEntry(
            entry_id=f"{kind}_{i:02d}", kind=kind,
            title="", period="",
            excerpt=mask_matches(chunk[:400]),
            fact_source="stated_in_source", extraction_method="section_excerpt_v1",
            quantified_achievements=quant,
        ))
    return out


# ------------------------------------------------------------------ 主入口
def parse_resume_text(text: str, *, profile_id: str = "student_unknown",
                      is_synthetic: bool = True,
                      source_document: str = "inline_text",
                      structured_fields: dict | None = None) -> StudentProfile:
    """纯文本简历 -> StudentProfile。structured_fields 用于外部已结构化的自报字段。"""
    raw = "" if text is None else str(text)
    warnings: list[str] = []
    if len(raw.strip()) < 8:
        return StudentProfile(profile_id=profile_id, parse_status="empty_text",
                              warnings=["resume_text_empty_or_too_short"],
                              is_synthetic=is_synthetic, source_document=source_document)
    pii_hits = detect_pii(raw)
    if pii_hits:
        warnings.append("pii_masked_in_evidence:" + ",".join(sorted(pii_hits)))
    body = mask_matches(raw)
    sections = _split_sections(body)
    sf = dict(structured_fields or {})

    # ---- 显式键值字段（stated_in_source）
    edu_field = Field.unknown()
    major_field = Field.unknown()
    year_field = Field.unknown()
    intention_field = Field.unknown()
    city_field = Field.unknown()
    employ_field = Field.unknown()

    kv = _first_kv(body, _INTENTION_KEYS)
    if kv:
        intention_field = Field(value=kv[1], status="ok", fact_source="stated_in_source",
                                extraction_method="key_value_v1",
                                evidence_text=f"{kv[0]}：{kv[1]}")
    kv = _first_kv(body, _EDU_KEYS)
    if kv:
        deg, window, note = _pick_degree(kv[1] or kv[0])
        edu_field = Field(value=deg or kv[1], status="ok" if deg else "needs_review",
                          fact_source="stated_in_source", extraction_method="key_value_v1",
                          evidence_text=f"{kv[0]}：{kv[1]}", note=note)
    kv = _first_kv(body, _MAJOR_KEYS)
    if kv:
        major_field = Field(value=kv[1], status="ok", fact_source="stated_in_source",
                            extraction_method="key_value_v1",
                            evidence_text=f"{kv[0]}：{kv[1]}")
    kv = _first_kv(body, _YEAR_KEYS)
    if kv:
        m = _YEAR_RE.search(kv[1])
        year_field = Field(value=m.group(1) if m else None,
                           status="ok" if m else "needs_review",
                           fact_source="stated_in_source", extraction_method="key_value_v1",
                           evidence_text=f"{kv[0]}：{kv[1]}")
    kv = _first_kv(body, _CITY_KEYS)
    if kv:
        cities = [c.strip() for c in re.split(r"[、,，/;;\s]+", kv[1]) if c.strip()]
        city_field = Field(value=cities, status="ok" if cities else "unknown",
                           fact_source="stated_in_source", extraction_method="key_value_v1",
                           evidence_text=f"{kv[0]}：{kv[1]}")
    kv = _first_kv(body, _EMPLOYMENT_KEYS)
    if kv:
        employ_field = Field(value=kv[1], status="ok", fact_source="stated_in_source",
                             extraction_method="key_value_v1",
                             evidence_text=f"{kv[0]}：{kv[1]}")

    # ---- 外部结构化自报字段（优先级高于文本推断，事实等级 self_reported）
    if sf.get("target_position") and intention_field.status == "unknown":
        intention_field = Field(value=norm_text(sf["target_position"]), status="ok",
                                fact_source="stated_in_source",
                                extraction_method="structured_self_report_v1",
                                evidence_text=norm_text(sf["target_position"]))
    if sf.get("education_level") and edu_field.status == "unknown":
        deg, window, note = _pick_degree(str(sf["education_level"]))
        edu_field = Field(value=deg or norm_text(sf["education_level"]),
                          status="ok" if deg else "needs_review",
                          fact_source="stated_in_source",
                          extraction_method="structured_self_report_v1",
                          evidence_text=norm_text(sf["education_level"]), note=note)
    if sf.get("graduation_cohort") and year_field.status == "unknown":
        m = _YEAR_RE.search(str(sf["graduation_cohort"]))
        year_field = Field(value=m.group(1) if m else None,
                           status="ok" if m else "needs_review",
                           fact_source="stated_in_source",
                           extraction_method="structured_self_report_v1",
                           evidence_text=str(sf["graduation_cohort"]))
    if sf.get("city") and city_field.status == "unknown":
        city_field = Field(value=[norm_text(sf["city"])], status="ok",
                           fact_source="stated_in_source",
                           extraction_method="structured_self_report_v1",
                           evidence_text=str(sf["city"]))
    if sf.get("employment_type") and employ_field.status == "unknown":
        employ_field = Field(value=norm_text(sf["employment_type"]), status="ok",
                             fact_source="stated_in_source",
                             extraction_method="structured_self_report_v1",
                             evidence_text=str(sf["employment_type"]))

    # ---- 规则回退（rule_parsed）
    if edu_field.status == "unknown":
        deg, window, note = _pick_degree(sections.get("教育背景", "") or body)
        if deg:
            edu_field = Field(value=deg, status="needs_review" if note else "ok",
                              fact_source="rule_parsed", extraction_method="degree_token_v1",
                              evidence_text=window, note=note)
    if year_field.status == "unknown":
        m = _COHORT_RE.search(body) or _YEAR_RE.search(sections.get("教育背景", "") or body)
        if m:
            year_field = Field(value=m.group(1), status="ok", fact_source="rule_parsed",
                               extraction_method="year_pattern_v1",
                               evidence_text=mask_matches(m.group(0)))
    if major_field.status == "unknown":
        m = _MAJOR_RE.search(sections.get("教育背景", "") or "")
        if m:
            value = (m.group(1) or m.group(2) or "").strip()
            major_field = Field(value=value or None,
                                status="ok" if value else "unknown",
                                fact_source="rule_parsed", extraction_method="major_pattern_v1",
                                evidence_text=mask_matches(m.group(0)))
    if employ_field.status == "unknown":
        for w in _EMPLOYMENT_WORDS:
            if w in body:
                employ_field = Field(value=w, status="ok", fact_source="rule_parsed",
                                     extraction_method="keyword_v1", evidence_text=w)
                break

    # ---- 技能：显式"技能"栏目（self_reported）+ 全文词表（extracted_from_resume）
    skill_section = ""
    for key in ("专业技能", "技能特长", "技能"):
        if sections.get(key):
            skill_section = sections[key]
            break
    skills = skills_from_segment(
        skill_section, evidence_source="stated_in_source",
        verification_status="self_reported") if skill_section else []
    seen = {s.canonical_name for s in skills}
    for sk in scan_skills_in_text(body):
        if sk.canonical_name not in seen:
            seen.add(sk.canonical_name)
            skills.append(sk)
    if sf.get("skills"):
        for sk in normalize_skill_terms(
                sf["skills"], evidence_text=str(sf.get("skills_text", "")),
                evidence_source="stated_in_source", verification_status="self_reported",
                extraction_method="explicit_field"):
            if sk.canonical_name not in seen:
                seen.add(sk.canonical_name)
                skills.append(sk)

    # ---- 经历栏目（只留原文摘录）
    projects = _build_experiences(sections.get("项目经历", "") or sections.get("项目经验", ""),
                                  "project")
    internships = _build_experiences(sections.get("实习经历", "") or sections.get("实习经验", ""),
                                     "internship")
    certificates = _build_experiences(sections.get("证书", "") or sections.get("资格证书", ""),
                                      "certificate")

    known = [f for f in (edu_field, major_field, year_field, intention_field,
                         city_field, employ_field) if f.status != "unknown"]
    parse_status = "ok" if (known or skills) else "needs_review"
    if edu_field.note.startswith("multiple_degree_tokens"):
        warnings.append("multiple_degree_tokens_needs_review")

    return StudentProfile(
        profile_id=profile_id,
        education_level=edu_field, major=major_field, graduation_year=year_field,
        employment_intention=intention_field, preferred_cities=city_field,
        employment_type=employ_field,
        skills=skills, project_experiences=projects,
        internship_experiences=internships, certificates=certificates,
        source_evidence={
            "text_sha256": sha256_text(body),
            "text_length": len(body),
            "extraction_pipeline": "resume_parser_v1",
            "pii_masked": bool(pii_hits),
            "pii_hit_kinds": sorted(pii_hits),
            "sections_detected": sorted(sections),
            "profile_version": PROFILE_VERSION,
        },
        profile_version=PROFILE_VERSION,
        parse_status=parse_status, is_synthetic=is_synthetic,
        warnings=warnings, source_document=source_document,
    )


def parse_resume_file(path: Path | str, *, profile_id: str | None = None,
                      is_synthetic: bool = True,
                      structured_fields: dict | None = None) -> StudentProfile:
    """文件简历 -> StudentProfile。扫描版 PDF 显式返回 ocr_required 状态。"""
    p = Path(path)
    got = extract_document(p)
    pid = profile_id or f"student_{sha256_text(str(p.name))[:10]}"
    if got["parse_status"] == "ocr_required":
        return StudentProfile(profile_id=pid, parse_status="ocr_required",
                              warnings=["ocr_required: " + got["note"]],
                              is_synthetic=is_synthetic, source_document=p.name,
                              source_evidence={
                                  "format": got["format"], "extractor": got["extractor"],
                                  "extraction_pipeline": "resume_parser_v1",
                                  "profile_version": PROFILE_VERSION,
                              })
    profile = parse_resume_text(got["text"], profile_id=pid, is_synthetic=is_synthetic,
                                source_document=p.name,
                                structured_fields=structured_fields)
    profile.source_evidence["format"] = got["format"]
    profile.source_evidence["extractor"] = got["extractor"]
    return profile
