# -*- coding: utf-8 -*-
"""查询级 Bootstrap 置信区间与零训练基线的本地复算（第四阶段 4.1 / 九）。

纪律：
  * Bootstrap 以查询组（candidate_id）为重采样单位，绝不把同一候选人的
    多个 pair 当作独立样本；
  * 第三阶段基线的汇总指标从 reports/baselines/baseline-results.json 加载，
    本地只复算「每查询指标」用于配对差值，并用汇总值一致性校验保证口径相同。
"""
from __future__ import annotations

import numpy as np

from ..metrics_ranking import dcg_at_k, ndcg_at_k


# ------------------------------------------------------------------ 每查询指标
def per_query_ndcg(group_ids, pred_scores, rel_scores, k: int = 5,
                   min_group_size: int = 2) -> dict[str, float]:
    """按查询组计算 NDCG@k（与 metrics_ranking 同口径：稳定 tie-breaking）。"""
    g = np.asarray(group_ids)
    p = np.asarray(pred_scores, dtype=np.float64)
    r = np.asarray(rel_scores, dtype=np.float64)
    out: dict[str, float] = {}
    for key in sorted(set(g.tolist())):
        m = g == key
        pr, rr = p[m], r[m]
        n = pr.size
        if n < min_group_size:
            continue
        order = np.lexsort((np.arange(n), -pr))
        ranked = rr[order]
        ideal = rr
        if float(np.sum(ideal)) <= 0:
            continue
        v = ndcg_at_k(ranked, ideal, k)
        if np.isfinite(v):
            out[str(key)] = float(v)
    return out


def per_query_pairwise_accuracy(group_ids, pred_scores, rel_scores,
                                tie_eps: float = 0.001) -> dict[str, float]:
    g = np.asarray(group_ids)
    p = np.asarray(pred_scores, dtype=np.float64)
    r = np.asarray(rel_scores, dtype=np.float64)
    out: dict[str, float] = {}
    for key in sorted(set(g.tolist())):
        m = g == key
        pr, rr = p[m], r[m]
        if pr.size < 2:
            continue
        diff = rr[:, None] - rr[None, :]
        iu, ju = np.where(np.triu(diff > tie_eps, k=1))
        if iu.size == 0:
            continue
        d_pred = pr[iu] - pr[ju]
        score = np.where(d_pred > 0, 1.0, np.where(d_pred < 0, 0.0, 0.5))
        out[str(key)] = float(score.mean())
    return out


# ------------------------------------------------------------------ Bootstrap
def bootstrap_diff(per_query_a: dict[str, float], per_query_b: dict[str, float],
                   n_boot: int = 1000, seed: int = 20261204, ci: float = 0.95) -> dict:
    """配对查询级 Bootstrap：对同一组查询重采样，估计 A - B 的均值差置信区间。"""
    keys = sorted(set(per_query_a) & set(per_query_b))
    if not keys:
        return {"note": "没有共同查询，无法做配对 Bootstrap", "queries": 0}
    a = np.array([per_query_a[k] for k in keys], dtype=np.float64)
    b = np.array([per_query_b[k] for k in keys], dtype=np.float64)
    diff = a - b
    n = diff.size
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(int(n_boot), n))
    boot_means = diff[idx].mean(axis=1)
    alpha = (1.0 - ci) / 2.0
    lo = float(np.quantile(boot_means, alpha))
    hi = float(np.quantile(boot_means, 1 - alpha))
    p_le_zero = float(np.mean(boot_means <= 0))
    return {
        "unit": "query(candidate_id)",
        "queries": int(n),
        "n_boot": int(n_boot),
        "seed": int(seed),
        "ci": float(ci),
        "mean_a": round(float(a.mean()), 6),
        "mean_b": round(float(b.mean()), 6),
        "mean_diff": round(float(diff.mean()), 6),
        "ci_low": round(lo, 6),
        "ci_high": round(hi, 6),
        "significant_at_95": bool(lo > 0 or hi < 0),
        "p_bootstrap_le_zero": round(p_le_zero, 6),
    }


# ------------------------------------------------------------------ 零训练基线复算
def local_baseline_scores(kind: str, frame, emb_scores: np.ndarray | None = None,
                          seed: int = 20261101) -> np.ndarray:
    """在给定子集上复算零训练基线的排序分数（与第三阶段 baseline_ranking.py 同口径）。"""
    if kind == "skill_jaccard":
        return frame["skill_jaccard"].to_numpy(dtype=np.float64)
    if kind == "position_token_overlap":
        return frame["position_token_overlap"].to_numpy(dtype=np.float64)
    if kind == "embedding_cosine":
        if emb_scores is None:
            raise ValueError("embedding_cosine 需要 emb_scores（按 pair_index 对齐）")
        return emb_scores[frame["pair_index"].to_numpy(dtype=np.int64)]
    if kind == "random_ranking":
        from ..metrics_ranking import random_ranking_scores
        return random_ranking_scores(len(frame), seed)
    raise ValueError(f"未知基线: {kind}")
