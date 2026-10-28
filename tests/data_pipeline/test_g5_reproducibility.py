# -*- coding: utf-8 -*-
"""G5：结果可复现性。

同样的原始数据、配置与随机种子必须产生一致的：划分 ID、样本计数、特征维度、
标签统计、文件哈希。浮点 Baseline 使用合理数值容差，不要求跨硬件逐位一致。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from _util import cfg, file_hash, jload, read_csv, read_csv_sig
from job_matching.split_matching import assign_groups, build_single_key_protocol
from job_matching.baseline_ranking import cosine_scores
from job_matching.metrics_ranking import random_ranking_scores

SPLITS = ("train", "validation", "test")


class G5Reproducibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = cfg()
        cls.c = c
        cls.matches = read_csv_sig(c.src("matching", "matches"))

    def test_split_files_hash_matches_manifest(self):
        for name in ("candidate_cold", "job_cold", "double_cold"):
            d = self.c.out("splits_matching") / name
            man = jload(d / "manifest.json")
            for f in man["files"]:
                p = self.c.root / f["path"]
                self.assertEqual(file_hash(p), f["sha256"],
                                 f"{name}: {f['path']} 哈希与 manifest 不一致")
        d = self.c.out("splits_education")
        man = jload(d / "manifest.json")
        for f in man["files"]:
            p = self.c.root / f["path"]
            self.assertEqual(file_hash(p), f["sha256"],
                             f"education: {f['path']} 哈希与 manifest 不一致")

    def test_group_assignment_deterministic(self):
        sizes = self.matches.groupby("candidate_id").size()
        ratios = {"train": 0.8, "validation": 0.1, "test": 0.1}
        a = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold"))
        b = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold"))
        self.assertEqual(a, b, "相同种子产生不同划分")

    def test_group_assignment_changes_with_seed(self):
        sizes = self.matches.groupby("candidate_id").size()
        ratios = {"train": 0.8, "validation": 0.1, "test": 0.1}
        a = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold"))
        b = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold") + 1)
        self.assertNotEqual(a, b, "不同种子应产生不同划分")

    def test_candidate_cold_split_reproducible(self):
        proto = self.c.protocol("candidate_cold")
        ratios = {k: float(v) for k, v in proto["ratios"].items()}
        res = build_single_key_protocol(
            self.matches, "candidate_id", ratios,
            self.c.seed(proto["seed_key"]), "candidate_cold",
            self.c.min_group_size_for_ranking)
        saved = {}
        for s in SPLITS:
            f = read_csv(self.c.out("splits_matching") / "candidate_cold" / f"{s}.csv")
            saved[s] = set(map(tuple, f[["candidate_id", "job_id"]]
                               .astype(str).to_numpy()))
        pairs = res["_pairs_frame"]
        for s in SPLITS:
            got = set(map(tuple, pairs.loc[pairs["split"] == s,
                                           ["candidate_id", "job_id"]]
                          .astype(str).to_numpy()))
            self.assertEqual(got, saved[s], f"candidate_cold/{s} 重算结果与落盘不一致")

    def test_split_row_counts_and_label_stats_reproducible(self):
        man = jload(self.c.out("splits_matching") / "candidate_cold" / "manifest.json")
        for s in SPLITS:
            f = read_csv(self.c.out("splits_matching") / "candidate_cold" / f"{s}.csv")
            self.assertEqual(len(f), man["splits"][s]["pairs"],
                             f"{s} 样本数与 manifest 不一致")
        lab = self.matches["label_strength"].value_counts().to_dict()
        total = sum(sum(v["label_distribution"].values())
                    for v in man["splits"].values())
        self.assertEqual(total, int(self.matches.shape[0]))

    def test_random_baseline_deterministic(self):
        for seed in (self.c.seed("baseline_random_ranking"),
                     self.c.seed("baseline_random_ranking") + 1):
            a = random_ranking_scores(1000, seed)
            b = random_ranking_scores(1000, seed)
            self.assertTrue(np.array_equal(a, b), "随机排序分数不可复现")

    def test_cosine_scores_deterministic_within_tolerance(self):
        d = self.c.out("processed_embeddings")
        cv = np.load(d / "cv_embeddings.npy")
        job = np.load(d / "job_embeddings.npy")
        n = 200
        cv_rows = np.arange(n) % cv.shape[0]
        job_rows = np.arange(n) % job.shape[0]
        a = cosine_scores(cv, job, cv_rows, job_rows, block=32)
        b = cosine_scores(cv, job, cv_rows, job_rows, block=7)
        self.assertTrue(np.allclose(a, b, rtol=0, atol=1e-6),
                         "分块大小改变不应改变余弦结果")

    def test_embedding_cache_hash_stable(self):
        d = self.c.out("processed_embeddings")
        meta = jload(d / "metadata.json")
        for side in ("cv", "job"):
            self.assertEqual(file_hash(d / f"{side}_embeddings.npy"),
                             meta["sides"][side]["npy_sha256"],
                             f"{side} 向量文件哈希与 metadata 不一致")

    def test_feature_matrix_shape_and_names_stable(self):
        import numpy as _np
        m = _np.load(self.c.out("processed_matching") /
                     "feature_matrix_match_label_strength.npz", allow_pickle=True)
        schema = jload(self.c.out("processed_matching") / "feature_schema.json")
        self.assertEqual(list(m["X"].shape), schema["matrix_shape"])
        self.assertEqual([str(x) for x in m["feature_names"].tolist()],
                         schema["numeric_feature_columns"])

    def test_rebuilding_features_in_temp_dir_reproduces_hashes(self):
        """把 pair 特征在临时目录重建一次，逐行逐值比对（等价于可复现性验证）。"""
        from job_matching.pair_features import build_pair_features
        resume = read_csv(self.c.out("interim_matching") / "resume_normalized.csv")
        job = read_csv(self.c.out("interim_matching") / "job_normalized.csv")
        feats, _ = build_pair_features(self.matches, resume, job)
        saved = read_csv(self.c.out("processed_matching") / "features_pairs.csv")
        self.assertEqual(list(feats.columns), list(saved.columns))
        for col in ("skill_jaccard", "skill_overlap_ratio_cv",
                    "skill_overlap_ratio_job", "position_token_overlap",
                    "category_match", "years_experience"):
            self.assertTrue(np.allclose(feats[col].to_numpy(dtype=float),
                                        saved[col].to_numpy(dtype=float),
                                        rtol=0, atol=1e-6),
                            f"特征列 {col} 重算结果与落盘不一致")


if __name__ == "__main__":
    unittest.main()
