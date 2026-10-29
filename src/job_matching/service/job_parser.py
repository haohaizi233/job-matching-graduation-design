# -*- coding: utf-8 -*-
"""中文岗位 JD 解析 -> JobProfile（模块 B）。

能力：
  * 岗位标题 / 岗位类别 / 城市 / 雇主 / 就业形式 / 毕业届别 / 薪资 / 职责；
  * 必要技能 vs 加分技能区分（"优先/加分/更佳"标记切段）；
  * 学历要求解析：优先 EducationNormalizer（模型），失败/缺失时明确规则模式，
    不伪造模型输出；记录 model_version、表达式是否在训练中出现过、拒识/人工复核状态；
  * 每个字段带 fact_source：stated_in_source / rule_parsed / model_inferred / human_corrected。

复用 annotation/pool 的中文启发式抽取（技能词表、类别、年限、加分段、学历字段）。
"""
from __future__ import annotations

import re
from pathlib import Path

from ..annotation.pii import mask_matches
from ..annotation.pool import (classify_job_category, preferred_segment)
from ..core import norm_text, sha256_text
from .contracts import (EDU_CONFIDENCE_MEANING, CohortRequirement,
                        EducationRequirement,
                        ExperienceRequirement, Field, JobProfile, PROFILE_VERSION)
from .requirements import (extract_cohort_clause, parse_cohort_requirement,
                           parse_experience_requirement_detail)
from .skills_normalize import (normalize_skill_terms, scan_skills_in_text,
                               skills_from_segment)
from .text_extract import extract_document

# 学历模型输入槽位（Phase4-2 口径）见 education/labels.py

_TITLE_KEYS = ("职位名称", "岗位名称", "职位", "岗位")
_EMPLOYER_KEYS = ("公司名称", "公司", "用人单位", "单位")
_CITY_KEYS = ("工作地点", "工作城市", "城市", "地点")
_SALARY_KEYS = ("薪资", "工资", "薪酬", "待遇")
_EMPLOYMENT_KEYS = ("工作性质", "职位性质", "招聘类型")

_SECTION_RE = re.compile(
    r"^\s*(岗位职责|工作职责|职责描述|岗位描述|任职要求|岗位要求|任职资格|"
    r"任职条件|岗位职责描述|加分项|优先条件)\s*[:：]?\s*$")

_KV_RE = re.compile(
    r"^\s*(职位名称|岗位名称|职位|岗位|公司名称|公司|用人单位|单位|"
    r"工作地点|工作城市|城市|地点|薪资|工资|薪酬|待遇|工作性质|职位性质|招聘类型)\s*[:：]\s*(.+)$")

_SALARY_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*[-~—至到]\s*(\d{1,3}(?:\.\d+)?)\s*([Kk千万元/月·\s年万]*)")
_COHORT_RE = re.compile(r"(20\d{2})\s*届")
_EMPLOYMENT_WORDS = ("全职", "兼职", "实习", "校招", "社招", "校园招聘", "应届")
_CITIES = ("北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "武汉", "成都",
           "西安", "天津", "重庆", "长沙", "郑州", "合肥", "青岛", "大连", "厦门",
           "福州", "济南", "宁波", "无锡", "东莞", "佛山")


def _first_kv(text: str, keys: tuple[str, ...]) -> tuple[str, str] | None:
    for line in text.splitlines():
        m = _KV_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if key in keys and value:
            return key, value
    return None


def _split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"__head__": []}
    current = "__head__"
    for line in text.splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _requirement_section(sections: dict[str, str]) -> str:
    for key in ("任职要求", "岗位要求", "任职资格", "任职条件"):
        if sections.get(key):
            return sections[key]
    return ""


def _duty_section(sections: dict[str, str]) -> str:
    for key in ("岗位职责", "工作职责", "职责描述", "岗位描述", "岗位职责描述"):
        if sections.get(key):
            return sections[key]
    return ""


