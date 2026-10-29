# -*- coding: utf-8 -*-
"""P2 场景 3：完全重复 / 规范化文本重复 / 近似重复检测（协议 3.4）。"""
from __future__ import annotations

import unittest

from _util import strip_comments_and_docstrings  # noqa: F401  (保持工具同源)

from job_matching.annotation import dedup as d


def long_cjk(n: int = 200, shift: int = 0) -> str:
    """确定性长中文串：前 n 个取自 900 字表，互不重复，shingle 集合可预测。"""
    return "".join(chr(0x4E00 + ((i * 719 + shift) % 900)) for i in range(n))


def variant_one_char(base: str, pos: int = 100) -> str:
    """只改 1 个字符 -> 字符 3-gram Jaccard = (S-3)/(S+3)。"""
    repl = chr(0x4E00 + 850) if base[pos] != chr(0x4E00 + 850) else chr(0x4E00 + 851)
    return base[:pos] + repl + base[pos + 1:]


class P2TestHashing(unittest.TestCase):
    def test_p2_exact_hash_ignores_whitespace_only(self):
        self.assertEqual(d.exact_hash("a  b\t c"), d.exact_hash("a b c"))
        self.assertNotEqual(d.exact_hash("abc"), d.exact_hash("abd"))

    def test_p2_norm_hash_ignores_case_and_punctuation(self):
        self.assertEqual(d.norm_hash("Ab-C"), d.norm_hash("ab c"))
        self.assertEqual(d.norm_hash("数据 分析！"), d.norm_hash("数据分析"))
        self.assertNotEqual(d.norm_hash("abc"), d.norm_hash("abd"))

    def test_p2_hash_is_sha256_hex(self):
        h = d.sha256_text("x")
        self.assertEqual(len(h), 64)
        self.assertRegex(h, r"^[0-9a-f]{64}$")

    def test_p2_jaccard_semantics(self):
        self.assertEqual(d.jaccard({"a", "b"}, {"a", "b"}), 1.0)
        self.assertEqual(d.jaccard({"a"}, {"b"}), 0.0)
        self.assertEqual(d.jaccard(set(), set()), 1.0)
        self.assertEqual(d.jaccard(set(), {"a"}), 0.0)
        self.assertAlmostEqual(d.jaccard({"a", "b"}, {"b", "c"}), 1 / 3, places=9)

    def test_p2_shingles_deterministic_and_bounded(self):
        s = long_cjk(50)
        a, b = d.shingles(s), d.shingles(s)
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(s) - d.DEFAULT_SHINGLE_N + 1)
        self.assertEqual(d.shingles(""), set())


class P2TestDuplicateIndex(unittest.TestCase):
    def test_p2_unique_then_exact_norm_near(self):
        idx = d.DuplicateIndex(threshold=0.90)
        base = long_cjk(200)
        self.assertEqual(idx.check("k0", base)["status"], "unique")
        # 完全重复：仅空白不同
        self.assertEqual(idx.check("k1", "  " + base + "  ")["status"], "exact_dup")
        # 规范化重复：大小写 / 标点不同
        self.assertEqual(idx.check("k2", "Ab-C")["status"], "unique")
        self.assertEqual(idx.check("k3", "ab c")["status"], "norm_dup")
        # 近似重复：只改 1 个字符
        res = idx.check("k4", variant_one_char(base))
        self.assertEqual(res["status"], "near_dup")
        self.assertEqual(res["dup_of"], "k0")
        self.assertGreaterEqual(res["similarity"], 0.90)

    def test_p2_distinct_text_is_unique(self):
        idx = d.DuplicateIndex(threshold=0.90)
        self.assertEqual(idx.check("a", long_cjk(200))["status"], "unique")
        self.assertEqual(idx.check("b", "the quick brown fox jumps over the lazy dog")["status"],
                         "unique")
        self.assertEqual(len(idx), 2)

    def test_p2_check_near_false_skips_near_duplicates(self):
        idx = d.DuplicateIndex(threshold=0.90, check_near=False)
        base = long_cjk(200)
        self.assertEqual(idx.check("k0", base)["status"], "unique")
        self.assertEqual(idx.check("k1", variant_one_char(base))["status"], "unique")


class P2TestPairwiseNearDuplicate(unittest.TestCase):
    def test_p2_near_duplicate_pairs_detects(self):
        base = long_cjk(200)
        texts = {"t0": base, "t1": variant_one_char(base), "t2": "完全不同的另一段文本，内容毫无关系"}
        found = d.near_duplicate_pairs(texts, threshold=0.90)
        pairs = {(x["a"], x["b"]) for x in found}
        self.assertIn(("t0", "t1"), pairs)
        self.assertNotIn(("t0", "t2"), pairs)
        self.assertNotIn(("t1", "t2"), pairs)
        for x in found:
            self.assertGreaterEqual(x["similarity"], 0.90)
            self.assertLess(x["a"], x["b"], "结果必须按字典序确定性输出")

    def test_p2_near_duplicate_pairs_empty_and_short(self):
        self.assertEqual(d.near_duplicate_pairs({}), [])
        self.assertEqual(d.near_duplicate_pairs({"a": "", "b": ""}), [])
        self.assertEqual(d.near_duplicate_pairs({"a": "abc"}), [])

    def test_p2_cross_near_duplicate_pairs_detects_overlap(self):
        base = long_cjk(200)
        target = {"pool_1": base}
        reference = [("train_1", variant_one_char(base)), ("train_2", "无关文本内容完全不同")]
        found = d.cross_near_duplicate_pairs(target, reference, threshold=0.90)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["a"], "pool_1")
        self.assertEqual(found[0]["b"], "train_1")

    def test_p2_cross_near_duplicate_pairs_disjoint(self):
        target = {"pool_1": long_cjk(200, shift=0)}
        reference = [("train_1", long_cjk(200, shift=500))]
        self.assertEqual(d.cross_near_duplicate_pairs(target, reference, threshold=0.90), [])

    def test_p2_cross_near_duplicate_accepts_dict_reference(self):
        base = long_cjk(200)
        found = d.cross_near_duplicate_pairs({"p": base}, {"r": base}, threshold=0.90)
        self.assertEqual(len(found), 1)

    def test_p2_blocking_threshold_helper(self):
        self.assertGreaterEqual(d.min_shared_for_threshold(0.90, 10), 3)
        self.assertEqual(d.min_shared_for_threshold(0.90, 1),
                         d.min_shared_for_threshold(0.90, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
