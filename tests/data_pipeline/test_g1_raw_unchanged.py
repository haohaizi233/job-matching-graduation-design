# -*- coding: utf-8 -*-
"""G1：原始数据不变。

对照第二阶段（data audit）记录的 SHA-256 基线，确认 data/raw/ 下的原始文件未被修改。
"""
from __future__ import annotations

import unittest

from _util import ROOT, cfg, file_hash
from job_matching.pipeline import RAW_HASH_BASELINE


class G1RawUnchanged(unittest.TestCase):
    def test_raw_file_hashes_match_phase2_baseline(self):
        c = cfg()
        for rel_path, expect in RAW_HASH_BASELINE.items():
            p = ROOT / rel_path
            self.assertTrue(p.exists(), f"原始文件缺失: {rel_path}")
            actual = file_hash(p)
            self.assertEqual(actual, expect,
                             f"原始文件被修改: {rel_path}\n  期望 {expect}\n  实际 {actual}")

    def test_raw_directory_not_written_by_pipeline(self):
        """流水线产物不得出现在 data/raw/ 下。"""
        raw = cfg().path("raw")
        forbidden_ext = {".npy", ".npz", ".parquet"}
        offenders = [str(p.relative_to(ROOT)) for p in raw.rglob("*")
                     if p.is_file() and p.suffix.lower() in forbidden_ext
                     and ".cache" not in str(p)]
        self.assertEqual(offenders, [], f"流水线产物写入了 data/raw: {offenders}")

    def test_raw_source_paths_declared_in_config(self):
        c = cfg()
        for group, items in c.pipeline["sources"].items():
            for key, rel_path in items.items():
                self.assertTrue((ROOT / rel_path).exists(),
                                f"配置声明的数据源不存在: {group}.{key} -> {rel_path}")


if __name__ == "__main__":
    unittest.main()
