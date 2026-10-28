# -*- coding: utf-8 -*-
"""训练器：阈值选择、PyTorch 训练循环、早停、Checkpoint、训练历史。

阈值选择约束（任务书）：阈值只能在合法 Validation 上选择，不得默认 0.5，更不得用金标准调参。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from .labels import LABEL_ORDER
from .neural_model import CharCNN

THRESHOLD_GRID = np.round(np.arange(0.20, 0.801, 0.05), 2)


# ------------------------------------------------------------------ 阈值
def _f1_at(y_true: np.ndarray, proba: np.ndarray, th: float) -> float:
    yp = (proba >= th).astype(int)
    tp = int(((y_true == 1) & (yp == 1)).sum())
    fp = int(((y_true == 0) & (yp == 1)).sum())
    fn = int(((y_true == 1) & (yp == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def select_thresholds(y_val: np.ndarray, proba_val: np.ndarray,
                      grid=THRESHOLD_GRID) -> dict:
    """每标签独立选择最大化 F1 的阈值；只能传入 Validation 的标签与概率。"""
    y = np.asarray(y_val).astype(int)
    p = np.asarray(proba_val, dtype=np.float64)
    ths, detail = [], {}
    for i, name in enumerate(LABEL_ORDER):
        if y[:, i].sum() == 0:
            ths.append(0.5)
            detail[name] = {"threshold": 0.5, "f1": None, "note": "验证集无正例，回退 0.5"}
            continue
        best_th, best_f1 = 0.5, -1.0
        for th in grid:
            f = _f1_at(y[:, i], p[:, i], float(th))
            if f > best_f1 + 1e-12:
                best_th, best_f1 = float(th), f
        ths.append(best_th)
        detail[name] = {"threshold": best_th, "f1": round(best_f1, 6)}
    return {"thresholds": np.asarray(ths, dtype=np.float64), "detail": detail,
            "grid": [float(g) for g in grid], "selected_on": "validation"}


def seed_everything(seed: int) -> None:
    """统一随机源：必须在**模型构造之前**调用，否则权重初始化不可复现。"""
    import random
    random.seed(int(seed))
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ------------------------------------------------------------------ 神经网络训练
def _to_device(t: torch.Tensor, device) -> torch.Tensor:
    return t.to(device, non_blocking=True)


def evaluate_proba(model: CharCNN, X, device, batch_size: int = 2048) -> np.ndarray:
    if not isinstance(X, torch.Tensor):
        X = torch.from_numpy(np.asarray(X, dtype=np.int64))
    model.eval()
    outs = []
    with torch.no_grad():
        for i in range(0, X.shape[0], batch_size):
            xb = _to_device(X[i:i + batch_size], device)
            outs.append(torch.sigmoid(model(xb)).cpu().numpy())
    return np.concatenate(outs, axis=0) if outs else np.zeros((0, len(LABEL_ORDER)))


def train_neural(model: CharCNN, X_train: torch.Tensor, Y_train: torch.Tensor,
                 X_val: torch.Tensor, Y_val: torch.Tensor, *, device,
                 epochs: int = 30, batch_size: int = 512, lr: float = 1e-3,
                 weight_decay: float = 1e-4, patience: int = 5,
                 sample_weight: np.ndarray | None = None,
                 pos_weight: np.ndarray | None = None,
                 monitor: str = "val_loss",
                 seed: int = 20261031, log=None) -> dict:
    """完整训练循环：前向 / 反向 / 优化器更新 / 梯度有限性 / 早停 / 最优权重。

    monitor: "val_loss"（默认，稳定、连续）或 "micro_f1_fixed05"（离散、抖动大）。
    """
    seed_everything(seed)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    minimize = monitor == "val_loss"

    n = int(X_train.shape[0])
    sw = (np.asarray(sample_weight, dtype=np.float64) if sample_weight is not None
          else np.ones(n, dtype=np.float64))
    pw = (torch.tensor(np.asarray(pos_weight, dtype=np.float32), device=device)
          if pos_weight is not None else None)
    crit = nn.BCEWithLogitsLoss(reduction="none", pos_weight=pw)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    history: list[dict] = []
    best = {"epoch": -1, "monitor": np.inf if minimize else -np.inf,
            "val_micro_f1": -1.0, "state": None}
    t0 = time.time()
    nonfinite_grad_steps = 0
    rng = np.random.default_rng(seed)

    for epoch in range(1, int(epochs) + 1):
        model.train()
        perm = rng.permutation(n)
        epoch_loss, n_batches = 0.0, 0
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            xb = _to_device(X_train[idx], device)
            yb = _to_device(Y_train[idx], device)
            wb = torch.tensor(sw[idx], dtype=torch.float32, device=device)
            opt.zero_grad(set_to_none=True)
            logits = model(xb)
            loss_mat = crit(logits, yb.float())
            loss = (loss_mat.mean(dim=1) * wb).sum() / wb.sum()
            loss.backward()
            grad_ok = True
            for p_ in model.parameters():
                if p_.grad is not None and not torch.isfinite(p_.grad).all():
                    grad_ok = False
                    break
            if not grad_ok:
                nonfinite_grad_steps += 1
                opt.zero_grad(set_to_none=True)
                continue
            opt.step()
            epoch_loss += float(loss.detach().cpu())
            n_batches += 1
        if device.type == "cuda":
            torch.cuda.synchronize(device)

        val_proba = evaluate_proba(model, X_val, device)
        val_pred = (val_proba >= 0.5).astype(np.int8)
        yt = np.asarray(Y_val, dtype=np.int8)
        val_f1 = _micro_f1(yt, val_pred)
        val_loss = _bce_np(yt, val_proba)
        rec = {"epoch": epoch,
               "train_loss": round(epoch_loss / max(n_batches, 1), 6),
               "val_loss": round(val_loss, 6),
               "val_micro_f1_fixed05": round(val_f1, 6),
               "val_exact_match_fixed05": round(float(np.all(yt == val_pred, axis=1).mean()), 6)}
        history.append(rec)
        if log:
            log.info("[神经网络] epoch %d train_loss=%.4f val_loss=%.4f val_microF1=%.4f",
                     epoch, rec["train_loss"], rec["val_loss"], rec["val_micro_f1_fixed05"])
        cur = val_loss if minimize else val_f1
        improved = (cur < best["monitor"] - 1e-6) if minimize else (cur > best["monitor"] + 1e-6)
        if improved:
            best = {"epoch": epoch, "monitor": cur, "val_micro_f1": val_f1,
                    "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
        elif epoch - best["epoch"] >= patience:
            if log:
                log.info("[神经网络] 早停：epoch %d（最优 epoch %d）", epoch, best["epoch"])
            break

    if best["state"] is not None:
        model.load_state_dict(best["state"])
    seconds = time.time() - t0
    peak_mem = (float(torch.cuda.max_memory_allocated(device)) / (1024 ** 2)
                if device.type == "cuda" else 0.0)
    return {
        "history": history,
        "best_epoch": int(best["epoch"]),
        "early_stopping_monitor": monitor,
        "best_monitor_value": round(float(best["monitor"]), 6),
        "best_val_micro_f1_fixed05": round(float(best["val_micro_f1"]), 6),
        "nonfinite_grad_steps": int(nonfinite_grad_steps),
        "seconds": round(seconds, 2),
        "peak_memory_mb": round(peak_mem, 1),
        "device": str(device),
        "epochs_run": len(history),
        "n_parameters": model.n_parameters,
    }


def _micro_f1(yt: np.ndarray, yp: np.ndarray) -> float:
    tp = int(((yt == 1) & (yp == 1)).sum())
    fp = int(((yt == 0) & (yp == 1)).sum())
    fn = int(((yt == 1) & (yp == 0)).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def _bce_np(yt: np.ndarray, proba: np.ndarray) -> float:
    p = np.clip(np.asarray(proba, dtype=np.float64), 1e-7, 1 - 1e-7)
    y = np.asarray(yt, dtype=np.float64)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
