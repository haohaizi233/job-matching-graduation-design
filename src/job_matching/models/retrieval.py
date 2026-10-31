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
    """Okapi BM25。k1=1.5, b=0.75（默认，未调参）。

    Phase6 / M2 检索性能优化（等价性见 tests/phase6/test_retrieval_equivalence.py）：
      * 倒排索引：term -> (doc_ids, tfs)，查询只遍历命中的 posting list，
        不再对全量文档做 `tokens.count(term)`（原实现 O(q_terms * n * doc_len)）；
      * 文档长度归一化因子 `k1*(1-b+b*dl/avgdl)` 与每词 IDF 在 build 期预计算；
      * Top-K 用 `argpartition` 选阈值 + 边界平分段按 doc_id 升序补齐，
        与全量 `lexsort((doc_id, -score))` 的排序（含 tie-breaking）**逐位一致**；
      * 浮点口径：分数按「query 词序逐词累加」，运算顺序与朴素实现完全相同，
        因此同输入分数为 bit 级一致（测试仍以 1e-12 容差断言，防御未来重构）；
      * 空查询返回 []；未登录词不贡献分；零分文档不出现在结果中（与原实现一致）。
    """

    index_id = "bm25_okapi"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = float(k1)
        self.b = float(b)
        self._docs_tokens: list[list[str]] = []
        self._doc_len: np.ndarray | None = None
        self._avgdl = 0.0
        self._df: dict[str, int] = {}
        self._n = 0
        # ---- Phase6 / M2 预计算结构 ----
        self._postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._idf_cache: dict[str, float] = {}
        self._norm: np.ndarray | None = None   # k1*(1-b+b*dl/avgdl)，逐文档

    def describe(self) -> dict:
        return {"index_id": self.index_id, "k1": self.k1, "b": self.b,
                "tokenizer": "jieba+_TOKEN_RE", "fitted_on": "corpus_only_no_labels",
                "implementation": "inverted_index_precomputed_idf_topk_partition"}

    def build(self, docs: list[str]) -> None:
        self._docs_tokens = [tokenize_zh(d) for d in docs]
        self._n = len(self._docs_tokens)
        self._doc_len = np.asarray([len(t) for t in self._docs_tokens], dtype=np.float64)
        self._avgdl = float(self._doc_len.mean()) if self._n else 0.0
        self._df = {}
        postings: dict[str, list[tuple[int, int]]] = {}
        for i, toks in enumerate(self._docs_tokens):
            if not toks:
                continue
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            for t, tf in counts.items():
                postings.setdefault(t, []).append((i, tf))
        for t, pl in postings.items():
            self._df[t] = len(pl)
            self._postings[t] = (
                np.asarray([d for d, _ in pl], dtype=np.int64),
                np.asarray([f for _, f in pl], dtype=np.float64),
            )
        self._idf_cache = {t: self._idf(t) for t in self._df}
        if self._n:
            # 与朴素实现逐位一致：k1*(1.0-b+b*doc_len/avgdl) 的运算顺序保持不变
            self._norm = self.k1 * (1.0 - self.b + self.b * self._doc_len / self._avgdl)
        else:
            self._norm = np.zeros(0, dtype=np.float64)

    def _idf(self, term: str) -> float:
        n_q = self._df.get(term, 0)
        return math.log(1.0 + (self._n - n_q + 0.5) / (n_q + 0.5))

    @staticmethod
    def _topk_indices(scores: np.ndarray, k: int) -> np.ndarray:
        """按 (-score, doc_id) 取前 k 个正分下标（与 lexsort 全排序逐位一致）。

        平分边界用「>阈值全体 + ==阈值按 doc_id 升序补齐」保证 tie-breaking 稳定，
        避免 argpartition 在平分段的任意选择。
        """
        idx = np.flatnonzero(scores > 0)
        if idx.size == 0:
            return idx
        if k <= 0:
            return idx[:0]
        if idx.size <= k:
            return idx[np.lexsort((idx, -scores[idx]))]
        kth = np.partition(scores[idx], idx.size - k)[idx.size - k]
        above = idx[scores[idx] > kth]
        tied = np.sort(idx[scores[idx] == kth])
        need = k - above.size
        above = above[np.lexsort((above, -scores[above]))]
        return np.concatenate([above, tied[:need]])

    def search(self, queries: list[str], top_k: int = 10) -> list[list[tuple[int, float]]]:
        out = []
        for q in queries:
            q_tokens = tokenize_zh(q)
            if not q_tokens:
                out.append([])
                continue
            scores = np.zeros(self._n, dtype=np.float64)
            for term in q_tokens:          # 保留重复查询词的重复累加语义
                pl = self._postings.get(term)
                if pl is None:
                    continue
                doc_ids, tf = pl
                idf = self._idf_cache[term]
                denom = tf + self._norm[doc_ids]
                scores[doc_ids] += idf * tf * (self.k1 + 1.0) / denom
            order = self._topk_indices(scores, top_k)
            out.append([(int(j), float(scores[j])) for j in order])
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
