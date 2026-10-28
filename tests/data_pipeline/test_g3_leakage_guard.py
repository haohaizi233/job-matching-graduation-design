# -*- coding: utf-8 -*-
"""G3：目标泄漏防护。

不只搜索 CSV 列名，还检查实际构建的 DataFrame、NumPy/Tensor 特征矩阵与最终样本 Schema。
覆盖：静态黑名单命中、ID 列当特征、目标列混入特征、派生评分间接重建。
"""
from __future__ import annotations

import unittest

import numpy as np

from _util import cfg, jload, read_csv
from job_matching.policy import (audit_feature_set, check_feature_columns,
                                 detect_indirect_leakage, assert_tensor_features)
from job_matching.pair_features import NUMERIC_FEATURE_COLUMNS


class G3LeakageGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = cfg()
        cls.c = c
        cls.features = read_csv(c.out("processed_matching") / "features_pairs.csv")
        cls.targets = read_csv(c.out("processed_matching") / "targets_pairs.csv")
        cls.edu_in = read_csv(c.out("processed_education") / "education_inputs.csv")
        cls.edu_lab = read_csv(c.out("processed_education") / "education_labels.csv")
        cls.schema_doc = jload(c.out("processed_matching") / "feature_schema.json")
        cls.matrix = np.load(c.out("processed_matching") /
                             "feature_matrix_match_label_strength.npz",
                             allow_pickle=True)

    # ---------------- 静态黑名单
    def test_forbidden_score_fields_not_in_features(self):
        forbidden = set(self.c.derived_score_chain())
        hit = forbidden & set(self.features.columns)
        self.assertEqual(hit, set(), f"派生评分字段进入特征表: {hit}")

    def test_feature_columns_pass_task_policy(self):
        cols = [c for c in self.features.columns if c not in ("candidate_id", "job_id")]
        res = check_feature_columns("match_label_strength", cols,
                                    raise_on_violation=False)
        self.assertTrue(res.ok, f"违反任务特征策略: {res.violations}")

    def test_target_columns_not_in_features(self):
        task = self.c.task("match_label_strength")
        targets = set(task["target_columns"]) | set(task["target_derived_columns"])
        hit = targets & set(self.features.columns)
        self.assertEqual(hit, set(), f"目标列混入特征表: {hit}")

    def test_id_columns_are_metadata_not_features(self):
        id_like = set(self.c.id_like_columns())
        feature_cols = set(self.schema_doc["all_feature_columns"])
        self.assertEqual(id_like & feature_cols, set())
        self.assertEqual(id_like & set(self.schema_doc["numeric_feature_columns"]), set())

    # ---------------- 物理隔离
    def test_targets_physically_isolated_from_features(self):
        share = (set(self.features.columns) & set(self.targets.columns)) - {
            "candidate_id", "job_id"}
        self.assertEqual(share, set(),
                         f"目标文件与特征文件共享了非键列: {share}")

    def test_education_inputs_do_not_contain_label_columns(self):
        forbidden = set(self.c.task("edu_label_multilabel")["forbidden_features"])
        hit = forbidden & set(self.edu_in.columns)
        self.assertEqual(hit, set(), f"学历输入表含标签/模型输出列: {hit}")
        leak_like = {"label_tokens_json", "label_multi_hot", "label_status",
                     "assistant", "ai", "diff"}
        self.assertEqual(leak_like & set(self.edu_in.columns), set())

    def test_education_labels_do_not_contain_features(self):
        feat_like = {"user_norm", "slot_education_norm", "user_len"}
        self.assertEqual(feat_like & set(self.edu_lab.columns), set())

    # ---------------- 矩阵级检查
    def test_matrix_feature_names_within_policy(self):
        names = [str(x) for x in self.matrix["feature_names"].tolist()]
        self.assertEqual(names, NUMERIC_FEATURE_COLUMNS)
        check_feature_columns("match_label_strength", names)

    def test_matrix_matches_declared_columns(self):
        X = self.matrix["X"]
        names = [str(x) for x in self.matrix["feature_names"].tolist()]
        self.assertEqual(X.shape, (len(self.features), len(names)))
        ref = self.features[names].to_numpy(dtype=np.float32)
        self.assertTrue(np.allclose(X, ref, rtol=0, atol=1e-6),
                         "特征矩阵与特征表数值不一致")

    def test_tensor_feature_matrix_passes_policy(self):
        import torch
        names = [str(x) for x in self.matrix["feature_names"].tolist()]
        t = torch.from_numpy(self.matrix["X"])
        self.assertEqual(tuple(t.shape), (len(self.features), len(names)))
        assert_tensor_features("match_label_strength", names, tuple(t.shape))

    # ---------------- 间接泄漏
    def test_features_cannot_reconstruct_derived_scores(self):
        reference = {c: self.targets[c].to_numpy(dtype=np.float64)
                     for c in ("final_score", "candidate_rank", "candidate_rank_pct")
                     if c in self.targets.columns}
        for col in self.c.derived_score_chain():
            if col in self.targets.columns and col not in reference:
                reference[col] = self.targets[col].to_numpy(dtype=np.float64)
        num = self.features[NUMERIC_FEATURE_COLUMNS]
        findings = detect_indirect_leakage(num, reference, "match_label_strength")
        hard = [f for f in findings if f.get("severity") != "warn"]
        self.assertEqual(hard, [], f"检出间接泄漏: {hard}")

    def test_audit_feature_set_reports_no_violation(self):
        reference = {"final_score": self.targets["final_score"].to_numpy(dtype=np.float64)}
        res = audit_feature_set("match_label_strength",
                                self.features[NUMERIC_FEATURE_COLUMNS], reference,
                                raise_on_violation=False)
        self.assertTrue(res.ok, f"特征集审计未通过: {res.violations}")

    def test_no_forbidden_field_in_any_declared_allowed_feature(self):
        task = self.c.task("match_label_strength")
        forbidden = set(task["forbidden_features"]) | set(self.c.always_forbidden())
        allowed = {a.split(".", 1)[-1] for a in task["allowed_features"]}
        self.assertEqual(forbidden & allowed, set(),
                         "白名单与黑名单存在冲突条目")

    def test_derived_score_chain_listed_as_forbidden_for_both_matching_tasks(self):
        chain = set(self.c.derived_score_chain())
        for task in ("match_label_strength", "match_ranking"):
            f = set(self.c.task(task)["forbidden_features"])
            self.assertTrue(chain <= f, f"{task} 的黑名单缺少派生评分字段: {chain - f}")


if __name__ == "__main__":
    unittest.main()
