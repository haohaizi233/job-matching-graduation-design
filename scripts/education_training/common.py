# -*- coding: utf-8 -*-
"""第四阶段 4.2 训练脚本公共工具：日志、数据准备、评估、运行记录。"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT, ensure_dir, jdump, rel  # noqa: E402
from job_matching.education.dataset import (conflict_aware_weights, high_confidence_subset,  # noqa: E402
                                            load_dev_sets, load_split_frame,
                                            multi_hot, slot_holdout_split,
                                            slot_weights, class_weights)
from job_matching.education.evaluator import education_metrics  # noqa: E402
from job_matching.education.labels import LABEL_ORDER  # noqa: E402

REPORT_DIR = ROOT / "reports" / "education-training"
MODELS_DIR = ROOT / "models" / "education"
LOG_DIR = REPORT_DIR / "logs"


def setup_train_logging(log_name: str, also_console: bool = True) -> logging.Logger:
    ensure_dir(LOG_DIR)
    logger = logging.getLogger("job_matching")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    tag = f"edu::{log_name}"
    for h in list(logger.handlers):
        if getattr(h, "_et_tag", None) == tag:
            return logger
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    if also_console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        sh._et_tag = tag  # type: ignore[attr-defined]
        logger.addHandler(sh)
    fh = logging.FileHandler(LOG_DIR / f"{log_name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    fh._et_tag = tag  # type: ignore[attr-defined]
    logger.addHandler(fh)
    return logger


def prepare_experiment_a(smoke_rows: int | None = None) -> dict:
    """实验 A：第三阶段 train/validation/gold_holdout 固定切分。"""
    sets = load_dev_sets()
    if smoke_rows:
        for k in list(sets):
            sets[k] = sets[k].head(min(int(smoke_rows), len(sets[k]))).reset_index(drop=True)
    return {"train": sets["train"], "validation": sets["validation"],
            "gold": sets["gold_holdout"], "experiment": "A_known_expression_distribution"}


def prepare_experiment_b(smoke_rows: int | None = None) -> dict:
    """实验 B：train 内部按槽位表达留出（未见过表达的泛化）。"""
    dev = load_dev_sets()
    tr, ho, info = slot_holdout_split(dev["train"])
    if smoke_rows:
        tr = tr.head(min(int(smoke_rows), len(tr))).reset_index(drop=True)
        ho = ho.head(min(int(smoke_rows), len(ho))).reset_index(drop=True)
    return {"train": tr, "validation": ho, "gold": dev["gold_holdout"],
            "holdout_info": info, "experiment": "B_unseen_expression_generalization"}


def texts_of(df: pd.DataFrame) -> list[str]:
    return df["slot"].astype(str).tolist()


def eval_frame(df: pd.DataFrame, Y_pred: np.ndarray, set_name: str,
               label_provenance: str) -> dict:
    """统一评估入口：真值来自 df["Y"]，一律标注集合名与标签来源。"""
    Y_true = multi_hot(df)
    m = education_metrics(Y_true, Y_pred,
                          texts=texts_of(df), groups=df["slot"].to_numpy(),
                          lengths=df["slot_len"].to_numpy())
    m["set"] = set_name
    m["label_provenance"] = label_provenance
    return m


def write_run_record(record: dict) -> Path:
    rid = record["run_id"]
    path = REPORT_DIR / "runs" / f"{rid}.json"
    jdump(record, path)
    return path


def new_run_id(model: str, tag: str) -> str:
    return f"{model}-{tag}-{time.strftime('%Y%m%d-%H%M%S')}"


def model_dir(model: str, run_id: str) -> Path:
    return ensure_dir(MODELS_DIR / model / run_id)


def slot_weight_vec(df: pd.DataFrame, strategy: str) -> np.ndarray | None:
    if strategy == "slot_balanced":
        return slot_weights(df)
    if strategy == "conflict_aware":
        return conflict_aware_weights(df)
    return None
