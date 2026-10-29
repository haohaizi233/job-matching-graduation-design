# -*- coding: utf-8 -*-
"""独立评估排序指标（协议第六节）。

复用 `job_matching.metrics_ranking.evaluate_ranking` 计算 NDCG@K / MRR@K / Recall@K，
本模块只补充其未提供的 Precision@K 与人工标签口径（unjudgeable 排除、阈值定义），
**不复制**已有指标实现，保证与第三/四阶段完全一致的组内排序与 tie-breaking。

口径（必须与协议一起引用）：
  * 查询组 = 一份简历（resume_id）；
  * relevance ∈ {0,1,2} 作为增益（gain_mode='score'），二值相关阈值 = 1（relevance >= 1）；
  * unjudgeable / 未标注样本不计入增益、不计入分母，只统计数量；
  * Precision@K 分母 = min(K, 组内候选数)；
  * 全零相关组沿用 metrics_ranking 的处理：单独计数（queries_skipped_zero_relevance），
    不进入主指标；同时给出把全零组计为 0 的对照值。
"""
from __future__ import annotations

import numpy as np

from ..metrics_ranking import evaluate_ranking

HUMAN_GAIN = {"0": 0.0, "1": 1.0, "2": 2.0}
DEFAULT_KS = (5, 10)
DEFAULT_MIN_GROUP_SIZE = 2


def prepare_human_labels(relevance_labels) -> tuple[np.ndarray, dict]:
    """把人工标签转成增益值，返回 (增益数组, 过滤统计)。非法标签直接报错。"""
    gains = []
    stats = {"unjudgeable": 0, "unlabeled": 0, "judgeable": 0, "invalid": 0}
    for lab in relevance_labels:
        s = "" if lab is None else str(lab).strip()
        if s == "unjudgeable":
            stats["unjudgeable"] += 1
            continue
        if s == "":
            stats["unlabeled"] += 1
            continue
        if s not in HUMAN_GAIN:
            stats["invalid"] += 1
            raise ValueError(f"非法人工标签: {lab!r}（合法值 0/1/2/unjudgeable）")
        stats["judgeable"] += 1
        gains.append(HUMAN_GAIN[s])
    return np.asarray(gains, dtype=np.float64), stats


def _precision_at_k(group_ids, pred_scores, gains, ks, min_group_size,
                    include_zero_rel_groups: bool) -> dict[int, float]:
    out = {k: [] for k in ks}
    for g in sorted(set(group_ids)):
        idx = [i for i, gg in enumerate(group_ids) if gg == g]
        n = len(idx)
        if n < min_group_size:
            continue
        s = np.asarray([pred_scores[i] for i in idx], dtype=np.float64)
        r = np.asarray([gains[i] for i in idx], dtype=np.float64)
        if float(r.sum()) <= 0 and not include_zero_rel_groups:
            continue
        order = np.lexsort((np.arange(n), -s))  # 与 metrics_ranking 一致的稳定 tie-breaking
        ranked = r[order]
        for k in ks:
            top = ranked[:k]
            denom = float(min(k, n))
            out[k].append(float((top >= 1.0).sum()) / denom if denom > 0 else 0.0)
    return {k: (round(float(np.mean(v)), 6) if v else None) for k, v in out.items()}


def _materialize_inputs(group_ids, pred_scores, relevance_labels) -> tuple[list, np.ndarray, list]:
    """入口统一物化输入（Phase5-1R F-009）。

    历史缺陷：函数内多次 list(relevance_labels)，传入生成器时第一次取到数据、
    后续迭代为空，导致长度校验误判或样本被静默丢弃。

    修复口径：三个输入（含 group_ids / pred_scores 生成器）各物化一次，
    后续逻辑只使用物化结果；长度不一致、NaN/Inf 分数一律显式报错。
    """
    groups_all = list(group_ids)
    scores_list = list(pred_scores)
    labels_all = list(relevance_labels)
    n = len(groups_all)
    if len(scores_list) != n or len(labels_all) != n:
        raise ValueError(
            "group_ids / pred_scores / relevance_labels 长度不一致: "
            f"{n} / {len(scores_list)} / {len(labels_all)}")
    scores_all = np.asarray(scores_list, dtype=np.float64)
    if not np.isfinite(scores_all).all():
        raise ValueError("pred_scores 含 NaN/Inf，排序指标不可确定性计算（拒绝输入）")
    return groups_all, scores_all, labels_all


