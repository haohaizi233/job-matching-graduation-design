# -*- coding: utf-8 -*-
"""门禁测试公共工具：路径、读取、断言助手。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_matching.config import get_config  # noqa: E402
from job_matching.core import sha256_file  # noqa: E402


def cfg():
    return get_config()


def jload(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def read_csv(p: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(p, encoding="utf-8", low_memory=False, **kw)


def read_csv_sig(p: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(p, encoding="utf-8-sig", low_memory=False, **kw)


def set_json(arr) -> set:
    return set(json.loads(x) if isinstance(x, str) else list(x) for x in arr)


def to_float_array(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return df[cols].to_numpy(dtype=np.float64)


def file_hash(p: Path) -> str:
    return sha256_file(p)
