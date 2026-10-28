# -*- coding: utf-8 -*-
"""E2：标签体系（六维映射 / 可逆 / 互斥规则）。"""
from __future__ import annotations

import unittest

import numpy as np

from _util import SYNTH_LABELS, synth_multi_hot


class E2Labels(unittest.TestCase):
    def test_label_order_matches_config(self):
        from job_matching.config import get_config
        from job_matching.education.labels import LABEL_ORDER
        self.assertEqual(list(LABEL_ORDER), ["博士", "硕士", "本科", "大专", "学历不限", "学历不明"])
        self.assertEqual(LABEL_ORDER, get_config().label_order)

    def test_multi_hot_roundtrip_reversible(self):
        from job_matching.education.labels import (multi_hot_to_tokens,
                                                   tokens_to_multi_hot)
        Y = tokens_to_multi_hot(SYNTH_LABELS)
        self.assertEqual(Y.shape, (len(SYNTH_LABELS), 6))
        back = [multi_hot_to_tokens(row) for row in Y]
        for src, got in zip(SYNTH_LABELS, back):
            self.assertEqual(sorted(got), sorted(src))

    def test_multi_hot_string_roundtrip(self):
        from job_matching.education.labels import (multi_hot_matrix_from_strings,
                                                   multi_hot_matrix_to_strings)
        Y = synth_multi_hot()
        s = multi_hot_matrix_to_strings(Y)
        Y2 = multi_hot_matrix_from_strings(s)
        self.assertTrue(np.array_equal(Y, Y2))

    def test_normalize_label_known_combinations(self):
        from job_matching.education.labels import normalize_label
        r = normalize_label("博士、硕士、本科")
        self.assertEqual(r["tokens"], ["博士", "硕士", "本科"])
        self.assertEqual(r["status"], "ok")
        r2 = normalize_label("学历不限")
        self.assertEqual(r2["tokens"], ["学历不限"])
        r3 = normalize_label("大四保研准硕士")
        self.assertEqual(r3["status"], "oov_token")
        self.assertEqual(r3["unresolved"], ["大四保研准硕士"])

    def test_terminal_token_exclusivity_flagged(self):
        from job_matching.education.labels import normalize_label
        self.assertEqual(normalize_label("学历不限、本科")["status"], "conflict")
        self.assertEqual(normalize_label("学历不明、学历不限")["status"], "conflict")

    def test_above_expansion_rule(self):
        from job_matching.education.rules import rule_predict
        self.assertEqual(rule_predict("本科及以上")["tokens"], ["博士", "硕士", "本科"])
        self.assertEqual(rule_predict("硕士及以上")["tokens"], ["博士", "硕士"])
        self.assertEqual(rule_predict("专科及以上")["tokens"], ["博士", "硕士", "本科", "大专"])
        self.assertEqual(rule_predict("")["tokens"], ["学历不明"])

    def test_predictor_conflict_resolution_never_mixes(self):
        from job_matching.education.predictor import EducationNormalizer
        nz = EducationNormalizer(model=None, model_type="tfidf_char_ovr_logreg",
                                 model_version="test", thresholds=np.full(6, 0.5),
                                 train_slot_vocab=set())
        scores = np.array([0.9, 0.1, 0.8, 0.1, 0.85, 0.1])  # 层级 + 学历不限 同时过阈值
        labels, note = nz._to_labels(scores)
        has_level = any(t in labels for t in ("博士", "硕士", "本科", "大专"))
        has_terminal = any(t in labels for t in ("学历不限", "学历不明"))
        self.assertFalse(has_level and has_terminal, f"终态 token 与层级 token 共存: {labels}")
        self.assertIn("conflict_resolution", note)


if __name__ == "__main__":
    unittest.main()
