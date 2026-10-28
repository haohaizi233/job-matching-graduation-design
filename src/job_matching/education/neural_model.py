# -*- coding: utf-8 -*-
"""Model B：轻量 PyTorch 字符模型（Embedding + CNN + 6 logits）。

显存约束：RTX 2050 仅 4GB，网络刻意保持小规模（学历槽位是短表达，无须大模型）。
"""
from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn

from .labels import LABEL_ORDER


class CharCNN(nn.Module):
    def __init__(self, vocab_size: int, emb_dim: int = 32, n_filters: int = 64,
                 kernel_size: int = 3, dropout: float = 0.1,
                 n_labels: int | None = None):
        super().__init__()
        n_labels = n_labels or len(LABEL_ORDER)
        self.params = {"vocab_size": int(vocab_size), "emb_dim": int(emb_dim),
                       "n_filters": int(n_filters), "kernel_size": int(kernel_size),
                       "dropout": float(dropout), "n_labels": int(n_labels)}
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=0)
        self.conv = nn.Conv1d(emb_dim, n_filters, kernel_size, padding=kernel_size // 2)
        self.act = nn.ReLU()
        self.drop = nn.Dropout(dropout)
        self.out = nn.Linear(n_filters, n_labels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, L) 字符 id
        h = self.emb(x)                       # (B, L, E)
        h = self.drop(h)
        h = h.transpose(1, 2)                 # (B, E, L)
        h = self.act(self.conv(h))            # (B, F, L)
        h = h.max(dim=2).values               # (B, F) 全局最大池化
        return self.out(h)                    # (B, 6) logits

    @property
    def n_parameters(self) -> int:
        return int(sum(p.numel() for p in self.parameters()))

    def save(self, path: Path, extra: dict | None = None) -> dict:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"state_dict": self.state_dict(), "params": self.params,
                   "extra": extra or {}}
        torch.save(payload, path)
        return {"model_file": str(path.name), "bytes": path.stat().st_size}

    @classmethod
    def load(cls, path: Path, map_location="cpu") -> tuple["CharCNN", dict]:
        payload = torch.load(Path(path), map_location=map_location)
        model = cls(**payload["params"])
        model.load_state_dict(payload["state_dict"])
        model.eval()
        return model, payload.get("extra", {})


class EducationCharDataset(torch.utils.data.Dataset):
    def __init__(self, X: torch.Tensor, Y: torch.Tensor):
        self.X = X
        self.Y = Y

    def __len__(self) -> int:
        return int(self.X.shape[0])

    def __getitem__(self, i: int):
        return self.X[i], self.Y[i]
