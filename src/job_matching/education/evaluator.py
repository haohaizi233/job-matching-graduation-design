# -*- coding: utf-8 -*-
"""学历多标签任务的扩展评估（第四阶段 4.2 第五部分）。

在 metrics_classification.multilabel_metrics 之上补充：
  Hamming Loss、标签组合错误率、输入组级别评估、输入长度分桶、每标签 P/R/F1（继承）。
评估结果一律区分集合来源（伪标签开发集 vs 人工金标准），不得混用。
"""
from __future__ import annotations

import numpy as np

from ..metrics_classification import multilabel_metrics
from .labels import LABEL_ORDER

LENGTH_BUCKETS = [(0, 0, "len0"), (1, 2, "len1-2"), (3, 5, "len3-5"),
                  (6, 10, "len6-10"), (11, 10 ** 9, "len11+")]


def hamming_loss(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    yt, yp = np.asarray(y_true).astype(int), np.asarray(y_pred).astype(int)
    return float((yt != yp).mean()) if yt.size else 0.0


def _set_key(row) -> str:
    return "".join(str(int(x)) for x in row)


def group_level_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                        groups) -> dict:
    """输入组（同一学历表达）级别评估。

    group_macro_exact_match : 各组内 exact-match 率的等权平均（高频表达不再主导）
    group_modal_match_rate  : 预测众数标签集合 == 真实众数标签集合 的组占比
    """
    yt = np.asarray(y_true).astype(int)
    yp = np.asarray(y_pred).astype(int)
    g = np.asarray([str(x) for x in groups])
    em = np.all(yt == yp, axis=1).astype(float)
    keys, inv = np.unique(g, return_inverse=True)
    rates, modal_ok = [], 0
    for i in range(len(keys)):
        m = inv == i
        rates.append(float(em[m].mean()))
        true_keys = [_set_key(r) for r in yt[m]]
        pred_keys = [_set_key(r) for r in yp[m]]
        mt = max(set(true_keys), key=true_keys.count)
        mp = max(set(pred_keys), key=pred_keys.count)
        modal_ok += 1 if mt == mp else 0
    return {
        "groups": int(len(keys)),
        "group_macro_exact_match": round(float(np.mean(rates)), 6) if rates else 0.0,
        "group_modal_match_rate": round(modal_ok / len(keys), 6) if len(keys) else 0.0,
    }


def length_bucket_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                          lengths) -> dict:
    yt = np.asarray(y_true).astype(int)
    yp = np.asarray(y_pred).astype(int)
    L = np.asarray([int(x) for x in lengths])
    out = {}
    for lo, hi, name in LENGTH_BUCKETS:
        m = (L >= lo) & (L <= hi)
        if not m.any():
            out[name] = {"samples": 0, "exact_match_ratio": None}
            continue
        out[name] = {
            "samples": int(m.sum()),
            "exact_match_ratio": round(float(np.all(yt[m] == yp[m], axis=1).mean()), 6),
            "micro_f1": multilabel_metrics(yt[m], yp[m], LABEL_ORDER)["micro_f1"],
        }
    return out


def education_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                      texts=None, groups=None, lengths=None) -> dict:
    """完整指标包：基础多标签指标 + Hamming + 组合错误率 + 分组/分桶。"""
    yt = np.asarray(y_true).astype(int)
    yp = np.asarray(y_pred).astype(int)
    m = multilabel_metrics(yt, yp, LABEL_ORDER)
    m["hamming_loss"] = round(hamming_loss(yt, yp), 6)
    m["label_combo_error_rate"] = round(1.0 - m["exact_match_ratio"], 6)
    m["empty_pred_samples"] = int((yp.sum(axis=1) == 0).sum())
    m["pred_label_combo_count"] = int(len({_set_key(r) for r in yp}))
    if groups is not None:
        m["group_level"] = group_level_metrics(yt, yp, groups)
    if lengths is not None:
        m["length_buckets"] = length_bucket_metrics(yt, yp, lengths)
    return m
