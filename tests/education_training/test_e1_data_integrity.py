# -*- coding: utf-8 -*-
"""E1：数据完整性与切分隔离（原始数据哈希 / 输入组互斥 / 金标准隔离）。"""
from __future__ import annotations

import unittest

from _util import ROOT, SPLITS_DIR, jload, sha256_file


class E1DataIntegrity(unittest.TestCase):
    def test_raw_hashes_match_phase2_baseline(self):
        from job_matching.pipeline import RAW_HASH_BASELINE
        for rel_path, expect in RAW_HASH_BASELINE.items():
            p = ROOT / rel_path
            self.assertTrue(p.exists(), f"原始文件缺失: {rel_path}")
            self.assertEqual(sha256_file(p), expect, f"原始文件被修改: {rel_path}")

    def test_split_files_match_manifest_hashes(self):
        manifest = jload(SPLITS_DIR / "manifest.json")
        for f in manifest["files"]:
            p = ROOT / f["path"]
            self.assertTrue(p.exists(), f"切分文件缺失: {f['path']}")
            self.assertEqual(sha256_file(p), f["sha256"], f"切分文件被修改: {f['path']}")

    def test_train_val_input_groups_disjoint(self):
        import pandas as pd
        tr = pd.read_csv(SPLITS_DIR / "train.csv", dtype=str)
        va = pd.read_csv(SPLITS_DIR / "validation.csv", dtype=str)
        for col in ("user_hash", "record_key"):
            self.assertEqual(len(set(tr[col]) & set(va[col])), 0,
                             f"train/validation 在 {col} 上不互斥")

    def test_gold_isolated_from_dev(self):
        import pandas as pd
        gold = pd.read_csv(SPLITS_DIR / "gold_holdout.csv", dtype=str)
        for split in ("train", "validation"):
            dev = pd.read_csv(SPLITS_DIR / f"{split}.csv", dtype=str)
            self.assertEqual(len(set(gold["user_hash"]) & set(dev["user_hash"])), 0,
                             f"gold_holdout 与 {split} 输入重叠")
            self.assertEqual(len(set(gold["record_key"]) & set(dev["record_key"])), 0,
                             f"gold_holdout 与 {split} 记录重叠")


if __name__ == "__main__":
    unittest.main()
