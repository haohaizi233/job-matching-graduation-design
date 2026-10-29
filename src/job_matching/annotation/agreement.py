# -*- coding: utf-8 -*-
"""标注一致性分析（协议第五节 / 测试场景 7）。

指标：原始一致率、Cohen's Kappa、Weighted Kappa（线性/二次，有序标签 0<1<2）、
分歧样本统计、按岗位类别一致性。

硬性规则：
  * 只在「双方都给出可判定标签（0/1/2）」的样本上计算 κ；
  * unjudgeable 单独统计，不参与 κ，也不视为 0；
  * 单人标注 / 无重叠样本 / 期望一致率退化 / 类别样本量 < 5 时，
    输出 status="not_computable" 与 reason，绝不填充任何数值。
"""
from __future__ import annotations

from collections import Counter

from .schema import RELEVANCE_ORDERED

MIN_SAMPLES_FOR_KAPPA = 5
NOT_COMPUTABLE = "not_computable"


def paired_labels(rows_a: list[dict], rows_b: list[dict]) -> list[dict]:
    """两个标注员在相同 pair 上的配对标签（按 pair_id 排序，确定性）。"""
    a = {r["pair_id"]: r for r in rows_a}
    b = {r["pair_id"]: r for r in rows_b}
    out = []
    for pid in sorted(set(a) & set(b)):
        out.append({"pair_id": pid,
                    "a": str(a[pid]["relevance"]), "b": str(b[pid]["relevance"]),
                    "annotator_a": a[pid]["annotator_id"], "annotator_b": b[pid]["annotator_id"]})
    return out


def _judgeable(pairs: list[dict]) -> list[dict]:
    return [p for p in pairs if p["a"] in RELEVANCE_ORDERED and p["b"] in RELEVANCE_ORDERED]


def raw_agreement(pairs: list[dict]) -> dict:
    """原始一致率（只算双方可判定样本）。"""
    j = _judgeable(pairs)
    if not j:
        return {"status": NOT_COMPUTABLE, "reason": "no_judgeable_overlap",
                "n_paired": len(pairs), "n_judgeable": 0, "agreements": 0, "value": None}
    agree = sum(1 for p in j if p["a"] == p["b"])
    return {"status": "ok", "n_paired": len(pairs), "n_judgeable": len(j),
            "agreements": agree, "value": round(agree / len(j), 6),
            "both_unjudgeable": sum(1 for p in pairs if p["a"] == p["b"] == "unjudgeable"),
            "one_side_unjudgeable": sum(1 for p in pairs
                                        if (p["a"] == "unjudgeable") != (p["b"] == "unjudgeable"))}


def _confusion(pairs: list[dict], values=RELEVANCE_ORDERED) -> list[list[int]]:
    idx = {v: i for i, v in enumerate(values)}
    m = [[0] * len(values) for _ in values]
    for p in pairs:
        if p["a"] in idx and p["b"] in idx:
            m[idx[p["a"]]][idx[p["b"]]] += 1
    return m


def cohens_kappa(pairs: list[dict], values=RELEVANCE_ORDERED) -> dict:
    j = _judgeable(pairs)
    if len(j) < MIN_SAMPLES_FOR_KAPPA:
        return {"status": NOT_COMPUTABLE,
                "reason": f"judgeable_samples<{MIN_SAMPLES_FOR_KAPPA}",
                "n": len(j), "value": None}
    m = _confusion(j, values)
    n = float(sum(sum(r) for r in m))
    po = sum(m[i][i] for i in range(len(values))) / n
    pa = [sum(m[i]) / n for i in range(len(values))]            # 行边际（标注员 A）
    pb = [sum(m[i][j] for i in range(len(values))) / n
          for j in range(len(values))]                           # 列边际（标注员 B）
    pe = sum(x * y for x, y in zip(pa, pb))
    if pe >= 1.0 - 1e-12:
        return {"status": NOT_COMPUTABLE, "reason": "degenerate_distribution",
                "n": int(n), "value": None}
    value = (po - pe) / (1.0 - pe)
    return {"status": "ok", "n": int(n), "po": round(po, 6), "pe": round(pe, 6),
            "value": round(float(value), 6)}


