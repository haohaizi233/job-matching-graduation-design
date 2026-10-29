# -*- coding: utf-8 -*-
"""S10~S12：Baseline 稳定排序 / 重复岗位处理 / 同分稳定排序。"""
from __future__ import annotations

import unittest

from _util import RESUME_TEXT, make_jd

from job_matching.service import (JobEducationResolver, MatchingService, ModelRegistry,
                                  RankOptions, parse_job_text, parse_resume_text,
                                  register_builtin_models)


def make_service() -> MatchingService:
    reg = ModelRegistry()
    register_builtin_models(reg)
    return MatchingService(reg)


def make_jobs(texts_ids, resolver=None):
    resolver = resolver or JobEducationResolver(None)
    return [parse_job_text(text, job_id=jid, resolver=resolver, is_synthetic=True)
            for text, jid in texts_ids]


class S10BaselineStableOrdering(unittest.TestCase):
    """场景 10：Baseline 稳定排序（同输入同结果）。"""

    def setUp(self):
        self.service = make_service()
        self.student = parse_resume_text(RESUME_TEXT, profile_id="stu_s10", is_synthetic=True)
        self.jobs = make_jobs([
            (make_jd(title="财务分析师", required="熟悉 财务分析、会计",
                     edu="1. 本科及以上学历"), "job_fin"),
            (make_jd(title="Java开发工程师", required="熟悉 Java、MySQL",
                     edu="1. 本科及以上学历"), "job_java"),
            (make_jd(title="测试工程师", required="熟悉 Python、Selenium",
                     edu="1. 本科及以上学历"), "job_qa"),
        ])

    def test_baseline_relevant_job_first(self):
        res = self.service.rank(self.student, self.jobs, {"mode": "baseline"})
        self.assertEqual(res["score_type"], "heuristic_score")
        self.assertEqual(res["results"][0]["job_id"], "job_java")

    def test_two_runs_identical(self):
        a = self.service.rank(self.student, self.jobs, {"mode": "baseline"})
        b = self.service.rank(self.student, self.jobs, {"mode": "baseline"})
        self.assertEqual([r["score"] for r in a["results"]],
                         [r["score"] for r in b["results"]])
        self.assertEqual([r["job_id"] for r in a["results"]],
                         [r["job_id"] for r in b["results"]])

    def test_top_k_respected(self):
        res = self.service.rank(self.student, self.jobs,
                                RankOptions.from_dict({"mode": "baseline", "top_k": 2}))
        self.assertEqual(len(res["results"]), 2)
        self.assertEqual([r["rank"] for r in res["results"]], [1, 2])


class S11DuplicateJobs(unittest.TestCase):
    """场景 11：重复岗位处理（job_id 去重 + 告警）。"""

    def test_duplicate_job_id_dropped_with_warning(self):
        service = make_service()
        student = parse_resume_text(RESUME_TEXT, profile_id="stu_s11", is_synthetic=True)
        jobs = make_jobs([
            (make_jd(title="Java开发工程师", required="熟悉 Java"), "job_dup"),
            (make_jd(title="Java开发工程师", required="熟悉 Java"), "job_dup"),
            (make_jd(title="测试工程师", required="熟悉 Python"), "job_other"),
        ])
        res = service.rank(student, jobs, {"mode": "baseline"})
        ids = [r["job_id"] for r in res["results"]]
        self.assertEqual(sorted(ids), ["job_dup", "job_other"])
        self.assertTrue(any(w.startswith("duplicate_job_ids_dropped") for w in res["warnings"]))


class S12TieStability(unittest.TestCase):
    """场景 12：同分稳定排序（分数相同保持输入顺序）。"""

    def test_equal_scores_keep_input_order(self):
        service = make_service()
        student = parse_resume_text(RESUME_TEXT, profile_id="stu_s12", is_synthetic=True)
        same = make_jd(title="Java开发工程师", required="熟悉 Java、MySQL",
                       edu="1. 本科及以上学历")
        jobs = make_jobs([(same, "job_a"), (same, "job_b"), (same, "job_c")])
        res = service.rank(student, jobs, {"mode": "baseline"})
        scores = [r["score"] for r in res["results"]]
        self.assertEqual(len(set(scores)), 1, "同内容岗位分数应相同")
        self.assertEqual([r["job_id"] for r in res["results"]],
                         ["job_a", "job_b", "job_c"])


if __name__ == "__main__":
    unittest.main()
