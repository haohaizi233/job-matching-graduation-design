# -*- coding: utf-8 -*-
"""Embedding 工程化缓存（第三阶段 3.1.5）。

要求：
  * 不修改原始 Embedding，不调用在线编码 API，不重新归一化；
  * NumPy float32 数组 + 明确 ID -> 行号映射 + 元数据 JSON + 文件哈希；
  * 从缓存读回后与原始数据逐元素一致性校验（bit 级）；
  * 不把 candidate_id / job_id 的整数形式当模型特征。
"""
from __future__ import annotations

import ast
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .core import (PIPELINE_VERSION, get_logger, jdump, rel, sha256_array,
                   sha256_file)

DIM = 768

LIMITATIONS = [
    "预计算 embedding 的编码模型未知（数据集卡片明确声明未指定），不得仅凭 768 维推断模型。",
    "编码输入是 resume_text / job_description 原文还是清洗后文本，未知。",
    "单塔（共享编码器）还是双塔（两个编码器），数据不提供判别依据。",
    "semantic_score = 0.5 * cosine(cv_emb, job_emb) + 0.5（审计以 R²=1.0 证实），"
    "故 embedding 经 semantic_score -> raw_score -> final_score -> label_strength "
    "参与了标签生成，属于派生信息链的一环。",
    "后续 '冷启动' 实验只能表示下游排序模型未使用这些候选人/岗位做监督训练，"
    "不能宣称预训练编码器从未见过相关文本。",
    "向量由全量数据产生，其归一化统计不得再用全量数据重复拟合（间接泄漏规则 IL-6）。",
]


def parse_embedding(s) -> np.ndarray | None:
    """把字符串化向量还原成 float32 ndarray；失败返回 None。"""
    t = str(s).strip()
    if not t or t.lower() in ("nan", "none"):
        return None
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


def _build_side(csv_path: Path, id_col: str, out_dir: Path, side: str) -> dict:
    log = get_logger()
    t0 = time.time()
    df = pd.read_csv(csv_path, usecols=[id_col, "embedding"], encoding="utf-8-sig",
                     low_memory=False)
    n = len(df)
    arr = np.zeros((n, DIM), dtype=np.float32)
    bad: list[int] = []
    for i, s in enumerate(df["embedding"].to_numpy()):
        v = parse_embedding(s)
        if v is None or v.size != DIM:
            bad.append(i)
            continue
        arr[i, :] = v
    if bad:
        raise ValueError(f"{side}: {len(bad)} 行向量解析失败或维度不是 {DIM}")

    ids = df[id_col].astype(str).tolist()
    if len(set(ids)) != len(ids):
        raise ValueError(f"{side}: {id_col} 不是唯一键，无法建立 1:1 ID 映射")

    npy_path = out_dir / f"{side}_embeddings.npy"
    map_path = out_dir / f"{side}_id_map.json"
    np.save(npy_path, arr)
    jdump({"id_to_row": {k: i for i, k in enumerate(ids)},
           "row_to_id": ids,
           "id_column": id_col,
           "rows": n}, map_path)

    norms = np.linalg.norm(arr, axis=1)
    info = {
        "side": side,
        "source_csv": rel(csv_path),
        "source_csv_sha256": sha256_file(csv_path),
        "rows": n,
        "dim": DIM,
        "dtype": "float32",
        "npy": rel(npy_path),
        "npy_sha256": sha256_file(npy_path),
        "array_sha256": sha256_array(arr),
        "id_map": rel(map_path),
        "id_map_sha256": sha256_file(map_path),
        "id_column": id_col,
        "all_finite": bool(np.isfinite(arr).all()),
        "zero_vectors": int((np.linalg.norm(arr, axis=1) == 0).sum()),
        "l2_norm_min": float(norms.min()),
        "l2_norm_max": float(norms.max()),
        "l2_norm_mean": float(norms.mean()),
        "l2_norm_std": float(norms.std()),
        "component_std": float(arr.std()),
        "duplicate_vectors": int(n - len({arr[i].tobytes() for i in range(n)})),
        "build_seconds": round(time.time() - t0, 2),
    }
    log.info("[embedding] %s: %d x %d float32, 范数 %.6f±%.6f, 全有限=%s",
             side, n, DIM, info["l2_norm_mean"], info["l2_norm_std"], info["all_finite"])
    return info


