# -*- coding: utf-8 -*-
"""中文文本向量编码契约与实现（Phase4-3B / M3-6.2）。

设计目标（任务书 6.2 逐条落地）：
  * 批量编码 encode(texts) -> np.ndarray[float32]，形状 (n, dim)；
  * 缓存控制：可选磁盘缓存（按 (model_id, revision, truncate, normalize, 文本 sha256) 命名）；
  * 模型版本：model_id + 精确 revision + license 全部写入 describe()；
  * 输入截断策略：max_length 显式截断并记录截断统计；
  * 编码失败处理：单条失败不静默，抛 TextEncodeError 或按 on_error='zero' 显式降级并计数；
  * 空文本处理：空串/None 统一映射为全零向量并计入 empty_count；
  * CPU/GPU 兼容：device 显式声明，默认 cpu；
  * 可重复运行：无随机算子，同输入同输出；
  * 记录向量维度与归一化方式。

实现说明：
  本模块**不**依赖 sentence-transformers（该依赖未在项目环境中），
  BGE 系列用 transformers 的 AutoModel + 显式 mean pooling 实现。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

__all__ = ["TextEncoder", "TextEncodeError", "EncoderInfo", "build_encoder"]


class TextEncodeError(RuntimeError):
    """编码失败：必须显式抛出，不得静默返回随机向量。"""


@dataclass
class EncoderInfo:
    encoder_id: str
    model_id: str
    revision: str | None
    license: str | None
    dim: int
    normalization: str
    max_length: int
    device: str
    backend: str
    offline: bool
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "encoder_id": self.encoder_id,
            "model_id": self.model_id,
            "revision": self.revision,
            "license": self.license,
            "dim": self.dim,
            "normalization": self.normalization,
            "max_length": self.max_length,
            "device": self.device,
            "backend": self.backend,
            "offline": self.offline,
            "notes": self.notes,
        }


# 固定 revision（下载时从 HF API 取得的精确 commit sha，避免权重漂移）
KNOWN_REVISIONS = {
    "BAAI/bge-small-zh-v1.5": {
        "revision": "7999e1d3359715c523056ef9478215996d62a620",
        "license": "MIT",
        "dim": 512,
    },
    "BAAI/bge-reranker-base": {
        "revision": "2cfc18c9415c912f9d8155881c133215df768a70",
        "license": "MIT",
        "dim": 1,
    },
}


@dataclass
class EncodeStats:
    calls: int = 0
    texts: int = 0
    empty_texts: int = 0
    truncated_texts: int = 0
    failed_texts: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class TextEncoder:
    """统一向量编码接口。"""

    encoder_id = "base"

    def encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - 抽象
        raise NotImplementedError

    def describe(self) -> EncoderInfo:  # pragma: no cover - 抽象
        raise NotImplementedError

    def stats(self) -> dict:
        return {}


# ---------------------------------------------------------------- 词袋/哈希基线
class HashNgramEncoder(TextEncoder):
    """确定性字符 n-gram 哈希向量（离线、无预训练权重、可复现）。

    用途：在没有预训练中文向量模型时提供一个**可执行**的语义近似基线，
    并作为 BGE 编码器的回归对照（同输入同输出）。
    """

    def __init__(self, dim: int = 512, ngram_range: tuple[int, int] = (2, 4),
                 max_length: int = 512, normalization: str = "l2", seed: int = 0):
        self.dim = int(dim)
        self.ngram_range = ngram_range
        self.max_length = int(max_length)
        self.normalization = normalization
        self.seed = int(seed)
        self._stats = EncodeStats()

    def describe(self) -> EncoderInfo:
        return EncoderInfo(
            encoder_id="hash_ngram",
            model_id="job-matching/hash-ngram",
            revision=f"dim{self.dim}-ng{self.ngram_range[0]}{self.ngram_range[1]}"
                     f"-seed{self.seed}",
            license="project-internal",
            dim=self.dim,
            normalization=self.normalization,
            max_length=self.max_length,
            device="cpu",
            backend="sklearn-free-hashing",
            offline=True,
            notes="确定性特征哈希，无预训练语义；仅作可执行基线",
        )

    def stats(self) -> dict:
        return self._stats.to_dict()

    def _hash(self, token: str) -> int:
        digest = hashlib.blake2b(
            token.encode("utf-8"), digest_size=8,
            salt=b"p43b" + self.seed.to_bytes(4, "little")).digest()
        return int.from_bytes(digest, "little")

    def encode(self, texts: list[str]) -> np.ndarray:
        if isinstance(texts, str):
            raise TextEncodeError("encode 需要 list[str]，不接受单个 str（避免把字符串当字符序列）")
        t0 = time.perf_counter()
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, raw in enumerate(texts):
            s = "" if raw is None else str(raw)
            if len(s) > self.max_length:
                s = s[: self.max_length]
                self._stats.truncated_texts += 1
            if not s.strip():
                self._stats.empty_texts += 1
                continue
            lo, hi = self.ngram_range
            for n in range(lo, hi + 1):
                for j in range(len(s) - n + 1):
                    idx = self._hash(s[j: j + n]) % self.dim
                    out[i, idx] += 1.0
        if self.normalization == "l2":
            norms = np.linalg.norm(out, axis=1, keepdims=True)
            np.divide(out, np.maximum(norms, 1e-12), out=out)
        self._stats.calls += 1
        self._stats.texts += len(texts)
        self._stats.seconds += time.perf_counter() - t0
        return out


# ---------------------------------------------------------------- BGE 编码器
class BgeEncoder(TextEncoder):
    """BAAI/bge-small-zh-v1.5 的 transformers 实现（mean pooling + 可选 L2）。"""

    encoder_id = "bge_small_zh_v15"

    def __init__(self, model_id: str = "BAAI/bge-small-zh-v1.5",
                 revision: str | None = None, device: str = "cpu",
                 max_length: int = 512, batch_size: int = 16,
                 normalization: str = "l2", query_instruction: str = "",
                 cache_dir: str | os.PathLike | None = None,
                 on_error: str = "raise", local_only: bool | None = None,
                 local_files_only: bool | None = None):
        meta = KNOWN_REVISIONS.get(model_id, {})
        self.model_id = model_id
        self.revision = revision or meta.get("revision")
        self.license = meta.get("license")
        self.dim_expected = meta.get("dim")
        self.device = device
        self.max_length = int(max_length)
        self.batch_size = int(batch_size)
        self.normalization = normalization
        self.query_instruction = query_instruction or ""
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.on_error = on_error
        self._stats = EncodeStats()
        if local_files_only is not None:
            local_only = local_files_only
        if local_only is None:
            local_only = os.environ.get("JM_OFFLINE", "") == "1"
        self.local_only = bool(local_only)

        try:
            import torch  # noqa: F401
            from transformers import AutoModel, AutoTokenizer
        except Exception as e:  # noqa: BLE001
            raise TextEncodeError(f"缺少 transformers/torch 依赖: {e}") from e

        t0 = time.perf_counter()
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_id, revision=self.revision, local_files_only=self.local_only)
            self.model = AutoModel.from_pretrained(
                model_id, revision=self.revision, local_files_only=self.local_only)
        except Exception as e:  # noqa: BLE001
            raise TextEncodeError(
                f"模型 {model_id}@{self.revision} 加载失败（local_files_only={self.local_only}）: {e}"
            ) from e
        self.model.eval()
        self.model.to(self.device)
        self.load_seconds = round(time.perf_counter() - t0, 3)
        self.dim = int(self.model.config.hidden_size)
        if self.dim_expected and self.dim != self.dim_expected:
            raise TextEncodeError(
                f"向量维度与登记不符：实际 {self.dim} != 登记 {self.dim_expected}")

    def describe(self) -> EncoderInfo:
        return EncoderInfo(
            encoder_id=self.encoder_id,
            model_id=self.model_id,
            revision=self.revision,
            license=self.license,
            dim=self.dim,
            normalization=self.normalization,
            max_length=self.max_length,
            device=self.device,
            backend="transformers-mean-pooling",
            offline=bool(self.local_only),
            notes=f"load_seconds={self.load_seconds}; mean pooling over last_hidden_state",
        )

    def stats(self) -> dict:
        d = self._stats.to_dict()
        d["load_seconds"] = getattr(self, "load_seconds", None)
        return d

    def _prepare(self, texts: list[str]) -> tuple[list[str], list[int], int]:
        kept: list[str] = []
        index: list[int] = []
        empty = 0
        for i, raw in enumerate(texts):
            s = "" if raw is None else str(raw)
            if not s.strip():
                empty += 1
                continue
            kept.append(self.query_instruction + s)
            index.append(i)
        return kept, index, empty

    def encode(self, texts: list[str]) -> np.ndarray:
        if isinstance(texts, str):
            raise TextEncodeError("encode 需要 list[str]，不接受单个 str")
        t0 = time.perf_counter()
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        kept, index, empty = self._prepare(texts)
        self._stats.empty_texts += empty
        if kept:
            import torch
            for start in range(0, len(kept), self.batch_size):
                chunk = kept[start: start + self.batch_size]
                try:
                    enc = self.tokenizer(
                        chunk, padding=True, truncation=True,
                        max_length=self.max_length, return_tensors="pt")
                    n_tokens = int(enc["input_ids"].shape[1])
                    if n_tokens >= self.max_length:
                        self._stats.truncated_texts += sum(
                            1 for c in chunk if len(c) >= self.max_length)
                    enc = {k: v.to(self.device) for k, v in enc.items()}
                    with torch.no_grad():
                        hidden = self.model(**enc).last_hidden_state
                    mask = enc["attention_mask"].unsqueeze(-1).float()
                    pooled = (hidden * mask).sum(dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)
                    vecs = pooled.cpu().numpy().astype(np.float32)
                    for row, idx in enumerate(index[start: start + self.batch_size]):
                        out[idx] = vecs[row]
                except Exception as e:  # noqa: BLE001
                    self._stats.failed_texts += len(chunk)
                    if self.on_error == "zero":
                        continue
                    raise TextEncodeError(
                        f"批量编码失败（batch_start={start}, n={len(chunk)}）: {e}") from e
        if self.normalization == "l2":
            norms = np.linalg.norm(out, axis=1, keepdims=True)
            np.divide(out, np.maximum(norms, 1e-12), out=out)
        self._stats.calls += 1
        self._stats.texts += len(texts)
        self._stats.seconds += time.perf_counter() - t0
        return out


# ---------------------------------------------------------------- 工厂与缓存
def build_encoder(name: str, **kw) -> TextEncoder:
    if name in ("hash_ngram", "hash"):
        return HashNgramEncoder(**kw)
    if name in ("bge_small_zh_v15", "bge-small-zh-v1.5", "BAAI/bge-small-zh-v1.5"):
        return BgeEncoder(**kw)
    raise TextEncodeError(f"未登记的编码器: {name}")


class CachedEncoder:
    """磁盘向量缓存包装器（可选）。缓存键含模型 revision 与截断配置。"""

    def __init__(self, inner: TextEncoder, cache_dir: str | os.PathLike):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, np.ndarray] = {}

    def describe(self) -> EncoderInfo:
        return self.inner.describe()

    def stats(self) -> dict:
        d = self.inner.stats()
        d["cache_dir"] = str(self.cache_dir)
        return d

    def _key(self, text: str) -> str:
        info = self.inner.describe()
        payload = json.dumps(
            [info.model_id, info.revision, info.max_length, info.normalization, text],
            ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def encode(self, texts: list[str]) -> np.ndarray:
        info = self.inner.describe()
        out = np.zeros((len(texts), info.dim), dtype=np.float32)
        todo: list[tuple[int, str]] = []
        for i, t in enumerate(texts):
            k = self._key("" if t is None else str(t))
            if k in self._mem:
                out[i] = self._mem[k]
                continue
            p = self.cache_dir / f"{k}.npy"
            if p.exists():
                arr = np.load(p)
                self._mem[k] = arr
                out[i] = arr
                continue
            todo.append((i, k))
        if todo:
            vecs = self.inner.encode([texts[i] for i, _ in todo])
            for (i, k), v in zip(todo, vecs):
                out[i] = v
                self._mem[k] = v
                np.save(self.cache_dir / f"{k}.npy", v)
        return out
