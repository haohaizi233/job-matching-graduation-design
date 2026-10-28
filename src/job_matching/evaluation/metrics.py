# -*- coding: utf-8 -*-
"""模型评估指标（第四阶段 4.1 / 九）。

排序指标完全沿用第三阶段 src/job_matching/metrics_ranking.py 的口径
（同一候选集合、同一 tie-breaking、同一 K 与组大小规则），保证与零训练 Baseline 可比。
本模块只补充：成对一致性、回归辅助指标、查询级统计，不做任何口径改动。

代理标签限制（必须随指标一起引用）：
  candidate_rank / label_strength / final_score 全部由原评分系统公式派生，
  指标只能解释为「预测结果与原系统代理偏好之间的一致程度」，
  不代表真实录用概率、招聘成功率或用户满意度。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..metrics_ranking import BINARY_RELEVANCE_RULE, evaluate_ranking

ORDINAL_GAIN = {"weak_positive": 1.0, "medium_positive": 2.0, "strong_positive": 3.0}
SELECTION_METRIC_KEYS = {
    "ndcg_at_5_ordinal": ("ordinal", "size_ge_2", "ndcg@5"),
    "ndcg_at_10_ordinal": ("ordinal", "size_ge_2", "ndcg@10"),
    "ndcg_at_5_score": ("score", "size_ge_2", "ndcg@5"),
    "ndcg_at_10_score": ("score", "size_ge_2", "ndcg@10"),
}


def binary_relevance(label_strength) -> np.ndarray:
    return (np.asarray(label_strength) != "weak_positive").astype(np.int8)


def pairwise_accuracy(group_ids, pred_scores, rel_scores,
                      tie_eps: float = 0.001, per_query_equal_weight: bool = True) -> dict:
    """组内成对一致性：rel_i - rel_j > tie_eps 的对中，预测顺序正确的比例。

    同分处理：|Δrel| <= tie_eps 的对视为同分，不计入分子分母；
    预测分数完全相等的对计 0.5 分（平局）。每个查询先算准确率，再对查询宏平均
    （per_query_equal_weight=True），避免高频候选人主导。
    """
    g = np.asarray(group_ids)
    p = np.asarray(pred_scores, dtype=np.float64)
    r = np.asarray(rel_scores, dtype=np.float64)
    accs: list[float] = []
    pairs_used = 0
    queries_used = 0
    queries_no_pair = 0
    for key in sorted(set(g.tolist())):
        m = g == key
        pr, rr = p[m], r[m]
        n = pr.size
        if n < 2:
            queries_no_pair += 1
            continue
        diff = rr[:, None] - rr[None, :]
        iu, ju = np.where(np.triu(diff > tie_eps, k=1))
        if iu.size == 0:
            queries_no_pair += 1
            continue
        d_pred = pr[iu] - pr[ju]
        score = np.where(d_pred > 0, 1.0, np.where(d_pred < 0, 0.0, 0.5))
        accs.append(float(score.mean()))
        pairs_used += int(iu.size)
        queries_used += 1
    return {
        "pairwise_accuracy": round(float(np.mean(accs)), 6) if accs else None,
        "weighting": "per_query_macro_average" if per_query_equal_weight else "pair_micro_average",
        "tie_eps": float(tie_eps),
        "tie_rule": "|Δfinal_score| <= tie_eps 的对不计入；预测分完全相同的对计 0.5",
        "pairs_used": int(pairs_used),
        "queries_used": int(queries_used),
        "queries_no_valid_pair": int(queries_no_pair),
    }


def _safe_corr(fn, a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    v = fn(a, b)
    try:
        val = float(v[0])
    except Exception:
        val = float(v)
    return None if not np.isfinite(val) else round(val, 6)


def regression_metrics(pred_scores, rel_scores) -> dict:
    from scipy import stats
    p = np.asarray(pred_scores, dtype=np.float64)
    r = np.asarray(rel_scores, dtype=np.float64)
    err = p - r
    out = {
        "mae": round(float(np.mean(np.abs(err))), 6),
        "rmse": round(float(np.sqrt(np.mean(err ** 2))), 6),
        "spearman": _safe_corr(stats.spearmanr, p, r),
        "kendall_tau_b": _safe_corr(lambda x, y: stats.kendalltau(x, y, variant="b"), p, r),
    }
    return out


def per_query_corr(group_ids, pred_scores, rel_scores) -> dict:
    """查询级 Spearman：组内样本 < 3 或零方差记为不可评估，不填 0。"""
    from scipy import stats
    g = np.asarray(group_ids)
    p = np.asarray(pred_scores, dtype=np.float64)
    r = np.asarray(rel_scores, dtype=np.float64)
    vals: list[float] = []
    skipped = 0
    for key in sorted(set(g.tolist())):
        m = g == key
        pr, rr = p[m], r[m]
        if pr.size < 3 or np.std(pr) == 0 or np.std(rr) == 0:
            skipped += 1
            continue
        v = stats.spearmanr(pr, rr).correlation
        if np.isfinite(v):
            vals.append(float(v))
        else:
            skipped += 1
    return {
        "spearman_per_query_mean": round(float(np.mean(vals)), 6) if vals else None,
        "queries_used": len(vals),
        "queries_not_evaluable": skipped,
        "note": "组内样本 < 3 或零方差记为不可评估，不强行填 0",
    }


def ranking_report(group_ids, pred_scores, frame: pd.DataFrame,
                   ks=(5, 10), min_group_size: int = 2,
                   tie_eps: float = 0.001) -> dict:
    """完整评估报告：score/ordinal 两种增益口径 + 成对一致性 + 辅助指标。"""
    pred = np.asarray(pred_scores, dtype=np.float64)
    rel_score = pd.to_numeric(frame["final_score"], errors="coerce").to_numpy(np.float64)
    label = frame["label_strength"].astype(str).to_numpy()
    rel_ordinal = np.array([ORDINAL_GAIN[v] for v in label], dtype=np.float64)
    binary = binary_relevance(label)

    out: dict = {
        "query_unit": "candidate_id",
        "ks": list(ks),
        "min_group_size_for_ranking": int(min_group_size),
        "binary_relevance_rule": BINARY_RELEVANCE_RULE,
        "gain_modes": {
            "score": evaluate_ranking(group_ids, pred, rel_score, binary_relevant=binary,
                                      ks=ks, gain_mode="score",
                                      min_group_size=min_group_size),
            "ordinal": evaluate_ranking(group_ids, pred, rel_ordinal, binary_relevant=binary,
                                        ks=ks, gain_mode="ordinal",
                                        min_group_size=min_group_size),
        },
        "pairwise": pairwise_accuracy(group_ids, pred, rel_score, tie_eps=tie_eps),
        "regression": regression_metrics(pred, rel_score),
        "per_query_spearman": per_query_corr(group_ids, pred, rel_score),
    }
    return out


def selection_value(report: dict, metric_key: str) -> float:
    """按配置的 selection_metric 从 ranking_report 中取模型选择用的标量（越大越好）。"""
    if metric_key not in SELECTION_METRIC_KEYS:
        raise KeyError(f"未登记的选择指标: {metric_key}")
    mode, scope, name = SELECTION_METRIC_KEYS[metric_key]
    v = report["gain_modes"][mode][scope][name]
    if v is None:
        raise ValueError(f"选择指标 {metric_key} 不可评估（None）")
    return float(v)
