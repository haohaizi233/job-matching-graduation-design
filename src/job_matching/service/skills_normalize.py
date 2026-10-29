# -*- coding: utf-8 -*-
"""技能词典归一化（模块 A / 测试场景 5）。

复用：
  * preprocess_skills.canonical_skill / canonicalize_skills —— 形式规范化 + 显式别名精确映射
    （铁律：禁止子串包含判断，Java != JavaScript，C != C++）；
  * annotation/pool.SKILL_LEXICON —— 中英混合技能词表（启发式辅助，非真值）；
  * annotation/pii.mask_matches —— 证据文本脱敏后再留存。

产出 SkillEntry：
  * confidence = 启发式抽取置信度（见 CONFIDENCE_MEANING），绝不是技能掌握概率；
  * verification_status 严格区分自报 / 简历抽取 / 评估支撑 / 人工核实 / 未知，
    本阶段自动流水线只产出 self_reported / extracted_from_resume / unknown；
  * 未映射技能保留原值 + needs_review=True，绝不强行归并。
"""
from __future__ import annotations

import re

from ..annotation.pii import mask_matches
from ..annotation.pool import SKILL_LEXICON
from ..core import sha256_text
from ..preprocess_skills import canonical_skill
from .contracts import CONFIDENCE_MEANING, SkillEntry

# 启发式置信度档位（只表示抽取可信度，不表示掌握程度）
CONF_BY_CONTEXT = {
    "explicit_field": 0.90,   # 简历/JD 以"技能：xxx"键值显式列出
    "lexicon_hit": 0.70,      # 正文词表命中
    "manual": 0.95,           # 人工补充/修正
}

_WANTED = sorted({*(str(s).lower() for s in SKILL_LEXICON),
                  "java", "mysql", "spring boot"}, key=len, reverse=True)

# 业务层技能切分（比 preprocess_skills.parse_skill_list 多支持 、 / 换行，
# 并过滤"熟悉/掌握"类引导词与超长非技能片段）
_TERM_SPLIT = re.compile(r"[;,，；、|/\n]+")
_NOISE_PREFIX = re.compile(r"^\s*(?:熟悉|掌握|了解|精通|熟练使用|熟练掌握|擅长|具备|善于|能够|能)\s*")
_LIST_MARKER = re.compile(r"^\s*(?:\d+\s*[.、)）:：]|[(（]\d+[)）])\s*")
# 岗位要求/学历句等非技能片段的强提示词（命中且未被词典识别 -> 丢弃）
_NON_SKILL_CUES = re.compile(
    r"学历|专业|及以上|毕业|年龄|周岁|任职|岗位职责|工作地点|招聘|人数|薪资|待遇")
_MAX_TERM_CHARS = 24


