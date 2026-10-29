# -*- coding: utf-8 -*-
"""S13~S16：MatchPredictor 输入适配 / 目标值泄漏禁止 / 权重缺失降级 / 正式模式门禁。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import RESUME_TEXT, StubMatchPredictor, make_jd

from job_matching.service import (JobEducationResolver, MatchingService, ModelRegistration,
                                  ModelRegistry, ServiceError, parse_job_text,
                                  parse_resume_text, register_builtin_models)
from job_matching.service.matching import (LEAKAGE_FORBIDDEN_KEYS, LegacyMatchAdapter,
                                           assert_no_forbidden_keys)


def build_profiles():
    student = parse_resume_text(RESUME_TEXT, profile_id="stu_s13", is_synthetic=True)
    job = parse_job_text(make_jd(required="熟悉 Java、MySQL"), job_id="job_s13",
                         resolver=JobEducationResolver(None), is_synthetic=True)
    return student, job


def stub_registry(model_id: str = "legacy_match_proxy_v1", **reg_kwargs) -> ModelRegistry:
    reg = ModelRegistry(loader_impl=lambda r: StubMatchPredictor())
    reg.register(ModelRegistration(
        model_id=model_id, model_version="stub-v1", task_type="match_ranking",
        training_data_version="stub", evaluation_status="research_only_proxy_labels",
        supported_languages=["en"], artifacts=[], checksum="stub",
        limitations=["stub"], loader="legacy_match", **reg_kwargs))
    return reg


class S13MatchPredictorAdaptation(unittest.TestCase):
    """场景 13：MatchPredictor 合法输入适配。"""

    def test_build_inputs_matches_feature_contract(self):
        from job_matching.training.feature_map import (RESUME_FIELDS, JOB_FIELDS,
                                                       compute_pair_raw_features)
        student, job = build_profiles()
        resume_in, job_in = LegacyMatchAdapter.build_inputs(student, job)
        for f in RESUME_FIELDS:
            self.assertIn(f, resume_in, f"resume 缺 {f}")
        for f in JOB_FIELDS:
            self.assertIn(f, job_in, f"job 缺 {f}")
        raw = compute_pair_raw_features(resume_in, job_in)
        self.assertIn("skill_jaccard", raw)
        self.assertIn("position_token_overlap", raw)
        self.assertTrue(raw["target_position_norm"])
        # job_title_norm 不回显进 raw（保持 Phase4-1 特征口径与历史测试不变），
        # 合法性在模型输入侧验证：字段名必须就是 FeatureMap 契约名且非空
        self.assertTrue(job_in["job_title_norm"])

    def test_feature_map_encodes_without_error(self):
        import numpy as np
        import pandas as pd
        from job_matching.training.feature_map import FeatureMap, compute_pair_raw_features
        student, job = build_profiles()
        resume_in, job_in = LegacyMatchAdapter.build_inputs(student, job)
        raw = compute_pair_raw_features(resume_in, job_in)
        df = pd.DataFrame([{**raw, "years_experience": 0.0},
                           {**raw, "years_experience": 3.0,
                            "target_position_norm": "数据分析师",
                            "inferred_category": "INFORMATION-TECHNOLOGY",
                            "job_category": "FINANCE"}])
        fm = FeatureMap(groups_enabled=["skill", "position", "category", "experience"])
        fm.fit(df)
        X = fm.transform_raw(raw)
        self.assertEqual(X.shape, (1, fm.n_features))
        self.assertTrue(np.isfinite(X).all(), "缺失年限必须由 train 统计填充，不得产生 NaN")

    def test_experimental_rank_with_stub_predictor(self):
        student, job = build_profiles()
        service = MatchingService(stub_registry())
        res = service.rank(student, [job], {"mode": "experimental_model",
                                            "model_id": "legacy_match_proxy_v1"})
        self.assertEqual(res["score_type"], "model_raw_score")
        self.assertEqual(res["model_version"], "stub-run-v1")
        self.assertTrue(any("not_a_chinese_validated_model" in w for w in res["warnings"]))

    def test_model_inapplicable_when_intention_missing(self):
        from job_matching.service import parse_resume_text as prt
        student = prt("自我评价：学习能力强。", profile_id="stu_s13b", is_synthetic=True)
        _, job = build_profiles()
        with self.assertRaises(ServiceError) as ctx:
            LegacyMatchAdapter.build_inputs(student, job)
        self.assertEqual(ctx.exception.code, "MODEL_INAPPLICABLE")
        self.assertIn("student.employment_intention", ctx.exception.detail["missing_fields"])


class S14NoTargetLeakage(unittest.TestCase):
    """场景 14：禁止模型目标值泄漏。"""

    def test_forbidden_keys_rejected(self):
        for key in ("final_score", "candidate_rank", "label_strength", "raw_score"):
            with self.assertRaises(ServiceError) as ctx:
                assert_no_forbidden_keys({"job_id": "j1", key: 0.9})
            self.assertEqual(ctx.exception.code, "LEAKAGE_GUARD")

    def test_built_inputs_contain_no_target_fields(self):
        student, job = build_profiles()
        resume_in, job_in = LegacyMatchAdapter.build_inputs(student, job)
        self.assertFalse(set(resume_in) & set(LEAKAGE_FORBIDDEN_KEYS))
        self.assertFalse(set(job_in) & set(LEAKAGE_FORBIDDEN_KEYS))

    def test_policy_rejects_forbidden_columns(self):
        from job_matching import policy
        with self.assertRaises(Exception):
            policy.check_feature_columns("match_ranking", ["final_score"],
                                         raise_on_violation=True)

    def test_check_feature_policy_accepts_whitelist(self):
        student, job = build_profiles()
        LegacyMatchAdapter.check_feature_policy(
            ["skill_jaccard", "position_token_overlap", "years_experience",
             "target_position_norm", "inferred_category", "job_category"])

    def test_no_score_derived_fields_in_rank_results(self):
        student, job = build_profiles()
        service = MatchingService(stub_registry())
        res = service.rank(student, [job], {"mode": "experimental_model",
                                            "model_id": "legacy_match_proxy_v1"})
        blob = json.dumps(res["results"], ensure_ascii=False)
        for key in ("final_score", "candidate_rank_pct", "label_strength", "semantic_score"):
            self.assertNotIn(f'"{key}"', blob)


class S15ModelMissingDegradation(unittest.TestCase):
    """场景 15：模型权重缺失 -> 显式错误或透明降级。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ph51_s15_")
        self.run_dir = Path(self._td.name)
        (self.run_dir / "manifest.json").write_text(
            json.dumps({"model_name": "ridge", "run_id": "broken-run"}), encoding="utf-8")
        # 故意不放 model.pkl -> 权重缺失

    def tearDown(self):
        self._td.cleanup()

    def _registry(self) -> ModelRegistry:
        reg = ModelRegistry(loader_impl=lambda r: (_ for _ in ()).throw(
            FileNotFoundError("model.pkl missing")))
        reg.register(ModelRegistration(
            model_id="legacy_match_proxy_v1", model_version="broken-run",
            task_type="match_ranking", training_data_version="x",
            evaluation_status="research_only_proxy_labels", supported_languages=["en"],
            artifacts=[], checksum="", limitations=[], loader="legacy_match",
            loader_kwargs={"run_dir": str(self.run_dir)}))
        return reg

    def test_registry_load_raises_model_missing(self):
        with self.assertRaises(ServiceError) as ctx:
            self._registry().load("legacy_match_proxy_v1")
        self.assertEqual(ctx.exception.code, "MODEL_MISSING")

    def test_explicit_error_without_fallback(self):
        student, job = build_profiles()
        service = MatchingService(self._registry())
        with self.assertRaises(ServiceError) as ctx:
            service.rank(student, [job], {"mode": "experimental_model",
                                          "model_id": "legacy_match_proxy_v1",
                                          "allow_fallback": False})
        self.assertEqual(ctx.exception.code, "MODEL_MISSING")

    def test_transparent_degradation_with_fallback(self):
        student, job = build_profiles()
        service = MatchingService(self._registry())
        res = service.rank(student, [job], {"mode": "experimental_model",
                                            "model_id": "legacy_match_proxy_v1",
                                            "allow_fallback": True})
        self.assertEqual(res["score_type"], "heuristic_score")
        self.assertTrue(any(w.startswith("degraded_to_baseline") for w in res["warnings"]))

    def test_unregistered_model_raises(self):
        with self.assertRaises(ServiceError) as ctx:
            ModelRegistry().load("ghost")
        self.assertEqual(ctx.exception.code, "MODEL_MISSING")


