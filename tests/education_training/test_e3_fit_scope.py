# -*- coding: utf-8 -*-
"""E3：拟合范围约束（TF-IDF / 字符词表不得在验证集上 fit）。"""
from __future__ import annotations

import unittest

import numpy as np


class E3FitScope(unittest.TestCase):
    def test_tfidf_vocabulary_excludes_validation_only_tokens(self):
        from job_matching.education.tfidf_model import TfidfEducationModel
        tr = ["本科", "硕士", "大专"]
        va = ["本科", "硕士", "琞士"]  # 「琞」只在验证集出现
        m = TfidfEducationModel().fit(tr, np.array([[0, 0, 1, 0, 0, 0],
                                                    [0, 1, 0, 0, 0, 0],
                                                    [1, 0, 0, 0, 0, 0]]))
        vocab = m.vectorizer.vocabulary_
        self.assertFalse(any("琞" in feat for feat in vocab),
                         f"验证集字符进入 TF-IDF 词表: {[f for f in vocab if '琞' in f]}")
        proba = m.predict_proba(va)  # 只 transform，不重建词表
        self.assertEqual(proba.shape, (3, 6))

    def test_char_vocab_excludes_validation_only_chars(self):
        from job_matching.education.tokenizer import CharTokenizer
        tok = CharTokenizer(max_len=8).fit(["本科", "硕士"])
        self.assertNotIn("琞", tok.stoi)
        arr, n_oov, n_bad = tok.transform_with_oov(["琞士"])
        self.assertEqual(n_oov, 1)
        self.assertEqual(n_bad, 1)
        self.assertEqual(int(arr[0][0]), tok.stoi["<unk>"])

    def test_tokenizer_refuses_second_fit(self):
        from job_matching.education.tokenizer import CharTokenizer
        tok = CharTokenizer().fit(["本科"])
        with self.assertRaises(RuntimeError):
            tok.fit(["硕士"])

    def test_thresholds_selected_without_gold(self):
        """阈值选择只依赖传入集合；金标准永远不是传入集合（由 run_all 顺序保证）。"""
        from job_matching.education.trainer import select_thresholds
        rng = np.random.default_rng(0)
        y = (rng.random((200, 6)) > 0.5).astype(int)
        p = np.clip(y * 0.7 + rng.random((200, 6)) * 0.3, 0, 1)
        out = select_thresholds(y, p)
        self.assertEqual(out["selected_on"], "validation")
        self.assertEqual(len(out["thresholds"]), 6)


if __name__ == "__main__":
    unittest.main()
