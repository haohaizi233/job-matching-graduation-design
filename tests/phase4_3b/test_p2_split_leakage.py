# -*- coding: utf-8 -*-
"""P2 切分互斥 / 文本哈希重叠 / 归一化与负采样泄漏。

覆盖任务书 7.2 检查点：resume_id 重叠、job_id 重叠、文本哈希重叠、
特征标准化泄漏（IL-1~IL-6 规则登记）、标注信息泄漏、特征/目标物理隔离。
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

SPLITS = ROOT / "data/splits/matching"
PROCESSED = ROOT / "data/processed/matching"
PROTOCOLS = ("candidate_cold", "job_cold", "double_cold")
SUBSETS = ("train", "validation", "test")
KEY_COLS = ("pair_index", "candidate_id", "job_id")


def _subset_df(proto: str, sub: str) -> pd.DataFrame:
    return pd.read_csv(SPLITS / proto / f"{sub}.csv", encoding="utf-8", low_memory=False)


def _manifest(proto: str) -> dict:
    return json.loads((SPLITS / proto / "manifest.json").read_text(encoding="utf-8"))


class P2SplitLeakage(unittest.TestCase):
    def test_protocol_files_exist(self):
        for proto in PROTOCOLS:
            for name in (*SUBSETS, "excluded"):
                p = SPLITS / proto / f"{name}.csv"
                self.assertTrue(p.exists(), f"{proto}/{name}.csv 应存在")
            self.assertTrue((SPLITS / proto / "manifest.json").exists())

    def test_split_schema_is_pair_level(self):
        for proto in PROTOCOLS:
            for sub in SUBSETS:
                cols = list(_subset_df(proto, sub).columns)
                self.assertEqual(sorted(cols), sorted(KEY_COLS),
                                 f"{proto}/{sub} 列结构应为 {KEY_COLS}")

    def test_pair_index_disjoint_across_subsets(self):
        for proto in PROTOCOLS:
            seen: dict[int, str] = {}
            for sub in SUBSETS:
                ids = _subset_df(proto, sub)["pair_index"].astype("int64").tolist()
                for v in ids:
                    self.assertNotIn(v, seen,
                                     f"{proto} pair_index={v} 同时出现在 "
                                     f"{seen.get(v)} 与 {sub}")
                    seen[v] = sub

    def test_candidate_cold_candidate_disjoint(self):
        cols = {s: set(_subset_df("candidate_cold", s)["candidate_id"].astype(str))
                for s in SUBSETS}
        self.assertEqual(set(), cols["train"] & cols["validation"])
        self.assertEqual(set(), cols["train"] & cols["test"])
        self.assertEqual(set(), cols["validation"] & cols["test"])
        self.assertGreater(len(cols["train"]), 0)

    def test_job_cold_job_disjoint(self):
        cols = {s: set(_subset_df("job_cold", s)["job_id"].astype(str))
                for s in SUBSETS}
        self.assertEqual(set(), cols["train"] & cols["validation"])
        self.assertEqual(set(), cols["train"] & cols["test"])
        self.assertEqual(set(), cols["validation"] & cols["test"])
        self.assertGreater(len(cols["train"]), 0)

    def test_double_cold_both_disjoint(self):
        for col in ("candidate_id", "job_id"):
            cols = {s: set(_subset_df("double_cold", s)[col].astype(str))
                    for s in SUBSETS}
            self.assertEqual(set(), cols["train"] & cols["validation"], col)
            self.assertEqual(set(), cols["train"] & cols["test"], col)
            self.assertEqual(set(), cols["validation"] & cols["test"], col)

    def test_excluded_rows_kept_not_deleted(self):
        for proto in PROTOCOLS:
            excluded = SPLITS / proto / "excluded.csv"
            self.assertTrue(excluded.exists(), f"{proto}/excluded.csv 应存在（保留而非删除）")
        n_double = sum(1 for _ in open(SPLITS / "double_cold" / "excluded.csv",
                                       encoding="utf-8")) - 1
        self.assertGreater(n_double, 0,
                           "double_cold 无法双向隔离的配对应保留在 excluded.csv")

    def test_manifest_overlap_stats_match_recomputation(self):
        for proto in PROTOCOLS:
            m = _manifest(proto)
            oc = m.get("overlap_check")
            self.assertIsInstance(oc, dict, f"{proto} manifest 必须记录 overlap_check")
            self.assertIn("pair_overlap", oc)
            for pair_key, (a, b) in {"train&test": ("train", "test"),
                                     "train&validation": ("train", "validation"),
                                     "validation&test": ("validation", "test")}.items():
                self.assertEqual(0, oc["pair_overlap"][pair_key],
                                 f"{proto} pair_overlap {pair_key} 必须为 0")
                # 重算 pair_index 交集，验证 manifest 不是空口声明
                sa = set(_subset_df(proto, a)["pair_index"].astype("int64"))
                sb = set(_subset_df(proto, b)["pair_index"].astype("int64"))
                self.assertEqual(0, len(sa & sb))

    def test_manifest_declares_group_key_matches_protocol(self):
        expect = {"candidate_cold": {"candidate_id"}, "job_cold": {"job_id"},
                  "double_cold": {"candidate_id", "job_id"}}
        for proto, keys in expect.items():
            gk = _manifest(proto).get("group_key")
            gk_set = set(gk) if isinstance(gk, (list, tuple)) else {gk}
            self.assertEqual(keys, gk_set,
                             f"{proto} group_key 与协议不符: {gk}")

    def test_manifest_file_hashes_match_content(self):
        for proto in PROTOCOLS:
            for rec in _manifest(proto).get("files", []):
                p = ROOT / rec["path"]
                self.assertTrue(p.exists(), f"清单登记的 {rec['path']} 不存在")
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                self.assertEqual(rec["sha256"], digest,
                                 f"{rec['path']} 内容与 manifest 登记哈希不一致（疑似被改动）")

    def test_features_have_no_target_or_forbidden_columns(self):
        """IL-3/IL-4/IL-5：派生评分链与标签列不得进入特征表。"""
        schema = json.loads((PROCESSED / "feature_schema.json").read_text(encoding="utf-8"))
        feats = pd.read_csv(PROCESSED / "features_pairs.csv", nrows=5,
                            encoding="utf-8", low_memory=False)
        cols = set(feats.columns)
        bad = set(schema["forbidden_features"]) & cols
        self.assertEqual(set(), bad, f"特征表包含禁止列: {bad}")
        for col in ("label_strength", "final_score", "candidate_rank",
                    "candidate_rank_pct", "label_ordinal", "relevance_role"):
            self.assertNotIn(col, cols, f"特征表不得包含标注/目标列 {col}")

    def test_feature_columns_pass_policy_check(self):
        from job_matching.policy import check_feature_columns
        schema = json.loads((PROCESSED / "feature_schema.json").read_text(encoding="utf-8"))
        cols = list(schema["all_feature_columns"])
        res = check_feature_columns("match_ranking", cols, raise_on_violation=False)
        self.assertTrue(res.ok,
                        f"登记特征列未通过策略检查: {res.violations[:5]}")

    def test_id_columns_only_as_keys_never_as_features(self):
        feats = pd.read_csv(PROCESSED / "features_pairs.csv", nrows=5,
                            encoding="utf-8", low_memory=False)
        schema = json.loads((PROCESSED / "feature_schema.json").read_text(encoding="utf-8"))
        id_cols = {"candidate_id", "job_id"}
        # ID 列可以作为连接键存在，但绝不能出现在登记的特征列里
        self.assertEqual(set(), id_cols & set(schema["all_feature_columns"]))
        self.assertTrue(id_cols <= set(feats.columns), "连接键应保留在特征表以便对齐")

    def test_targets_file_physically_separate(self):
        tg = pd.read_csv(PROCESSED / "targets_pairs.csv", nrows=5,
                         encoding="utf-8", low_memory=False)
        self.assertIn("label_strength", tg.columns)
        self.assertIn("final_score", tg.columns)
        self.assertTrue((PROCESSED / "features_pairs.csv").exists())

    def test_no_pair_level_random_split(self):
        """同 candidate 的记录必须整体落在同一子集（candidate_cold）。"""
        holder: dict[str, set] = {}
        for sub in SUBSETS:
            holder[sub] = set(_subset_df("candidate_cold", sub)["candidate_id"].astype(str))
        self.assertEqual(set(), holder["train"] & holder["test"])
        self.assertEqual(set(), holder["train"] & holder["validation"])

    def test_text_hash_overlap_double_cold(self):
        """文本哈希重叠审计（double_cold）：
        1. pair 级（简历画像文本 + 岗位文本）跨子集必须严格互斥；
        2. 实体级近似重复（不同 ID 相同画像文本）单独计量并写入证据文件，
           超过回归容忍上限（2%）即失败 —— 这是**回归防线**，不是「零泄漏」声明。
        """
        cv_cols = ["target_position_norm", "inferred_category", "cv_skills_canonical_json"]
        job_cols = ["job_title_norm", "job_category", "job_skills_canonical_json"]
        feats = pd.read_csv(PROCESSED / "features_pairs.csv", encoding="utf-8",
                            low_memory=False)
        splits = {s: _subset_df("double_cold", s) for s in SUBSETS}

        def _entity_hash(id_col: str, cols: list[str]) -> dict[str, str]:
            out: dict[str, str] = {}
            for key, grp in feats.groupby(feats[id_col].astype(str)):
                text = "|".join(sorted({str(v) for c in cols
                                        for v in grp[c].fillna("").tolist()}))
                out[key] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return out

        cv_hash = _entity_hash("candidate_id", cv_cols)
        job_hash = _entity_hash("job_id", job_cols)

        # ---- 1. pair 级文本哈希互斥（硬性）
        pair_hash: dict[str, str] = {}
        for (c, j), grp in feats.groupby([feats["candidate_id"].astype(str),
                                          feats["job_id"].astype(str)]):
            text = "|".join(sorted({str(v) for col in cv_cols + job_cols
                                    for v in grp[col].fillna("").tolist()}))
            pair_hash[f"{c}|{j}"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        seen: dict[str, str] = {}
        for sub in SUBSETS:
            df = splits[sub]
            for key in (f"{c}|{j}" for c, j in zip(df["candidate_id"].astype(str),
                                                   df["job_id"].astype(str))):
                digest = pair_hash.get(key)
                if digest is None:
                    continue
                if digest in seen:
                    self.assertEqual(seen[digest], sub,
                                     f"pair 文本哈希 {digest[:12]} 跨 "
                                     f"{seen[digest]}/{sub} 重复（严格泄漏）")
                seen[digest] = sub

        # ---- 2. 实体级近似重复计量（回归防线 + 证据落盘）
        report: dict = {"protocol": "double_cold", "unit": "normalized_profile_text_hash"}
        for name, id_col, hmap in (("candidate", "candidate_id", cv_hash),
                                   ("job", "job_id", job_hash)):
            sets = {s: {hmap[i] for i in df[id_col].astype(str).unique() if i in hmap}
                    for s, df in splits.items()}
            counts = {
                "train&test": len(sets["train"] & sets["test"]),
                "train&validation": len(sets["train"] & sets["validation"]),
                "validation&test": len(sets["validation"] & sets["test"]),
            }
            n_test = max(len(sets["test"]), 1)
            report[name] = {
                "overlap_hash_counts": counts,
                "test_entities": len(sets["test"]),
                "train_and_test_rate": round(counts["train&test"] / n_test, 6),
            }
            self.assertLess(
                counts["train&test"] / n_test, 0.02,
                f"{name} 实体级文本哈希在 double_cold train/test 间重叠 "
                f"{counts['train&test']}/{len(sets['test'])}，超过 2% 回归容忍上限："
                f"历史 phase3-v1 切分存在近似重复，需在新 Gold 中隔离")

        out_dir = ROOT / "reports/phase4-3b"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "split-text-overlap.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_scaler_leakage_rules_registered(self):
        """IL-1/IL-2/IL-6：归一化与词表统计只能在 train 上拟合（规则必须登记在案）。"""
        schema = json.loads((PROCESSED / "feature_schema.json").read_text(encoding="utf-8"))
        rules = {r["id"]: r["rule"] for r in schema.get("indirect_leakage_rules", [])}
        for rid in ("IL-1", "IL-2", "IL-3", "IL-4", "IL-5", "IL-6"):
            self.assertIn(rid, rules, f"{rid} 泄漏防护规则必须登记")
        self.assertIn("train", rules["IL-1"])


if __name__ == "__main__":
    unittest.main()
