# -*- coding: utf-8 -*-
"""候选召回：BM25 / TF-IDF / 向量召回与融合（Phase4-3B / M3-6.1-6.2）。

统一契约：
    class RecallIndex:
        def build(self, docs: list[str]) -> None
        def search(self, queries: list[str], top_k: int) -> list[list[tuple[str, float]]]

中文分词统一使用 jieba（项目既有依赖），保证三类召回的分词口径一致。
BM25 参数 (k1=1.5, b=0.75) 为信息检索常用默认值，未在本数据上做超参数搜索；
如做调参必须只在开发集上进行并登记。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

__all__ = ["tokenize_zh", "TfidfRecall", "BM25Recall", "EmbeddingRecall", "RecallFusion"]

_TOKEN_RE = re.compile(r"[一-鿿A-Za-z0-9]+")


def tokenize_zh(text: str) -> list[str]:
    """中文分词 + 英文/数字词元；空文本返回空列表。"""
    if text is None:
        return []
    s = str(text).strip()
    if not s:
        return []
    try:
        import jieba
        jieba.setLogLevel(60)
        raw = [t.strip() for t in jieba.cut(s) if t.strip()]
    except Exception:  # jieba 缺失时退化为字符 bigram
        raw = list(s)
    out: list[str] = []
    for tok in raw:
        if _TOKEN_RE.fullmatch(tok):
            out.append(tok.lower())
        else:
            out.extend(t.lower() for t in _TOKEN_RE.findall(tok))
    return out


class RecallIndex:
    index_id = "base"

    def build(self, docs: list[str]) -> None:  # pragma: no cover
        raise NotImplementedError

    def search(self, queries: list[str], top_k: int = 10) -> list[list[tuple[int, float]]]:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"index_id": self.index_id}


class TfidfRecall(RecallIndex):
    index_id = "tfidf_char"

    def __init__(self, ngram_range: tuple[int, int] = (2, 4), use_tokens: bool = False):
        self.ngram_range = ngram_range
        self.use_tokens = use_tokens
        self._vec = None
        self._mat = None

    def describe(self) -> dict:
        return {"index_id": self.index_id, "ngram_range": list(self.ngram_range),
                "analyzer": "tokens" if self.use_tokens else "char_wb",
                "fitted_on": "corpus_only_no_labels"}

    def build(self, docs: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        corpus = ["" if d is None else str(d) for d in docs]
        if self.use_tokens:
            self._vec = TfidfVectorizer(
                tokenizer=tokenize_zh, token_pattern=None, lowercase=False,
                sublinear_tf=True)
        else:
            self._vec = TfidfVectorizer(
                analyzer="char_wb", ngram_range=self.ngram_range, sublinear_tf=True)
        self._mat = self._vec.fit_transform(corpus)

    def search(self, queries: list[str], top_k: int = 10) -> list[list[tuple[int, float]]]:
        from sklearn.metrics.pairwise import cosine_similarity
        q = ["" if x is None else str(x) for x in queries]
        Q = self._vec.transform(q)
        sims = cosine_similarity(Q, self._mat, dense_output=False)
        out = []
        for i in range(sims.shape[0]):
            row = sims.getrow(i).toarray().ravel()
            order = np.lexsort((np.arange(len(row)), -row))[:top_k]
            out.append([(int(j), float(row[j])) for j in order if row[j] > 0])
        return out


class BM25Recall(RecallIndex):
    """Okapi BM25。k1=1.5, b=0.75（默认，未调参）。"""

    index_id = "bm25_okapi"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = float(k1)
        self.b = float(b)
        self._docs_tokens: list[list[str]] = []
        self._doc_len: np.ndarray | None = None
        self._avgdl = 0.0
        self._df: dict[str, int] = {}
        self._n = 0

    def describe(self) -> dict:
        return {"index_id": self.index_id, "k1": self.k1, "b": self.b,
                "tokenizer": "jieba+_TOKEN_RE", "fitted_on": "corpus_only_no_labels"}

    def build(self, docs: list[str]) -> None:
        self._docs_tokens = [tokenize_zh(d) for d in docs]
        self._n = len(self._docs_tokens)
        self._doc_len = np.asarray([len(t) for t in self._docs_tokens], dtype=np.float64)
        self._avgdl = float(self._doc_len.mean()) if self._n else 0.0
        self._df = {}
        for toks in self._docs_tokens:
            for t in set(toks):
                self._df[t] = self._df.get(t, 0) + 1

    def _idf(self, term: str) -> float:
        n_q = self._df.get(term, 0)
        return math.log(1.0 + (self._n - n_q + 0.5) / (n_q + 0.5))

    def search(self, queries: list[str], top_k: int = 10) -> list[list[tuple[int, float]]]:
        out = []
        for q in queries:
            q_tokens = tokenize_zh(q)
            scores = np.zeros(self._n, dtype=np.float64)
            if not q_tokens:
                out.append([])
                continue
            for term in q_tokens:
                if term not in self._df:
                    continue
                idf = self._idf(term)
                for i, toks in enumerate(self._docs_tokens):
                    if not toks:
                        continue
                    tf = toks.count(term)
                    if tf == 0:
                        continue
                    denom = tf + self.k1 * (1.0 - self.b + self.b * self._doc_len[i] / self._avgdl)
                    scores[i] += idf * tf * (self.k1 + 1.0) / denom
            order = np.lexsort((np.arange(self._n), -scores))[:top_k]
            out.append([(int(j), float(scores[j])) for j in order if scores[j] > 0])
        return out


class EmbeddingRecall(RecallIndex):
    """向量召回：复用 TextEncoder 契约。"""

    index_id = "embedding_cosine"

    def __init__(self, encoder, normalize: bool = True):
        self.encoder = encoder
        self.normalize = normalize
        self._mat: np.ndarray | None = None

    def describe(self) -> dict:
        info = self.encoder.describe().to_dict()
        info["index_id"] = self.index_id
        return info

    def build(self, docs: list[str]) -> None:
        self._mat = self.encoder.encode([("" if d is None else str(d)) for d in docs])

    def search(self, queries: list[str], top_k: int = 10) -> list[list[tuple[int, float]]]:
        Q = self.encoder.encode([("" if q is None else str(q)) for q in queries])
        out = []
        for i in range(Q.shape[0]):
            sims = self._mat @ Q[i]
            order = np.lexsort((np.arange(len(sims)), -sims))[:top_k]
            out.append([(int(j), float(sims[j])) for j in order])
        return out


@dataclass
class RecallFusion:
    """多路召回融合（RRF，k=60 为常用默认值，未调参）。"""

    indexes: list[RecallIndex]
    rrf_k: int = 60
    weights: list[float] | None = None
    fusion_id: str = "rrf"

    def describe(self) -> dict:
        return {
            "fusion_id": self.fusion_id,
            "rrf_k": self.rrf_k,
            "weights": self.weights,
            "members": [ix.describe() for ix in self.indexes],
            "note": "权重为人工设定；RRF 参数未在本数据上搜索",
        }

    def build(self, docs: list[str]) -> None:
        for ix in self.indexes:
            ix.build(docs)

    def search(self, queries: list[str], top_k: int = 10,
               pool: int = 50) -> list[list[tuple[int, float]]]:
        per = [ix.search(queries, top_k=pool) for ix in self.indexes]
        w = self.weights or [1.0] * len(self.indexes)
        out = []
        for qi in range(len(queries)):
            acc: dict[int, float] = {}
            for wi, res in zip(w, per):
                for rank, (doc_id, _s) in enumerate(res[qi], start=1):
                    acc[doc_id] = acc.get(doc_id, 0.0) + wi / (self.rrf_k + rank)
            order = sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
            out.append([(int(d), float(s)) for d, s in order])
        return out
