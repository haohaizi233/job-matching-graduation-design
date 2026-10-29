# -*- coding: utf-8 -*-
"""配对 Bootstrap 统计推断（协议第七节 / 测试场景 11）。

纪律：
  * 重采样单位 = 查询组（一份简历），不把同一简历的多个 pair 当独立样本；
  * 同一次 Bootstrap 中所有模型使用相同的重采样组：实现复用
    `evaluation.statistical_tests.bootstrap_diff`，其 rng 由 (key 集合, n_boot, seed)
    完全决定，因此不同模型对比调用时生成的重采样索引矩阵完全一致；
  * 默认 1000 次重采样、固定种子；输出模型 − 基线均值差与 95% 置信区间；
  * 有效查询组不足时显式报告统计不稳定，禁止声明显著优于 Baseline。
"""
from __future__ import annotations

import numpy as np

from ..evaluation.statistical_tests import bootstrap_diff
from ..metrics_ranking import ndcg_at_k

DEFAULT_N_BOOT = 1000
DEFAULT_SEED = 20261205
DEFAULT_CI = 0.95
MIN_GROUPS_FOR_STABILITY = 20
METRICS = ("precision", "recall", "ndcg", "mrr")


def _order(scores: np.ndarray) -> np.ndarray:
    n = scores.size
    return np.lexsort((np.arange(n), -scores))  # 与 metrics_ranking 一致


def per_query_metric(group_ids, pred_scores, relevance_labels, metric: str = "ndcg",
                     k: int = 5, min_group_size: int = 2) -> dict[str, float]:
    """按查询组计算单指标值（用于配对 Bootstrap）。

    口径与 metrics.evaluate_ranking_human 一致：
      * unjudgeable / 未标注样本剔除；
      * 组内候选数 < min_group_size 剔除；
      * 全零相关组剔除（计数返回给调用方）。
    """
    if metric not in METRICS:
        raise ValueError(f"未知指标: {metric}")
    gain = {"0": 0.0, "1": 1.0, "2": 2.0}
    rows: dict[str, list[tuple[float, float]]] = {}
    skipped = {"unjudgeable_or_unlabeled": 0}
    for g, s, lab in zip(group_ids, pred_scores, relevance_labels):
        txt = "" if lab is None else str(lab).strip()
        if txt not in gain:
            skipped["unjudgeable_or_unlabeled"] += 1
            continue
        rows.setdefault(str(g), []).append((float(s), gain[txt]))

    out: dict[str, float] = {}
    skipped_small = 0
    skipped_zero = 0
    for g in sorted(rows):
        pairs = rows[g]
        if len(pairs) < min_group_size:
            skipped_small += 1
            continue
        s = np.asarray([p[0] for p in pairs], dtype=np.float64)
        r = np.asarray([p[1] for p in pairs], dtype=np.float64)
        if float(r.sum()) <= 0:
            skipped_zero += 1
            continue
        order = _order(s)
        ranked = r[order]
        if metric == "ndcg":
            out[g] = float(ndcg_at_k(ranked, r, k))
        elif metric == "precision":
            top = ranked[:k]
            out[g] = float((top >= 1.0).sum()) / float(min(k, ranked.size))
        elif metric == "recall":
            total = float((r >= 1.0).sum())
            hits = float((ranked[:k] >= 1.0).sum())
            out[g] = hits / total if total > 0 else 0.0
        else:  # mrr
            top = ranked[:k]
            hits = np.where(top >= 1.0)[0]
            out[g] = 1.0 / float(hits[0] + 1) if hits.size else 0.0
    out_stats = {"skipped_small_groups": skipped_small,
                 "skipped_zero_relevance_groups": skipped_zero, **skipped}
    per_query_metric.last_stats = out_stats  # type: ignore[attr-defined]
    return out


def paired_bootstrap_vs_baseline(per_query_by_model: dict[str, dict[str, float]],
                                 baseline: str, *, metric: str = "ndcg", k: int = 5,
                                 n_boot: int = DEFAULT_N_BOOT, seed: int = DEFAULT_SEED,
                                 ci: float = DEFAULT_CI,
                                 min_groups: int = MIN_GROUPS_FOR_STABILITY) -> dict:
    """所有模型 vs 基线的配对 Bootstrap（共享同一批重采样组）。"""
    if baseline not in per_query_by_model:
        raise ValueError(f"基线 {baseline!r} 不在模型集合中: {sorted(per_query_by_model)}")
    key_sets = {m: set(v) for m, v in per_query_by_model.items()}
    ref = key_sets[baseline]
    if not ref:
        return {"status": "not_computable", "reason": "no_effective_queries",
                "metric": metric, "k": k}
    for m, ks_ in key_sets.items():
        if ks_ != ref:
            raise ValueError(
                f"模型 {m!r} 的有效查询组与基线不一致，无法保证共享重采样组 "
                f"(|model|={len(ks_)}, |baseline|={len(ref)})")

    comparisons = {}
    for model in sorted(per_query_by_model):
        if model == baseline:
            continue
        res = bootstrap_diff(per_query_by_model[model], per_query_by_model[baseline],
                             n_boot=int(n_boot), seed=int(seed), ci=float(ci))
        res["model"] = model
        res["baseline"] = baseline
        res["interpretation"] = ("significant" if res.get("significant_at_95") else "not_significant")
        comparisons[model] = res

    n_groups = len(ref)
    return {
        "status": "ok",
        "metric": metric,
        "k": k,
        "unit": "query(resume_id)",
        "queries": n_groups,
        "n_boot": int(n_boot),
        "seed": int(seed),
        "ci": float(ci),
        "comparisons": comparisons,
        "statistical_stability": ("stable" if n_groups >= min_groups else "unstable"),
        "stability_note": ("" if n_groups >= min_groups else
                           f"有效查询组 {n_groups} < {min_groups}：统计不稳定，"
                           "禁止声明显著优于 Baseline"),
        "shared_resampling_guarantee":
            "重采样单位为查询组（resume_id）；bootstrap_diff 的重采样索引由 "
            "(排序后的 key 集合, n_boot, seed) 完全决定；"
            "本函数强制所有模型 key 集合一致，因此各对比使用同一批重采样组",
    }
