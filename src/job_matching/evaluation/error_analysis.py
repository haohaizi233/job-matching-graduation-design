# -*- coding: utf-8 -*-
"""预测错误分类与错误样本分析（第四阶段 4.1 / 十）。

只使用非敏感字段（pair_index、特征值、代理标签），绝不写入简历正文 / JD 原文。
错误对定义：同一 candidate_id 内，final_score 差距 > tie_eps 的两个岗位，
模型预测顺序与代理偏好（final_score 降序）相反。
统计时每个查询只取「最大反序差」的那一对，避免高频候选人重复计数；
同时给出全部错误对的总量。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CATEGORIES = [
    "排名接近导致偏好标签不稳定",
    "极少数 strong 类别",
    "岗位名称相似但技能不同",
    "类别不一致",
    "经验要求异常",
    "技能不一致",
    "其他",
]


def _classify(row_a: pd.Series, row_b: pd.Series, rel_diff: float,
              tie_eps: float) -> str:
    """row_a = 代理偏好更优的一侧，row_b = 模型错误地排在其上的岗位。"""
    if rel_diff < tie_eps * 5:
        return "排名接近导致偏好标签不稳定"
    if "strong_positive" in (row_a["label_strength"], row_b["label_strength"]):
        return "极少数 strong 类别"
    pos_ov = float(max(row_a["position_token_overlap"], row_b["position_token_overlap"]))
    skill_j = float(max(row_a["skill_jaccard"], row_b["skill_jaccard"]))
    if pos_ov >= 0.5 and skill_j < 0.1:
        return "岗位名称相似但技能不同"
    if float(row_b["category_match"]) < 0.5:
        return "类别不一致"
    yrs = float(row_b["years_experience"])
    if not np.isfinite(yrs) or yrs <= 0 or yrs > 30:
        return "经验要求异常"
    if skill_j < 0.1:
        return "技能不一致"
    return "其他"


def analyze_errors(frame: pd.DataFrame, pred_scores: np.ndarray,
                   tie_eps: float = 0.001, max_samples_per_category: int = 5) -> dict:
    df = frame.reset_index(drop=True).copy()
    df["_pred"] = np.asarray(pred_scores, dtype=np.float64)
    df["_rel"] = pd.to_numeric(df["final_score"], errors="coerce").astype(np.float64)

    total_pairs = 0
    error_pairs = 0
    worst_rows: list[dict] = []

    for _, sub in df.groupby("candidate_id", sort=True):
        sub = sub.reset_index(drop=True)
        n = len(sub)
        if n < 2:
            continue
        rel = sub["_rel"].to_numpy()
        pred = sub["_pred"].to_numpy()
        diff = rel[:, None] - rel[None, :]
        iu, ju = np.where(np.triu(diff > tie_eps, k=1))       # i 代理偏好更优
        if iu.size == 0:
            continue
        total_pairs += int(iu.size)
        d_pred = pred[iu] - pred[ju]
        bad = d_pred < 0                                      # 模型把更弱的排前面
        error_pairs += int(bad.sum())
        if not bad.any():
            continue
        bi, bj = iu[bad], ju[bad]
        d_rel = diff[bi, bj]
        worst = int(np.argmax(d_rel))                         # 反序差最大的一对
        a = sub.iloc[bi[worst]]
        b = sub.iloc[bj[worst]]
        rel_diff = float(d_rel[worst])
        cat = _classify(a, b, rel_diff, tie_eps)
        worst_rows.append({
            "category": cat,
            "candidate_id": str(a["candidate_id"]),
            "pair_index_preferred": int(a["pair_index"]),
            "pair_index_overranked": int(b["pair_index"]),
            "job_id_preferred": int(a["job_id"]),
            "job_id_overranked": int(b["job_id"]),
            "label_preferred": str(a["label_strength"]),
            "label_overranked": str(b["label_strength"]),
            "final_score_diff": round(rel_diff, 6),
            "pred_score_diff": round(float(d_pred[worst]), 6),
            "skill_jaccard": round(float(max(a["skill_jaccard"], b["skill_jaccard"])), 4),
            "position_token_overlap": round(float(max(a["position_token_overlap"],
                                                      b["position_token_overlap"])), 4),
            "category_match": int(b["category_match"]),
            "years_experience": float(b["years_experience"]),
        })

    counts = {c: 0 for c in CATEGORIES}
    for r in worst_rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    samples: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for r in worst_rows:
        if len(samples[r["category"]]) < max_samples_per_category:
            samples[r["category"]].append(r)

    groups_with_error = len(worst_rows)
    groups_total = int(df["candidate_id"].nunique())
    return {
        "tie_eps": float(tie_eps),
        "preference_pairs_total": int(total_pairs),
        "preference_pairs_misordered": int(error_pairs),
        "pair_error_rate": round(error_pairs / total_pairs, 6) if total_pairs else None,
        "queries_total": groups_total,
        "queries_with_error": groups_with_error,
        "query_error_rate": round(groups_with_error / groups_total, 6) if groups_total else None,
        "category_counts_worst_pair_per_query": counts,
        "samples_by_category": samples,
        "privacy_note": "样本只含 pair_index / job_id / 特征值 / 代理标签，不含简历正文与 JD 原文",
    }
