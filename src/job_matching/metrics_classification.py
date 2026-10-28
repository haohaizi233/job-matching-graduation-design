# -*- coding: utf-8 -*-
"""多标签分类评估指标（第三阶段 3.3.3）。

严格区分伪标签验证集合与人工金标准测试集合，输出中必须带集合名与标签来源。
"""
from __future__ import annotations

import numpy as np


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": round(p, 6), "recall": round(r, 6), "f1": round(f, 6),
            "support": int(tp + fn), "predicted": int(tp + fp)}


def multilabel_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                       label_names: list[str]) -> dict:
    """y_true / y_pred: (n, L) 0/1 矩阵。"""
    yt = np.asarray(y_true).astype(int)
    yp = np.asarray(y_pred).astype(int)
    if yt.shape != yp.shape:
        raise ValueError(f"形状不一致: {yt.shape} vs {yp.shape}")
    n, L = yt.shape

    exact = float(np.mean(np.all(yt == yp, axis=1))) if n else 0.0

    tp = int(((yt == 1) & (yp == 1)).sum())
    fp = int(((yt == 0) & (yp == 1)).sum())
    fn = int(((yt == 1) & (yp == 0)).sum())
    tn = int(((yt == 0) & (yp == 0)).sum())
    micro = _prf(tp, fp, fn)

    per_class = {}
    f1s = []
    for i, name in enumerate(label_names):
        m = _prf(int(((yt[:, i] == 1) & (yp[:, i] == 1)).sum()),
                 int(((yt[:, i] == 0) & (yp[:, i] == 1)).sum()),
                 int(((yt[:, i] == 1) & (yp[:, i] == 0)).sum()))
        per_class[name] = m
        if m["support"] > 0:
            f1s.append(m["f1"])
    macro_f1 = round(float(np.mean(f1s)), 6) if f1s else 0.0

    # 错误类型分布
    err = {
        "exact_match": int(np.all(yt == yp, axis=1).sum()),
        "missing_label_only": int(((yt.sum(1) > yp.sum(1)) & np.any(yt > yp, axis=1)).sum()),
        "extra_label_only": int(((yp.sum(1) > yt.sum(1)) & np.any(yp > yt, axis=1)).sum()),
        "substitution": int((((yp.sum(1) == yt.sum(1)) & np.any(yt != yp, axis=1))).sum()),
        "empty_pred_nonempty_true": int(((yp.sum(1) == 0) & (yt.sum(1) > 0)).sum()),
    }
    err["total_wrong"] = int(n - err["exact_match"])

    return {
        "samples": int(n),
        "labels": list(label_names),
        "exact_match_ratio": round(exact, 6),
        "micro_precision": micro["precision"],
        "micro_recall": micro["recall"],
        "micro_f1": micro["f1"],
        "macro_f1": macro_f1,
        "per_label": per_class,
        "confusion_counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "error_types": err,
    }
