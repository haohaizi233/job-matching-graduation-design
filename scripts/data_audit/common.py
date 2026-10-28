# -*- coding: utf-8 -*-
"""data_audit 公共工具：路径解析、分块读取、统计与 JSON 写出。

设计约束：
  * 只读 data/raw，绝不写入；
  * 大文件一律分块处理，内存占用恒定；
  * 不把简历全文/联系方式等敏感内容写进任何输出。
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "reports" / "data-audit"

SRC_JOB_MATCH = RAW / "job-resume-matching"
SRC_JOB_EDU = RAW / "job-education"
SRC_OTHER = RAW / "other"

CV = SRC_JOB_MATCH / "cv.csv"
JOB = SRC_JOB_MATCH / "job.csv"
MATCHES = SRC_JOB_MATCH / "matches.csv"
EDU_TRAIN = SRC_JOB_EDU / "default" / "train" / "19w_0701.csv"
EDU_VAL = SRC_JOB_EDU / "default" / "validation" / "4w_0708.csv"
EDU_TEST = SRC_JOB_EDU / "default" / "test" / "2w_0716.csv"
EDU_ANNOT = SRC_JOB_EDU / "annotated" / "2w_0716_eval.csv"
RISK = SRC_OTHER / "all_df.csv" / "all_df.csv"

FEATS = ["semantic_score", "skill_score", "position_score",
         "category_score", "experience_score", "education_score"]


# ---------------------------------------------------------------- 基础工具
def ensure_out() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT


def rel(p: Path) -> str:
    """相对项目根的路径，统一用 / 分隔，便于跨平台阅读。"""
    return str(p.relative_to(ROOT)).replace("\\", "/")


def file_meta(p: Path) -> dict:
    size = p.stat().st_size
    with open(p, "rb") as f:
        head = f.read(3)
    return {
        "path": rel(p),
        "abs_path": str(p),
        "bytes": size,
        "mb": round(size / 1048576.0, 3),
        "encoding": "UTF-8 (BOM)" if head == b"\xef\xbb\xbf" else "UTF-8",
    }


def sha256_head(p: Path, nbytes: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read(nbytes))
    return h.hexdigest()


def jdump(obj, path: Path) -> None:
    ensure_out()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_json_default)
    print("已写出 %s" % rel(path), file=sys.stderr)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)


# ---------------------------------------------------------------- 统计工具
def quantiles(s: pd.Series, qs=(0, 1, 5, 25, 50, 75, 95, 99, 100)) -> dict:
    v = pd.to_numeric(s, errors="coerce").dropna().to_numpy(dtype=float)
    if v.size == 0:
        return {}
    return {("p%g" % q): round(float(np.percentile(v, q)), 6) for q in qs}


def num_summary(s: pd.Series) -> dict:
    v = pd.to_numeric(s, errors="coerce")
    n = int(v.notna().sum())
    if n == 0:
        return {"count": 0}
    return {
        "count": n,
        "missing": int(v.isna().sum()),
        "missing_pct": round(float(v.isna().mean()) * 100, 4),
        "unique": int(v.nunique(dropna=True)),
        "min": float(v.min()),
        "max": float(v.max()),
        "mean": float(v.mean()),
        "std": float(v.std()),
        "quantiles": quantiles(v),
    }


def text_len_summary(s: pd.Series) -> dict:
    L = s.astype(str).str.len()
    return {
        "rows": int(len(L)),
        "min": int(L.min()) if len(L) else 0,
        "p25": int(L.quantile(0.25)) if len(L) else 0,
        "median": int(L.median()) if len(L) else 0,
        "p75": int(L.quantile(0.75)) if len(L) else 0,
        "max": int(L.max()) if len(L) else 0,
        "mean": round(float(L.mean()), 1) if len(L) else 0,
        "empty_or_tiny_len_le3": int((L <= 3).sum()),
    }


def value_counts(s: pd.Series, top: int = 20) -> dict:
    vc = s.astype(str).value_counts(dropna=False).head(top)
    return {str(k): int(v) for k, v in vc.items()}


def column_profile(df: pd.DataFrame, text_cols=(), id_cols=()) -> dict:
    out = {}
    for c in df.columns:
        item = {
            "dtype": str(df[c].dtype),
            "missing": int(df[c].isna().sum()),
            "missing_pct": round(float(df[c].isna().mean()) * 100, 4),
            "unique": int(df[c].nunique(dropna=True)),
        }
        if c in text_cols:
            # 不写入任何原始文本片段（简历/联系方式/公司信息等敏感内容），
            # 只保留长度分布与（当基数很低时的）取值计数。
            item["text_len"] = text_len_summary(df[c])
            nu = int(df[c].nunique(dropna=True))
            if nu <= 30:
                item["value_counts_top"] = value_counts(df[c], 30)
            item["sample_head"] = None
        elif c in id_cols:
            item["is_unique"] = bool(df[c].is_unique)
            item["duplicated_rows"] = int(df[c].duplicated().sum())
        elif pd.api.types.is_numeric_dtype(df[c]):
            item["numeric"] = num_summary(df[c])
        else:
            item["value_counts_top"] = value_counts(df[c], 15)
        out[c] = item
    return out


# ---------------------------------------------------------------- 文本规整
_WS = re.compile(r"\s+")


def norm_text(s) -> str:
    return _WS.sub(" ", str(s)).strip()


def parse_list(s):
    """把 clean_skills 这类字符串化列表还原成 list[str]；失败返回 None。"""
    try:
        v = ast.literal_eval(str(s))
    except Exception:
        return None
    return v if isinstance(v, list) else None


def skill_set(s) -> set:
    v = parse_list(s)
    if v is None:
        return set()
    return {str(x).strip().lower() for x in v if str(x).strip()}


def parse_embedding(s):
    """把字符串化向量还原成 np.ndarray(float32)；失败返回 None。"""
    t = str(s).strip()
    try:
        a = np.fromstring(t.strip("[]"), sep=",", dtype=np.float32)
        if a.size:
            return a
    except Exception:
        pass
    try:
        v = ast.literal_eval(t)
        return np.asarray(v, dtype=np.float32).ravel()
    except Exception:
        return None


# ---------------------------------------------------------------- 分块读取
def read_chunks(path: Path, usecols=None, chunksize=20000):
    return pd.read_csv(path, usecols=usecols, chunksize=chunksize,
                       encoding="utf-8-sig", low_memory=False)


def count_rows(path: Path) -> int:
    n = 0
    for ch in read_chunks(path, usecols=[0]):
        n += len(ch)
    return n


def timed(fn):
    def wrapper(*a, **kw):
        t0 = time.time()
        r = fn(*a, **kw)
        print("[%s] 耗时 %.1fs" % (fn.__name__, time.time() - t0), file=sys.stderr)
        return r
    return wrapper