def evaluate_ranking_human(group_ids, pred_scores, relevance_labels,
                           ks=DEFAULT_KS, min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
                           relevance_threshold: int = 1) -> dict:
    """人工 Gold 排序评估：Precision@K / Recall@K / NDCG@K / MRR@K / 有效查询组数量。"""
    ks = tuple(int(k) for k in ks)
    groups_all, scores_all, labels_all = _materialize_inputs(
        group_ids, pred_scores, relevance_labels)

    keep_groups, keep_scores, keep_labels = [], [], []
    stats = {"unjudgeable": 0, "unlabeled": 0, "judgeable": 0, "invalid": 0}
    for g, s, lab in zip(groups_all, scores_all, labels_all):
        txt = "" if lab is None else str(lab).strip()
        if txt == "unjudgeable":
            stats["unjudgeable"] += 1
            continue
        if txt == "":
            stats["unlabeled"] += 1
            continue
        if txt not in HUMAN_GAIN:
            stats["invalid"] += 1
            raise ValueError(f"非法人工标签: {lab!r}")
        stats["judgeable"] += 1
        keep_groups.append(g)
        keep_scores.append(float(s))
        keep_labels.append(txt)

    gains = np.asarray([HUMAN_GAIN[t] for t in keep_labels], dtype=np.float64)
    binary = (gains >= float(relevance_threshold)).astype(np.int8)

    out: dict = {
        "label_source": "human_gold",
        "gain_mode": "human_ordinal_0_1_2",
        "relevance_threshold": int(relevance_threshold),
        "precision_denominator": "min(k, group_size)",
        "unjudgeable_policy": "excluded_from_gain_and_denominator",
        "label_filter_stats": stats,
        "min_group_size": int(min_group_size),
        "ks": list(ks),
    }
    if not keep_groups:
        out.update({
            "queries_total": 0, "queries_size_ge_2": 0, "queries_evaluated": 0,
            "queries_skipped_zero_relevance": 0, "effective_query_count": 0,
            "note": "无任何可判定样本，指标不可计算（不填充数值）",
        })
        for k in ks:
            out[f"precision@{k}"] = None
            out[f"ndcg@{k}"] = None
            out[f"mrr@{k}"] = None
            out[f"recall@{k}"] = None
        return out

    base = evaluate_ranking(keep_groups, keep_scores, gains, binary_relevant=binary,
                            ks=ks, gain_mode="score", min_group_size=int(min_group_size))
    out.update({k: v for k, v in base.items()
                if k not in ("binary_relevance_rule", "gain_mode")})
    out["gain_mode"] = "human_ordinal_0_1_2"
    out["underlying_gain_mode"] = "score（metrics_ranking 增益口径，传入人工 0/1/2 序数）"
    out["binary_relevance_rule"] = f"human relevance >= {int(relevance_threshold)}"
    for scope, cond in (("all", lambda n: True),
                        ("size_ge_2", lambda n: n >= 2),
                        ("size_ge_maxk", lambda n: n >= max(ks))):
        sub_g, sub_s, sub_r = [], [], []
        counts: dict[str, int] = {}
        for g in sorted(set(keep_groups)):
            idx = [i for i, gg in enumerate(keep_groups) if gg == g]
            counts[g] = len(idx)
            if not cond(len(idx)):
                continue
            for i in idx:
                sub_g.append(keep_groups[i])
                sub_s.append(keep_scores[i])
                sub_r.append(keep_labels[i])
        gains_s = np.asarray([HUMAN_GAIN[t] for t in sub_r], dtype=np.float64)
        prec = _precision_at_k(sub_g, sub_s, gains_s, ks, int(min_group_size),
                               include_zero_rel_groups=False)
        prec_all = _precision_at_k(sub_g, sub_s, gains_s, ks, int(min_group_size),
                                   include_zero_rel_groups=True)
        entry = out.get(scope, {})
        for k in ks:
            entry[f"precision@{k}"] = prec[k]
            entry[f"precision@{k}_with_zero_rel_groups"] = prec_all[k]
        out[scope] = entry

    # 顶层给出有效查询组统计（与空输入分支字段一致，避免口径分叉）
    out["queries_evaluated"] = int(out["all"].get("queries_evaluated", 0))
    out["queries_skipped_zero_relevance"] = int(
        out["all"].get("queries_skipped_zero_relevance", 0))
    out["effective_query_count"] = out["queries_evaluated"]
    return out
