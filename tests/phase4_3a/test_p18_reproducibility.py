# -*- coding: utf-8 -*-
"""P18 场景 18：同等输入 + 固定随机种子具有可复现输出（模块 C/E）。

纪律：配对生成、组级切分、resume_id 派生、近似重复隔离都必须确定性；
同种子两次运行输出逐条一致，改种子才允许变化。
"""
from __future__ import annotations

import unittest

from _util import make_job, make_resume

from job_matching.annotation import gold_gate
from job_matching.annotation.freeze import assign_splits
from job_matching.annotation.pool import build_pairs, make_pair_id, pair_content_hash
from job_matching.annotation.resume_intake import assign_resume_id


def _resumes():
    out = []
    for i in range(4):
        out.append(make_resume(i, rid=f"resume_{i:03d}", is_synthetic=False,
                               skills=["python", "sql", "数据分析"] if i % 2 == 0
                               else ["java", "spring", "mysql"],
                               target_position="数据分析师" if i % 2 == 0 else "Java 开发工程师"))
    return out


def _jobs():
    out = []
    specs = [
        ("数据分析师", ["python", "sql", "数据分析"], "INFORMATION-TECHNOLOGY"),
        ("数据分析师", ["python", "sql", "etl", "数据仓库"], "INFORMATION-TECHNOLOGY"),
        ("Java 后端开发", ["java", "spring", "mysql"], "INFORMATION-TECHNOLOGY"),
        ("Java 后端开发", ["java", "spring", "redis", "kafka"], "INFORMATION-TECHNOLOGY"),
        ("Web 前端开发", ["javascript", "vue", "css"], "INFORMATION-TECHNOLOGY"),
        ("软件测试", ["测试用例", "selenium", "python"], "INFORMATION-TECHNOLOGY"),
    ]
    for i, (title, skills, cat) in enumerate(specs):
        out.append(make_job(i, jid=f"job_{i:03d}", title=title, required=skills,
                            category=cat))
    return out


class P18TestPairBuildReproducible(unittest.TestCase):
    """场景 18：配对生成固定种子可复现。"""

    def test_p18_same_seed_same_pairs(self):
        a, _ = build_pairs(_resumes(), _jobs(), seed=20261212, pairs_per_resume=6)
        b, _ = build_pairs(_resumes(), _jobs(), seed=20261212, pairs_per_resume=6)
        self.assertEqual([p["pair_id"] for p in a], [p["pair_id"] for p in b])
        self.assertEqual([p["content_hash"] for p in a], [p["content_hash"] for p in b])
        self.assertEqual([p["job_id"] for p in a], [p["job_id"] for p in b])

    def test_p18_different_seed_may_differ(self):
        a, _ = build_pairs(_resumes(), _jobs(), seed=1, pairs_per_resume=6)
        b, _ = build_pairs(_resumes(), _jobs(), seed=2, pairs_per_resume=6)
        self.assertNotEqual([p["pair_id"] for p in a], [p["pair_id"] for p in b])

    def test_p18_pair_id_stable_from_content_hash(self):
        h = pair_content_hash("求职意向：数据分析师。技能：python。",
                              "数据分析师 任职要求：python。")
        self.assertEqual(make_pair_id(h), make_pair_id(h))
        self.assertTrue(make_pair_id(h).startswith("pair-"))

    def test_p18_pairs_not_auto_labeled(self):
        pairs, _ = build_pairs(_resumes(), _jobs(), seed=20261212, pairs_per_resume=6)
        for p in pairs:
            self.assertNotIn("relevance", p, "候选配对不得自带相关性标签")
            self.assertNotIn("label", p)


class P18TestSplitAndIdReproducible(unittest.TestCase):
    """切分与去标识化 ID 的确定性。"""

    def test_p18_assign_splits_deterministic(self):
        pairs = [{"pair_id": f"pair-{i:04d}", "resume_id": f"resume_{i // 3:03d}",
                  "job_id": f"job_{i:03d}"} for i in range(12)]
        a = assign_splits(pairs, seed=20261213, blind_ratio=0.3)
        b = assign_splits(pairs, seed=20261213, blind_ratio=0.3)
        self.assertEqual([p["split"] for p in a], [p["split"] for p in b])

    def test_p18_assign_splits_group_level_stable(self):
        pairs = [{"pair_id": f"pair-{i:04d}", "resume_id": f"resume_{i // 3:03d}",
                  "job_id": f"job_{i:03d}"} for i in range(12)]
        assigned = assign_splits(pairs, seed=7, blind_ratio=0.5)
        by_resume = {}
        for p in assigned:
            by_resume.setdefault(p["resume_id"], set()).add(p["split"])
        self.assertTrue(all(len(v) == 1 for v in by_resume.values()))

    def test_p18_resume_id_deterministic_per_content(self):
        self.assertEqual(assign_resume_id("hash_a", seed=20261212),
                         assign_resume_id("hash_a", seed=20261212))
        self.assertNotEqual(assign_resume_id("hash_a", seed=20261212),
                            assign_resume_id("hash_b", seed=20261212))

    def test_p18_near_dup_quarantine_deterministic(self):
        text = ("求职意向：数据分析师。教育背景：本科，2027 届。"
                "项目经历：参与数据平台建设，负责核心模块交付。"
                "技能：python、sql、数据分析、etl。")
        job = ("数据分析师 岗位职责：报表体系。任职要求：python、sql。")

        def build():
            pairs = [{"pair_id": "pair-0001", "resume_id": "resume_a", "job_id": "job_1",
                      "resume_text": text, "job_text": job},
                     {"pair_id": "pair-0002", "resume_id": "resume_a", "job_id": "job_2",
                      "resume_text": text, "job_text": job + "加分项：tableau。"}]
            return gold_gate.quarantine_near_duplicates(pairs, threshold=0.90)

        kept_a, q_a = build()
        kept_b, q_b = build()
        self.assertEqual([p["pair_id"] for p in kept_a], [p["pair_id"] for p in kept_b])
        self.assertEqual([q["pair_id"] for q in q_a], [q["pair_id"] for q in q_b])
        self.assertEqual([q.get("dup_of") for q in q_a], [q.get("dup_of") for q in q_b])


if __name__ == "__main__":
    unittest.main()
