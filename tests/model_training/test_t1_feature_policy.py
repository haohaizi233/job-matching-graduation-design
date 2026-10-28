# -*- coding: utf-8 -*-
"""T1 特征黑名单与无标签依赖（验收项 1、12）。

  1. 派生评分 10 字段 + label_strength / ID 列绝不能进入模型输入矩阵。
 12. 推理特征构建不得查询 label_strength / final_score 等标签生成结果。
"""
from __future__ import annotations

import unittest

import numpy as np

from _util import any_run_dir, jload, synthetic_frame

from job_matching.policy import check_feature_columns, forbidden_for_task
from job_matching.training.feature_map import FeatureMap, compute_pair_raw_features
from job_matching.training.config_train import get_train_config

FORBIDDEN = sorted(forbidden_for_task("match_ranking"))


class T1FeaturePolicy(unittest.TestCase):
    def test_config_whitelist_excludes_forbidden(self):
        cfg = get_train_config("ridge")
        cols = list(cfg.common["data"]["feature_columns"]["numeric"]) + \
            list(cfg.common["data"]["feature_columns"]["categorical"])
        hit = sorted(set(cols) & set(FORBIDDEN))
        self.assertEqual(hit, [], f"配置白名单命中禁止字段: {hit}")
        for col in cols:
            check_feature_columns("match_ranking", [col], raise_on_violation=True)

    def test_feature_map_fit_rejects_forbidden(self):
        fm = FeatureMap(task="match_ranking")
        with self.assertRaises(Exception):
            fm.fit(synthetic_frame().rename(columns={"skill_jaccard": "final_score"}))

    def test_trained_model_inputs_exclude_forbidden(self):
        run = any_run_dir()
        self.assertIsNotNone(run, "没有可用的已训练模型目录")
        fm = FeatureMap.load(run / "feature_map.json")
        hit = sorted(set(fm.raw_columns_) & set(FORBIDDEN))
        self.assertEqual(hit, [], f"{run.name} 特征矩阵命中禁止字段: {hit}")
        id_hit = sorted(set(fm.raw_columns_) & {"candidate_id", "job_id", "pair_index"})
        self.assertEqual(id_hit, [], f"ID 列进入特征: {id_hit}")
        self.assertGreater(fm.n_features, 0)

    def test_inference_features_have_no_label_fields(self):
        resume = {"target_position_norm": "软件工程师", "skills_canonical_json": '["java"]',
                  "inferred_category": "INFORMATION-TECHNOLOGY", "years_experience": 3}
        job = {"job_title_norm": "java 开发", "category": "INFORMATION-TECHNOLOGY",
               "skills_canonical_json": '["java", "spring"]'}
        raw = compute_pair_raw_features(resume, job)
        hit = sorted(set(raw) & set(FORBIDDEN))
        self.assertEqual(hit, [], f"单 pair 特征键命中禁止字段: {hit}")
        # 传入标签字段也不得影响特征（推理无标签依赖）
        resume2 = dict(resume, final_score=99.0, label_strength="strong_positive")
        job2 = dict(job, candidate_rank=1)
        raw2 = compute_pair_raw_features(resume2, job2)
        for k in raw:
            if k in ("target_position_norm", "inferred_category", "job_category"):
                continue
            self.assertTrue(np.isclose(float(raw[k]), float(raw2[k])),
                            f"标签字段影响了特征 {k}")

    def test_model_matrix_values_are_finite(self):
        run = any_run_dir()
        self.assertIsNotNone(run, "没有可用的已训练模型目录")
        fm = FeatureMap.load(run / "feature_map.json")
        X = fm.transform(synthetic_frame())
        self.assertEqual(X.shape[1], fm.n_features)
        self.assertTrue(np.isfinite(X).all(), "特征矩阵出现 NaN/Inf")


if __name__ == "__main__":
    unittest.main()
