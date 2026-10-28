# -*- coding: utf-8 -*-
"""训练脚本公共工具：日志、数据准备、预测适配、运行记录。"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT, ensure_dir, jdump  # noqa: E402
from job_matching.training.config_train import TrainConfig, get_train_config  # noqa: E402
from job_matching.training.dataset import build_xy, load_pairs, load_protocol  # noqa: E402
from job_matching.training.feature_map import FeatureMap  # noqa: E402

TRAIN_LOG_DIR = ROOT / "reports" / "model-training" / "logs"


def setup_train_logging(log_name: str, also_console: bool = True) -> logging.Logger:
    """训练日志：写 reports/model-training/logs/，绝不输出简历/JD 正文。"""
    ensure_dir(TRAIN_LOG_DIR)
    logger = logging.getLogger("job_matching")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    tag = f"train::{log_name}"
    for h in list(logger.handlers):
        if getattr(h, "_mt_tag", None) == tag:
            return logger
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    if also_console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        sh._mt_tag = tag  # type: ignore[attr-defined]
        logger.addHandler(sh)
    fh = logging.FileHandler(TRAIN_LOG_DIR / f"{log_name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    fh._mt_tag = tag  # type: ignore[attr-defined]
    logger.addHandler(fh)
    return logger


def prepare_data(train_cfg: TrainConfig, protocol: str,
                 drop_groups: tuple[str, ...] = (),
                 smoke_rows: int | None = None) -> dict:
    """加载第三阶段产物 -> train/validation 矩阵。FeatureMap 只在 train 上 fit（IL-1/IL-2）。"""
    pairs = load_pairs()
    idx = load_protocol(protocol)
    tr = pairs.subset(idx["train"])
    va = pairs.subset(idx["validation"])
    if smoke_rows:
        tr = tr.head(int(smoke_rows)).reset_index(drop=True)
        va = va.head(min(int(smoke_rows), len(va))).reset_index(drop=True)

    enabled = [g for g in train_cfg.group_order() if g not in drop_groups]
    if not enabled:
        raise ValueError("消融后没有任何可用特征组")
    fm = FeatureMap(groups_enabled=enabled, task=train_cfg.task)
    fm.fit(tr)

    X_tr, y_tr = build_xy(tr, fm, train_cfg.common["data"]["regression_target"])
    X_va, y_va = build_xy(va, fm, train_cfg.common["data"]["regression_target"])
    return {
        "pairs": pairs,
        "pair_index": idx,
        "train_frame": tr,
        "val_frame": va,
        "X_train": X_tr, "y_train": y_tr,
        "X_val": X_va, "y_val": y_va,
        "groups_train": tr["candidate_id"].to_numpy(),
        "groups_val": va["candidate_id"].to_numpy(),
        "feature_map": fm,
    }


def predict_scores(model, X: np.ndarray, device="cpu") -> np.ndarray:
    try:
        return np.asarray(model.predict(X, device=device), dtype=np.float64)
    except TypeError:
        return np.asarray(model.predict(X), dtype=np.float64)


def write_run_record(record: dict) -> Path:
    rid = record["run_id"]
    path = ROOT / "reports" / "model-training" / "runs" / f"{rid}.json"
    jdump(record, path)
    return path
