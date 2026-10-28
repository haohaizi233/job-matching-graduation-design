# -*- coding: utf-8 -*-
"""G6：数据可加载。

验证 NumPy 缓存可读、Embedding 与 ID 映射一致、切分索引可加载、小批量数据能正确转为
PyTorch Tensor、不含意外 NaN/Inf、不会把数值型 ID 当成语义特征。
"""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from _util import cfg, jload, read_csv, read_csv_sig


class G6Loadability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = cfg()
        cls.c = c
        cls.features = read_csv(c.out("processed_matching") / "features_pairs.csv")
        cls.targets = read_csv(c.out("processed_matching") / "targets_pairs.csv")
        cls.matches = read_csv_sig(c.src("matching", "matches"))

    def test_numpy_cache_readable_and_finite(self):
        d = self.c.out("processed_embeddings")
        for side in ("cv", "job"):
            a = np.load(d / f"{side}_embeddings.npy", mmap_mode="r")
            self.assertEqual(a.dtype, np.float32)
            self.assertTrue(np.isfinite(np.asarray(a[:8])).all())

    def test_embedding_rows_match_id_map(self):
        d = self.c.out("processed_embeddings")
        for side, id_col in (("cv", "candidate_id"), ("job", "job_id")):
            m = jload(d / f"{side}_id_map.json")
            arr = np.load(d / f"{side}_embeddings.npy")
            self.assertEqual(arr.shape[0], len(m["row_to_id"]))
            src = read_csv_sig(self.c.src("matching", side if side != "cv" else "cv"))
            src_ids = set(src[id_col].astype(str))
            self.assertEqual(set(m["id_to_row"]), src_ids,
                             f"{side}: ID 映射与原始数据不一致")

    def test_split_indices_loadable_and_in_range(self):
        n = len(self.matches)
        for name in ("candidate_cold", "job_cold", "double_cold"):
            for s in ("train", "validation", "test"):
                f = read_csv(self.c.out("splits_matching") / name / f"{s}.csv")
                self.assertTrue(f["pair_index"].between(0, n - 1).all(),
                                f"{name}/{s} 索引越界")
                self.assertEqual(f["pair_index"].is_monotonic_increasing, True)

    def test_small_batch_to_torch_tensor_no_nan_inf(self):
        import torch
        cols = ["skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
                "position_token_overlap", "category_match", "years_experience"]
        batch = self.features[cols].head(32).to_numpy(dtype=np.float32)
        t = torch.from_numpy(batch)
        self.assertEqual(tuple(t.shape), (32, len(cols)))
        self.assertFalse(torch.isnan(t).any().item(), "Tensor 含 NaN")
        self.assertFalse(torch.isinf(t).any().item(), "Tensor 含 Inf")
        self.assertEqual(t.dtype, torch.float32)

    def test_target_tensor_conversion(self):
        import torch
        m = {"weak_positive": 0, "medium_positive": 1, "strong_positive": 2}
        y = torch.tensor([m[v] for v in self.targets["label_strength"].head(32)],
                         dtype=torch.long)
        self.assertEqual(int(y.max()) <= 2, True)

    def test_numeric_ids_not_used_as_semantic_features(self):
        schema = jload(self.c.out("processed_matching") / "feature_schema.json")
        id_like = set(self.c.id_like_columns())
        self.assertEqual(id_like & set(schema["numeric_feature_columns"]), set())
        self.assertEqual(id_like & set(schema["all_feature_columns"]), set())
        self.assertNotIn("candidate_id", schema["numeric_feature_columns"])
        self.assertNotIn("job_id", schema["numeric_feature_columns"])

    def test_education_inputs_loadable(self):
        df = read_csv(self.c.out("processed_education") / "education_inputs.csv")
        self.assertGreater(len(df), 0)
        self.assertTrue(df["record_key"].is_unique)
        self.assertIn("slot_education_norm", df.columns)

    def test_education_multihot_matrix_loadable(self):
        lab = read_csv(self.c.out("processed_education") / "education_labels.csv",
                       dtype={"label_multi_hot": str})
        order = self.c.label_order
        mat = np.zeros((len(lab), len(order)), dtype=np.int8)
        for i, s in enumerate(lab["label_multi_hot"].astype(str)):
            self.assertEqual(len(s), len(order), f"多热向量长度错误: {s}")
            mat[i] = [1 if ch == "1" else 0 for ch in s]
        self.assertEqual(mat.shape[1], 6)
        self.assertTrue(set(np.unique(mat)) <= {0, 1})
        self.assertGreater(int(mat.sum()), 0)

    def test_no_nan_in_key_feature_columns(self):
        cols = ["skill_jaccard", "position_token_overlap", "category_match"]
        self.assertFalse(self.features[cols].isna().any().any(),
                         "关键特征列存在 NaN")


if __name__ == "__main__":
    unittest.main()
