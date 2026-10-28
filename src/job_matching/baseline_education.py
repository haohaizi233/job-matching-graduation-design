# -*- coding: utf-8 -*-
"""学历任务零训练 Baseline（第三阶段 3.3.3）。

Baseline E0：明确词表的规则解析器（Rule Baseline，不使用任何标签拟合）
Baseline E1：槽位 -> 标签 经验映射（Empirical Baseline，只在开发集伪标签上统计）
参照系：线上旧系统输出（线上学历-旧的）与新模型输出（模型结果-新的），仅作对照

约束：
  * "X及以上" 的展开方式来自对伪标注数据的实测惯例（pseudo_convention），
    并在报告中给出条件分布证据；不由代码作者臆断。
  * 736 条人工金标准不做任何规则拟合与调参，只做一次性最终评估。
"""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from .config import get_config
from .core import get_logger
from .metrics_classification import multilabel_metrics
from .preprocess_education import norm_text, token_maps

_ABOVE = re.compile(r"^(?P<base>.+?)(?:及以上学历|及以上文化程度|及以上|或以上|以上|学历以上)$")
_STRIP = re.compile(r"[\s：:，,、。;；/\\|()\(\)【】\[\]]+")
_SPLIT = re.compile(r"[或、,，/|]+")


def _clean(s: str) -> str:
    return _STRIP.sub("", norm_text(s))


def _match_degree(s: str) -> str | None:
    """把一段文本精确匹配到学历层级；只做整段/显式同义匹配，不做子串包含。"""
    _, syn = token_maps()
    if not s:
        return None
    if s in syn:
        return syn[s]
    # 允许 "本科""本科""研究生" 后缀
    for suffix in ("学历", "毕业", "文化程度", "生"):
        if s.endswith(suffix) and len(s) > len(suffix):
            t = s[: -len(suffix)]
            if t in syn:
                return syn[t]
    return None


def expand_all_levels_ge(degree: str) -> list[str]:
    """按标签规范把 "X及以上" 展开成层级不低于 X 的全部学历标签（从高到低）。"""
    order = get_config().label_order
    ranks = get_config().edu_labels["degree_rank"]
    if degree not in ranks:
        return []
    r = ranks[degree]
    return [d for d in order if ranks.get(d, -1) >= r]


def rule_predict(slot: str) -> dict:
    """规则基线：由 <学历描述> 槽位直接产出 6 token 多标签。

    规则全部写在 configs/education_labels.yaml，执行时不使用任何训练数据统计。
    """
    order = get_config().label_order
    canon, _ = token_maps()
    raw = "" if slot is None else str(slot)
    s = _clean(raw)
    unresolved: list[str] = []

    if not s:
        return {"tokens": ["学历不明"], "unresolved": [], "rule": "empty_slot"}

    if s in canon:
        return {"tokens": [canon[s]], "unresolved": [], "rule": "direct_token"}

    m = _ABOVE.match(s)
    if m:
        base = _match_degree(_clean(m.group("base")))
        if base:
            toks = expand_all_levels_ge(base)
            return {"tokens": toks, "unresolved": [], "rule": f"above_expand:{base}"}

    d = _match_degree(s)
    if d:
        return {"tokens": [d], "unresolved": [], "rule": "degree_single"}

    pieces = [_clean(p) for p in _SPLIT.split(s) if _clean(p)]
    if pieces:
        degs = [_match_degree(p) for p in pieces]
        if all(degs):
            uniq = []
            for d2 in sorted(set(degs), key=lambda x: -get_config().edu_labels["degree_rank"][x]):
                if d2 not in uniq:
                    uniq.append(d2)
            return {"tokens": uniq, "unresolved": [], "rule": "degree_list"}

    unresolved = [s]
    return {"tokens": ["学历不明"], "unresolved": unresolved, "rule": "unmatched"}