def _preferred_window(text: str) -> str:
    """加分语义窗口：命中"优先/加分/更佳"标记时，从所在行行首截取到结尾。"""
    seg = preferred_segment(text)
    if not seg:
        return ""
    idx = text.find(seg)
    line_start = text.rfind("\n", 0, idx) + 1
    return text[line_start:].strip()


_EDU_CLAUSE_HINTS = ("学历", "本科", "硕士", "博士", "大专", "专科", "不限", "统招")


def _edu_clause(line: str) -> str:
    """从岗位行内抽取学历相关分句（避免把整条任职要求塞给学历解析器）。"""
    for clause in re.split(r"[，,。；;、\n]", line):
        c = clause.strip()
        if c and any(h in c for h in _EDU_CLAUSE_HINTS):
            return re.sub(r"^\s*\d+[.、)]\s*", "", c)
    return re.sub(r"^\s*\d+[.、)]\s*", "", line.strip())


# ------------------------------------------------------------------ 学历解析器
class JobEducationResolver:
    """岗位学历要求解析器：模型优先 + 规则回退 + 拒识/人工复核。

    * model_dir 可用时加载 EducationNormalizer（支持批量），记录 model_version 与
      expression_seen_in_train；confidence 沿用其未校准声明；
    * model_dir=None 或模型不可用 -> 明确 rules_only 模式，只输出规则结果，
      不生成任何 model_* 字段（不允许伪造模型输出）；
    * 异常表达（无中英数字符号、超长）-> status="rejected"，转人工复核。
    """

    MAX_INPUT_CHARS = 20000

    def __init__(self, model_dir: Path | str | None = None,
                 fallback_to_rules: bool = True):
        self.fallback_to_rules = bool(fallback_to_rules)
        self.model_dir = Path(model_dir) if model_dir else None
        self.normalizer = None
        self.model_version = None
        self.mode = "rules_only"
        self.load_error: str | None = None
        if self.model_dir is not None:
            try:
                from ..education.predictor import EducationNormalizer
                self.normalizer = EducationNormalizer.from_model_dir(
                    self.model_dir, fallback_to_rules=fallback_to_rules)
                self.model_version = getattr(self.normalizer, "model_version", self.model_dir.name)
                self.mode = "model+rule_fallback"
            except Exception as e:  # 模型缺失/损坏 -> 显式规则模式
                self.load_error = f"{type(e).__name__}: {e}"
                self.mode = "rules_only"

    # ---------------------------------------------------------- 单条
    def resolve(self, raw_text: str) -> EducationRequirement:
        return self.resolve_batch([raw_text])[0]

    # ---------------------------------------------------------- 批量
    def resolve_batch(self, texts: list[str]) -> list[EducationRequirement]:
        raw_list = ["" if t is None else str(t) for t in texts]
        out: list[EducationRequirement] = []
        model_inputs: list[int] = []
        model_texts: list[str] = []
        for i, raw in enumerate(raw_list):
            s = norm_text(raw)
            if not s:
                out.append(EducationRequirement(
                    raw="", tokens=["学历不明"], status="rules_only", source="rule",
                    rule="empty_input", needs_human_review=True,
                    note="空输入按标签规范返回 学历不明"))
                continue
            if len(s) > self.MAX_INPUT_CHARS or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", s):
                out.append(EducationRequirement(
                    raw=s[:200], tokens=[], status="rejected", source="rule",
                    rule="anomalous_input", needs_human_review=True,
                    note="输入表达异常（无有效字符或超长），拒识并转人工复核"))
                continue
            out.append(None)  # 占位
            if self.normalizer is not None:
                model_inputs.append(i)
                model_texts.append(s)
            else:
                out[i] = self._rule_only(s)

        if self.normalizer is not None and model_texts:
            try:
                recs = self.normalizer.batch(model_texts)
            except Exception as e:  # 模型前向失败 -> 显式降级规则，不伪造
                self.load_error = f"inference_failed: {type(e).__name__}: {e}"
                for k, i in enumerate(model_inputs):
                    out[i] = self._rule_only(model_texts[k])
                return out
            for k, i in enumerate(model_inputs):
                out[i] = self._from_model_record(recs[k])
        return out

    # ---------------------------------------------------------- 结果映射
    def _from_model_record(self, rec: dict) -> EducationRequirement:
        labels = list(rec.get("labels") or [])
        rule = rec.get("rule")
        used_rule = bool(rec.get("fallback_to_rule"))
        status = "rules_only" if used_rule else "model"
        needs_review = (labels == ["学历不明"]) or not labels
        return EducationRequirement(
            raw=str(rec.get("input", ""))[:200],
            tokens=labels,
            status=status,
            source="rule" if used_rule else "model",
            model_version=rec.get("model_version"),
            expression_seen_in_train=rec.get("expression_seen_in_train"),
            confidence=rec.get("confidence"),
            confidence_meaning=EDU_CONFIDENCE_MEANING,
            rule=rule,
            needs_human_review=needs_review,
            note=("模型输出为 学历不明，建议人工复核" if needs_review else ""),
        )

    def _rule_only(self, s: str) -> EducationRequirement:
        from ..education.rules import rule_predict

        def _try(text: str):
            return rule_predict(re.sub(r"^\s*\d+[.、)]\s*", "", text.strip()))

        r = _try(s)
        if r.get("tokens") == ["学历不明"]:
            for clause in re.split(r"[，,。；;、\n]", s):
                if not any(h in clause for h in _EDU_CLAUSE_HINTS):
                    continue
                r2 = _try(clause)
                if r2.get("tokens") and r2.get("tokens") != ["学历不明"]:
                    r = r2
                    break
        labels = list(r.get("tokens") or [])
        needs_review = (labels == ["学历不明"]) or not labels
        return EducationRequirement(
            raw=s[:200], tokens=labels, status="rules_only", source="rule",
            model_version=None, expression_seen_in_train=None,
            confidence=None, confidence_meaning=EDU_CONFIDENCE_MEANING,
            rule=f"rule_predict:{r.get('rule')}",
            needs_human_review=needs_review,
            note="规则模式（模型不可用），未生成任何模型输出" +
                 ("；结果为 学历不明，建议人工复核" if needs_review else ""),
        )

    def describe(self) -> dict:
        return {"mode": self.mode, "model_dir": str(self.model_dir) if self.model_dir else None,
                "model_version": self.model_version,
                "fallback_to_rules": self.fallback_to_rules,
                "load_error": self.load_error,
                "confidence_meaning": EDU_CONFIDENCE_MEANING}


