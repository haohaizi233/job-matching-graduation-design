# -*- coding: utf-8 -*-
"""P1 场景 1、2：合法配对生成 / 固定随机种子复现（协议第三节）。"""
from __future__ import annotations

import unittest

from _util import make_job, make_resume

from job_matching.annotation import pool as pool_mod
from job_matching.annotation.freeze import assign_splits
from job_matching.annotation.schema import DIFFICULTY_TIERS, PAIR_FIELDS


def _fixtures():
    resumes = [
        make_resume(0, rid="resume_000", target_position="数据分析师",
                    skills=["python", "sql", "数据分析"], education_level="本科",
                    years_experience=1.0, is_synthetic=False),
        make_resume(1, rid="resume_001", target_position="财务专员",
                    skills=["会计", "财务报表", "excel"], education_level="大专",
                    years_experience=0.0, is_synthetic=True),
    ]
    jobs = [
        make_job(0, jid="job_000", title="数据分析师", category="INFORMATION-TECHNOLOGY",
                 required=["python", "sql", "数据分析"], edu_tokens=["本科"]),
        make_job(1, jid="job_001", title="数据挖掘工程师", category="INFORMATION-TECHNOLOGY",
                 required=["机器学习", "python", "hadoop"], edu_tokens=["硕士"]),
        make_job(2, jid="job_002", title="Java开发工程师", category="INFORMATION-TECHNOLOGY",
                 required=["java", "spring", "mysql"], edu_tokens=["本科"]),
        make_job(3, jid="job_003", title="财务分析师", category="FINANCE",
                 required=["财务分析", "会计", "excel"], edu_tokens=["本科"]),
        make_job(4, jid="job_004", title="销售经理", category="SALES",
                 required=["销售", "商务谈判", "客户开发"], edu_tokens=[], exp_years=3.0),
        make_job(5, jid="job_005", title="新媒体运营", category="MARKETING-OPS",
                 required=["新媒体运营", "文案策划", "ps"], edu_tokens=[]),
    ]
    return resumes, jobs


class P1TestPairGeneration(unittest.TestCase):
    """场景 1：合法配对生成。"""

    def test_p1_pairs_have_all_required_fields(self):
        resumes, jobs = _fixtures()
        pairs, info = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        self.assertGreater(len(pairs), 0)
        for p in pairs:
            for field in PAIR_FIELDS:
                self.assertIn(field, p, f"配对缺少字段 {field}: {p['pair_id']}")
            self.assertRegex(p["pair_id"], r"^pair-[0-9a-f]{12}$")
            self.assertEqual(p["difficulty_tier"] in DIFFICULTY_TIERS, True,
                             f"非法难度层 {p['difficulty_tier']}")
        self.assertEqual(len({p["pair_id"] for p in pairs}), len(pairs), "pair_id 必须唯一")
        self.assertEqual(info["pairs_built"], len(pairs))

    def test_p1_pair_id_and_content_hash_deterministic(self):
        resumes, jobs = _fixtures()
        pairs, _ = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        for p in pairs:
            expect = pool_mod.pair_content_hash(p["resume_text"], p["job_text"])
            self.assertEqual(p["content_hash"], expect)
            self.assertEqual(p["pair_id"], pool_mod.make_pair_id(expect))

    def test_p1_synthetic_and_gold_eligibility_flags(self):
        resumes, jobs = _fixtures()
        pairs, info = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        for p in pairs:
            if p["resume_id"] == "resume_001":
                self.assertTrue(p["is_synthetic"])
                self.assertFalse(p["eligible_for_gold"], "合成配对禁止进入人工真值")
                self.assertEqual(p["pair_provenance"], "synthetic_resume_x_real_job")
            else:
                self.assertFalse(p["is_synthetic"])
                self.assertTrue(p["eligible_for_gold"])
        self.assertEqual(info["synthetic_pairs"],
                         sum(1 for p in pairs if p["is_synthetic"]))

    def test_p1_all_df_jobs_not_eligible_for_gold(self):
        resumes = [make_resume(0, rid="resume_000")]
        jobs = [make_job(0, jid="allf_0", title="数据分析师",
                         category="INFORMATION-TECHNOLOGY", source="other/all_df")]
        pairs, _ = pool_mod.build_pairs(resumes, jobs, seed=1, pairs_per_resume=32)
        self.assertGreater(len(pairs), 0)
        for p in pairs:
            self.assertFalse(p["eligible_for_gold"],
                             "来源不明（other/all_df）的岗位不得进入正式真值")

    def test_p1_difficulty_tiers_covered(self):
        """五类难度层都要能被独立构造出来（互斥、优先级固定）。"""
        r_data = make_resume(0, rid="r_data", target_position="数据分析师",
                             skills=["python", "sql", "数据分析"], education_level="本科",
                             years_experience=1.0)
        r_fin = make_resume(1, rid="r_fin", target_position="财务专员",
                            skills=["会计"], education_level="本科", years_experience=1.0)
        r_pm = make_resume(2, rid="r_pm", target_position="产品经理",
                           skills=["python", "java", "sql"], education_level="本科",
                           years_experience=1.0)
        cases = {
            "cross_category_negative": (
                r_fin, make_job(0, jid="j_it", title="Java开发工程师",
                                category="INFORMATION-TECHNOLOGY", required=["java", "go"])),
            "hard_requirement_gap": (
                r_data, make_job(1, jid="j_edu", title="数据分析师",
                                 category="INFORMATION-TECHNOLOGY",
                                 required=["python", "sql", "数据分析"], edu_tokens=["硕士"])),
            "high_skill_overlap": (
                r_data, make_job(2, jid="j_hi", title="数据分析师",
                                 category="INFORMATION-TECHNOLOGY",
                                 required=["python", "sql", "数据分析"])),
            "same_direction_diff_duties": (
                r_data, make_job(3, jid="j_same", title="数据挖掘工程师",
                                 category="INFORMATION-TECHNOLOGY",
                                 required=["hadoop", "spark", "hive"])),
            "medium_skill_overlap": (
                r_pm, make_job(4, jid="j_med", title="销售经理", category="SALES",
                               required=["python", "c++", "go", "rust"])),
        }
        seen = set()
        for want, (resume, job) in cases.items():
            tier, factors = pool_mod.difficulty_tier(resume, job)
            self.assertEqual(tier, want,
                             f"期望 {want}，实际 {tier}，因子 {factors}")
            seen.add(tier)
        self.assertEqual(seen, set(DIFFICULTY_TIERS))

    def test_p1_skill_and_category_extraction_is_heuristic_only(self):
        job = make_job(0, required=["python", "sql"])
        cat, src = pool_mod.classify_job_category(job["job_title"], job["job_description"])
        self.assertEqual(src, "heuristic_keyword_v1")
        self.assertIn("python", pool_mod.extract_skills("熟悉 python 与 sql 开发"))
        self.assertEqual(pool_mod.detect_language("这是一个中文岗位描述"), "zh")
        self.assertEqual(pool_mod.detect_language("This is an English job description"), "en")

    def test_p1_coverage_report_records_gaps(self):
        resumes, jobs = _fixtures()
        pairs, pair_stats = pool_mod.build_pairs(resumes, jobs, seed=20261210,
                                                 pairs_per_resume=32)
        cov = pool_mod.coverage_report(pairs, {"jobs_selected": len(jobs),
                                               "category_distribution": {}},
                                       {"tier_counts": pair_stats["tier_counts"]})
        self.assertGreater(cov["pairs_total"], 0)
        gap_items = {g["item"] for g in cov["gaps"]}
        self.assertIn("真实中文简历", gap_items)
        self.assertIn("真实中文简历-岗位配对", gap_items)


