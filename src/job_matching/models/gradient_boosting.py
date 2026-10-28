# -*- coding: utf-8 -*-
"""Model B：HistGradientBoostingRegressor（梯度提升树非线性回归）。

使用已安装的 scikit-learn 1.5.2 实现，不引入新的 GBDT 依赖。
复杂度受配置约束（max_depth / max_iter / learning_rate），网格规模受 search_limit 截断。
目标仍是代理匹配分数 final_score，不代表真实就业匹配效果。
"""
from __future__ import annotations

import itertools
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from ..evaluation.metrics import ranking_report
from .base import make_val_eval


class GradientBoostingModel:
    name = "gradient_boosting"

    def __init__(self, params: dict | None = None):
        self.params = dict(params or {})
        self.est = HistGradientBoostingRegressor(**self.params)
        self.feature_names: list[str] = []

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GradientBoostingModel":
        self.est.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.est.predict(X), dtype=np.float64)

    def param_count(self) -> int:
        # 直方图 GBDT：以「叶子节点数 x (树数)」近似模型容量，另记录树数
        return int(self.est.n_features_in_ * 0 + getattr(self.est, "n_iter_", 0) * 31)

    def save(self, run_dir: Path) -> list[str]:
        path = Path(run_dir) / "model.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"params": self.params, "est": self.est,
                     "feature_names": self.feature_names}, path)
        return ["model.pkl"]

    @classmethod
    def load(cls, run_dir: Path) -> "GradientBoostingModel":
        blob = joblib.load(Path(run_dir) / "model.pkl")
        m = cls(blob["params"])
        m.est = blob["est"]
        m.feature_names = list(blob["feature_names"])
        return m


def train_model(*, model_cfg: dict, X_train, y_train, X_val, groups_train, groups_val,
                val_frame, feature_map, train_cfg, device, run_dir, seed, **_ignored) -> dict:
    space = model_cfg.get("search_space", {}) or {}
    keys = list(space.keys())
    combos = list(itertools.product(*[space[k] for k in keys])) if keys else [()]
    limit = int(model_cfg.get("search_limit", len(combos)))
    combos = combos[:limit]
    base_params = dict(model_cfg.get("params", {}) or {})
    base_params.setdefault("random_state", int(seed))

    holder: list[GradientBoostingModel] = []
    val_eval = make_val_eval(lambda X: holder[0].predict(X), X_val, groups_val, val_frame,
                             train_cfg.ks, train_cfg.min_group_size,
                             train_cfg.pairwise_tie_eps, train_cfg.selection_metric)

    search_rows = []
    best_value, best_model, best_params = None, None, None
    t0 = time.time()
    for combo in combos:
        params = dict(base_params)
        params.update(dict(zip(keys, combo)))
        model = GradientBoostingModel(params)
        model.feature_names = list(feature_map.feature_names_)
        model.fit(X_train, y_train)
        holder[:] = [model]
        value, _ = val_eval()
        search_rows.append({"params": {k: params.get(k) for k in keys},
                            "selection_value": round(float(value), 6)})
        if best_value is None or value > best_value:
            best_value, best_model, best_params = value, model, {k: params.get(k) for k in keys}

    val_report = ranking_report(groups_val, best_model.predict(X_val), val_frame,
                                ks=train_cfg.ks, min_group_size=train_cfg.min_group_size,
                                tie_eps=train_cfg.pairwise_tie_eps)
    return {
        "model": best_model,
        "best_params": dict(best_params),
        "search": {"space": space, "evaluated": search_rows, "limit": limit},
        "history": [],
        "val_report": val_report,
        "selection_value": float(best_value),
        "train_seconds": round(time.time() - t0, 2),
    }
