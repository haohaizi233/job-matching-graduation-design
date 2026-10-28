# -*- coding: utf-8 -*-
"""技能解析与规范化（第三阶段 3.1.3）。

铁律：不做子串包含判断。Java 与 JavaScript、C 与 C++ 必须保持独立。
只做：NFKC + casefold + 空白折叠 + 显式别名表精确映射。
无法确认的技能保留原值并标记 needs_review，绝不强行归并。
"""
from __future__ import annotations

import ast
import re
import unicodedata

from .config import get_config

_EDGE_PUNCT = re.compile(r"^[\s\.,;:、，；：/\-_]+|[\s\.,;:、，；：/\-_]+$")
_WS = re.compile(r"\s+")

# 别名表 key -> 规范展示名（保持符号原貌，避免 cplusplus / csharp 这类改写）
CANONICAL_DISPLAY = {
    "cplusplus": "c++",
    "csharp": "c#",
    "golang": "go",
    "ci/cd": "ci/cd",
    "node.js": "node.js",
    "restful": "restful",
    "spring boot": "spring boot",
}


def norm_skill_form(s) -> str:
    """技能写法规范化：不改变语义，只统一形式。"""
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.casefold()
    t = _WS.sub(" ", t).strip()
    t = _EDGE_PUNCT.sub("", t).strip()
    return t


def _build_alias_index() -> tuple[dict[str, str], dict[str, str]]:
    cfg = get_config()
    alias_to_canon: dict[str, str] = {}
    display: dict[str, str] = {}
    for key, aliases in (cfg.skills.get("aliases") or {}).items():
        canon_display = CANONICAL_DISPLAY.get(key, key)
        display[key] = canon_display
        for a in list(aliases) + [key]:
            f = norm_skill_form(a)
            if f:
                alias_to_canon[f] = canon_display
    return alias_to_canon, display


_ALIAS_INDEX: dict[str, str] | None = None


def alias_index() -> dict[str, str]:
    global _ALIAS_INDEX
    if _ALIAS_INDEX is None:
        _ALIAS_INDEX, _ = _build_alias_index()
    return _ALIAS_INDEX


def canonical_skill(raw) -> tuple[str, str]:
    """返回 (规范技能名, 状态)。状态 ∈ {alias, normalized, needs_review}。"""
    form = norm_skill_form(raw)
    if not form:
        return "", "empty"
    idx = alias_index()
    if form in idx:
        return idx[form], ("alias" if idx[form] != form else "normalized")
    # 不在别名表里 -> 保留规范化后的原值，标记待复核
    return form, "needs_review"


def parse_skill_list(raw) -> list[str]:
    """把 clean_skills 这类字符串化列表还原成 list[str]；失败返回空列表。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "[]"):
        return []
    try:
        v = ast.literal_eval(s)
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v]
    except Exception:
        pass
    try:
        import json
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x) for x in v]
    except Exception:
        pass
    return [p.strip() for p in re.split(r"[;,，；|]", s) if p.strip()]


def canonicalize_skills(raw) -> dict:
    """返回 canonical / raw / unmapped 三份列表 + 计数，保留完整映射关系。"""
    raw_list = parse_skill_list(raw)
    canon: list[str] = []
    unmapped: list[str] = []
    mapping: dict[str, str] = {}
    for item in raw_list:
        c, status = canonical_skill(item)
        if not c:
            continue
        mapping[item] = c
        if status == "needs_review":
            unmapped.append(c)
        if c not in canon:
            canon.append(c)
    return {
        "skills_raw": raw_list,
        "skills_canonical": canon,
        "skills_unmapped": sorted(set(unmapped)),
        "skills_mapping": mapping,
        "skills_count": len(canon),
        "needs_review": bool(unmapped),
    }


def skill_set(raw) -> set[str]:
    return set(canonicalize_skills(raw)["skills_canonical"])


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def overlap_ratio(a: set[str], b: set[str]) -> float:
    """|a∩b| / |a|；空集返回 0。"""
    return (len(a & b) / len(a)) if a else 0.0
