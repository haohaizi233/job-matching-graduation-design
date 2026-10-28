# -*- coding: utf-8 -*-
"""模型产物保存 / 加载与运行清单（第四阶段 4.1 / 十一）。

每个实验目录 models/matching/<model>/<protocol>/<run_id>/ 固定包含：
  model.pkl | model.pt        模型权重/文件
  feature_map.json            特征映射（含 train 拟合的词表与统计量）
  config.json                 训练配置快照（模型 + 公共配置）
  metrics.json                validation/test 指标摘要
  manifest.json               数据版本 / 切分协议 / 特征 Schema 哈希 / 训练时间等
  history.json                逐 epoch 训练历史（仅 torch 模型）
不同 run_id 目录互不覆盖。
"""
from __future__ import annotations

import json
import platform
import time
from pathlib import Path

from ..core import ROOT, jdump, rel, sha256_file


def run_id(model_name: str, protocol: str, tag: str = "") -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    return f"{model_name}-{protocol}-{ts}" + (f"-{tag}" if tag else "")


def run_dir_for(model_name: str, protocol: str, rid: str,
                models_root: Path | None = None) -> Path:
    base = Path(models_root or ROOT / "models" / "matching")
    d = base / model_name / protocol / rid
    d.mkdir(parents=True, exist_ok=True)
    return d


def environment_info() -> dict:
    import numpy as np
    import pandas as pd
    import sklearn
    import torch
    info = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "sklearn": sklearn.__version__,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
    }
    if torch.cuda.is_available():
        info["gpu"] = torch.cuda.get_device_name(0)
        info["gpu_total_memory_mb"] = round(
            torch.cuda.get_device_properties(0).total_memory / (1024 ** 2))
    return info


def write_manifest(run_dir: Path, *, run_id_: str, model_name: str, protocol: str,
                   dataset_version: str, feature_map_summary: dict,
                   rows: dict, params_count: int, seed: int,
                   seconds: float, extra: dict | None = None) -> dict:
    feature_schema = ROOT / "data/processed/matching/feature_schema.json"
    split_manifest = ROOT / "data/splits/matching" / protocol / "manifest.json"
    artifacts = []
    for p in sorted(Path(run_dir).iterdir()):
        if p.is_file():
            artifacts.append({"path": p.name, "bytes": p.stat().st_size,
                              "sha256": sha256_file(p)})
    manifest = {
        "generated_by": "scripts/model_training/train.py",
        "pipeline_version": "phase4-matching-v1",
        "run_id": run_id_,
        "model_name": model_name,
        "protocol": protocol,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_version": dataset_version,
        "feature_schema_file": rel(feature_schema),
        "feature_schema_sha256": sha256_file(feature_schema) if feature_schema.exists() else None,
        "split_manifest_file": rel(split_manifest),
        "split_manifest_sha256": sha256_file(split_manifest) if split_manifest.exists() else None,
        "feature_map": feature_map_summary,
        "rows": rows,
        "model_parameters": params_count,
        "seed": seed,
        "training_seconds": round(seconds, 2),
        "environment": environment_info(),
        "inference": {
            "interface": "predict_score(resume, job) -> float; rank_jobs(resume, jobs) -> list",
            "supports_cpu": True,
            "requires_labels": False,
            "forbidden_inputs": ["final_score", "raw_score", "candidate_rank",
                                 "candidate_rank_pct", "label_strength",
                                 "semantic_score", "skill_score", "position_score",
                                 "category_score", "experience_score", "education_score"],
        },
        "artifacts": artifacts,
    }
    if extra:
        manifest.update(extra)
    jdump(manifest, Path(run_dir) / "manifest.json")
    return manifest


def save_config_snapshot(run_dir: Path, model_config: dict, common_config: dict) -> Path:
    return jdump({"model": model_config, "common": common_config},
                 Path(run_dir) / "config.json")


def read_run_record(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
