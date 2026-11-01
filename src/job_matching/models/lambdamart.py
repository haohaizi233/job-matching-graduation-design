# -*- coding: utf-8 -*-
"""LightGBM LambdaMART Learning-to-Rank（Phase 10-R2）。

完全兼容 models/base.py 统一接口：
- train_model(*, model_cfg, X_train, y_train, X_val, groups_train, groups_val, ...)
- save(run_dir) -> list[str]
- load(run_dir) -> LambdaMARTModel
- param_count() -> int
- predict(X) -> np.ndarray

标签映射：weak_positive=1, medium_positive=2, strong_positive=3
label_gain: [0, 1, 2, 3]
未知标签/非法数值必须报错，禁止静默映射为0。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

# ---- 标签映射 ----
LABEL_MAP = {"weak_positive": 1, "medium_positive": 2, "strong_positive": 3}
LABEL_GAIN = [0, 1, 2, 3]


def map_labels_to_int(y: np.ndarray) -> np.ndarray:
    """将相关性标签严格映射为 {1,2,3} 整数。未知标签报错。"""
    y = np.asarray(y)
    if y.dtype.kind in ('U', 'S', 'O'):
        out = np.empty(len(y), dtype=np.int64)
        for i, v in enumerate(y):
            s = str(v).strip()
            if s not in LABEL_MAP:
                raise ValueError(f"未知标签 '{s}'，合法值: {sorted(LABEL_MAP.keys())}")
            out[i] = LABEL_MAP[s]
        return out
    # 数值标签：只允许 0/1/2/3
    y_int = np.empty(len(y), dtype=np.int64)
    for i, v in enumerate(y):
        fv = float(v)
        if fv != int(fv) or int(fv) not in (0, 1, 2, 3):
            raise ValueError(f"非法标签数值: {v!r}，只允许 0/1/2/3")
        y_int[i] = int(fv)
    return y_int


def build_query_groups(candidate_ids: np.ndarray) -> np.ndarray:
    """将 candidate_id 转换为连续 Query Group Sizes。

    假设数据已按 candidate_id 分组排序。验证：
    - sum(group_sizes) == len(candidate_ids)
    - 每组内 candidate_id 相同
    """
    ids = np.asarray(candidate_ids)
    if len(ids) == 0:
        return np.array([], dtype=np.int64)
    # 计算连续组大小
    changes = np.where(np.diff(ids) != 0)[0] + 1
    boundaries = np.concatenate([[0], changes, [len(ids)]])
    group_sizes = np.diff(boundaries).astype(np.int64)
    assert group_sizes.sum() == len(ids), \
        f"sum(group_sizes)={group_sizes.sum()} != len(X)={len(ids)}"
    return group_sizes


class LambdaMARTModel:
    """LightGBM LambdaMART 排序模型。"""

    def __init__(self, booster: Any = None, feature_map: Any = None):
        self.booster = booster
        self.feature_map = feature_map

    def predict(self, X: np.ndarray, device: str | None = None) -> np.ndarray:
        return self.booster.predict(X)

    def param_count(self) -> int:
        if self.booster is None:
            return 0
        return int(self.booster.num_trees())

    def save(self, run_dir: Path) -> list[str]:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        files = []
        # LightGBM model.txt
        model_path = run_dir / "model.txt"
        self.booster.save_model(str(model_path))
        files.append("model.txt")
        # FeatureMap
        if self.feature_map is not None:
            fm_path = run_dir / "feature_map.json"
            self.feature_map.save(fm_path)
            files.append("feature_map.json")
        # Manifest
        manifest = {
            "model_type": "lambdamart",
            "num_trees": self.booster.num_trees(),
            "label_map": LABEL_MAP,
            "label_gain": LABEL_GAIN,
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        files.append("manifest.json")
        return files

    @classmethod
    def load(cls, run_dir: Path) -> "LambdaMARTModel":
        import lightgbm as lgb
        run_dir = Path(run_dir)
        model_path = run_dir / "model.txt"
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        booster = lgb.Booster(model_file=str(model_path))
        # FeatureMap：实际位于 job_matching.training.feature_map
        feature_map = None
        fm_path = run_dir / "feature_map.json"
        if fm_path.exists():
            from ..training.feature_map import FeatureMap
            feature_map = FeatureMap.load(fm_path)
        return cls(booster, feature_map)


def train_model(*, model_cfg: dict, X_train, y_train, X_val, y_val, groups_train, groups_val,
                feature_map=None, run_dir=None, seed=42, **kwargs) -> LambdaMARTModel:
    """统一训练入口（与 base.py 兼容）。

    Args:
        model_cfg: 模型配置（num_leaves, learning_rate 等）
        X_train/X_val: 特征矩阵
        y_train/y_val: 相关性标签（字符串或0/1/2/3）
        groups_train/groups_val: Query Group Sizes（连续数组）
        feature_map: 可选 FeatureMap
        run_dir: 可选保存目录
        seed: 随机种子
    """
    import lightgbm as lgb

    # 验证 Query Group
    assert groups_train.sum() == len(X_train), \
        f"sum(groups_train)={groups_train.sum()} != len(X_train)={len(X_train)}"
    if X_val is not None:
        assert groups_val.sum() == len(X_val), \
            f"sum(groups_val)={groups_val.sum()} != len(X_val)={len(X_val)}"

    # 标签映射（严格，未知标签报错）
    y_train_int = map_labels_to_int(y_train)

    params = {
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
        "label_gain": LABEL_GAIN,
    }
    # 合并用户配置
    for k in ("num_leaves", "learning_rate", "feature_fraction", "bagging_fraction",
              "min_child_samples", "lambda_l1", "lambda_l2", "num_boost_round"):
        if k in model_cfg:
            params[k] = model_cfg[k]

    train_set = lgb.Dataset(X_train, y_train_int, group=groups_train)
    val_set = None
    if X_val is not None and groups_val is not None:
        y_val_int = map_labels_to_int(y_val)
        val_set = lgb.Dataset(X_val, y_val_int, group=groups_val, reference=train_set)

    num_boost_round = model_cfg.get("num_boost_round", 500)
    early_stopping = model_cfg.get("early_stopping_rounds", 50)

    callbacks = [lgb.log_evaluation(period=50)]
    if val_set is not None:
        callbacks.append(lgb.early_stopping(early_stopping))

    booster = lgb.train(
        params, train_set,
        num_boost_round=num_boost_round,
        valid_sets=[val_set] if val_set else None,
        callbacks=callbacks,
    )

    model = LambdaMARTModel(booster, feature_map)

    if run_dir is not None:
        model.save(run_dir)

    return model
