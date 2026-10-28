# -*- coding: utf-8 -*-
"""G2：字段约束。

验证主键有效、必需字段存在、向量长度正确、数值字段类型正确、多标签编码符合词表、
无非法 ID 映射。全部针对**实际落盘的产物**，不是只看 CSV 列名。
"""
from __future__ import annotations

import json
import unittest

import numpy as np

from _util import ROOT, cfg, jload, read_csv


class G2FieldConstraints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = cfg()
        cls.c = c
        cls.resume = read_csv(c.out("interim_matching") / "resume_normalized.csv")
        cls.job = read_csv(c.out("interim_matching") / "job_normalized.csv")
        cls.features = read_csv(c.out("processed_matching") / "features_pairs.csv")
        cls.targets = read_csv(c.out("processed_matching") / "targets_pairs.csv")
        cls.edu_in = read_csv(c.out("processed_education") / "education_inputs.csv")
        cls.edu_lab = read_csv(c.out("processed_education") / "education_labels.csv")

    # ---------------- 主键
    def test_resume_primary_key_unique(self):
        self.assertTrue(self.resume["candidate_id"].is_unique)
        self.assertEqual(int(self.resume["candidate_id"].isna().sum()), 0)

    def test_job_primary_key_unique(self):
        self.assertTrue(self.job["job_id"].is_unique)
        self.assertEqual(int(self.job["job_id"].isna().sum()), 0)

    def test_match_composite_key_unique(self):
        dup = int(self.targets.duplicated(["candidate_id", "job_id"]).sum())
        self.assertEqual(dup, 0, f"(candidate_id, job_id) 重复 {dup} 行")

    def test_education_record_key_unique(self):
        self.assertTrue(self.edu_lab["record_key"].is_unique)

    # ---------------- 外键
    def test_match_foreign_keys_complete(self):
        cand = set(self.resume["candidate_id"].astype(str))
        jobs = set(self.job["job_id"].astype(str))
        orphan_c = set(self.targets["candidate_id"].astype(str)) - cand
        orphan_j = set(self.targets["job_id"].astype(str)) - jobs
        self.assertEqual(orphan_c, set(), f"孤儿 candidate_id {len(orphan_c)} 个")
        self.assertEqual(orphan_j, set(), f"孤儿 job_id {len(orphan_j)} 个")

    # ---------------- 向量
    def test_embedding_cache_shape_dtype_finite(self):
        d = c = self.c.out("processed_embeddings")
        for side, rows in (("cv", len(self.resume)), ("job", len(self.job))):
            a = np.load(d / f"{side}_embeddings.npy")
            self.assertEqual(a.dtype, np.float32)
            self.assertEqual(a.shape, (rows, 768), f"{side} 向量形状异常")
            self.assertTrue(np.isfinite(a).all(), f"{side} 含 NaN/Inf")

    def test_id_map_is_bijection(self):
        d = self.c.out("processed_embeddings")
        for side in ("cv", "job"):
            m = jload(d / f"{side}_id_map.json")
            self.assertEqual(len(m["id_to_row"]), len(m["row_to_id"]))
            for k, v in m["id_to_row"].items():
                self.assertEqual(m["row_to_id"][v], k, f"{side} ID 映射不可逆")
            self.assertEqual(sorted(m["id_to_row"].values()),
                             list(range(len(m["row_to_id"]))), f"{side} 行号不连续")

    # ---------------- 数值字段
    def test_pair_numeric_features_finite_and_bounded(self):
        cols = ["skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
                "position_token_overlap", "category_match", "years_experience"]
        X = self.features[cols].to_numpy(dtype=np.float64)
        self.assertTrue(np.isfinite(X).all(), "pair 数值特征含 NaN/Inf")
        for col in cols[:4]:
            v = self.features[col].to_numpy(dtype=np.float64)
            self.assertTrue((v >= 0).all() and (v <= 1).all(), f"{col} 超出 [0,1]")
        self.assertTrue(set(self.features["category_match"].unique()) <= {0.0, 1.0})

    def test_label_strength_in_declared_enum(self):
        allowed = set(self.c.task("match_label_strength")["target_columns"]) | {
            "weak_positive", "medium_positive", "strong_positive"}
        vals = set(self.targets["label_strength"].unique())
        self.assertTrue(vals <= {"weak_positive", "medium_positive", "strong_positive"},
                        f"非法 label_strength: {vals - allowed}")

    def test_label_ordinal_consistent(self):
        m = {"weak_positive": 1, "medium_positive": 2, "strong_positive": 3}
        expect = self.targets["label_strength"].map(m)
        self.assertTrue((expect.to_numpy() == self.targets["label_ordinal"].to_numpy()).all())

    # ---------------- 多标签编码
    def test_education_multihot_matches_vocabulary(self):
        order = self.c.label_order
        for rec_key, mh, toks in zip(self.edu_lab["record_key"],
                                     self.edu_lab["label_multi_hot"],
                                     self.edu_lab["label_tokens_json"]):
            s = str(mh)
            self.assertEqual(len(s), len(order), f"多热向量长度错误: {rec_key}")
            self.assertTrue(set(s) <= {"0", "1"}, f"多热向量含非法值: {rec_key}")
            got = {order[i] for i, ch in enumerate(s) if ch == "1"}
            want = set(json.loads(toks))
            self.assertEqual(got, want, f"多热向量与 token 列表不一致: {rec_key}")
            break  # 抽查一条 + 下面的批量检查

    def test_education_multihot_all_rows_valid(self):
        order = self.c.label_order
        bad = 0
        for mh, toks in zip(self.edu_lab["label_multi_hot"].astype(str),
                            self.edu_lab["label_tokens_json"].astype(str)):
            if len(mh) != len(order) or set(mh) - {"0", "1"}:
                bad += 1
                continue
            if {order[i] for i, ch in enumerate(mh) if ch == "1"} != set(json.loads(toks)):
                bad += 1
        self.assertEqual(bad, 0, f"{bad} 行多热编码与词表不一致")

    def test_education_tokens_within_vocabulary_or_flagged(self):
        order = set(self.c.label_order)
        oov_rows = 0
        for toks, status in zip(self.edu_lab["label_tokens_json"].astype(str),
                                self.edu_lab["label_status"].astype(str)):
            for t in json.loads(toks):
                if t not in order:
                    oov_rows += 1
                    self.assertEqual(status, "oov_token",
                                     f"词表外 token 未标记 oov_token: {t}")
        # 词表外 token 必须被 unresolved 保留而不是混进 tokens
        for toks, unres in zip(self.edu_lab["label_tokens_json"].astype(str),
                               self.edu_lab["unresolved_tokens_json"].astype(str)):
            for t in json.loads(toks):
                self.assertNotIn(t, json.loads(unres),
                                 "同一 token 同时出现在规范 token 与 unresolved")

    # ---------------- ID 映射无非法
    def test_no_numeric_id_in_feature_columns(self):
        """ID 列只能作为 join 键 / 评估元数据随表携带，绝不能成为特征列。

        features_pairs.csv 携带 candidate_id / job_id 仅用于与 matches 关联
        （见 baseline_ranking 的 merge），因此检查对象是"特征列声明"与
        "去掉键列后的实际列"，而不是键列本身。
        """
        id_like = set(self.c.id_like_columns())
        key_cols = {"candidate_id", "job_id"}
        non_key_cols = set(self.features.columns) - key_cols
        hit = id_like & non_key_cols
        self.assertEqual(hit, set(), f"ID 列出现在特征列中: {hit}")
        schema = jload(self.c.out("processed_matching") / "feature_schema.json")
        self.assertEqual(id_like & set(schema["all_feature_columns"]), set())
        self.assertEqual(id_like & set(schema["numeric_feature_columns"]), set())


if __name__ == "__main__":
    unittest.main()