# ------------------------------------------------------------------ 主入口
def parse_job_text(text: str, *, job_id: str = "job_unknown",
                   source: str = "inline_text", source_license: str = "UNKNOWN",
                   employer: str = "", is_synthetic: bool = True,
                   resolver: JobEducationResolver | None = None,
                   structured_fields: dict | None = None) -> JobProfile:
    """纯文本岗位 JD -> JobProfile（缺失字段保留 unknown 状态）。"""
    raw = "" if text is None else str(text)
    warnings: list[str] = []
    if len(raw.strip()) < 8:
        return JobProfile(job_id=job_id, source=source, source_license=source_license,
                          parse_status="empty_text",
                          warnings=["job_text_empty_or_too_short"], is_synthetic=is_synthetic)
    body = mask_matches(raw)
    sections = _split_sections(body)
    sf = dict(structured_fields or {})
    head = sections.get("__head__", "")

    # ---- 标题
    title_val, title_status, title_src, title_ev = None, "unknown", "unknown", ""
    kv = _first_kv(head + "\n" + body, _TITLE_KEYS)
    if kv:
        title_val, title_status, title_src, title_ev = kv[1], "ok", "stated_in_source", f"{kv[0]}：{kv[1]}"
    elif sf.get("job_title"):
        title_val, title_status, title_src, title_ev = norm_text(sf["job_title"]), "ok", "stated_in_source", str(sf["job_title"])
    else:
        for line in body.splitlines():
            line = line.strip()
            if 2 <= len(line) <= 40 and not _SECTION_RE.match(line):
                title_val, title_status, title_src, title_ev = line, "ok", "rule_parsed", line
                break

    # ---- 雇主 / 城市 / 薪资 / 就业形式
    employer_val = employer or ""
    employer_src = "stated_in_source" if employer else "unknown"
    kv = _first_kv(body, _EMPLOYER_KEYS)
    if kv:
        employer_val, employer_src = kv[1], "stated_in_source"

    city_val, city_src, city_ev = None, "unknown", ""
    kv = _first_kv(body, _CITY_KEYS)
    if kv:
        city_val, city_src, city_ev = kv[1], "stated_in_source", f"{kv[0]}：{kv[1]}"
    else:
        for c in _CITIES:
            if c in body:
                city_val, city_src, city_ev = c, "rule_parsed", c
                break

    salary_val, salary_src, salary_ev = None, "unknown", ""
    kv = _first_kv(body, _SALARY_KEYS)
    if kv:
        salary_val, salary_src, salary_ev = kv[1], "stated_in_source", f"{kv[0]}：{kv[1]}"
    else:
        m = _SALARY_RE.search(body)
        if m:
            salary_val, salary_src = m.group(0), "rule_parsed"
            salary_ev = m.group(0)

    employ_val, employ_src = None, "unknown"
    kv = _first_kv(body, _EMPLOYMENT_KEYS)
    if kv:
        employ_val, employ_src = kv[1], "stated_in_source"
    else:
        for w in _EMPLOYMENT_WORDS:
            if w in body:
                employ_val, employ_src = w, "rule_parsed"
                break

    cohort_val, cohort_src, cohort_ev = None, "unknown", ""
    m = _COHORT_RE.search(body)
    if m:
        cohort_val, cohort_src, cohort_ev = m.group(1), "rule_parsed", m.group(0)
    elif "应届" in body:
        cohort_val, cohort_src, cohort_ev = "应届", "rule_parsed", "应届"
    # Phase5-1R F-005：规范化届别约束（支持仅限某届/多届/区间/及以后/应届/往届/不限）
    cohort_clause = extract_cohort_clause(body)
    cohort_req = parse_cohort_requirement(cohort_clause, source=cohort_src,
                                          evidence_text=cohort_ev or cohort_clause)
    if cohort_req.rule != "unclear" and cohort_src == "unknown":
        cohort_src = "rule_parsed"

    # ---- 类别（启发式，来源显式登记）
    category, category_src = classify_job_category(title_val or "", body)

    # ---- 必要 / 加分技能
    duty_text = _duty_section(sections)
    req_text = _requirement_section(sections)
    pref_section = sections.get("加分项", "") or sections.get("优先条件", "")
    pref_marker_seg = _preferred_window(req_text) if req_text else _preferred_window(body)
    req_only = req_text
    if pref_marker_seg and pref_marker_seg in req_only:
        req_only = req_only.split(pref_marker_seg)[0]
    pref_segment = pref_section or pref_marker_seg
    required_skills = skills_from_segment(
        req_only, evidence_source="rule_parsed",
        verification_status="extracted_from_resume") if req_only else []
    seen = {s.canonical_name for s in required_skills}
    preferred_skills = skills_from_segment(
        pref_segment, evidence_source="rule_parsed",
        verification_status="extracted_from_resume") if pref_segment else []
    preferred_skills = [s for s in preferred_skills if s.canonical_name not in seen]
    seen_p = {s.canonical_name for s in preferred_skills}
    if sf.get("required_skills"):
        for sk in normalize_skill_terms(sf["required_skills"],
                                        evidence_text="structured:required_skills",
                                        evidence_source="stated_in_source",
                                        verification_status="extracted_from_resume",
                                        extraction_method="explicit_field"):
            if sk.canonical_name not in seen:
                seen.add(sk.canonical_name)
                required_skills.append(sk)
    if sf.get("preferred_skills"):
        for sk in normalize_skill_terms(sf["preferred_skills"],
                                        evidence_text="structured:preferred_skills",
                                        evidence_source="stated_in_source",
                                        verification_status="extracted_from_resume",
                                        extraction_method="explicit_field"):
            if sk.canonical_name not in seen_p:
                seen_p.add(sk.canonical_name)
                preferred_skills.append(sk)

    # ---- 学历 / 经验
    edu_raw = ""
    for key in ("任职要求", "岗位要求", "任职资格", "任职条件", "学历"):
        for line in body.splitlines():
            if key in line and ("学历" in line or "本科" in line or "硕士" in line
                                or "博士" in line or "大专" in line or "不限" in line):
                edu_raw = _edu_clause(line)
                break
        if edu_raw:
            break
    if not edu_raw and sf.get("education_raw"):
        edu_raw = str(sf["education_raw"])
    if resolver is None:
        resolver = JobEducationResolver(None)
    if edu_raw:
        edu_req = resolver.resolve(edu_raw)
    else:
        edu_req = EducationRequirement(raw="", tokens=[], status="unknown", source="absent",
                                       needs_human_review=True,
                                       note="JD 未提供学历要求，保留 unknown")
    # Phase5-1R F-006：服务层经验解析（先特殊状态后缺失值；"学历不限" 不得误读为经验不限）
    exp_req = parse_experience_requirement_detail(body)

    responsibilities = [c for c in re.split(r"\n", duty_text) if c.strip()][:10] if duty_text else []

    return JobProfile(
        job_id=job_id,
        job_title=Field(value=title_val, status=title_status, fact_source=title_src,
                        extraction_method="key_value_v1" if title_src == "stated_in_source" else "first_line_v1",
                        evidence_text=title_ev),
        job_category=Field(value=category, status="ok", fact_source="rule_parsed",
                           extraction_method=category_src,
                           evidence_text=f"{title_val or ''} {body[:60]}".strip()),
        employer=Field(value=employer_val or None,
                       status="ok" if employer_val else "unknown",
                       fact_source=employer_src, extraction_method="key_value_v1",
                       evidence_text=employer_val),
        city=Field(value=city_val, status="ok" if city_val else "unknown",
                   fact_source=city_src, extraction_method="key_value_v1",
                   evidence_text=city_ev),
        employment_type=Field(value=employ_val, status="ok" if employ_val else "unknown",
                              fact_source=employ_src, extraction_method="key_value_v1",
                              evidence_text=employ_val or ""),
        graduation_cohort=Field(value=cohort_val, status="ok" if cohort_val else "unknown",
                                fact_source=cohort_src, extraction_method="cohort_pattern_v1",
                                evidence_text=cohort_ev),
        cohort_requirement=cohort_req,
        salary=Field(value=salary_val, status="ok" if salary_val else "unknown",
                     fact_source=salary_src, extraction_method="salary_pattern_v1",
                     evidence_text=mask_matches(salary_ev)),
        education_requirement=edu_req,
        experience_requirement=exp_req,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        responsibilities=Field(value=responsibilities or None,
                               status="ok" if responsibilities else "unknown",
                               fact_source="rule_parsed",
                               extraction_method="section_excerpt_v1",
                               evidence_text=mask_matches(duty_text[:300])),
        source=source, source_license=source_license,
        source_evidence={
            "text_sha256": sha256_text(body),
            "text_length": len(body),
            "extraction_pipeline": "job_parser_v1",
            "sections_detected": sorted(sections),
            "education_resolver": resolver.describe(),
            "profile_version": PROFILE_VERSION,
        },
        profile_version=PROFILE_VERSION,
        parse_status="ok" if title_val else "partial",
        is_synthetic=is_synthetic, warnings=warnings,
    )


def parse_job_file(path: Path | str, *, job_id: str | None = None,
                   source_license: str = "UNKNOWN",
                   resolver: JobEducationResolver | None = None,
                   is_synthetic: bool = True) -> JobProfile:
    p = Path(path)
    got = extract_document(p)
    jid = job_id or f"job_{sha256_text(p.name)[:10]}"
    profile = parse_job_text(got["text"], job_id=jid, source=p.name,
                             source_license=source_license,
                             resolver=resolver, is_synthetic=is_synthetic)
    profile.source_evidence["format"] = got["format"]
    return profile
