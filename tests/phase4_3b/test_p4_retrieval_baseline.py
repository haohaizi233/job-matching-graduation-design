# -*- coding: utf-8 -*-
"""P4 TF-IDF / BM25 / 向量召回基线行为契约。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.models.retrieval import (  # noqa: E402
    BM25Recall, EmbeddingRecall, RecallFusion, TfidfRecall, tokenize_zh)
from job_matching.models.text_encoder import HashNgramEncoder  # noqa: E402

DOCS = [
    "Python 后端开发工程师 熟悉 Django 与 MySQL",
    "前端开发工程师 精通 Vue 与 TypeScript",
    "数据分析工程师 熟练使用 pandas 与 SQL 建模",
    "财务专员 负责日常账务处理与报表编制",
]


class P4RetrievalBaseline(unittest.TestCase):
    def test_tokenize_zh_handles_empty_and_none(self):
        self.assertEqual([], tokenize_zh(""))
        self.assertEqual([], tokenize_zh(None))
        self.assertEqual([], tokenize_zh("   "))
        self.assertTrue(all(isinstance(t, str) for t in tokenize_zh("Python 开发")))

    def test_tfidf_returns_ranked_doc_ids(self):
        ix = TfidfRecall()
        ix.build(DOCS)
        res = ix.search(["Python 后端开发"], top_k=3)
        self.assertEqual(1, len(res))
        self.assertGreater(len(res[0]), 0)
        self.assertLessEqual(len(res[0]), 3)
        ids = [d for d, _ in res[0]]
        self.assertIn(0, ids, "含相同关键词的文档应被召回")
        scores = [s for _, s in res[0]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_tfidf_empty_query_returns_empty(self):
        ix = TfidfRecall()
        ix.build(DOCS)
        res = ix.search([""], top_k=3)
        self.assertEqual([[]], res)

    def test_bm25_ranks_matching_doc_first(self):
        ix = BM25Recall()
        ix.build(DOCS)
        res = ix.search(["财务 报表"], top_k=2)
        self.assertGreater(len(res[0]), 0)
        self.assertEqual(3, res[0][0][0], "与查询词匹配的文档应排第一")

    def test_bm25_empty_query_returns_empty(self):
        ix = BM25Recall()
        ix.build(DOCS)
        self.assertEqual([[]], ix.search([""], top_k=3))
        self.assertEqual([[]], ix.search([None], top_k=3))

    def test_bm25_oov_query_returns_empty(self):
        ix = BM25Recall()
        ix.build(DOCS)
        self.assertEqual([[]], ix.search(["量子纠缠拓扑绝缘体"], top_k=3))

    def test_top_k_respected(self):
        for cls in (TfidfRecall, BM25Recall):
            ix = cls()
            ix.build(DOCS)
            res = ix.search(["开发 工程师"], top_k=2)
            self.assertLessEqual(len(res[0]), 2, cls.__name__)

    def test_embedding_recall_with_deterministic_encoder(self):
        enc = HashNgramEncoder(dim=128)
        ix = EmbeddingRecall(enc)
        ix.build(DOCS)
        res = ix.search(["Python 后端"], top_k=2)
        self.assertEqual(2, len(res[0]))
        for d, s in res[0]:
            self.assertIn(d, range(len(DOCS)))
            self.assertTrue(np.isfinite(s))
        scores = [s for _, s in res[0]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_fusion_prefers_shared_evidence(self):
        enc = HashNgramEncoder(dim=128)
        fusion = RecallFusion(indexes=[TfidfRecall(), BM25Recall(), EmbeddingRecall(enc)])
        fusion.build(DOCS)
        res = fusion.search(["财务 报表 编制"], top_k=3)
        self.assertGreater(len(res[0]), 0)
        self.assertEqual(3, res[0][0][0])

    def test_describe_declares_fitted_on_corpus_only(self):
        for cls in (TfidfRecall, BM25Recall):
            ix = cls()
            d = ix.describe()
            self.assertEqual("corpus_only_no_labels", d["fitted_on"],
                             f"{cls.__name__} 必须声明只在语料上构建、不使用标签")

    def test_fusion_describe_declares_manual_weights(self):
        fusion = RecallFusion(indexes=[TfidfRecall(), BM25Recall()])
        d = fusion.describe()
        self.assertIn("人工", d["note"], "融合权重来源必须显式声明")

    def test_index_rebuild_is_deterministic(self):
        ix = BM25Recall()
        ix.build(DOCS)
        a = ix.search(["开发 工程师"], top_k=3)
        ix.build(DOCS)
        b = ix.search(["开发 工程师"], top_k=3)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
