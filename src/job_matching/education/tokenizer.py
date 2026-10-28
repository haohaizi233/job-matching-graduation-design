# -*- coding: utf-8 -*-
"""字符级词表与定长编码（只在 Train 上 fit，验证/推理只 transform）。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PAD, UNK = "<pad>", "<unk>"


class CharTokenizer:
    """字符级 tokenizer：fit 只接受训练文本，未知字符映射到 <unk>。"""

    def __init__(self, max_len: int = 32):
        self.max_len = int(max_len)
        self.stoi: dict[str, int] = {PAD: 0, UNK: 1}
        self.fitted = False

    # -- fit / transform
    def fit(self, texts) -> "CharTokenizer":
        if self.fitted:
            raise RuntimeError("CharTokenizer 只允许 fit 一次（防止验证集泄漏）")
        for t in texts:
            for ch in str(t):
                if ch not in self.stoi:
                    self.stoi[ch] = len(self.stoi)
        self.fitted = True
        return self

    def transform(self, texts) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("CharTokenizer 尚未 fit")
        unk = self.stoi[UNK]
        out = np.zeros((len(list(texts)), self.max_len), dtype=np.int64)
        for r, t in enumerate(texts):
            for c, ch in enumerate(str(t)[: self.max_len]):
                out[r, c] = self.stoi.get(ch, unk)
        return out

    def encode(self, text: str) -> np.ndarray:
        return self.transform([text])[0]

    @property
    def vocab_size(self) -> int:
        return len(self.stoi)

    def transform_with_oov(self, texts) -> tuple[np.ndarray, int, int]:
        """返回 (矩阵, oov 字符数, 含 oov 的样本数)。"""
        if not self.fitted:
            raise RuntimeError("CharTokenizer 尚未 fit")
        unk = self.stoi[UNK]
        arrs, n_oov, n_bad = [], 0, 0
        for t in texts:
            ids, bad = [], 0
            for ch in str(t)[: self.max_len]:
                idx = self.stoi.get(ch, None)
                if idx is None:
                    idx = unk
                    n_oov += 1
                    bad += 1
                ids.append(idx)
            ids += [0] * (self.max_len - len(ids))
            arrs.append(ids)
            n_bad += 1 if bad else 0
        return np.asarray(arrs, dtype=np.int64), int(n_oov), int(n_bad)

    # -- 持久化
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"max_len": self.max_len, "stoi": self.stoi}, f,
                      ensure_ascii=False, indent=1)
            f.write("\n")

    @classmethod
    def load(cls, path: Path) -> "CharTokenizer":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        tok = cls(max_len=int(d["max_len"]))
        tok.stoi = {str(k): int(v) for k, v in d["stoi"].items()}
        tok.fitted = True
        return tok
