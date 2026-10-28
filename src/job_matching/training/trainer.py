# -*- coding: utf-8 -*-
"""PyTorch 训练循环、早停、随机种子与检查点（第四阶段 4.1）。

设计要求（configs/training/*.yaml）：
  * 固定随机种子（Python / NumPy / Torch / CUDA）；
  * AdamW + 梯度裁剪；小批量训练适配 RTX 2050 4GB 显存；
  * Early Stopping 只看 validation（selection_metric），绝不接触 test；
  * Checkpoint 保存最优权重与优化器状态，支持训练恢复（--resume）；
  * 训练历史逐 epoch 记录（loss / 验证指标 / 耗时）。
"""
from __future__ import annotations

import random
import time
from pathlib import Path

import numpy as np
import torch

from ..core import get_logger


# ------------------------------------------------------------------ 基础
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(prefer_gpu: bool = True, gpu_budget_mb: int = 4094) -> torch.device:
    if prefer_gpu and torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        free_mb = props.total_memory / (1024 ** 2)
        if free_mb <= gpu_budget_mb * 1.5:   # 4GB 卡正常；仅当卡远小于预算时退回 CPU
            return torch.device("cuda")
        return torch.device("cuda")
    return torch.device("cpu")


def count_parameters(model: torch.nn.Module) -> int:
    return int(sum(p.numel() for p in model.parameters()))


class EarlyStopping:
    def __init__(self, patience: int, mode: str = "max", min_delta: float = 0.0):
        self.patience = int(patience)
        self.mode = mode
        self.min_delta = float(min_delta)
        self.best: float | None = None
        self.best_epoch = -1
        self.bad_epochs = 0

    def step(self, value: float, epoch: int) -> bool:
        """返回 True 表示应该停止。"""
        improved = (self.best is None or
                    (value > self.best + self.min_delta if self.mode == "max"
                     else value < self.best - self.min_delta))
        if improved:
            self.best = float(value)
            self.best_epoch = int(epoch)
            self.bad_epochs = 0
            return False
        self.bad_epochs += 1
        return self.bad_epochs >= self.patience


def save_checkpoint(path: Path, model: torch.nn.Module, optimizer, epoch: int,
                    best_value: float, best_epoch: int, extra: dict | None = None) -> Path:
    payload = {
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict() if optimizer is not None else None,
        "epoch": int(epoch),
        "best_value": float(best_value),
        "best_epoch": int(best_epoch),
        "extra": extra or {},
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)
    return path


def load_checkpoint(path: Path, model: torch.nn.Module, optimizer=None,
                    map_location="cpu") -> dict:
    payload = torch.load(path, map_location=map_location)
    model.load_state_dict(payload["model_state"])
    if optimizer is not None and payload.get("optimizer_state"):
        optimizer.load_state_dict(payload["optimizer_state"])
    return payload


# ------------------------------------------------------------------ 训练循环
def _clip(model, max_norm: float | None) -> None:
    if max_norm and max_norm > 0:
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)


def train_pointwise(model: torch.nn.Module, X_train: np.ndarray, y_train: np.ndarray,
                    val_eval_fn, params: dict, device: torch.device,
                    run_dir: Path, seed: int, resume_from: Path | None = None,
                    ckpt_name: str = "checkpoint_best.pt") -> dict:
    """MSE 回归训练（MLP）。val_eval_fn(model) -> (selection_value, report_dict)。"""
    log = get_logger()
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(),
                            lr=float(params.get("learning_rate", 1e-3)),
                            weight_decay=float(params.get("weight_decay", 1e-4)))
    loss_fn = torch.nn.MSELoss()
    Xt = torch.from_numpy(np.asarray(X_train, dtype=np.float32))
    yt = torch.from_numpy(np.asarray(y_train, dtype=np.float32))
    n = Xt.shape[0]
    bs = int(params.get("batch_size", 2048))
    epochs = int(params.get("epochs", 60))
    start_epoch, best_value, best_epoch = 0, float("-inf"), -1

    if resume_from and Path(resume_from).exists():
        ck = load_checkpoint(resume_from, model, opt, map_location=device)
        start_epoch = int(ck["epoch"]) + 1
        best_value = float(ck["best_value"])
        best_epoch = int(ck["best_epoch"])
        log.info("[resume] 从 %s 恢复（epoch=%d best=%.6f）", resume_from, start_epoch, best_value)

    stopper = EarlyStopping(patience=int(params.get("early_stopping_patience", 8)), mode="max")
    stopper.best, stopper.best_epoch = best_value, best_epoch
    history: list[dict] = []
    ckpt_path = Path(run_dir) / ckpt_name
    t0 = time.time()

    for epoch in range(start_epoch, epochs):
        model.train()
        g = torch.Generator().manual_seed(seed + epoch)
        perm = torch.randperm(n, generator=g)
        total, batches = 0.0, 0
        for s in range(0, n, bs):
            take = perm[s:s + bs]
            xb = Xt[take].to(device)
            yb = yt[take].to(device)
            opt.zero_grad(set_to_none=True)
            pred = model(xb).squeeze(-1)
            loss = loss_fn(pred, yb)
            if not torch.isfinite(loss):
                raise RuntimeError(f"epoch {epoch} 出现非有限 loss")
            loss.backward()
            _clip(model, params.get("grad_clip_norm"))
            for p in model.parameters():          # 梯度必须存在且有限
                if p.grad is not None and not torch.isfinite(p.grad).all():
                    raise RuntimeError(f"epoch {epoch} 出现非有限梯度")
            opt.step()
            total += float(loss.item())
            batches += 1
        if device.type == "cuda":
            torch.cuda.synchronize()

        model.eval()
        with torch.no_grad():
            value, report = val_eval_fn(model)
        history.append({
            "epoch": epoch,
            "train_loss": round(total / max(batches, 1), 8),
            "selection_value": round(float(value), 6),
            "seconds": round(time.time() - t0, 2),
        })
        if stopper.best is None or value > stopper.best:
            save_checkpoint(ckpt_path, model, opt, epoch, value, epoch,
                            extra={"selection_value": float(value)})
        if stopper.step(value, epoch):
            log.info("[early-stop] epoch=%d（patience 用尽，best=%.6f@%d）",
                     epoch, stopper.best, stopper.best_epoch)
            break

    return {
        "history": history,
        "best_value": float(stopper.best),
        "best_epoch": int(stopper.best_epoch),
        "epochs_run": len(history),
        "checkpoint": str(ckpt_path),
        "seconds": round(time.time() - t0, 2),
        "device": str(device),
    }


