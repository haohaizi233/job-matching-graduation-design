"""LightGBM LambdaMART Learning-to-Rank 模型（Phase 10 P1）。

LGBMRanker 是成熟的 LTR 算法，CPU 执行即可。
复用现有 FeatureMap / FeaturePolicy / 数据切分。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


class LambdaMARTModel:
    """LightGBM LambdaMART 排序模型。"""

    def __init__(self, model: Any, feature_map: Any = None):
        self.model = model
        self.feature_map = feature_map

    def predict(self, X: np.ndarray, device: str | None = None) -> np.ndarray:
        return self.model.predict(X)

    @classmethod
    def load(cls, run_dir: Path | str) -> "LambdaMARTModel":
        import joblib
        d = Path(run_dir)
        blob = joblib.load(d / "model.pkl")
        feature_map = None
        fm_path = d / "feature_map.json"
        if fm_path.exists():
            from .feature_map import FeatureMap
            feature_map = FeatureMap.load(fm_path)
        return cls(blob, feature_map)

    def save(self, run_dir: Path | str) -> None:
        import joblib
        d = Path(run_dir)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, d / "model.pkl")
        if self.feature_map:
            self.feature_map.save(d / "feature_map.json")


def train_lambdamart(
    X_train: np.ndarray,
    y_train: np.ndarray,
    group_train: np.ndarray,
    X_val: np.ndarray | None = None,
    y_val: np.ndarray | None = None,
    group_val: np.ndarray | None = None,
    params: dict | None = None,
    num_boost_round: int = 500,
    early_stopping_rounds: int = 50,
    seed: int = 42,
) -> LambdaMARTModel:
    """训练 LightGBM LambdaMART 模型。"""
    import lightgbm as lgb

    default_params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "seed": seed,
    }
    if params:
        default_params.update(params)

    # LightGBM LambdaMART要求整数标签
    y_train_int = np.round(y_train).astype(int)
    train_set = lgb.Dataset(X_train, y_train_int, group=group_train)
    val_set = None
    if X_val is not None and y_val is not None and group_val is not None:
        y_val_int = np.round(y_val).astype(int)
        val_set = lgb.Dataset(X_val, y_val_int, group=group_val, reference=train_set)

    callbacks = [lgb.log_evaluation(period=50)]
    if val_set is not None:
        callbacks.append(lgb.early_stopping(early_stopping_rounds))

    model = lgb.train(
        default_params,
        train_set,
        num_boost_round=num_boost_round,
        valid_sets=[val_set] if val_set else None,
        callbacks=callbacks,
    )

    return LambdaMARTModel(model)