class S16FormalModeGate(unittest.TestCase):
    """场景 16：中文不兼容 / 未验证模型拒绝正式模式。"""

    def test_english_proxy_model_rejected_in_formal_mode(self):
        student, job = build_profiles()
        service = MatchingService(stub_registry())
        with self.assertRaises(ServiceError) as ctx:
            service.rank(student, [job], {"mode": "experimental_model",
                                          "model_id": "legacy_match_proxy_v1",
                                          "formal": True})
        self.assertEqual(ctx.exception.code, "MODEL_FORMAL_USE_FORBIDDEN")
        self.assertIn("en", ctx.exception.detail["supported_languages"])

    def test_research_only_zh_model_also_rejected(self):
        reg = ModelRegistry(loader_impl=lambda r: StubMatchPredictor())
        reg.register(ModelRegistration(
            model_id="zh_research_model", model_version="v1", task_type="match_ranking",
            training_data_version="x", evaluation_status="research_only_zh",
            supported_languages=["zh"], artifacts=[], checksum="", limitations=[],
            loader="legacy_match"))
        student, job = build_profiles()
        service = MatchingService(reg)
        with self.assertRaises(ServiceError) as ctx:
            service.rank(student, [job], {"mode": "experimental_model",
                                          "model_id": "zh_research_model",
                                          "formal": True})
        self.assertEqual(ctx.exception.code, "MODEL_FORMAL_USE_FORBIDDEN")

    def test_future_verified_slot_is_not_fabricated(self):
        reg = ModelRegistry()
        register_builtin_models(reg)
        service = MatchingService(reg)
        student, job = build_profiles()
        with self.assertRaises(ServiceError) as ctx:
            service.rank(student, [job], {"mode": "future_verified"})
        self.assertEqual(ctx.exception.code, "FUTURE_MODEL_UNAVAILABLE")

    def test_baseline_allowed_but_never_calibrated(self):
        reg = ModelRegistry()
        register_builtin_models(reg)
        student, job = build_profiles()
        res = MatchingService(reg).rank(student, [job],
                                        {"mode": "baseline", "formal": True})
        self.assertEqual(res["score_type"], "heuristic_score")
        self.assertNotEqual(res["score_type"], "calibrated_score")
        self.assertTrue(any("heuristic_baseline_unvalidated" in w or
                            "score_semantics" in w for w in res["warnings"]))


if __name__ == "__main__":
    unittest.main()
