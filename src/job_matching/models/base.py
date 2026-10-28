# -*- coding: utf-8 -*-
"""模型公共工具：验证评估闭包、torch 预测适配、模块注册。"""
from __future__ import annotations

import numpy as np
import torch

from ..evaluation.metrics import ranking_report, selection_value

MODEL_MODULES = {
    "ridge": "job_matching.models.ridge",
    "gradient_boosting": "job_matching.models.gradient_boosting",
    "mlp": "job_matching.models.mlp",
    "ranknet": "job_matching.models.ranknet",
}


def get_model_module(name: str):
    import importlib
    if name not in MODEL_MODULES:
        raise KeyError(f"未登记的模型: {name}")
    return importlib.import_module(MODEL_MODULES[name])


def make_predict_np(model: torch.nn.Module, device: torch.device, batch_size: int = 8192):
    def predict_np(X: np.ndarray) -> np.ndarray:
        model.eval()
        out = []
        with torch.no_grad():
            for s in range(0, len(X), batch_size):
                xb = torch.from_numpy(np.asarray(X[s:s + batch_size], dtype=np.float32)).to(device)
                out.append(model(xb).squeeze(-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
    return predict_np


def make_val_eval(predict_fn, X_val, groups_val, val_frame, ks, min_size, tie_eps,
                  selection_metric):
    """返回 val_eval_fn(model_or_none) -> (selection_value, report)。"""
    def _eval(_model=None):
        pred = predict_fn(X_val)
        rep = ranking_report(groups_val, pred, val_frame, ks=ks,
                             min_group_size=min_size, tie_eps=tie_eps)
        return selection_value(rep, selection_metric), rep
    return _eval


class TorchScorer(torch.nn.Module):
    """Input -> Linear(d,h1) -> LayerNorm -> ReLU -> Linear(h1,h2) -> ReLU -> Linear(h2,1)"""

    def __init__(self, input_dim: int, hidden=(64, 32), layernorm: bool = True,
                 dropout: float = 0.0):
        super().__init__()
        h1, h2 = int(hidden[0]), int(hidden[1])
        layers: list[torch.nn.Module] = [torch.nn.Linear(input_dim, h1)]
        if layernorm:
            layers.append(torch.nn.LayerNorm(h1))
        layers.append(torch.nn.ReLU())
        if dropout and dropout > 0:
            layers.append(torch.nn.Dropout(float(dropout)))
        layers.append(torch.nn.Linear(h1, h2))
        layers.append(torch.nn.ReLU())
        layers.append(torch.nn.Linear(h2, 1))
        self.net = torch.nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)
