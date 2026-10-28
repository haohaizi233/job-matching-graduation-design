# -*- coding: utf-8 -*-
"""排序评估指标（第三阶段 3.3.2）。

口径统一，所有 Baseline 必须在完全相同的候选集合、评估协议与标签定义下比较。

代理标签限制（必须写进报告）：
  candidate_rank / label_strength / final_score 全部由原评分系统公式派生，
  因此本模块输出的指标只能衡量 "预测结果与原系统代理偏好之间的一致程度"，
  不代表实际招聘成功率、真实录用概率或用户真实满意度。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 二值相关性的显式定义（代理定义，非真实录用结果）
BINARY_RELEVANCE_RULE = "label_strength in {medium_positive, strong_positive}"
GAIN_MODES = ("score", "ordinal")
ORDINAL_GAIN = {"weak_positive": 1.0, "medium_positive": 2.0, "strong_positive": 3.0}


def dcg_at_k(gains: np.ndarray, k: int) -> float:
    g = np.asarray(gains, dtype=np.float64)[:k]
    if g.size == 0:
        return 0.0
    discounts = 1.0 / np.log2(np.arange(2, g.size + 2))
    return float(np.sum(g * discounts))


def ndcg_at_k(ranked_gains: np.ndarray, ideal_gains: np.ndarray, k: int) -> float:
    idcg = dcg_at_k(np.sort(np.asarray(ideal_gains, dtype=np.float64))[::-1], k)
    if idcg <= 0:
        return float("nan")
    return dcg_at_k(ranked_gains, k) / idcg


def relevance_to_gain(relevance: np.ndarray, mode: str) -> np.ndarray:
    r = np.asarray(relevance, dtype=np.float64)
    if mode == "score":
        return r
    if mode == "ordinal":
        return r
    raise ValueError(f"未知 gain_mode: {mode}")


def evaluate_ranking(group_ids, pred_scores, relevance, binary_relevant=None,
                     ks=(5, 10), gain_mode: str = "score",
                     min_group_size: int = 2) -> dict:
    """按查询组计算 NDCG@K / MRR@K / Recall@K 与有效查询统计。

    group_ids:     每条样本所属的查询组（candidate_id）
    pred_scores:   模型/基线给出的排序分数（越大越靠前）
    relevance:     代理相关性数值（gain_mode='score' 时直接作为增益）
    binary_relevant: 二值相关性，用于 MRR / Recall；None 表示不计算这两项
    """
    df = pd.DataFrame({
        "g": list(group_ids),
        "s": np.asarray(pred_scores, dtype=np.float64),
        "r": np.asarray(relevance, dtype=np.float64),
    })
    if binary_relevant is not None:
        df["b"] = np.asarray(binary_relevant, dtype=np.int8)

    sizes = df.groupby("g").size()
    size_dist = {
        "min": int(sizes.min()) if len(sizes) else 0,
        "p25": float(sizes.quantile(0.25)) if len(sizes) else 0.0,
        "median": float(sizes.median()) if len(sizes) else 0.0,
        "p75": float(sizes.quantile(0.75)) if len(sizes) else 0.0,
        "max": int(sizes.max()) if len(sizes) else 0,
        "mean": round(float(sizes.mean()), 4) if len(sizes) else 0.0,
    }

    out: dict = {
        "gain_mode": gain_mode,
        "binary_relevance_rule": BINARY_RELEVANCE_RULE if binary_relevant is not None else None,
        "queries_total": int(len(sizes)),
        "queries_size_ge_2": int((sizes >= 2).sum()),
        "queries_size_ge_min": int((sizes >= min_group_size).sum()),
        "queries_size_eq_1": int((sizes == 1).sum()),
        "group_size_distribution": size_dist,
        "ks": list(ks),
    }

    for scope, cond in (("all", lambda n: True),
                        ("size_ge_2", lambda n: n >= 2),
                        ("size_ge_maxk", lambda n: n >= max(ks))):
        ndcg = {k: [] for k in ks}
        mrr = {k: [] for k in ks}
        recall = {k: [] for k in ks}
        n_used = 0
        n_skipped = 0
        for g, sub in df.groupby("g", sort=True):
            n = len(sub)
            if not cond(n) or n < min_group_size:
                continue
            # 确定性 tie-breaking：分数相同按原始行序（稳定）
            sub = sub.reset_index(drop=True)
            order = np.lexsort((sub.index.to_numpy(), -sub["s"].to_numpy()))
            ranked_gain = relevance_to_gain(sub["r"].to_numpy()[order], gain_mode)
            ideal_gain = relevance_to_gain(sub["r"].to_numpy(), gain_mode)
            if float(np.sum(ideal_gain)) <= 0:
                n_skipped += 1
                continue
            n_used += 1
            for k in ks:
                ndcg[k].append(ndcg_at_k(ranked_gain, ideal_gain, k))
            if binary_relevant is not None:
                b = sub["b"].to_numpy()[order]
                rel_total = int(sub["b"].sum())
                for k in ks:
                    top = b[:k]
                    hits = np.where(top == 1)[0]
                    mrr[k].append(1.0 / (hits[0] + 1) if hits.size else 0.0)
                    recall[k].append((hits.size / rel_total) if rel_total > 0 else float("nan"))
        entry = {
            "queries_evaluated": n_used,
            "queries_skipped_zero_relevance": n_skipped,
        }
        for k in ks:
            v = np.asarray(ndcg[k], dtype=np.float64)
            entry[f"ndcg@{k}"] = round(float(np.nanmean(v)), 6) if v.size else None
            if binary_relevant is not None:
                m = np.asarray(mrr[k], dtype=np.float64)
                r = np.asarray(recall[k], dtype=np.float64)
                entry[f"mrr@{k}"] = round(float(np.nanmean(m)), 6) if m.size else None
                entry[f"recall@{k}"] = round(float(np.nanmean(r)), 6) if r.size else None
        out[scope] = entry
    return out


def random_ranking_scores(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).random(n)
