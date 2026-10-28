# -*- coding: utf-8 -*-
"""Model D：RankNet 成对排序模型（本阶段重点研究模型）。

共享参数评分网络 + Pairwise Logistic Loss：
    loss = softplus(-(s_a - s_b))，a = 组内代理偏好更优的一侧（final_score 更高）。
偏好对仅在 Train 内构造（training/pair_sampler.py），近似同分对按 min_score_margin 丢弃。
注意：这里学习的是原评分系统的代理排序偏好，不是用户真实偏好。
"""
from __future__ import annotations

import itertools
import time
from pathlib import Path

import numpy as np
import torch

from ..core import jdump
from ..evaluation.metrics import ranking_report
from ..training import trainer as T
from ..training.pair_sampler import build_preference_pairs
from .base import TorchScorer, make_predict_np, make_val_eval


class RankNetModel:
    name = "ranknet"

    def __init__(self, input_dim: int, arch: dict, params: dict, feature_names: list[str]):
        self.input_dim = int(input_dim)
        self.arch = dict(arch)
        self.params = dict(params)
        self.feature_names = list(feature_names)
        self.net = TorchScorer(self.input_dim,
                               hidden=tuple(arch.get("hidden", (64, 32))),
                               layernorm=bool(arch.get("layernorm", True)),
                               dropout=float(arch.get("dropout", 0.0)))

    def to(self, device) -> "RankNetModel":
        self.net.to(device)
        return self

    def predict(self, X: np.ndarray, device=None, batch_size: int = 8192) -> np.ndarray:
        dev = next(self.net.parameters()).device if device is None else device
        return make_predict_np(self.net, dev, batch_size)(X)

    def param_count(self) -> int:
        return T.count_parameters(self.net)

    def save(self, run_dir: Path) -> list[str]:
        path = Path(run_dir) / "model.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"state_dict": self.net.state_dict(), "input_dim": self.input_dim,
                    "arch": self.arch, "params": self.params,
                    "feature_names": self.feature_names}, path)
        return ["model.pt"]

    @classmethod
    def load(cls, run_dir: Path) -> "RankNetModel":
        blob = torch.load(Path(run_dir) / "model.pt", map_location="cpu")
        m = cls(blob["input_dim"], blob["arch"], blob["params"], blob["feature_names"])
        m.net.load_state_dict(blob["state_dict"])
        m.net.eval()
        return m


def train_model(*, model_cfg: dict, X_train, y_train, X_val, groups_train, groups_val,
                val_frame, feature_map, train_cfg, device, run_dir, seed,
                resume_from=None, **_ignored) -> dict:
    arch = dict(model_cfg.get("architecture", {}) or {})
    sampling = dict(model_cfg.get("pair_sampling", {}) or {})
    space = model_cfg.get("search_space", {}) or {}
    keys = list(space.keys())
    combos = list(itertools.product(*[space[k] for k in keys])) if keys else [()]
    limit = int(model_cfg.get("search_limit", len(combos)))
    combos = combos[:limit]
    base_params = dict(model_cfg.get("params", {}) or {})

    # ---- 成对样本只在 Train 内构造（组 = candidate_id，偏好来自 final_score 代理序）
    pairs = build_preference_pairs(
        groups_train, y_train, seed=int(seed),
        min_score_margin=float(sampling.get("min_score_margin", 0.001)),
        max_pairs_per_group=int(sampling.get("max_pairs_per_group", 64)),
        max_total_pairs=int(sampling.get("max_total_pairs", 400000)))
    jdump(pairs.stats, Path(run_dir) / "pair_stats.json")

    search_rows, best = [], None
    t0 = time.time()
    for i, combo in enumerate(combos):
        params = dict(base_params)
        params.update(dict(zip(keys, combo)))
        model = RankNetModel(X_train.shape[1], arch, params, feature_map.feature_names_)
        model.to(device)
        predict_np = make_predict_np(model.net, device)
        val_eval = make_val_eval(predict_np, X_val, groups_val, val_frame,
                                 train_cfg.ks, train_cfg.min_group_size,
                                 train_cfg.pairwise_tie_eps, train_cfg.selection_metric)
        train_info = T.train_pairwise(model.net, X_train, pairs,
                                      lambda m: val_eval(m), params, device,
                                      Path(run_dir), int(seed),
                                      resume_from=resume_from if i == 0 else None,
                                      ckpt_name=f"checkpoint_search_{i}.pt")
        search_rows.append({"params": {k: params.get(k) for k in keys},
                            "selection_value": round(float(train_info["best_value"]), 6),
                            "best_epoch": train_info["best_epoch"],
                            "epochs_run": train_info["epochs_run"],
                            "checkpoint": train_info["checkpoint"]})
        if best is None or train_info["best_value"] > best[0]["best_value"]:
            best = (train_info, model, params)

    train_info, model, params = best
    best_ckpt = Path(train_info["checkpoint"])
    final_ckpt = Path(run_dir) / "checkpoint_best.pt"
    T.load_checkpoint(best_ckpt, model.net, None, map_location=device)
    if best_ckpt != final_ckpt:
        T.save_checkpoint(final_ckpt, model.net, None, train_info["best_epoch"],
                          train_info["best_value"], train_info["best_epoch"])

    predict_np = make_predict_np(model.net, device)
    val_report = ranking_report(groups_val, predict_np(X_val), val_frame,
                                ks=train_cfg.ks, min_group_size=train_cfg.min_group_size,
                                tie_eps=train_cfg.pairwise_tie_eps)
    return {
        "model": model,
        "best_params": {k: params.get(k) for k in keys},
        "search": {"space": space, "evaluated": search_rows, "limit": limit},
        "history": train_info["history"],
        "val_report": val_report,
        "selection_value": float(train_info["best_value"]),
        "train_seconds": round(time.time() - t0, 2),
        "device": str(device),
        "best_epoch": train_info["best_epoch"],
        "pair_stats": pairs.stats,
    }