def train_pairwise(model: torch.nn.Module, X_all: np.ndarray, pairs, val_eval_fn,
                   params: dict, device: torch.device, run_dir: Path, seed: int,
                   resume_from: Path | None = None,
                   ckpt_name: str = "checkpoint_best.pt") -> dict:
    """RankNet 成对训练：loss = softplus(-(s_a - s_b))，a 为偏好更优一侧。"""
    log = get_logger()
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(),
                            lr=float(params.get("learning_rate", 1e-3)),
                            weight_decay=float(params.get("weight_decay", 1e-4)))
    X = torch.from_numpy(np.asarray(X_all, dtype=np.float32))
    n_pairs = len(pairs)
    if n_pairs == 0:
        raise ValueError("没有可用的成对偏好样本，无法训练 RankNet")
    bs = int(params.get("pair_batch_size", 4096))
    epochs = int(params.get("epochs", 60))
    start_epoch, best_value, best_epoch = 0, float("-inf"), -1

    if resume_from and Path(resume_from).exists():
        ck = load_checkpoint(resume_from, model, opt, map_location=device)
        start_epoch = int(ck["epoch"]) + 1
        best_value = float(ck["best_value"])
        best_epoch = int(ck["best_epoch"])
        log.info("[resume] 从 %s 恢复（epoch=%d best=%.6f）", resume_from, start_epoch, best_value)

    stopper = EarlyStopping(patience=int(params.get("early_stopping_patience", 8)), mode="max")
    stopper.best, stopper.best_epoch = best_value, best_epoch
    history: list[dict] = []
    ckpt_path = Path(run_dir) / ckpt_name
    t0 = time.time()

    for epoch in range(start_epoch, epochs):
        model.train()
        g = torch.Generator().manual_seed(seed + epoch)
        perm = torch.randperm(n_pairs, generator=g)
        total, batches = 0.0, 0
        for s in range(0, n_pairs, bs):
            take = perm[s:s + bs]
            ia = torch.from_numpy(pairs.idx_a[take])
            ib = torch.from_numpy(pairs.idx_b[take])
            # 索引张量保持在 CPU 上，先对 CPU 上的完整特征矩阵做索引，再把小批次搬到训练设备，
            # 避免 CUDA 索引张量索引 CPU 张量导致的设备不匹配错误。
            xa = X[ia].to(device)
            xb = X[ib].to(device)
            opt.zero_grad(set_to_none=True)
            sa = model(xa).squeeze(-1)
            sb = model(xb).squeeze(-1)
            # 标签方向自检：a 必须是偏好更优一侧，loss = softplus(-(sa - sb))
            loss = torch.nn.functional.softplus(-(sa - sb)).mean()
            if not torch.isfinite(loss):
                raise RuntimeError(f"epoch {epoch} 出现非有限 loss")
            loss.backward()
            _clip(model, params.get("grad_clip_norm"))
            for p in model.parameters():
                if p.grad is not None and not torch.isfinite(p.grad).all():
                    raise RuntimeError(f"epoch {epoch} 出现非有限梯度")
            opt.step()
            total += float(loss.item())
            batches += 1
        if device.type == "cuda":
            torch.cuda.synchronize()

        model.eval()
        with torch.no_grad():
            value, report = val_eval_fn(model)
        history.append({
            "epoch": epoch,
            "train_loss": round(total / max(batches, 1), 8),
            "selection_value": round(float(value), 6),
            "seconds": round(time.time() - t0, 2),
        })
        if stopper.best is None or value > stopper.best:
            save_checkpoint(ckpt_path, model, opt, epoch, value, epoch,
                            extra={"selection_value": float(value)})
        if stopper.step(value, epoch):
            log.info("[early-stop] epoch=%d（patience 用尽，best=%.6f@%d）",
                     epoch, stopper.best, stopper.best_epoch)
            break

    return {
        "history": history,
        "best_value": float(stopper.best),
        "best_epoch": int(stopper.best_epoch),
        "epochs_run": len(history),
        "checkpoint": str(ckpt_path),
        "seconds": round(time.time() - t0, 2),
        "device": str(device),
        "pairs": n_pairs,
    }
