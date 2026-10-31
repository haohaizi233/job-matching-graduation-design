# -*- coding: utf-8 -*-
"""两阶段匹配的精排（Cross-Encoder）契约与实现（Phase4-3B / M3-6.3）。

纪律：
  * 优先预训练模型零样本推理，不微调；
  * 最大输入长度显式设置并记录截断；
  * 支持批量推理；
  * 训练权重在推理过程中只读，不被修改；
  * 无监督训练数据前不进行任何微调（E07 前置条件未满足）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

__all__ = ["Reranker", "RerankError", "RerankStats", "BgeReranker", "LexicalReranker",
           "build_reranker"]


class RerankError(RuntimeError):
    pass


@dataclass
class RerankStats:
    calls: int = 0
    pairs: int = 0
    truncated_pairs: int = 0
    failed_pairs: int = 0
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class RerankResult:
    scores: np.ndarray
    truncated: int = 0
    note: str = ""


class Reranker:
    reranker_id = "base"

    def score(self, queries: list[str], documents: list[str]) -> RerankResult:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> dict:  # pragma: no cover
        raise NotImplementedError

    def stats(self) -> dict:
        return {}


class BgeReranker(Reranker):
    """BAAI/bge-reranker-base（cross-encoder，MIT）。零样本，不微调。"""

    reranker_id = "bge_reranker_base"

    def __init__(self, model_id: str = "BAAI/bge-reranker-base",
                 revision: str | None = None, device: str = "cpu",
                 max_length: int = 256, batch_size: int = 8,
                 local_files_only: bool = True, on_error: str = "raise"):
        from ..models.text_encoder import KNOWN_REVISIONS
        meta = KNOWN_REVISIONS.get(model_id, {})
        self.model_id = model_id
        self.revision = revision or meta.get("revision")
        self.license = meta.get("license")
        self.device = device
        self.max_length = int(max_length)
        self.batch_size = int(batch_size)
        self.local_files_only = local_files_only
        self.on_error = on_error
        self._stats = RerankStats()

        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        t0 = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id, revision=self.revision, local_files_only=local_files_only)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_id, revision=self.revision, local_files_only=local_files_only)
        self.model.eval()
        self.model.to(self.device)
        self.load_seconds = round(time.perf_counter() - t0, 3)

    def describe(self) -> dict:
        return {
            "reranker_id": self.reranker_id,
            "model_id": self.model_id,
            "revision": self.revision,
            "license": self.license,
            "max_length": self.max_length,
            "batch_size": self.batch_size,
            "device": self.device,
            "load_seconds": getattr(self, "load_seconds", None),
            "finetuned": False,
            "backend": "transformers-sequence-classification",
        }

    def stats(self) -> dict:
        d = self._stats.to_dict()
        d["load_seconds"] = getattr(self, "load_seconds", None)
        return d

    def score(self, queries: list[str], documents: list[str]) -> RerankResult:
        if len(queries) != len(documents):
            raise RerankError("queries 与 documents 长度必须一致")
        import torch
        t0 = time.perf_counter()
        n = len(queries)
        out = np.zeros(n, dtype=np.float64)
        truncated = 0
        for start in range(0, n, self.batch_size):
            q = ["" if x is None else str(x) for x in queries[start: start + self.batch_size]]
            d = ["" if x is None else str(x) for x in documents[start: start + self.batch_size]]
            truncated += sum(1 for a, b in zip(q, d) if len(a) + len(b) >= self.max_length)
            try:
                enc = self.tokenizer(
                    q, d, padding=True, truncation=True,
                    max_length=self.max_length, return_tensors="pt")
                enc = {k: v.to(self.device) for k, v in enc.items()}
                with torch.no_grad():
                    logits = self.model(**enc).logits
                if logits.shape[-1] == 1:
                    vals = logits.squeeze(-1)
                else:
                    vals = logits[:, -1] if logits.shape[-1] > 1 else logits.squeeze(-1)
                out[start: start + len(q)] = vals.detach().cpu().numpy().astype(np.float64)
            except Exception as e:  # noqa: BLE001
                self._stats.failed_pairs += len(q)
                if self.on_error == "zero":
                    continue
                raise RerankError(f"精排批量推理失败（batch_start={start}）: {e}") from e
        self._stats.calls += 1
        self._stats.pairs += n
        self._stats.truncated_pairs += truncated
        self._stats.seconds += time.perf_counter() - t0
        return RerankResult(scores=out, truncated=truncated,
                            note="bge-reranker-base 零样本 logits（未校准为概率）")


class LexicalReranker(Reranker):
    """离线词法精排基线（字符 n-gram + 技能重合），用于无预训练模型时保持链路可执行。"""

    reranker_id = "lexical_v1"

    def __init__(self, max_length: int = 512, skill_weight: float = 0.3):
        self.max_length = int(max_length)
        self.skill_weight = float(skill_weight)
        self._stats = RerankStats()

    def describe(self) -> dict:
        return {
            "reranker_id": self.reranker_id,
            "model_id": "job-matching/lexical-reranker",
            "revision": "v1",
            "license": "project-internal",
            "max_length": self.max_length,
            "device": "cpu",
            "finetuned": False,
            "backend": "char-ngram-tfidf-cosine",
        }

    def stats(self) -> dict:
        return self._stats.to_dict()

    def score(self, queries: list[str], documents: list[str]) -> RerankResult:
        if len(queries) != len(documents):
            raise RerankError("queries 与 documents 长度必须一致")
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        t0 = time.perf_counter()
        n = len(queries)
        if n == 0:
            return RerankResult(scores=np.zeros(0))
        q = [("" if x is None else str(x))[: self.max_length] for x in queries]
        d = [("" if x is None else str(x))[: self.max_length] for x in documents]
        truncated = sum(1 for a, b in zip(queries, documents)
                        if len("" if a is None else str(a)) + len("" if b is None else str(b))
                        >= self.max_length)
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), sublinear_tf=True)
        X = vec.fit_transform(q + d)
        sims = cosine_similarity(X[:n], X[n:], dense_output=False).diagonal()
        out = np.asarray(sims, dtype=np.float64).ravel()
        self._stats.calls += 1
        self._stats.pairs += n
        self._stats.truncated_pairs += truncated
        self._stats.seconds += time.perf_counter() - t0
        return RerankResult(scores=out, truncated=truncated,
                            note="字符 n-gram TF-IDF 余弦，IDF 在本批文本上拟合（无标签）")


def build_reranker(name: str, **kw) -> Reranker:
    if name in ("bge_reranker_base", "BAAI/bge-reranker-base", "bge-reranker-base"):
        return BgeReranker(**kw)
    if name in ("lexical", "lexical_v1"):
        return LexicalReranker(**kw)
    raise RerankError(f"未登记的精排器: {name}")