def build_embedding_cache(cv_path: Path, job_path: Path, out_dir: Path,
                          dataset_ver: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_info = _build_side(cv_path, "candidate_id", out_dir, "cv")
    job_info = _build_side(job_path, "job_id", out_dir, "job")

    meta = {
        "generated_by": "src/job_matching/embeddings.py",
        "pipeline_version": PIPELINE_VERSION,
        "data_version": dataset_ver,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dim": DIM,
        "dtype": "float32",
        "sides": {"cv": cv_info, "job": job_info},
        "normalization_policy": "沿用原始向量的 L2 归一化状态，不做任何重新归一化",
        "id_mapping_policy": "id_map.json 提供 id->row 与 row->id 双向可逆索引",
        "id_as_feature": "禁止：candidate_id / job_id 的整数形式不得作为模型特征",
        "limitations": LIMITATIONS,
    }
    jdump(meta, out_dir / "metadata.json")
    return meta


# ------------------------------------------------------------------ 一致性校验
def verify_embedding_cache(out_dir: Path, cv_path: Path, job_path: Path,
                           sample_rows: int = 64, seed: int = 20261028) -> dict:
    """从缓存读回后与原始 CSV 逐元素比对（bit 级），并校验 ID 映射可逆。"""
    out: dict = {"ok": True, "checks": []}
    rng = np.random.default_rng(seed)

    for side, csv_path, id_col in (("cv", cv_path, "candidate_id"),
                                   ("job", job_path, "job_id")):
        arr = np.load(out_dir / f"{side}_embeddings.npy")
        idmap = __import__("json").loads((out_dir / f"{side}_id_map.json").read_text("utf-8"))
        rows = idmap["row_to_id"]
        assert arr.shape[0] == len(rows), f"{side}: 行数与 ID 映射不一致"
        assert arr.dtype == np.float32, f"{side}: dtype 不是 float32"

        # 可逆性
        rev_ok = all(idmap["id_to_row"][k] == i for i, k in enumerate(rows))

        # 抽样与原始 CSV 比对
        idx = rng.choice(arr.shape[0], size=min(sample_rows, arr.shape[0]), replace=False)
        idx = sorted(int(i) for i in idx)
        raw = pd.read_csv(csv_path, usecols=[id_col, "embedding"], encoding="utf-8-sig",
                          low_memory=False)
        raw_ids = raw[id_col].astype(str).tolist()
        raw_map = {k: i for i, k in enumerate(raw_ids)}
        max_diff = 0.0
        id_mismatch = 0
        for i in idx:
            want = parse_embedding(raw["embedding"].iloc[raw_map[rows[i]]])
            d = float(np.max(np.abs(arr[i] - want)))
            max_diff = max(max_diff, d)
            if raw_map.get(rows[i]) is None:
                id_mismatch += 1

        # 全量有限性与维度
        finite = bool(np.isfinite(arr).all())
        dim_ok = arr.shape[1] == DIM

        ok = (rev_ok and max_diff == 0.0 and id_mismatch == 0 and finite and dim_ok)
        out["ok"] = out["ok"] and ok
        out["checks"].append({
            "side": side, "rows": int(arr.shape[0]), "dim": int(arr.shape[1]),
            "id_map_reversible": rev_ok, "sample_rows_compared": len(idx),
            "max_abs_diff_vs_source": max_diff, "id_not_in_source": id_mismatch,
            "all_finite": finite, "dim_ok": dim_ok, "ok": ok,
        })
    return out