def split_skill_terms(raw) -> list[str]:
    """把技能字段/段落切成词条；过滤列表编号与"学历/专业"类非技能片段。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(v).strip() for v in raw if str(v).strip()]
    out: list[str] = []
    for piece in _TERM_SPLIT.split(str(raw)):
        p = _LIST_MARKER.sub("", piece.strip())
        p = _NOISE_PREFIX.sub("", p).strip(" .。:：;；")
        if not p or len(p) > _MAX_TERM_CHARS:
            continue
        if _NON_SKILL_CUES.search(p):
            canon, status = canonical_skill(p)
            if status == "needs_review":     # 词典/别名不认识的"要求句" -> 非技能
                continue
        out.append(p)
    return out


def _boundary_regex(term: str) -> re.Pattern:
    if re.match(r"^[A-Za-z0-9+#]", term):
        return re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(term)}(?![A-Za-z0-9+#])")
    return re.compile(re.escape(term))


_LEXICON_RES = [(t, _boundary_regex(t)) for t in _WANTED]


def make_skill_id(canonical_name: str) -> str:
    return "skill_" + sha256_text(canonical_name.lower())[:12]


def build_skill_entry(raw_form: str, *, evidence_text: str = "",
                      evidence_source: str = "unknown",
                      verification_status: str = "unknown",
                      extraction_method: str = "lexicon_v1",
                      confidence: float | None = None) -> SkillEntry | None:
    """把一个原始技能写法归一化为 SkillEntry；空值返回 None。"""
    canon, status = canonical_skill(raw_form)
    if not canon:
        return None
    conf = CONF_BY_CONTEXT.get(extraction_method, 0.5) if confidence is None else float(confidence)
    aliases: list[str] = []
    if canon.lower() != str(raw_form).strip().lower():
        aliases.append(str(raw_form).strip())
    return SkillEntry(
        skill_id=make_skill_id(canon),
        canonical_name=canon,
        aliases=aliases,
        evidence_source=evidence_source,
        evidence_text=mask_matches(evidence_text),
        confidence=round(conf, 4),
        confidence_meaning=CONFIDENCE_MEANING,
        verification_status=verification_status,
        raw_form=str(raw_form).strip(),
        extraction_method=extraction_method,
        needs_review=(status == "needs_review"),
    )


def normalize_skill_terms(raw_terms, *, evidence_text: str = "",
                          evidence_source: str = "unknown",
                          verification_status: str = "unknown",
                          extraction_method: str = "explicit_field") -> list[SkillEntry]:
    """结构化/短语技能列表 -> SkillEntry 列表（去重按规范名，保留首次证据）。"""
    out: list[SkillEntry] = []
    seen: set[str] = set()
    for term in split_skill_terms(raw_terms):
        entry = build_skill_entry(term, evidence_text=evidence_text,
                                  evidence_source=evidence_source,
                                  verification_status=verification_status,
                                  extraction_method=extraction_method)
        if entry is None or entry.canonical_name in seen:
            continue
        seen.add(entry.canonical_name)
        out.append(entry)
    return out


def scan_skills_in_text(text: str, *, evidence_source: str = "rule_parsed",
                        verification_status: str = "extracted_from_resume") -> list[SkillEntry]:
    """正文词表扫描：返回命中技能（带原文窗口证据），按词表顺序确定性输出。"""
    s = "" if text is None else str(text)
    low = s.lower()
    out: list[SkillEntry] = []
    seen: set[str] = set()
    for term, rx in _LEXICON_RES:
        m = rx.search(low)
        if not m:
            continue
        start, end = m.span()
        window = s[max(0, start - 30): min(len(s), end + 30)].strip()
        entry = build_skill_entry(term, evidence_text=window,
                                  evidence_source=evidence_source,
                                  verification_status=verification_status,
                                  extraction_method="lexicon_hit")
        if entry is None or entry.canonical_name in seen:
            continue
        seen.add(entry.canonical_name)
        out.append(entry)
    return out


def skills_from_segment(text: str, *, evidence_source: str = "rule_parsed",
                        verification_status: str = "extracted_from_resume",
                        extraction_method: str = "explicit_field") -> list[SkillEntry]:
    """技能段落 -> SkillEntry 列表：短词显式归一化 + 词表扫描，按出现顺序去重。

    段落文本里的非技能片段（如"本科及以上学历"）会被过滤：只有
    命中别名表/规范名，或出现在技能词表中的短词才被接受。
    """
    out: list[SkillEntry] = []
    seen: set[str] = set()
    lexicon = {str(s).lower() for s in SKILL_LEXICON}
    for term in split_skill_terms(text):
        canon, status = canonical_skill(term)
        if not canon:
            continue
        if status == "needs_review" and term.strip().lower() not in lexicon:
            continue   # 段落里的非技能片段，不进画像
        entry = build_skill_entry(term, evidence_text=mask_matches(str(text)[:300]),
                                  evidence_source=evidence_source,
                                  verification_status=verification_status,
                                  extraction_method=extraction_method)
        if entry is None or entry.canonical_name in seen:
            continue
        seen.add(entry.canonical_name)
        out.append(entry)
    for entry in scan_skills_in_text(text or "", evidence_source=evidence_source,
                                     verification_status=verification_status):
        if entry.canonical_name in seen:
            continue
        seen.add(entry.canonical_name)
        out.append(entry)
    return out


def match_skill_sets(required: list[SkillEntry], owned: list[SkillEntry]
                     ) -> tuple[list[dict], list[dict]]:
    """按规范名做集合匹配。返回 (matched, missing) 证据记录。

    missing 只表示「当前简历证据未覆盖」，禁止表述为「不会该技能」。
    """
    own = {}
    for sk in owned:
        own.setdefault(sk.canonical_name, sk)
    matched, missing = [], []
    for req in required:
        hit = own.get(req.canonical_name)
        if hit is not None:
            matched.append({"canonical_name": req.canonical_name,
                            "evidence_text": hit.evidence_text,
                            "evidence_source": hit.evidence_source,
                            "verification_status": hit.verification_status,
                            "jd_evidence_text": req.evidence_text})
        else:
            missing.append({"canonical_name": req.canonical_name,
                            "status": "evidence_missing",
                            "jd_evidence_text": req.evidence_text,
                            "note": "当前简历证据未覆盖该技能，不代表候选人不具备该技能"})
    return matched, missing
