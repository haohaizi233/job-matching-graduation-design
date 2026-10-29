# -*- coding: utf-8 -*-
"""P12 场景 4–7：配对唯一性 / 组级切分隔离 / 训练交叉检查 / 近似重复检查（模块 C/E）。

纪律：重复 pair_id 直接拒绝；同一 resume_id 不得跨 dev/blind；
与训练语料交叉的配对必须显式标记并禁入盲测；近似重复配对隔离不重复计数。
"""
from __future__ import annotations

import unittest

from _util import make_pair

from job_matching.annotation import gold_gate
from job_matching.annotation.freeze import assign_splits


def _pair(pid: str, rid: str, jid: str, *, resume_text: str = "", job_text: str = "",
          **extra) -> dict:
    return make_pair(0, pid=pid, rid=rid, jid=jid, resume_text=resume_text,
                     job_text=job_text, **extra)


class P12TestUniquePairs(unittest.TestCase):
    """场景 4：重复 pair_id 拒绝。"""

    def test_p12_duplicate_pair_id_rejected(self):
        pairs = [_pair("pair-0001", "resume_a", "job_1"),
                 _pair("pair-0001", "resume_b", "job_2")]
        with self.assertRaises(gold_gate.GateError) as ctx:
            gold_gate.ensure_unique_pair_ids(pairs)
        self.assertEqual(ctx.exception.code, "duplicate_pair_id")

    def test_p12_duplicate_resume_job_rejected(self):
        pairs = [_pair("pair-0001", "resume_a", "job_1"),
                 _pair("pair-0002", "resume_a", "job_1")]
        with self.assertRaises(gold_gate.GateError) as ctx:
            gold_gate.ensure_unique_pair_ids(pairs)
        self.assertEqual(ctx.exception.code, "duplicate_resume_job_pair")

    def test_p12_unique_pairs_pass(self):
        pairs = [_pair("pair-0001", "resume_a", "job_1"),
                 _pair("pair-0002", "resume_a", "job_2")]
        gold_gate.ensure_unique_pair_ids(pairs)  # 不抛异常


class P12TestSplitIsolation(unittest.TestCase):
    """场景 5：同一 resume_id 跨 dev/blind 拒绝。"""

    def test_p12_cross_split_resume_detected(self):
        pairs = [_pair("pair-0001", "resume_a", "job_1", split="dev_validation"),
                 _pair("pair-0002", "resume_a", "job_2", split="blind_test")]
        res = gold_gate.check_split_isolation(pairs)
        self.assertFalse(res["ok"])
        self.assertEqual(res["resume_overlap"], ["resume_a"])
        self.assertEqual(res["resume_overlap_count"], 1)

    def test_p12_group_split_never_breaks_resume(self):
        pairs = [_pair(f"pair-{i:04d}", f"resume_{i // 3:03d}", f"job_{i:03d}")
                 for i in range(12)]
        assigned = assign_splits(pairs, seed=20261213, blind_ratio=0.3)
        res = gold_gate.check_split_isolation(assigned)
        self.assertTrue(res["ok"], res)
        by_resume = {}
        for p in assigned:
            by_resume.setdefault(p["resume_id"], set()).add(p["split"])
        self.assertTrue(all(len(v) == 1 for v in by_resume.values()))

    def test_p12_job_isolated_mode_flags_job_overlap(self):
        pairs = [_pair("pair-0001", "resume_a", "job_1", split="dev_validation"),
                 _pair("pair-0002", "resume_b", "job_1", split="blind_test")]
        res = gold_gate.check_split_isolation(pairs, job_isolated=True)
        self.assertFalse(res["ok"])
        self.assertEqual(res["job_overlap_count"], 1)


class P12TestTrainingOverlap(unittest.TestCase):
    """场景 6：训练数据交叉检查。"""

    def test_p12_overlap_job_flagged_and_blind_excluded(self):
        pairs = [_pair("pair-0001", "resume_a", "job_1"),
                 _pair("pair-0002", "resume_a", "job_2")]
        out = gold_gate.flag_training_overlap(pairs, {"job_2"},
                                              reason="edu_training_corpus_overlap")
        hit = [p for p in out if p["job_id"] == "job_2"][0]
        clean = [p for p in out if p["job_id"] == "job_1"][0]
        self.assertTrue(hit["training_overlap"])
        self.assertFalse(hit["blind_eligible"])
        self.assertEqual(hit["training_overlap_reason"], "edu_training_corpus_overlap")
        self.assertFalse(clean["training_overlap"])
        self.assertTrue(clean["blind_eligible"])
        self.assertFalse(pairs[1].get("training_overlap"), "不得就地修改输入")

    def test_p12_task_separated_rationale_preserved(self):
        # 不同训练任务的语料重合不得一概当泄漏：标记保留任务口径说明的入口
        out = gold_gate.flag_training_overlap([_pair("pair-0001", "resume_a", "job_1")],
                                              {"job_1"}, reason="edu_corpus_text_overlap")
        self.assertEqual(out[0]["training_overlap_reason"], "edu_corpus_text_overlap")
        self.assertIn("blind_eligible", out[0])


class P12TestNearDuplicateQuarantine(unittest.TestCase):
    """场景 7：近似重复检查（不通过重复简历/岗位机械凑数）。"""

    def test_p12_near_duplicate_pair_quarantined(self):
        text = ("求职意向：数据分析师。教育背景：本科，2027 届，统计学专业。"
                "项目经历：参与数据平台建设，负责核心模块设计与交付，"
                "完成报表体系与指标口径治理。技能：python、sql、数据分析、etl、数据仓库。")
        job = ("数据分析师\n岗位职责：负责数据平台与报表体系，"
               "与业务团队对齐指标口径，完成数据可视化与分析报告。"
               "任职要求：python、sql、数据分析、数据仓库、etl。")
        pairs = [_pair("pair-0001", "resume_a", "job_1", resume_text=text, job_text=job),
                 _pair("pair-0002", "resume_a", "job_2", resume_text=text,
                       job_text=job + "加分项：tableau。")]
        kept, quarantined = gold_gate.quarantine_near_duplicates(pairs, threshold=0.90)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(quarantined), 1)
        self.assertIn(quarantined[0]["quarantine_reason"],
                      ("near_duplicate_pair", "duplicate_pair_text"))
        self.assertEqual(quarantined[0]["dup_of"], "pair-0001")

    def test_p12_distinct_pairs_kept(self):
        pairs = [
            _pair("pair-0001", "resume_a", "job_1",
                  resume_text="求职意向：数据分析师。技能：python、sql。",
                  job_text="数据分析师 岗位职责：报表体系。任职要求：sql。"),
            _pair("pair-0002", "resume_a", "job_2",
                  resume_text="求职意向：数据分析师。技能：python、sql。",
                  job_text="Java 后端工程师 岗位职责：微服务开发。任职要求：java、spring、mysql。"),
        ]
        kept, quarantined = gold_gate.quarantine_near_duplicates(pairs, threshold=0.90)
        self.assertEqual(len(kept), 2)
        self.assertEqual(quarantined, [])


if __name__ == "__main__":
    unittest.main()