class P1TestSeedReproducibility(unittest.TestCase):
    """场景 2：固定随机种子复现。"""

    def test_p1_same_seed_same_pairs(self):
        resumes, jobs = _fixtures()
        a, _ = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        b, _ = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        self.assertEqual([p["pair_id"] for p in a], [p["pair_id"] for p in b])
        self.assertEqual([p["content_hash"] for p in a], [p["content_hash"] for p in b])
        self.assertEqual([p["difficulty_tier"] for p in a],
                         [p["difficulty_tier"] for p in b])

    def test_p1_different_seed_still_valid(self):
        resumes, jobs = _fixtures()
        a, _ = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        b, _ = pool_mod.build_pairs(resumes, jobs, seed=20261211, pairs_per_resume=32)
        self.assertEqual(len({p["pair_id"] for p in a}), len(a))
        self.assertEqual(len({p["pair_id"] for p in b}), len(b))

    def test_p1_synthetic_resume_generator_reproducible(self):
        a = pool_mod.make_synthetic_resumes(n=6, seed=20261210)
        b = pool_mod.make_synthetic_resumes(n=6, seed=20261210)
        self.assertEqual(a, b)
        for r in a:
            self.assertTrue(r["is_synthetic"])
            self.assertEqual(r["resume_source"], "synthetic_fixture")

    def test_p1_split_assignment_reproducible_and_disjoint(self):
        resumes, jobs = _fixtures()
        pairs, _ = pool_mod.build_pairs(resumes, jobs, seed=20261210, pairs_per_resume=32)
        s1 = assign_splits(pairs, seed=20261211, blind_ratio=0.5)
        s2 = assign_splits(pairs, seed=20261211, blind_ratio=0.5)
        self.assertEqual([p["split"] for p in s1], [p["split"] for p in s2])
        by_resume: dict[str, set[str]] = {}
        for p in s1:
            by_resume.setdefault(p["resume_id"], set()).add(p["split"])
        for rid, splits in by_resume.items():
            self.assertEqual(len(splits), 1, f"同一简历被拆到多个 split: {rid}")
        self.assertLessEqual(set(p["split"] for p in s1),
                             {"dev_validation", "blind_test"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
