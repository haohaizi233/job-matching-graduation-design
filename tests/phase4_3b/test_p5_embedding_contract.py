# -*- coding: utf-8 -*-
"""P5 TextEncoder 契约：空文本 / 截断 / 批量 / 失败处理 / 可复现 / 版本登记。

BGE 预训练编码器为**有条件**测试：本地缓存与依赖可用才执行，
不可用时显式 SKIP 并写明原因（ENV_INCOMPATIBLE / 模型未下载），
不允许伪装成无条件 PASS。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.models.text_encoder import (  # noqa: E402
    CachedEncoder, HashNgramEncoder, TextEncodeError, build_encoder)


class P5EmbeddingContract(unittest.TestCase):
    def test_encode_returns_float32_matrix(self):
        enc = HashNgramEncoder(dim=64)
        out = enc.encode(["中文文本", "another text"])
        self.assertEqual((2, 64), out.shape)
        self.assertEqual(np.float32, out.dtype)

    def test_encode_rejects_bare_string(self):
        enc = HashNgramEncoder(dim=32)
        with self.assertRaises(TextEncodeError):
            enc.encode("把字符串当序列是错的")

    def test_empty_text_maps_to_zero_vector_and_is_counted(self):
        enc = HashNgramEncoder(dim=32)
        out = enc.encode(["", None, "   ", "有内容"])
        self.assertEqual((4, 32), out.shape)
        self.assertTrue(np.allclose(out[0], 0.0))
        self.assertTrue(np.allclose(out[1], 0.0))
        self.assertTrue(np.allclose(out[2], 0.0))
        self.assertGreater(float(np.linalg.norm(out[3])), 0.0)
        self.assertEqual(3, enc.stats()["empty_texts"])

    def test_truncation_is_explicit_and_counted(self):
        enc = HashNgramEncoder(dim=32, max_length=10)
        enc.encode(["x" * 500])
        self.assertGreater(enc.stats()["truncated_texts"], 0)

    def test_batch_encoding_matches_single(self):
        enc = HashNgramEncoder(dim=64)
        texts = ["简历文本甲", "岗位描述乙", "第三条"]
        batch = enc.encode(texts)
        for i, t in enumerate(texts):
            single = enc.encode([t])
            self.assertTrue(np.allclose(batch[i], single[0]),
                            f"批量与单条编码必须一致: {t}")

    def test_reproducible_across_instances(self):
        a = HashNgramEncoder(dim=64).encode(["同一输入", "stable"])
        b = HashNgramEncoder(dim=64).encode(["同一输入", "stable"])
        self.assertTrue(np.array_equal(a, b), "同输入必须同输出")

    def test_seed_is_part_of_identity(self):
        a = HashNgramEncoder(dim=64, seed=0).encode(["seeded"])
        b = HashNgramEncoder(dim=64, seed=1).encode(["seeded"])
        c = HashNgramEncoder(dim=64, seed=0).encode(["seeded"])
        self.assertTrue(np.array_equal(a, c), "同 seed 必须可复现")
        self.assertFalse(np.array_equal(a, b), "不同 seed 应产生不同特征哈希")

    def test_l2_normalization(self):
        enc = HashNgramEncoder(dim=64, normalization="l2")
        out = enc.encode(["归一化检查", "另一条"])
        norms = np.linalg.norm(out, axis=1)
        for v in norms:
            self.assertAlmostEqual(1.0, float(v), places=5)

    def test_describe_records_version_dim_and_normalization(self):
        info = HashNgramEncoder(dim=64).describe().to_dict()
        for key in ("model_id", "revision", "license", "dim", "normalization",
                    "max_length", "device", "backend"):
            self.assertIn(key, info)
            self.assertIsNotNone(info[key])
        self.assertEqual(64, info["dim"])
        self.assertEqual("l2", info["normalization"])

    def test_build_encoder_rejects_unknown(self):
        with self.assertRaises(TextEncodeError):
            build_encoder("not-a-registered-encoder")

    def test_build_encoder_hash_alias(self):
        enc = build_encoder("hash", dim=32)
        self.assertEqual(32, enc.describe().dim)

    def test_cached_encoder_matches_uncached(self):
        enc = HashNgramEncoder(dim=32)
        texts = ["缓存一致性甲", "缓存一致性乙"]
        direct = enc.encode(texts)
        with tempfile.TemporaryDirectory() as td:
            cached = CachedEncoder(HashNgramEncoder(dim=32), td)
            first = cached.encode(texts)
            files_after_first = set(Path(td).glob("*.npy"))
            second = cached.encode(texts)
            self.assertTrue(np.array_equal(direct, first))
            self.assertTrue(np.array_equal(first, second))
            self.assertGreater(len(files_after_first), 0, "缓存应落盘")
            self.assertEqual(files_after_first, set(Path(td).glob("*.npy")),
                             "命中缓存不应新增文件")

    def test_cached_encoder_key_covers_model_identity(self):
        with tempfile.TemporaryDirectory() as td:
            a = CachedEncoder(HashNgramEncoder(dim=32, seed=0), td)
            b = CachedEncoder(HashNgramEncoder(dim=32, seed=1), td)
            ka = a._key("同一文本")
            kb = b._key("同一文本")
            self.assertNotEqual(ka, kb, "缓存键必须包含模型版本/配置")

    def test_bge_encoder_conditional(self):
        """有条件：BGE 权重在本地且依赖可用才执行；否则显式 SKIP。"""
        try:
            enc = build_encoder("bge_small_zh_v15", local_files_only=True,
                                max_length=64, batch_size=4)
        except TextEncodeError as e:
            self.skipTest(f"ENV_INCOMPATIBLE/模型不可用，BGE 编码测试显式跳过: {e}")
        info = enc.describe()
        self.assertEqual("BAAI/bge-small-zh-v1.5", info.model_id)
        self.assertTrue(info.revision, "必须固定精确 revision")
        self.assertEqual("MIT", info.license)
        out = enc.encode(["中文简历文本样例", "", "岗位描述样例"])
        self.assertEqual((3, info.dim), out.shape)
        self.assertTrue(np.allclose(out[1], 0.0), "空文本必须映射为零向量")
        for v in out:
            self.assertTrue(np.all(np.isfinite(v)))
        again = enc.encode(["中文简历文本样例", "", "岗位描述样例"])
        self.assertTrue(np.allclose(out, again), "BGE 推理必须可复现")


if __name__ == "__main__":
    unittest.main()
