# -*- coding: utf-8 -*-
"""T2 数据切分不变与协议合规（验收项 2、3、8）。

  2. data/splits/matching 三套切分文件 SHA-256 必须与第三阶段 manifest 记录一致。
  3. Train/Validation/Test 的 pair / candidate / job 不得违反各自协议的互斥规则。
  8. 训练流程只能读取 train/validation，绝不读取 test 调参。
"""
from __future__ import annotations

import unittest

import pandas as pd

from _util import ROOT, SPLITS_DIR, jload, sha256_file

from job_matching.training import dataset as ds
from job_matching.training.config_train import get_train_config

PROTOCOLS = ["candidate_cold", "job_cold", "double_cold"]
# 各协议要求互斥的分组键（candidate_cold 只保证候选人互斥，job 可重叠）
GROUP_RULES = {
    "candidate_cold": ("candidate_id",),
    "job_cold": ("job_id",),
    "double_cold": ("candidate_id", "job_id"),
}


class T2SplitProtocol(unittest.TestCase):
    def test_split_files_unchanged_since_phase3(self):
        for protocol in PROTOCOLS:
            manifest = jload(SPLITS_DIR / protocol / "manifest.json")
            for rec in manifest["files"]:
                path = ROOT / rec["path"]
                self.assertTrue(path.exists(), f"切分文件缺失: {rec['path']}")
                got = sha256_file(path)
                self.assertEqual(got, rec["sha256"],
                                 f"{rec['path']} 哈希与第三阶段记录不一致")
                rows = len(pd.read_csv(path, usecols=["pair_index"]))
                self.assertEqual(rows, rec["rows"], f"{rec['path']} 行数变化")

    def test_protocol_overlap_rules(self):
        for protocol in PROTOCOLS:
            idx = ds.load_protocol(protocol)
            sets = {k: set(v.tolist()) for k, v in idx.items()}
            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
                self.assertEqual(sets[a] & sets[b], set(),
                                 f"{protocol}: {a}/{b} pair_index 交叉")

            pairs = ds.load_pairs()
            frame = pairs.frame.set_index("pair_index", drop=False)

            def ids(subset: str, col: str) -> set:
                return set(frame.loc[idx[subset], col].astype(str))

            for col in GROUP_RULES[protocol]:
                for other in ("validation", "test"):
                    self.assertFalse(ids("train", col) & ids(other, col),
                                     f"{protocol}: {col} 在 train/{other} 交叉")

    def test_training_pipeline_never_reads_test(self):
        """动态探针：把 test 索引访问变成异常，prepare_data 必须仍能完成。"""
        import common as mt_common

        def make_guarded(real):
            def guarded(protocol, splits_dir=None):
                idx = real(protocol, splits_dir)

                class _NoTest(dict):
                    def __getitem__(self, key):
                        if key == "test":
                            raise AssertionError("训练流程读取了 test 集")
                        return dict.__getitem__(self, key)

                return _NoTest(idx)
            return guarded

        real_ds, real_common = ds.load_protocol, mt_common.load_protocol
        ds.load_protocol = make_guarded(real_ds)
        mt_common.load_protocol = make_guarded(real_common)
        try:
            cfg = get_train_config("ridge")
            data = mt_common.prepare_data(cfg, "candidate_cold", smoke_rows=200)
            self.assertGreater(len(data["X_train"]), 0)
            self.assertGreater(len(data["X_val"]), 0)
        finally:
            ds.load_protocol = real_ds
            mt_common.load_protocol = real_common

    def test_run_records_mark_test_unused(self):
        runs_dir = ROOT / "reports" / "model-training" / "runs"
        recs = [jload(p) for p in sorted(runs_dir.glob("*.json"))] if runs_dir.exists() else []
        if not recs:
            self.skipTest("尚无训练 run 记录")
        for r in recs:
            self.assertFalse(r.get("test_used_during_training", True),
                             f"{r.get('run_id')} 记录显示训练期间使用了 test")


if __name__ == "__main__":
    unittest.main()
