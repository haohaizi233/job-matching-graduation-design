# -*- coding: utf-8 -*-
"""P7 特征融合：硬/软约束语义、可解释明细、权重来源登记、非法权重拒绝。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.models.fusion import (  # noqa: E402
    DEFAULT_WEIGHTS, FeatureFusion, FusionConfig, WeightProvenance, education_rank)

RESUME = {
    "education_level": "硕士",
    "skills": {"Python", "SQL", "机器学习"},
    "years_experience": 3.0,
    "inferred_category": "IT",
    "city": "上海",
    "target_position": "算法工程师",
}
JOB_OK = {
    "education_tokens": ["本科"],
    "skills": {"Python", "SQL"},
    "years_min": 1.0,
    "category": "IT",
    "city": "上海",
    "job_title": "算法工程师",
}


class P7FeatureFusion(unittest.TestCase):
    def test_default_weights_sum_to_one(self):
        self.assertAlmostEqual(1.0, sum(DEFAULT_WEIGHTS.values()), places=6)

    def test_weight_provenance_is_manual_not_trained(self):
        prov = WeightProvenance()
        self.assertEqual("analyst_set_manual", prov.source)
        self.assertIsNone(prov.fitted_on, "人工权重不得伪装为训练结果")
        self.assertIsNone(prov.run_id)
        self.assertIn("不是", prov.basis)

    def test_unknown_component_rejected(self):
        cfg = FusionConfig(weights={**DEFAULT_WEIGHTS, "magic": 0.1})
        with self.assertRaises(ValueError):
            FeatureFusion(cfg).score(RESUME, JOB_OK)

    def test_weights_must_sum_to_one(self):
        cfg = FusionConfig(weights={**DEFAULT_WEIGHTS,
                                    "semantic": DEFAULT_WEIGHTS["semantic"] + 0.1})
        with self.assertRaises(ValueError):
            FeatureFusion(cfg).score(RESUME, JOB_OK)

    def test_happy_path_breakdown_is_explainable(self):
        bd = FeatureFusion().score(RESUME, JOB_OK, semantic_score=0.8)
        d = bd.to_dict()
        self.assertFalse(d["filtered"])
        self.assertIsNone(d["filter_reason"])
        self.assertGreater(d["total"], 0.0)
        self.assertEqual(set(DEFAULT_WEIGHTS), set(d["contributions"]))
        self.assertEqual(set(DEFAULT_WEIGHTS), set(d["weights"]))
        names = [c["name"] for c in d["constraints"]]
        for expected in ("semantic", "skill", "education", "experience",
                         "category", "intent"):
            self.assertIn(expected, names)
        for c in d["constraints"]:
            self.assertIn(c["kind"], ("hard", "soft"))
            self.assertTrue(c["reason"], "每条判定必须给出原因")
        json.dumps(d, ensure_ascii=False)  # 明细必须可序列化

    def test_total_equals_weighted_contributions(self):
        bd = FeatureFusion().score(RESUME, JOB_OK, semantic_score=0.7)
        self.assertAlmostEqual(bd.total,
                               round(sum(bd.contributions.values()), 6),
                               places=5)

    def test_hard_education_filters_and_records_reason(self):
        resume = {**RESUME, "education_level": "大专"}
        job = {**JOB_OK, "education_tokens": ["硕士"]}
        bd = FeatureFusion().score(resume, job)
        self.assertTrue(bd.filtered, "学历低于岗位硬性要求必须过滤")
        self.assertEqual(0.0, bd.total)
        self.assertIn("学历不满足", bd.filter_reason)
        edu = [c for c in bd.constraints if c.name == "education"][0]
        self.assertEqual("hard", edu.kind)
        self.assertFalse(edu.passed)

    def test_soft_constraints_never_filter(self):
        job = {**JOB_OK, "city": "北京", "category": "FINANCE"}
        bd = FeatureFusion().score(RESUME, job, semantic_score=0.1)
        self.assertFalse(bd.filtered, "软约束（城市/类别不一致）不得淘汰候选")
        self.assertGreater(bd.total, 0.0)
        intent = [c for c in bd.constraints if c.name == "intent"][0]
        self.assertEqual(0.0, intent.score)
        self.assertTrue(intent.passed)

    def test_unparseable_education_is_neutral_not_filtered(self):
        resume = {**RESUME, "education_level": ""}
        job = {**JOB_OK, "education_tokens": ["硕士"]}
        bd = FeatureFusion().score(resume, job)
        self.assertFalse(bd.filtered, "学历无法解析应中性处理，不得误杀")
        edu = [c for c in bd.constraints if c.name == "education"][0]
        self.assertEqual(0.5, edu.score)

    def test_missing_semantic_score_is_neutral(self):
        bd = FeatureFusion().score(RESUME, JOB_OK)
        sem = [c for c in bd.constraints if c.name == "semantic"][0]
        self.assertEqual(0.5, sem.score)
        self.assertIn("未提供", sem.reason)

    def test_missing_experience_years_is_neutral(self):
        resume = {**RESUME, "years_experience": float("nan")}
        bd = FeatureFusion().score(resume, JOB_OK)
        exp = [c for c in bd.constraints if c.name == "experience"][0]
        self.assertEqual(0.5, exp.score)
        self.assertFalse(bd.filtered)

    def test_experience_gap_softly_decays(self):
        resume = {**RESUME, "years_experience": 0.0}
        job = {**JOB_OK, "years_min": 2.0}
        bd = FeatureFusion().score(resume, job)
        exp = [c for c in bd.constraints if c.name == "experience"][0]
        self.assertAlmostEqual(0.0, exp.score, places=6)
        self.assertTrue(bd.filtered is False)

    def test_skill_coverage_score(self):
        resume = {**RESUME, "skills": {"Python"}}
        job = {**JOB_OK, "skills": {"Python", "SQL"}}
        bd = FeatureFusion().score(resume, job, semantic_score=1.0)
        skill = [c for c in bd.constraints if c.name == "skill"][0]
        self.assertAlmostEqual(0.5, skill.score, places=6)
        self.assertIn("1/2", skill.reason)

    def test_missing_profile_hard_filter_when_configured(self):
        cfg = FusionConfig(hard_missing_profile=True)
        bd = FeatureFusion(cfg).score({"education_level": "", "skills": set()}, JOB_OK)
        self.assertTrue(bd.filtered)
        self.assertIn("缺失", bd.filter_reason)

    def test_education_rank_ordering(self):
        self.assertGreater(education_rank("博士"), education_rank("硕士"))
        self.assertGreater(education_rank("硕士"), education_rank("本科"))
        self.assertGreater(education_rank("本科"), education_rank("大专"))
        self.assertEqual(0, education_rank("无法解析"))
        self.assertEqual(0, education_rank(""))

    def test_deterministic_scoring(self):
        a = FeatureFusion().score(RESUME, JOB_OK, semantic_score=0.42).to_dict()
        b = FeatureFusion().score(RESUME, JOB_OK, semantic_score=0.42).to_dict()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
