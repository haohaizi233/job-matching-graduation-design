# -*- coding: utf-8 -*-
"""学历样本的输入解析与标签规范化（第三阶段 3.2.2）。

输入结构（实测）：
  user = <岗位名称>…</岗位名称><岗位描述>…</岗位描述><学历描述>…</学历描述>
其中 <学历描述> 是上游已抽取的短槽位（中位长度 2 字符）。

标签结构（实测）：
  assistant / 人工正确结果 = "博士、硕士、本科" 这类 6 token 组合串，从高到低排列。
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np

from .config import get_config

_SEG_RES = {
    "job_title_norm": re.compile(r"<岗位名称>(.*?)</岗位名称>", re.S),
    "job_description_norm": re.compile(r"<岗位描述>(.*?)</岗位描述>", re.S),
    "slot_education_norm": re.compile(r"<学历描述>(.*?)</学历描述>", re.S),
}
_LABEL_SPLIT = re.compile(r"[、,，/|\n]+")
_WS = re.compile(r"\s+")


def norm_text(s) -> str:
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    return _WS.sub(" ", t).strip()


def parse_user_segments(user: str) -> dict:
    """把 user 拆成三段；缺失段返回空串并置 present=False。"""
    s = "" if user is None else str(user)
    out = {}
    for k, rx in _SEG_RES.items():
        m = rx.search(s)
        out[k] = norm_text(m.group(1)) if m else ""
    out["slot_present"] = bool(_SEG_RES["slot_education_norm"].search(s))
    out["user_norm"] = norm_text(s)
    out["user_len"] = len(s)
    return out


# ------------------------------------------------------------------ 标签规范化
def _token_maps() -> tuple[dict[str, str], dict[str, str]]:
    cfg = get_config()
    canon: dict[str, str] = {}
    for token, forms in (cfg.edu_labels.get("canonical_tokens") or {}).items():
        for f in list(forms) + [token]:
            canon[norm_text(f)] = token
    syn: dict[str, str] = {}
    for degree, forms in (cfg.edu_labels.get("degree_synonyms") or {}).items():
        for f in list(forms) + [degree]:
            syn[norm_text(f)] = degree
    return canon, syn


_CANON: dict[str, str] | None = None
_SYN: dict[str, str] | None = None


def token_maps() -> tuple[dict[str, str], dict[str, str]]:
    global _CANON, _SYN
    if _CANON is None:
        _CANON, _SYN = _token_maps()
    return _CANON, _SYN


def normalize_label(raw) -> dict:
    """把标签串规范成 6 token 多热向量。

    返回：
      tokens        规范后的 token 列表（按 label_order 排序）
      unresolved    无法映射到词表的原 token（保留原值，不强行归并）
      status        ok | empty | oov_token | conflict
    """
    cfg = get_config()
    order = cfg.label_order
    canon, _ = token_maps()

    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return {"tokens": [], "unresolved": [], "status": "empty",
                "multi_hot": [0] * len(order)}
    s = norm_text(raw)
    if not s:
        return {"tokens": [], "unresolved": [], "status": "empty",
                "multi_hot": [0] * len(order)}

    toks: list[str] = []
    unresolved: list[str] = []
    for piece in _LABEL_SPLIT.split(s):
        p = norm_text(piece)
        if not p:
            continue
        if p in canon:
            t = canon[p]
            if t not in toks:
                toks.append(t)
        else:
            unresolved.append(p)

    status = "ok"
    if unresolved:
        status = "oov_token"
    has_level = any(t in ("博士", "硕士", "本科", "大专") for t in toks)
    if ("学历不限" in toks and has_level) or ("学历不明" in toks and (has_level or "学历不限" in toks)):
        status = "conflict"
    if not toks and not unresolved:
        status = "empty"

    toks_sorted = [t for t in order if t in toks]
    multi_hot = [1 if t in toks else 0 for t in order]
    return {"tokens": toks_sorted, "unresolved": unresolved, "status": status,
            "multi_hot": multi_hot}


def multi_hot_to_tokens(vec) -> list[str]:
    order = get_config().label_order
    return [t for t, v in zip(order, list(vec)) if int(v) == 1]


def encode_multi_hot(token_lists: list[list[str]]) -> np.ndarray:
    order = get_config().label_order
    idx = {t: i for i, t in enumerate(order)}
    out = np.zeros((len(token_lists), len(order)), dtype=np.int8)
    for r, toks in enumerate(token_lists):
        for t in toks:
            if t in idx:
                out[r, idx[t]] = 1
    return out
