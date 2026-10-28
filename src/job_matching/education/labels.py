# -*- coding: utf-8 -*-
"""标签词表与多热编码的统一入口（薄封装，实现在 preprocess_education / config）。"""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..preprocess_education import (encode_multi_hot, multi_hot_to_tokens,
                                    normalize_label)

LABEL_ORDER: list[str] = get_config().label_order


def label_names() -> list[str]:
    return list(LABEL_ORDER)


def tokens_to_multi_hot(token_lists: list[list[str]]) -> np.ndarray:
    """token 列表 -> (n, 6) 0/1 矩阵，列顺序 = label_order。"""
    return encode_multi_hot(token_lists).astype(np.int8)


def multi_hot_matrix_from_strings(values) -> np.ndarray:
    """从 "001010" 形式的定宽字符串恢复多热矩阵（前导 0 必须保留）。"""
    out = np.zeros((len(values), len(LABEL_ORDER)), dtype=np.int8)
    for r, v in enumerate(values):
        s = str(v)
        if len(s) != len(LABEL_ORDER):
            raise ValueError(f"label_multi_hot 宽度异常: {s!r}")
        out[r, :] = [1 if c == "1" else 0 for c in s]
    return out


def multi_hot_matrix_to_strings(mat: np.ndarray) -> list[str]:
    return ["".join(str(int(x)) for x in row) for row in np.asarray(mat)]
