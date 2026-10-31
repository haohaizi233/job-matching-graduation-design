# -*- coding: utf-8 -*-
"""中文岗位检索 / 重排序评价指标（Phase4-3B / M5-8.1）。

口径纪律（与 docs/evaluation-protocol.md 第三节保持一致）：
  * 查询组 = 一份简历（resume_id），组内候选 = 该简历的岗位配对；
  * 相关性标签必须显式给出，来源写入结果元数据；
  * 组内候选不足 K 时按实际组大小截断，不剔除该组；
  * tie-breaking 固定：分数相同按输入顺序（稳定排序）；
  * 只有正例 / 全零相关 / 组过小的查询组必须单独计数，
    不允许强行输出会误导的指标。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "RelevanceSpec",
    "GroupEval",
    "evaluate_groups",
    "relevance_from_labels",
    "ndcg_at_k",
    "mrr_at_k",
    "recall_at_k",
    "precision_at_k",
    "pairwise_accuracy",
]


@dataclass
class RelevanceSpec:
    """相关性定义（必须显式，禁止隐式二值化）。"""

    kind: str                       # "binary" | "graded"
    relevant_values: tuple = ("2", "1")
    gain_mode: str = "ordinal"      # "ordinal" | "binary"
    label_source: str = "unknown"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class GroupEval:
    group_id: str
    n_candidates: int
    n_relevant: int
    ndcg: dict = field(default_factory=dict)
    mrr: dict = field(default_factory=dict)
    recall: dict = field(default_factory=dict)
    precision: dict = field(default_factory=dict)
    skipped_reason: str | None = None


# ---------------------------------------------------------------- 基本指标
def _dcg(gains: np.ndarray, k: int) -> float:
    k = min(k, len(gains))
    if k <= 0:
        return 0.0
    disc = 1.0 / np.log2(np.arange(2, k + 2))
    return float(np.sum(gains[:k] * disc))


def ndcg_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int,
              gain_mode: str = "ordinal") -> float:
    if len(y_true) == 0:
        return float("nan")
    order = np.lexsort((np.arange(len(y_score)), -np.asarray(y_score, dtype=np.float64)))
    gains = _gains(y_true, gain_mode)[order]
    ideal = np.sort(_gains(y_true, gain_mode))[::-1]
    idcg = _dcg(ideal, k)
    if idcg <= 0:
        return float("nan")
    return _dcg(gains, k) / idcg


def _gains(y_true: np.ndarray, gain_mode: str) -> np.ndarray:
    y = np.asarray(y_true, dtype=np.float64)
    if gain_mode == "binary":
        return (y > 0).astype(np.float64)
    return y.copy()


def mrr_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    if len(y_true) == 0:
        return float("nan")
    order = np.lexsort((np.arange(len(y_score)), -np.asarray(y_score, dtype=np.float64)))
    rel = np.asarray(y_true)[order][:k] > 0
    hits = np.flatnonzero(rel)
    return float(1.0 / (hits[0] + 1)) if len(hits) else 0.0


def recall_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    total = int(np.sum(np.asarray(y_true) > 0))
    if total == 0:
        return float("nan")
    order = np.lexsort((np.arange(len(y_score)), -np.asarray(y_score, dtype=np.float64)))
    return float(np.sum(np.asarray(y_true)[order][:k] > 0) / total)


def precision_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    if len(y_true) == 0:
        return float("nan")
    order = np.lexsort((np.arange(len(y_score)), -np.asarray(y_score, dtype=np.float64)))
    return float(np.sum(np.asarray(y_true)[order][:k] > 0) / min(k, len(y_true)))


def pairwise_accuracy(y_true: np.ndarray, y_score: np.ndarray,
                      tie_eps: float = 0.0) -> float:
    """可比较对中预测顺序正确的比例（分数并列不计入）。"""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_score = np.asarray(y_score, dtype=np.float64)
    n = len(y_true)
    if n < 2:
        return float("nan")
    correct = total = 0
    for i in range(n):
        for j in range(i + 1, n):
            if y_true[i] == y_true[j]:
                continue
            if abs(y_score[i] - y_score[j]) <= tie_eps:
                continue
            total += 1
            if (y_true[i] - y_true[j]) * (y_score[i] - y_score[j]) > 0:
                correct += 1
    return float(correct / total) if total else float("nan")


# ---------------------------------------------------------------- 组级评估
def relevance_from_labels(labels: list[str], spec: RelevanceSpec) -> np.ndarray:
    out = []
    for lab in labels:
        s = "" if lab is None else str(lab).strip()
        if s in ("unjudgeable", ""):
            out.append(float("nan"))
        else:
            out.append(float(s))
    return np.asarray(out, dtype=np.float64)


def evaluate_groups(group_ids: np.ndarray, scores: np.ndarray, relevance: np.ndarray,
                    ks: tuple[int, ...] = (5, 10),
                    spec: RelevanceSpec | None = None,
                    min_group_size: int = 2) -> dict:
    spec = spec or RelevanceSpec(kind="graded", label_source="unspecified")
    group_ids = np.asarray(group_ids)
    scores = np.asarray(scores, dtype=np.float64)
    relevance = np.asarray(relevance, dtype=np.float64)

    if not (len(group_ids) == len(scores) == len(relevance)):
        raise ValueError("group_ids / scores / relevance 长度不一致")

    results: list[GroupEval] = []
    skipped = {"too_small": 0, "no_relevance_labels": 0, "all_zero_relevance": 0,
               "nan_relevance_dropped": 0}
    uniq = sorted(set(group_ids.tolist()))
    for gid in uniq:
        mask = group_ids == gid
        g_rel = relevance[mask]
        g_score = scores[mask]
        keep = ~np.isnan(g_rel)
        skipped["nan_relevance_dropped"] += int((~keep).sum())
        g_rel, g_score = g_rel[keep], g_score[keep]
        n = len(g_rel)
        if n < min_group_size:
            skipped["too_small"] += 1
            results.append(GroupEval(str(gid), n, 0, skipped_reason="too_small"))
            continue
        n_rel = int(np.sum(g_rel > 0))
        if n_rel == 0:
            skipped["all_zero_relevance"] += 1
            results.append(GroupEval(str(gid), n, 0, skipped_reason="all_zero_relevance"))
            continue
        ge = GroupEval(str(gid), n, n_rel)
        for k in ks:
            ge.ndcg[k] = ndcg_at_k(g_rel, g_score, k, spec.gain_mode)
            ge.mrr[k] = mrr_at_k(g_rel, g_score, k)
            ge.recall[k] = recall_at_k(g_rel, g_score, k)
            ge.precision[k] = precision_at_k(g_rel, g_score, k)
        results.append(ge)

    def _agg(attr: str, k: int) -> dict:
        vals = [getattr(r, attr).get(k) for r in results
                if r.skipped_reason is None and k in getattr(r, attr)]
        vals = [v for v in vals if v is not None and not math.isnan(v)]
        if not vals:
            return {"mean": None, "n": 0}
        return {"mean": float(np.mean(vals)), "std": float(np.std(vals)),
                "n": len(vals)}

    metrics_block: dict[str, dict] = {}
    for k in ks:
        metrics_block[f"ndcg@{k}"] = _agg("ndcg", k)
        metrics_block[f"mrr@{k}"] = _agg("mrr", k)
        metrics_block[f"recall@{k}"] = _agg("recall", k)
        metrics_block[f"precision@{k}"] = _agg("precision", k)

    summary = {
        "relevance_spec": spec.to_dict(),
        "queries_total": len(uniq),
        "queries_evaluated": sum(1 for r in results if r.skipped_reason is None),
        "queries_skipped": skipped,
        "group_size": {
            "min": int(min((r.n_candidates for r in results), default=0)),
            "max": int(max((r.n_candidates for r in results), default=0)),
            "mean": float(np.mean([r.n_candidates for r in results])) if results else 0.0,
        },
        "metrics": metrics_block,
    }
    pa_values = []
    for r in results:
        if r.skipped_reason is not None:
            continue
        mask = group_ids == r.group_id
        g_rel = relevance[mask]
        g_score = scores[mask]
        keep = ~np.isnan(g_rel)
        pa_values.append(pairwise_accuracy(g_rel[keep], g_score[keep]))
    pa_values = [v for v in pa_values if not math.isnan(v)]
    summary["pairwise_accuracy"] = {
        "mean": float(np.mean(pa_values)) if pa_values else None,
        "std": float(np.std(pa_values)) if pa_values else None,
        "n": len(pa_values),
        "note": "组内可比较对（真实标签不同且预测不并列）上的顺序正确率",
    }
    return {"summary": summary, "per_group": results}
