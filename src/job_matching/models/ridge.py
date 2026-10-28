# -*- coding: utf-8 -*-
"""Model A：Ridge 回归（可解释线性对照）。

目标：预测代理连续匹配分数 final_score（原评分系统派生，非真实就业效果）。
超参数（alpha）只在 train 拟合、validation 上选择，绝不接触 test。
"""
from __future__ import annotations

import itertools
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import Ridge

from ..evaluation.metrics import ranking_report, selection_value
from .base import make_val_eval


class RidgeModel:
    name = "ridge"

    def __init__(self, params: dict | None = None):
        self.params = dict(params or {})
        self.est = Ridge(fit_intercept=bool(self.params.get("fit_intercept", True)),
                         alpha=float(self.params.get("alpha", 1.0)))
        self.feature_names: list[str] = []

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeModel":
        self.est.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.est.predict(X), dtype=np.float64)

    def param_count(self) -> int:
        return int(np.asarray(self.est.coef_).size + (1 if self.est.fit_intercept else 0))

    def coefficients(self) -> list[dict]:
        out = [{"feature": f, "coefficient": round(float(c), 8)}
               for f, c in zip(self.feature_names, self.est.coef_)]
        out.sort(key=lambda d: -abs(d["coefficient"]))
        if self.est.fit_intercept:
            out.append({"feature": "__intercept__",
                        "coefficient": round(float(self.est.intercept_), 8)})
        return out

    def save(self, run_dir: Path) -> list[str]:
        path = Path(run_dir) / "model.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"params": self.params, "est": self.est,
                     "feature_names": self.feature_names}, path)
        return ["model.pkl"]

    @classmethod
    def load(cls, run_dir: Path) -> "RidgeModel":
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

    holder: list[RidgeModel] = []
    val_eval = make_val_eval(lambda X: holder[0].predict(X), X_val, groups_val, val_frame,
                             train_cfg.ks, train_cfg.min_group_size,
                             train_cfg.pairwise_tie_eps, train_cfg.selection_metric)

    search_rows = []
    best_value, best_model, best_params = None, None, None
    t0 = time.time()
    for combo in combos:
        params = dict(base_params)
        params.update(dict(zip(keys, combo)))
        model = RidgeModel(params)
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
        "best_params": {"alpha": float(best_model.params.get("alpha", 1.0)), **best_params},
        "search": {"space": space, "evaluated": search_rows, "limit": limit},
        "history": [],
        "val_report": val_report,
        "selection_value": float(best_value),
        "train_seconds": round(time.time() - t0, 2),
    }