def empirical_slot_mapping(df: pd.DataFrame, slot_col: str = "slot_education_norm",
                           label_col: str = "label_tokens_json") -> dict:
    """在开发集伪标签上统计 P(标签 | 槽位表达)，作为展开规则的实测证据。"""
    table: dict[str, Counter] = defaultdict(Counter)
    for slot, lab in zip(df[slot_col].astype(str), df[label_col].astype(str)):
        table[slot][lab] += 1
    out = {}
    for slot, counter in sorted(table.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(counter.values())
        top, top_n = counter.most_common(1)[0]
        out[slot] = {
            "support": total,
            "top_label": top,
            "top_ratio": round(top_n / total, 6),
            "distinct_labels": len(counter),
            "label_counts": {k: int(v) for k, v in counter.most_common(8)},
        }
    return out


def empirical_predict(slot: str, mapping: dict) -> dict:
    key = norm_text("" if slot is None else str(slot))
    if key in mapping:
        top = mapping[key]["top_label"]
        import json
        toks = json.loads(top) if isinstance(top, str) else list(top)
        return {"tokens": toks, "unresolved": [], "rule": "empirical_lookup"}
    return rule_predict(slot)


# ------------------------------------------------------------------ 评估
def tokens_to_multihot(token_lists: list[list[str]]) -> np.ndarray:
    order = get_config().label_order
    idx = {t: i for i, t in enumerate(order)}
    out = np.zeros((len(token_lists), len(order)), dtype=np.int8)
    for r, toks in enumerate(token_lists):
        for t in toks:
            if t in idx:
                out[r, idx[t]] = 1
    return out


def evaluate_education(true_tokens: list[list[str]], pred_tokens: list[list[str]],
                       unresolved: list[list[str]] | None = None) -> dict:
    order = get_config().label_order
    yt = tokens_to_multihot(true_tokens)
    yp = tokens_to_multihot(pred_tokens)
    m = multilabel_metrics(yt, yp, order)
    if unresolved is not None:
        n_oov = sum(1 for u in unresolved if u)
        m["error_types"]["oov_token_samples"] = int(n_oov)
    return m


def run_education_baselines(dev_train: pd.DataFrame, dev_eval: pd.DataFrame,
                            gold: pd.DataFrame, dataset_version: str) -> dict:
    """在开发集（伪标签）与人工金标准上分别评估规则基线与经验映射基线。"""
    log = get_logger()
    import json
    t0 = time.time()

    mapping = empirical_slot_mapping(dev_train)
    gold_used_for_fitting = False

    def run_one(df: pd.DataFrame, name: str) -> dict:
        slots = df["slot_education_norm"].astype(str).tolist()
        true = [json.loads(x) for x in df["label_tokens_json"].astype(str).tolist()]
        pred_rule, unres = [], []
        pred_emp = []
        for s in slots:
            r = rule_predict(s)
            pred_rule.append(r["tokens"])
            unres.append(r["unresolved"])
            e = empirical_predict(s, mapping)
            pred_emp.append(e["tokens"])
        return {
            "rows": int(len(df)),
            "label_provenance": df["label_provenance"].value_counts().to_dict()
            if "label_provenance" in df.columns else {},
            "rule_baseline": evaluate_education(true, pred_rule, unres),
            "empirical_slot_baseline": evaluate_education(true, pred_emp),
        }

    result = {
        "dataset_version": dataset_version,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "label_order": get_config().label_order,
        "binary_note": "多标签任务，指标为 Exact Match Ratio / Micro-F1 / Macro-F1 / 每标签 P-R-F1",
        "gold_used_for_rule_fitting": gold_used_for_fitting,
        "gold_eval_policy": "金标准只做一次性评估；规则定义在见到金标准之前已由 configs/education_labels.yaml 固定",
        "evaluation_sets": {
            "dev_validation_pseudo": run_one(dev_eval, "dev_validation_pseudo"),
            "gold_holdout_human": run_one(gold, "gold_holdout_human"),
        },
        "slot_label_mapping_top": dict(list(mapping.items())[:20]),
        "slot_label_mapping_size": len(mapping),
        "seconds": round(time.time() - t0, 2),
    }
    log.info("[学历基线] gold exact_match=%.4f micro_f1=%.4f",
             result["evaluation_sets"]["gold_holdout_human"]["rule_baseline"]["exact_match_ratio"],
             result["evaluation_sets"]["gold_holdout_human"]["rule_baseline"]["micro_f1"])
    return result
