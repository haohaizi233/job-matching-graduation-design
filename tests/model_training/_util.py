# -*- coding: utf-8 -*-
"""第四阶段 4.1 模型训练/推理测试公共工具（stdlib unittest，不引入 pytest）。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
SCRIPTS_MT = ROOT / "scripts" / "model_training"
for _p in (str(SRC), str(SCRIPTS_MT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RUNS_ROOT = ROOT / "models" / "matching"
SPLITS_DIR = ROOT / "data" / "splits" / "matching"
LOG_DIR = ROOT / "reports" / "model-training" / "logs"

NUMERIC_COLS = ["skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
                "both_skills_empty", "position_token_overlap", "category_match",
                "years_experience"]
CATEGORICAL_COLS = ["target_position_norm", "inferred_category", "job_category"]
SYNTH_COLS = NUMERIC_COLS + CATEGORICAL_COLS + [
    "candidate_id", "job_id", "final_score", "label_strength", "label_ordinal"]


def jload(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def all_run_dirs(model: str | None = None, include_smoke: bool = False) -> list[Path]:
    out = []
    for mdir in sorted(RUNS_ROOT.glob(f"{model or '*'}/*")):
        for run in sorted(mdir.iterdir()):
            if not (run / "manifest.json").exists():
                continue
            if not include_smoke and ("-smoke" in run.name):
                continue
            out.append(run)
    return out


def any_run_dir(model: str | None = None) -> Path | None:
    runs = all_run_dirs(model) or all_run_dirs(model, include_smoke=True)
    return runs[0] if runs else None


def synthetic_frame(n_groups: int = 6, per_group: int = 5, seed: int = 7) -> pd.DataFrame:
    """构造最小合法 pair 表（含特征列与评估所需的目标列），仅用于测试。"""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_groups):
        for k in range(per_group):
            rows.append({
                "candidate_id": f"cand_{g:03d}",
                "job_id": 1000 + g * 10 + k,
                "skill_jaccard": float(rng.random()),
                "skill_overlap_ratio_cv": float(rng.random()),
                "skill_overlap_ratio_job": float(rng.random()),
                "both_skills_empty": float(rng.integers(0, 2)),
                "position_token_overlap": float(rng.random()),
                "category_match": float(rng.integers(0, 2)),
                "years_experience": float(rng.integers(0, 12)),
                "target_position_norm": ["软件工程师", "数据分析师", "产品经理"][g % 3],
                "inferred_category": ["INFORMATION-TECHNOLOGY", "FINANCE", "OTHER"][g % 3],
                "job_category": ["INFORMATION-TECHNOLOGY", "FINANCE", "OTHER"][(g + k) % 3],
                "final_score": float(rng.random()),
                "label_strength": ["weak_positive", "medium_positive", "strong_positive"][k % 3],
                "label_ordinal": float((k % 3) + 1),
            })
    return pd.DataFrame(rows, columns=SYNTH_COLS)
