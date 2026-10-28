# -*- coding: utf-8 -*-
"""人岗匹配零训练 Baseline（第三阶段 3.3.1）。

Baseline 0：Random Ranking（多次运行，报均值与标准差）
Baseline 1：Embedding Cosine Similarity（预计算 768 维向量，不调 API、不训练）
Baseline 2：技能集合 Jaccard（只用 clean_skills 原始字段独立计算）
Baseline 3：职位名称词元重合度（只用 target_position / job_title 原始字段）

全部 Baseline 在完全相同的候选集合、评估协议与标签定义下比较。
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .config import get_config
from .core import get_logger
from .metrics_ranking import evaluate_ranking, random_ranking_scores

BASELINES = ("random_ranking", "embedding_cosine", "skill_jaccard", "position_token_overlap")

CAVEATS = [
    "label_strength / candidate_rank / final_score 全部由原评分系统公式派生，"
    "本节指标只能衡量预测结果与原系统代理偏好的一致程度，不代表真实录用概率或用户满意度。",
    "semantic_score = 0.5 * cosine(cv_emb, job_emb) + 0.5 已被审计以 R²=1.0 证实，"
    "而 semantic_score 占 raw_score 的 0.25 权重、raw_score 占 final_score 的 0.7 权重。"
    "因此 Embedding Cosine Baseline 与代理标签的生成机制直接耦合，"
    "即使 NDCG 很高也不能视为独立的语义匹配有效性证明。",
    "matches.csv 只含正样本记录（weak/medium/strong 全部为 *_positive），无真实负例；"
    "本阶段不做负采样，仅在观测组合内部做组内排序评估。",
    "Random Ranking 的均值±标准差基于固定种子序列的多次独立运行，不是同一运行的重复采样误差。",
]


def cosine_scores(cv_emb: np.ndarray, job_emb: np.ndarray,
                  cv_rows: np.ndarray, job_rows: np.ndarray,
                  block: int = 512) -> np.ndarray:
    """分块计算 cosine(cv_emb[i], job_emb[j])，避免大中间矩阵常驻内存。"""
    n = cv_rows.shape[0]
    out = np.zeros(n, dtype=np.float32)
    for s in range(0, n, block):
        e = min(s + block, n)
        a = cv_emb[cv_rows[s:e]]
        b = job_emb[job_rows[s:e]]
        out[s:e] = np.einsum("ij,ij->i", a, b)
    return out


def _subset_scores(name: str, df: pd.DataFrame, emb_scores: np.ndarray | None,
                   rng_seed: int) -> np.ndarray:
    if name == "random_ranking":
        return random_ranking_scores(len(df), rng_seed)
    if name == "embedding_cosine":
        # emb_scores 按 matches.csv 原始行序存放，pair_index 即行号
        return emb_scores[df["pair_index"].to_numpy(dtype=np.int64)]
    if name == "skill_jaccard":
        return df["skill_jaccard"].to_numpy(dtype=np.float64)
    if name == "position_token_overlap":
        return df["position_token_overlap"].to_numpy(dtype=np.float64)
    raise ValueError(name)


def run_matching_baselines(pairs: pd.DataFrame, features: pd.DataFrame,
                           emb_scores: np.ndarray | None,
                           protocol: str, split_col: str = "split") -> dict:
    """在指定协议的 validation / test 子集上运行全部 Baseline。"""
    log = get_logger()
    cfg = get_config()
    ks = (5, 10)
    min_size = cfg.min_group_size_for_ranking

    # 合并 pair 键与特征（行序对齐）
    merged = pairs.reset_index(drop=True).copy()
    if "pair_index" not in merged.columns:
        raise ValueError("pairs 必须携带 pair_index（matches.csv 原始行号）")
    merged["pair_index"] = merged["pair_index"].astype(np.int64)
    feat_cols = ["skill_jaccard", "position_token_overlap"]
    merged = merged.merge(features[["candidate_id", "job_id"] + feat_cols],
                          on=["candidate_id", "job_id"], how="left", validate="one_to_one")
    if merged[feat_cols].isna().any().any():
        raise ValueError("pair 特征与匹配键未对齐（出现 NaN）")

    label_ord = {"weak_positive": 1.0, "medium_positive": 2.0, "strong_positive": 3.0}
    merged["gain_ordinal"] = merged["label_strength"].map(label_ord).astype(np.float64)
    merged["binary_relevant"] = (merged["label_strength"] != "weak_positive").astype(np.int8)

    out: dict = {
        "protocol": protocol,
        "baselines": list(BASELINES),
        "k_values": list(ks),
        "min_group_size_for_ranking": min_size,
        "caveats": CAVEATS,
        "subsets": {},
    }

    for subset in ("validation", "test"):
        sub = merged[merged[split_col] == subset].reset_index(drop=True)
        if len(sub) == 0:
            out["subsets"][subset] = {"rows": 0, "note": "该协议下此子集为空"}
            continue
        entry: dict = {
            "rows": int(len(sub)),
            "candidates": int(sub["candidate_id"].nunique()),
            "jobs": int(sub["job_id"].nunique()),
            "label_distribution": sub["label_strength"].value_counts().to_dict(),
            "results": {},
        }
        for gain_mode in ("score", "ordinal"):
            rel_col = "final_score" if gain_mode == "score" else "gain_ordinal"
            gain_entry = {}
            for name in BASELINES:
                t0 = time.time()
                if name == "random_ranking":
                    reps = int(cfg.seed("baseline_random_repeats"))
                    base_seed = cfg.seed("baseline_random_ranking")
                    nd = {k: [] for k in ks}
                    mrr = {k: [] for k in ks}
                    rec = {k: [] for k in ks}
                    agg = None
                    for r in range(reps):
                        scores = random_ranking_scores(len(sub), base_seed + r)
                        res = evaluate_ranking(sub["candidate_id"], scores,
                                               sub[rel_col].to_numpy(),
                                               binary_relevant=sub["binary_relevant"].to_numpy(),
                                               ks=ks, gain_mode=gain_mode,
                                               min_group_size=min_size)
                        agg = res
                        for scope in ("size_ge_2",):
                            for k in ks:
                                nd[k].append(res[scope][f"ndcg@{k}"])
                                mrr[k].append(res[scope][f"mrr@{k}"])
                                rec[k].append(res[scope][f"recall@{k}"])
                    rnd = {}
                    for k in ks:
                        a = np.asarray(nd[k], dtype=np.float64)
                        b = np.asarray(mrr[k], dtype=np.float64)
                        c = np.asarray(rec[k], dtype=np.float64)
                        rnd[f"ndcg@{k}_mean"] = round(float(a.mean()), 6)
                        rnd[f"ndcg@{k}_std"] = round(float(a.std(ddof=1)), 6) if a.size > 1 else 0.0
                        rnd[f"mrr@{k}_mean"] = round(float(b.mean()), 6)
                        rnd[f"mrr@{k}_std"] = round(float(b.std(ddof=1)), 6) if b.size > 1 else 0.0
                        rnd[f"recall@{k}_mean"] = round(float(c.mean()), 6)
                        rnd[f"recall@{k}_std"] = round(float(c.std(ddof=1)), 6) if c.size > 1 else 0.0
                    entry_stats = {s: agg[s] for s in agg if isinstance(agg[s], dict)}
                    gain_entry[name] = {
                        "runs": reps, "seed_base": base_seed,
                        "aggregate": entry_stats, "repeated_stats": rnd,
                        "seconds": round(time.time() - t0, 2),
                    }
                else:
                    scores = _subset_scores(name, sub, emb_scores,
                                            cfg.seed("baseline_random_ranking"))
                    res = evaluate_ranking(sub["candidate_id"], scores,
                                           sub[rel_col].to_numpy(),
                                           binary_relevant=sub["binary_relevant"].to_numpy(),
                                           ks=ks, gain_mode=gain_mode,
                                           min_group_size=min_size)
                    gain_entry[name] = {"aggregate": {s: res[s] for s in res
                                                      if isinstance(res[s], dict)},
                                        "group_stats": {s: res[s] for s in res
                                                        if not isinstance(res[s], dict)},
                                        "seconds": round(time.time() - t0, 2)}
            entry["results"][gain_mode] = gain_entry
        out["subsets"][subset] = entry
        log.info("[baseline/%s/%s] rows=%d candidates=%d", protocol, subset,
                 len(sub), entry["candidates"])
    return out
