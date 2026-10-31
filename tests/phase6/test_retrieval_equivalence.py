# -*- coding: utf-8 -*-
"""Phase6 / M2 检索等价性：优化后 BM25 与朴素实现 Top-K 逐位一致。

朴素参照实现直接内联在本文件（O(q*n*doc_len) 全量扫描 + 全量 lexsort），
不依赖被测代码的任何私有结构，保证「优化前后相同数据 Top-K 一致」可独立验证。

验证维度（任务书 5.3 正确性）：
  * Top-K 一致性（含分数，容差 1e-12，浮点口径见实现注释）；
  * tie-breaking 稳定（平分文档按 doc_id 升序）；
  * 空查询 / 未知词 / 重复查询词；
  * 只出正分文档；
  * top_k 边界（0 / 1 / 超过文档数）。
"""
from __future__ import annotations

import math
import unittest

from _util import synthetic_job_pool, synthetic_queries

from job_matching.models.retrieval import BM25Recall, tokenize_zh


def naive_bm25_search(docs: list[str], query: str, top_k: int,
                      k1: float = 1.5, b: float = 0.75) -> list[tuple[int, float]]:
    """朴素参照：与历史 Phase4-3B 实现同语义（全量扫描 + lexsort 全排序）。"""
    docs_tokens = [tokenize_zh(d) for d in docs]
    n = len(docs_tokens)
    if n == 0:
        return []
    doc_len = [len(t) for t in docs_tokens]
    avgdl = sum(doc_len) / n
    df: dict[str, int] = {}
    for toks in docs_tokens:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    q_tokens = tokenize_zh(query)
    if not q_tokens:
        return []
    scores = [0.0] * n
    for term in q_tokens:
        if term not in df:
            continue
        idf = math.log(1.0 + (n - df[term] + 0.5) / (df[term] + 0.5))
        for i, toks in enumerate(docs_tokens):
            if not toks:
                continue
            tf = toks.count(term)
            if tf == 0:
                continue
            denom = tf + k1 * (1.0 - b + b * doc_len[i] / avgdl)
            scores[i] += idf * tf * (k1 + 1.0) / denom
    order = sorted(range(n), key=lambda i: (-scores[i], i))[:top_k]
    return [(i, scores[i]) for i in order if scores[i] > 0]


class M2RetrievalEquivalence(unittest.TestCase):
    maxDiff = None

    def _check(self, docs: list[str], queries: list[str], top_k: int = 10):
        idx = BM25Recall()
        idx.build(docs)
        got = idx.search(queries, top_k=top_k)
        self.assertEqual(len(queries), len(got))
        for q, rows in zip(queries, got):
            exp = naive_bm25_search(docs, q, top_k)
            self.assertEqual([d for d, _ in exp], [d for d, _ in rows],
                             f"Top-K 文档序不一致: q={q!r}")
            for (_e, es), (_g, gs) in zip(exp, rows):
                self.assertAlmostEqual(es, gs, delta=1e-12,
                                       msg=f"分数不一致: q={q!r}")

    def test_small_pool_exact_match(self):
        self._check(synthetic_job_pool(30), synthetic_queries(6), top_k=10)

    def test_medium_pool_exact_match(self):
        self._check(synthetic_job_pool(200), synthetic_queries(8), top_k=10)

    def test_topk_variants(self):
        docs = synthetic_job_pool(40)
        for k in (0, 1, 5, 40, 999):
            self._check(docs, synthetic_queries(3), top_k=k)

    def test_tie_breaking_stable_by_doc_id(self):
        # 完全相同的文档 -> 分数全部相等 -> 排名按 doc_id 升序
        docs = ["Java 开发工程师 熟练掌握 Java"] * 8
        idx = BM25Recall()
        idx.build(docs)
        rows = idx.search(["Java 开发"], top_k=8)[0]
        self.assertEqual(list(range(8)), [d for d, _ in rows])
        scores = [s for _d, s in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def _oov_query(self, docs: list[str]) -> str:
        """构造在**当前分词口径**下与语料词元完全不相交的查询。

        分词口径随 jieba 是否安装而不同（jieba 分词 / 字符退化，见
        models/retrieval.tokenize_zh）：同一字符串在两种口径下的词元集合不同，
        「未登录」前提必须按当前 token 集显式断言，不能硬编码查询串，
        否则换环境就出现假失败（CI 干净 checkout 无 jieba 时曾复现）。
        """
        vocab: set[str] = set()
        for d in docs:
            vocab.update(tokenize_zh(d))
        for cand in ("啊嗷龘鬱", "完全未登录词xyzzy", "qxzjvk9"):
            if set(tokenize_zh(cand)).isdisjoint(vocab):
                return cand
        self.fail("合成语料词元覆盖了全部候选查询，无法构造未登录查询（夹具问题）")

    def test_empty_query_and_unknown_terms(self):
        docs = synthetic_job_pool(10)
        idx = BM25Recall()
        idx.build(docs)
        self.assertEqual([[]], idx.search([""], top_k=5))
        self.assertEqual([[]], idx.search(["   "], top_k=5))
        self.assertEqual([[]], idx.search([self._oov_query(docs)], top_k=5))

    def test_repeated_query_terms_accumulate(self):
        # 重复查询词重复累加语义与朴素实现一致
        docs = synthetic_job_pool(25)
        self._check(docs, ["Java Java Spring", "SQL SQL"], top_k=5)

    def test_only_positive_scores_returned(self):
        docs = synthetic_job_pool(50)
        idx = BM25Recall()
        idx.build(docs)
        for _d, s in idx.search(synthetic_queries(4), top_k=10)[0:4][0]:
            pass
        for rows in idx.search(synthetic_queries(4), top_k=10):
            for _d, s in rows:
                self.assertGreater(s, 0.0)

    def test_empty_corpus(self):
        idx = BM25Recall()
        idx.build([])
        self.assertEqual([[]], idx.search(["Java"], top_k=5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
