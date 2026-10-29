# -*- coding: utf-8 -*-
"""P6 场景 8：双人分歧仲裁与最终标签追踪（协议 4.2）。

纪律：两份原始标注、仲裁记录、最终标签分别留痕，任何环节不得覆盖。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import (
    ANNOTATOR_A, ANNOTATOR_B, ANNOTATION_FIELDS, ARBITRATOR, PV,
    annotation_row, arbitration_row, make_pair, paired, write_csv,
)

from job_matching.annotation.arbitration import (
    INSUFFICIENT, PENDING, build_final_labels, export_arbitration_sheet,
    find_disagreements, group_annotations, write_annotations_template,
    write_final_labels,
)
from job_matching.annotation.schema import FINAL_LABEL_FIELDS

PAIR_IDS = ["pair-000", "pair-001", "pair-002", "pair-003"]


def fixture_rows():
    """4 条：2 条一致（其中 1 条双方 unjudgeable）、2 条分歧。"""
    a, b = paired(ANNOTATOR_A, ["2", "1", "unjudgeable", "0"],
                  ANNOTATOR_B, ["2", "0", "unjudgeable", "1"])
    return a + b


def fixture_pairs():
    return [make_pair(i, pid=PAIR_IDS[i]) for i in range(len(PAIR_IDS))]


class P6TestDisagreementDetection(unittest.TestCase):
    def test_p6_find_disagreements(self):
        rows = fixture_rows()
        d = find_disagreements(rows)
        self.assertEqual([x["pair_id"] for x in d], ["pair-001", "pair-003"])
        self.assertEqual(d[0]["relevance_a"], "1")
        self.assertEqual(d[0]["relevance_b"], "0")
        self.assertTrue(d[0]["reason_a"])
        self.assertTrue(d[0]["evidence_b"])

    def test_p6_unjudgeable_vs_numeric_is_a_disagreement(self):
        rows = [annotation_row("pair-000", "unjudgeable", who=ANNOTATOR_A),
                annotation_row("pair-000", "1", who=ANNOTATOR_B)]
        d = find_disagreements(rows)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["relevance_a"], "unjudgeable")

    def test_p6_both_unjudgeable_is_not_a_disagreement(self):
        rows = [annotation_row("pair-000", "unjudgeable", who=ANNOTATOR_A),
                annotation_row("pair-000", "unjudgeable", who=ANNOTATOR_B)]
        self.assertEqual(find_disagreements(rows), [])

    def test_p6_group_annotations_sorted_by_annotator(self):
        grouped = group_annotations(fixture_rows())
        self.assertEqual(len(grouped), 4)
        self.assertEqual([r["annotator_id"] for r in grouped["pair-000"]],
                         [ANNOTATOR_A, ANNOTATOR_B])

    def test_p6_missing_second_annotation_not_a_disagreement(self):
        rows = [annotation_row("pair-000", "1", who=ANNOTATOR_A)]
        self.assertEqual(find_disagreements(rows), [])


class P6TestArbitrationSheet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_p6_export_sheet_has_reference_columns(self):
        d = find_disagreements(fixture_rows())
        path = export_arbitration_sheet(d, self.dir / "pending.csv")
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        header = text.splitlines()[0].split(",")
        for col in ("arbitrator_id", "pair_id", "final_relevance", "final_confidence",
                    "reason", "evidence", "annotation_timestamp", "protocol_version",
                    "_relevance_a", "_relevance_b", "_reason_a", "_reason_b"):
            self.assertIn(col, header)
        self.assertEqual(len(text.splitlines()) - 1, 2, "每条分歧一行")
        # 参考列必须带下划线前缀，避免被当成仲裁结论
        self.assertNotIn("model_score", text)

    def test_p6_export_empty_sheet(self):
        path = export_arbitration_sheet([], self.dir / "empty.csv")
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)


class P6TestFinalLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_p6_agreement_and_arbitration_and_pending(self):
        rows = fixture_rows()
        arb = [arbitration_row("pair-001", "1")]
        res = build_final_labels(fixture_pairs(), rows, arb)
        by_id = {r["pair_id"]: r for r in res["final_rows"]}
        self.assertEqual(res["checks"]["both_agree"], 2)
        self.assertEqual(res["checks"]["arbitration_used"], 1)
        self.assertEqual(res["checks"]["pending"], 1)
        self.assertEqual(res["checks"]["insufficient"], 0)
        self.assertEqual(res["finalized"], 3)
        self.assertEqual(by_id["pair-000"]["final_source"], "both_agree")
        self.assertEqual(by_id["pair-000"]["final_relevance"], "2")
        self.assertEqual(by_id["pair-001"]["final_source"], "arbitration")
        self.assertEqual(by_id["pair-001"]["final_relevance"], "1")
        self.assertEqual(by_id["pair-001"]["arbitrator_id"], ARBITRATOR)
        self.assertIsNone(by_id["pair-003"]["final_relevance"], "未仲裁不得自动择一")
        self.assertEqual(by_id["pair-003"]["final_source"], PENDING)
        self.assertEqual(res["checks"]["missing_final"],
                         [{"pair_id": "pair-003", "reason": PENDING}])

    def test_p6_both_unjudgeable_stays_unjudgeable(self):
        rows = fixture_rows()
        res = build_final_labels(fixture_pairs(), rows, [])
        by_id = {r["pair_id"]: r for r in res["final_rows"]}
        self.assertEqual(by_id["pair-002"]["final_relevance"], "unjudgeable")
        self.assertEqual(by_id["pair-002"]["final_source"], "both_agree")
        self.assertEqual(res["checks"]["unjudgeable_forced"], [])

    def test_p6_arbitration_cannot_force_numeric_over_both_unjudgeable(self):
        rows = [annotation_row("pair-000", "unjudgeable", who=ANNOTATOR_A),
                annotation_row("pair-000", "unjudgeable", who=ANNOTATOR_B)]
        arb = [arbitration_row("pair-000", "1")]
        res = build_final_labels([make_pair(0, pid="pair-000")], rows, arb)
        self.assertEqual(len(res["checks"]["unjudgeable_forced"]), 1)
        self.assertEqual(res["checks"]["unjudgeable_forced"][0]["pair_id"], "pair-000")

    def test_p6_insufficient_annotators(self):
        rows = [annotation_row("pair-000", "2", who=ANNOTATOR_A)]
        res = build_final_labels([make_pair(0, pid="pair-000")], rows, [])
        self.assertEqual(res["checks"]["insufficient"], 1)
        self.assertEqual(res["checks"]["missing_final"],
                         [{"pair_id": "pair-000", "reason": INSUFFICIENT}])
        self.assertEqual(res["finalized"], 0)
        self.assertIsNone(res["final_rows"][0]["final_relevance"])

    def test_p6_original_annotations_preserved_in_final_rows(self):
        rows = fixture_rows()
        res = build_final_labels(fixture_pairs(), rows, [arbitration_row("pair-001", "1")])
        r = {x["pair_id"]: x for x in res["final_rows"]}["pair-001"]
        self.assertEqual(r["annotator_a_id"], ANNOTATOR_A)
        self.assertEqual(r["annotator_a_relevance"], "1")
        self.assertEqual(r["annotator_b_id"], ANNOTATOR_B)
        self.assertEqual(r["annotator_b_relevance"], "0")
        self.assertEqual(r["protocol_version"], PV)

    def test_p6_write_final_labels_keeps_all_columns(self):
        rows = fixture_rows()
        res = build_final_labels(fixture_pairs(), rows, [arbitration_row("pair-001", "1")])
        path = write_final_labels(res["final_rows"], self.dir / "final_labels.csv")
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        self.assertEqual(header, list(FINAL_LABEL_FIELDS))
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()) - 1, 4)

    def test_p6_template_blank_rows(self):
        path = write_annotations_template(ANNOTATOR_A, PAIR_IDS,
                                          self.dir / "tpl.csv", PV)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0].split(","), list(ANNOTATION_FIELDS))
        self.assertEqual(len(lines) - 1, 4)
        for line in lines[1:]:
            cols = line.split(",")
            self.assertEqual(cols[0], ANNOTATOR_A)
            self.assertEqual(cols[7], PV, "模板必须预填协议版本")
            self.assertEqual(cols[2], "", "relevance 必须留空待人工填写")

    def test_p6_arbitration_and_final_written_to_separate_files(self):
        rows = fixture_rows()
        arb_path = write_csv([arbitration_row("pair-001", "1")],
                             ["arbitrator_id", "pair_id", "final_relevance",
                              "final_confidence", "reason", "evidence",
                              "annotation_timestamp", "protocol_version"],
                             self.dir / "arbitration.csv")
        raw_path = write_csv(rows, list(ANNOTATION_FIELDS), self.dir / "annotations.csv")
        res = build_final_labels(fixture_pairs(), rows, [arbitration_row("pair-001", "1")])
        write_final_labels(res["final_rows"], self.dir / "final_labels.csv")
        self.assertTrue(all(p.exists() for p in (arb_path, raw_path,
                                                 self.dir / "final_labels.csv")))
        raw_text = raw_path.read_text(encoding="utf-8")
        self.assertIn("unjudgeable", raw_text, "原始标注必须原样保留")


if __name__ == "__main__":
    unittest.main(verbosity=2)