def weighted_kappa(pairs: list[dict], weights: str = "linear",
                   values=RELEVANCE_ORDERED) -> dict:
    """有序标签加权 Kappa。weights: linear | quadratic。

    权重口径与 sklearn.metrics.cohen_kappa_score(weights=...) 一致：
    w[i][j] 为**不一致权重**（对角线为 0），线性 w = |i-j|/(k-1)，
    二次 w = ((i-j)/(k-1))^2，最终 κ = 1 - Σw_ij·p_ij / Σw_ij·p_i·p_.j。
    """
    j = _judgeable(pairs)
    if len(j) < MIN_SAMPLES_FOR_KAPPA:
        return {"status": NOT_COMPUTABLE,
                "reason": f"judgeable_samples<{MIN_SAMPLES_FOR_KAPPA}",
                "n": len(j), "value": None, "weights": weights}
    k = len(values)
    if k < 2:
        return {"status": NOT_COMPUTABLE, "reason": "degenerate_label_set",
                "n": len(j), "value": None, "weights": weights}
    if weights == "linear":
        w = [[abs(i - j_) / (k - 1) for j_ in range(k)] for i in range(k)]
    elif weights == "quadratic":
        w = [[((i - j_) / (k - 1)) ** 2 for j_ in range(k)] for i in range(k)]
    else:
        raise ValueError(f"未知权重类型: {weights}")
    m = _confusion(j, values)
    n = float(sum(sum(r) for r in m))
    pa = [sum(m[i]) / n for i in range(k)]                        # 行边际（标注员 A）
    pb = [sum(m[i][j_] for i in range(k)) / n for j_ in range(k)]  # 列边际（标注员 B）
    num = sum(w[i][j_] * (m[i][j_] / n) for i in range(k) for j_ in range(k))
    den = sum(w[i][j_] * pa[i] * pb[j_] for i in range(k) for j_ in range(k))
    if den <= 0:
        return {"status": NOT_COMPUTABLE, "reason": "degenerate_distribution",
                "n": int(n), "value": None, "weights": weights}
    value = 1.0 - num / den
    return {"status": "ok", "n": int(n), "value": round(float(value), 6), "weights": weights}


def disagreement_detail(pairs: list[dict]) -> list[dict]:
    """分歧样本（含 unjudgeable vs 数值）。"""
    out = []
    for p in pairs:
        if p["a"] != p["b"]:
            out.append({"pair_id": p["pair_id"], "annotator_a": p["annotator_a"],
                        "annotator_b": p["annotator_b"],
                        "relevance_a": p["a"], "relevance_b": p["b"]})
    return out


def agreement_report(rows_a: list[dict], rows_b: list[dict],
                     pair_meta: dict[str, dict] | None = None) -> dict:
    """完整一致性报告（协议第五节）。"""
    pair_meta = pair_meta or {}
    if not rows_a or not rows_b:
        return {
            "status": NOT_COMPUTABLE,
            "reason": "single_annotator" if (bool(rows_a) != bool(rows_b)) else "no_annotations",
            "annotators": sorted({r["annotator_id"] for r in rows_a + rows_b}),
            "note": "缺少双人标注，一致性指标不可计算；不填充任何数值",
        }
    pairs = paired_labels(rows_a, rows_b)
    annotators = sorted({str(r["annotator_id"]) for r in rows_a} |
                        {str(r["annotator_id"]) for r in rows_b})
    if len(annotators) < 2:
        return {"status": NOT_COMPUTABLE, "reason": "single_annotator",
                "annotators": annotators,
                "note": "单人标注，一致性指标不可计算"}
    if not pairs:
        return {"status": NOT_COMPUTABLE, "reason": "no_overlapping_pairs",
                "annotators": annotators,
                "note": "两位标注员没有共同样本，一致性指标不可计算"}

    categories: dict[str, list[dict]] = {}
    for p in pairs:
        cat = str((pair_meta.get(p["pair_id"]) or {}).get("job_category", "UNKNOWN"))
        categories.setdefault(cat, []).append(p)

    per_category = {}
    for cat in sorted(categories):
        sub = categories[cat]
        entry = {"n_paired": len(sub), "n_judgeable": len(_judgeable(sub))}
        if len(sub) < MIN_SAMPLES_FOR_KAPPA:
            entry.update({"status": "insufficient_evidence",
                          "reason": f"n_paired<{MIN_SAMPLES_FOR_KAPPA}",
                          "raw_agreement": None, "cohens_kappa": None,
                          "weighted_kappa_linear": None})
        else:
            entry.update({
                "status": "ok",
                "raw_agreement": raw_agreement(sub).get("value"),
                "cohens_kappa": cohens_kappa(sub).get("value"),
                "weighted_kappa_linear": weighted_kappa(sub, "linear").get("value"),
            })
        per_category[cat] = entry

    return {
        "status": "ok",
        "annotators": annotators,
        "n_paired": len(pairs),
        "n_judgeable": len(_judgeable(pairs)),
        "raw_agreement": raw_agreement(pairs),
        "cohens_kappa": cohens_kappa(pairs),
        "weighted_kappa_linear": weighted_kappa(pairs, "linear"),
        "weighted_kappa_quadratic": weighted_kappa(pairs, "quadratic"),
        "label_distribution_a": dict(Counter(p["a"] for p in pairs)),
        "label_distribution_b": dict(Counter(p["b"] for p in pairs)),
        "disagreements": disagreement_detail(pairs),
        "n_disagreements": len(disagreement_detail(pairs)),
        "per_category": per_category,
    }
