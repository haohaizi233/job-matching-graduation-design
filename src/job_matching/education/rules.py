# -*- coding: utf-8 -*-
"""规则基线 / 经验映射基线的统一入口（实现在 baseline_education，不重复实现）。"""
from __future__ import annotations

import numpy as np

from ..baseline_education import (empirical_predict, empirical_slot_mapping,
                                  expand_all_levels_ge, rule_predict)
from .labels import LABEL_ORDER, tokens_to_multi_hot


def rule_labels(texts) -> np.ndarray:
    """规则基线批量预测 -> (n, 6) 多热矩阵。"""
    return tokens_to_multi_hot([rule_predict(t)["tokens"] for t in texts])


def empirical_labels_from_mapping(texts, mapping: dict) -> np.ndarray:
    """经验映射批量预测（未命中的表达回退规则基线）。"""
    return tokens_to_multi_hot([empirical_predict(t, mapping)["tokens"] for t in texts])


__all__ = ["rule_predict", "empirical_predict", "empirical_slot_mapping",
           "expand_all_levels_ge", "rule_labels", "empirical_labels_from_mapping"]

