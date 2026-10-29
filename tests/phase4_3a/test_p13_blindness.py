# -*- coding: utf-8 -*-
"""P13 场景 8–9：模型预测不得泄漏给标注员 / 标注员独立性（Phase4-3A-2 模块 D）。

纪律：标注视图按白名单构建，模型预测与旧评分列直接拒收；
抽样难度层、pair 来源、split、他人答案对标注员隐藏；
同一标注员不得冒充两名独立标注员（共享 ID / 整表镜像直接判违规）。
"""
from __future__ import annotations

import unittest

from _util import annotation_row, make_pair

from job_matching.annotation import blind_guard
from job_matching.annotation.schema import AnnotationError


class P13TestBlindView(unittest.TestCase):
    """场景 8：模型预测字段不得泄漏给标注员。"""

    def test_p13_view_hides_sampling_and_split_columns(self):
        pair = make_pair(0, pid="pair-0001", resume_text="求职意向：数据分析师。",
                         job_text="数据分析师 岗位职责：报表。", difficulty_tier="cross_category_negative",
                         pair_provenance="resume x job", split="blind_test",
                         is_synthetic=False, eligible_for_gold=True,
                         model_score=0.87)
        with self.assertRaises(AnnotationError) as ctx:
            blind_guard.build_annotation_view(pair)
        self.assertEqual(ctx.exception.code, "model_output_columns")

    def test_p13_view_drops_pipeline_metadata(self):
        pair = make_pair(0, pid="pair-0001", resume_text="求职意向：数据分析师。",
                         job_text="数据分析师 岗位职责：报表。", difficulty_tier="high_skill_overlap",
                         pair_provenance="resume x job", split="blind_test")
        view = blind_guard.build_annotation_view(pair)
        self.assertNotIn("difficulty_tier", view)
        self.assertNotIn("pair_provenance", view)
        self.assertNotIn("split", view)
        self.assertNotIn("is_synthetic", view)
        self.assertIn("resume_text", view)
        self.assertIn("job_text", view)
        self.assertIn("pair_id", view)

    def test_p13_packet_columns_reject_model_output(self):
        bad = list(blind_guard.ANNOTATION_VIEW_COLUMNS) + ["final_score", "relevance"]
        problems = blind_guard.check_packet_columns(bad)
        self.assertTrue(any("final_score" in p for p in problems))

    def test_p13_packet_columns_reject_hidden_columns(self):
        bad = list(blind_guard.ANNOTATION_VIEW_COLUMNS) + \
            ["difficulty_tier", "relevance", "confidence"]
        problems = blind_guard.check_packet_columns(bad)
        self.assertTrue(any("difficulty_tier" in p for p in problems))

    def test_p13_view_check_flags_model_columns(self):
        problems = blind_guard.check_annotation_view({"pair_id": "p", "label_strength": "x"})
        self.assertTrue(any("label_strength" in p for p in problems))


class P13TestAnnotatorIndependence(unittest.TestCase):
    """场景 9：同一标注员不能冒充两名独立标注员。"""

    def test_p13_shared_annotator_id_rejected(self):
        rows_a = [annotation_row("pair-0001", "2", who="annotator_A")]
        rows_b = [annotation_row("pair-0001", "1", who="annotator_A")]
        res = blind_guard.check_annotator_independence(rows_a, rows_b)
        self.assertEqual(res["status"], "violation")
        codes = [v["code"] for v in res["violations"]]
        self.assertIn("shared_annotator_id", codes)

    def test_p13_mirrored_annotations_rejected(self):
        rows_a = [annotation_row("pair-0001", "2", who="annotator_A"),
                  annotation_row("pair-0002", "1", who="annotator_A")]
        rows_b = [dict(r, annotator_id="annotator_B") for r in rows_a]
        res = blind_guard.check_annotator_independence(rows_a, rows_b)
        self.assertEqual(res["status"], "violation")
        codes = [v["code"] for v in res["violations"]]
        self.assertIn("mirrored_annotations", codes)

    def test_p13_independent_annotators_pass(self):
        rows_a = [annotation_row("pair-0001", "2", who="annotator_A",
                                 reason="1,2 必备技能满足", evidence="简历：python 项目")]
        rows_b = [annotation_row("pair-0001", "1", who="annotator_B",
                                 reason="3 学历不符", evidence="JD：要求硕士")]
        res = blind_guard.check_annotator_independence(rows_a, rows_b)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["violations"], [])

    def test_p13_final_label_same_person_rejected(self):
        finals = [{"pair_id": "pair-0001", "annotator_a_id": "annotator_A",
                   "annotator_b_id": "annotator_A"}]
        problems = blind_guard.check_final_label_independence(finals)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["code"], "shared_annotator_id")


if __name__ == "__main__":
    unittest.main()
