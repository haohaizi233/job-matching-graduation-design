# -*- coding: utf-8 -*-
"""Phase7 标注工具链演练测试（隔离合成夹具）。

纪律：演练用合成配对 + 机械标签，**不是**人工标注；本模块只验证工具链契约。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import ROOT

import annotation_drill as drill  # noqa: E402


class TestAnnotationDrill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ws = Path(tempfile.mkdtemp(prefix="phase7-drill-test-"))
        cls.payload = drill.run_drill(cls.ws)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.ws, ignore_errors=True)

    def test_drill_overall_pass(self):
        self.assertEqual("PASS", self.payload["status"],
                         f"失败项: {self.payload['summary']['failed']}")

    def test_drill_is_explicitly_marked_synthetic(self):
        self.assertTrue(self.payload["drill_only"])
        self.assertIn("不是真人", self.payload["nature"])
        self.assertTrue(self.payload["fixture"]["is_synthetic"])
        self.assertFalse(self.payload["fixture"]["eligible_for_gold"])

    def test_all_required_capabilities_covered(self):
        required = {
            "independent_export", "annotation_save", "resume_partial_annotation",
            "required_field_check", "illegal_label_rejected",
            "same_person_two_annotators_rejected", "mirrored_answer_detection",
            "privacy_residual_scan", "annotation_progress_stats",
        }
        self.assertTrue(required.issubset(set(self.payload["checks"])),
                        f"缺失能力: {required - set(self.payload['checks'])}")

    def test_each_capability_passed(self):
        for name, res in self.payload["checks"].items():
            self.assertEqual("PASS", res["status"], f"{name} 未通过: {res.get('detail')}")

    def test_workspace_guard_blocks_real_data_dirs(self):
        res = drill.drill_workspace_guard(self.ws)
        self.assertEqual("PASS", res["status"], res.get("unexpected"))
        self.assertEqual([], res["unexpected"])

    def test_mirror_detection_flags_full_mirror_only(self):
        pairs = drill._synthetic_pairs(6)
        rows_a = [drill._annotation_row(p["pair_id"], drill.ANNOTATOR_A,
                                        __import__("random").Random(1)) for p in pairs]
        rows_b = [drill._annotation_row(p["pair_id"], drill.ANNOTATOR_B,
                                        __import__("random").Random(2)) for p in pairs]
        res = drill.drill_mirror_detection(rows_a, rows_b)
        self.assertEqual("PASS", res["status"], res.get("detail"))

    def test_same_person_rejected(self):
        pairs = drill._synthetic_pairs(6)
        rows_a = [drill._annotation_row(p["pair_id"], drill.ANNOTATOR_A,
                                        __import__("random").Random(3)) for p in pairs]
        rows_b = [drill._annotation_row(p["pair_id"], drill.ANNOTATOR_B,
                                        __import__("random").Random(4)) for p in pairs]
        res = drill.drill_same_person_two_annotators(rows_a, rows_b)
        self.assertEqual("PASS", res["status"], res.get("detail"))

    def test_freeze_refused_without_real_data(self):
        pairs = drill._synthetic_pairs(4)
        res = drill.drill_freeze_refusal(pairs)
        self.assertEqual("PASS", res["status"], res.get("detail"))
        self.assertTrue(res["reasons"], "必须给出阻断原因")

    def test_synthetic_pairs_never_gold(self):
        pairs = drill._synthetic_pairs(4)
        self.assertTrue(all(p["is_synthetic"] for p in pairs))
        self.assertTrue(all(p["eligible_for_gold"] is False for p in pairs))


if __name__ == "__main__":
    unittest.main()
