# -*- coding: utf-8 -*-
"""P4 场景 5、6：非法标签拒绝 / 缺失人工标注的处理（协议 4.3）。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import (
    ANNOTATOR_A, ANNOTATOR_B, PV, TS,
    annotation_row, arbitration_row, make_pair, write_csv, write_jsonl,
)

from job_matching.annotation import schema as s
from job_matching.annotation.schema import ANNOTATION_FIELDS
from job_matching.annotation.importer import (
    check_missing_annotations, check_unjudgeable_not_forced,
    validate_annotation_file, validate_arbitration_file,
)

PAIRS = {"pair-0000", "pair-0001", "pair-0002", "pair-0003"}


class P4TestLabelValidation(unittest.TestCase):
    def test_p4_reject_invalid_relevance(self):
        for bad in ("3", "-1", "", None, "yes", "true", "2.0"):
            with self.assertRaises(s.AnnotationError) as ctx:
                s.norm_relevance(bad)
            self.assertEqual(ctx.exception.code, "invalid_relevance", f"输入 {bad!r}")

    def test_p4_accept_valid_relevance(self):
        self.assertEqual(s.norm_relevance("0"), "0")
        self.assertEqual(s.norm_relevance(" 2 "), "2")
        self.assertEqual(s.norm_relevance("Unjudgeable"), "unjudgeable")
        self.assertEqual(s.norm_relevance("U"), "unjudgeable")

    def test_p4_reject_invalid_confidence(self):
        for bad in ("sure", "", None, "highish"):
            with self.assertRaises(s.AnnotationError) as ctx:
                s.norm_confidence(bad)
            self.assertEqual(ctx.exception.code, "invalid_confidence")

    def test_p4_reject_invalid_timestamp(self):
        for bad in ("2026/10/29", "yesterday", "", None, "2026-13-45T99:99:99"):
            with self.assertRaises(s.AnnotationError) as ctx:
                s.norm_timestamp(bad)
            self.assertEqual(ctx.exception.code, "invalid_timestamp")
        self.assertEqual(s.norm_timestamp("2026-10-29T10:00:00"), "2026-10-29T10:00:00")
        self.assertEqual(s.norm_timestamp("2026-10-29 10:00"), "2026-10-29 10:00")

    def test_p4_reject_machine_annotator_ids(self):
        for bad in ("gpt_1", "auto_label", "model_bot", "llm_score", "pred_system"):
            with self.assertRaises(s.AnnotationError) as ctx:
                s.check_annotator_id(bad)
            self.assertEqual(ctx.exception.code, "machine_annotator", f"输入 {bad!r}")
        self.assertEqual(s.check_annotator_id(ANNOTATOR_A), ANNOTATOR_A)
        self.assertEqual(s.check_annotator_id("arbitrator_1"), "arbitrator_1")

    def test_p4_reject_protocol_version_mix(self):
        with self.assertRaises(s.AnnotationError) as ctx:
            s.check_protocol_version("phase4-3a-annotation-v2")
        self.assertEqual(ctx.exception.code, "protocol_version_mismatch")
        self.assertEqual(s.check_protocol_version(PV), PV)

    def test_p4_reject_missing_evidence(self):
        row = annotation_row("pair-0000", "1", evidence="短")
        with self.assertRaises(s.AnnotationError) as ctx:
            s.validate_annotation_row(row, known_pairs=PAIRS)
        self.assertEqual(ctx.exception.code, "missing_evidence")

    def test_p4_reject_unknown_pair_and_annotator(self):
        with self.assertRaises(s.AnnotationError) as ctx:
            s.validate_annotation_row(annotation_row("pair-9999", "1"), known_pairs=PAIRS)
        self.assertEqual(ctx.exception.code, "unknown_pair")
        with self.assertRaises(s.AnnotationError) as ctx:
            s.validate_annotation_row(annotation_row("pair-0000", "1"),
                                      known_pairs=PAIRS, known_annotators={"annotator_B"})
        self.assertEqual(ctx.exception.code, "unknown_annotator")

    def test_p4_model_output_columns_are_banned(self):
        bad = s.has_model_output_columns(["annotator_id", "final_score", "model_score"])
        self.assertEqual(sorted(bad), ["final_score", "model_score"])
        self.assertEqual(s.has_model_output_columns(list(ANNOTATION_FIELDS)), [])


class P4TestAnnotationFileImport(unittest.TestCase):
    def _write(self, rows, name="annotations.jsonl"):
        p = Path(self.tmp.name) / name
        write_jsonl(rows, p)
        return p

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_p4_valid_file_imported(self):
        rows = [annotation_row("pair-0000", "2", who=ANNOTATOR_A),
                annotation_row("pair-0001", "unjudgeable", who=ANNOTATOR_A)]
        rep = validate_annotation_file(self._write(rows), known_pairs=PAIRS,
                                       known_annotators={ANNOTATOR_A})
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["counts"]["valid"], 2)
        self.assertEqual(rep["counts"]["by_relevance"], {"2": 1, "unjudgeable": 1})
        self.assertEqual(rep["counts"]["annotators"], [ANNOTATOR_A])

    def test_p4_model_output_column_rejects_whole_file(self):
        rows = [{"annotator_id": ANNOTATOR_A, "pair_id": "pair-0000", "relevance": "2",
                 "confidence": "high", "reason": "1,2", "evidence": "简历：python",
                 "annotation_timestamp": TS, "protocol_version": PV,
                 "model_score": "0.93"}]
        rep = validate_annotation_file(self._write(rows), known_pairs=PAIRS)
        self.assertEqual(rep["rows_valid"], [])
        self.assertEqual(rep["errors"][0]["code"], "model_output_columns")
        self.assertIn("model_score", rep["errors"][0]["message"])

    def test_p4_invalid_label_rejected_but_other_rows_kept(self):
        rows = [annotation_row("pair-0000", "2"),
                annotation_row("pair-0001", "5"),
                annotation_row("pair-0002", "0")]
        rep = validate_annotation_file(self._write(rows), known_pairs=PAIRS)
        self.assertEqual(rep["counts"]["valid"], 2)
        self.assertEqual([e["code"] for e in rep["errors"]], ["invalid_relevance"])
        self.assertEqual(rep["errors"][0]["row"], 3, "错误必须带行号")

    def test_p4_duplicate_conflict_rejected(self):
        rows = [annotation_row("pair-0000", "2"),
                annotation_row("pair-0000", "1")]
        rep = validate_annotation_file(self._write(rows), known_pairs=PAIRS)
        self.assertEqual(rep["counts"]["valid"], 1)
        self.assertEqual(rep["errors"][0]["code"], "duplicate_conflict")

    def test_p4_duplicate_identical_is_warning_not_error(self):
        rows = [annotation_row("pair-0000", "2"), annotation_row("pair-0000", "2")]
        rep = validate_annotation_file(self._write(rows), known_pairs=PAIRS)
        self.assertEqual(rep["counts"]["valid"], 1)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["warnings"][0]["code"], "duplicate_identical")

    def test_p4_missing_columns_reported(self):
        p = Path(self.tmp.name) / "short.jsonl"
        write_jsonl([{"annotator_id": ANNOTATOR_A, "pair_id": "pair-0000"}], p)
        rep = validate_annotation_file(p, known_pairs=PAIRS)
        self.assertEqual(rep["errors"][0]["code"], "missing_columns")
        self.assertEqual(rep["rows_valid"], [])

    def test_p4_csv_import_supported(self):
        rows = [annotation_row("pair-0000", "1"), annotation_row("pair-0001", "0")]
        p = Path(self.tmp.name) / "annotations.csv"
        write_csv(rows, list(ANNOTATION_FIELDS), p)
        rep = validate_annotation_file(p, known_pairs=PAIRS)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["counts"]["valid"], 2)

    def test_p4_mixed_protocol_versions_rejected(self):
        rows = [annotation_row("pair-0000", "1"),
                annotation_row("pair-0001", "1", protocol_version="phase4-3a-annotation-v2")]
        rep = validate_annotation_file(self._write(rows), known_pairs=PAIRS)
        self.assertEqual(rep["counts"]["valid"], 1)
        self.assertEqual(rep["errors"][0]["code"], "protocol_version_mismatch")

    def test_p4_arbitration_file_rejects_undisputed_and_duplicates(self):
        rows = [arbitration_row("pair-0000", "1"),
                arbitration_row("pair-0000", "2"),
                arbitration_row("pair-0002", "1")]
        p = Path(self.tmp.name) / "arbitration.jsonl"
        write_jsonl(rows, p)
        rep = validate_arbitration_file(p, known_pairs=PAIRS, disputed_pairs={"pair-0000"})
        codes = [e["code"] for e in rep["errors"]]
        self.assertIn("duplicate_conflict", codes)
        self.assertEqual(rep["counts"]["valid"], 2, "重复仲裁被拒，未分歧仲裁保留并标记")
        self.assertEqual(rep["warnings"][0]["code"], "arbitration_not_disputed")


class P4TestMissingAnnotations(unittest.TestCase):
    def test_p4_missing_annotations_counted_not_filled(self):
        pairs = [make_pair(i, pid=f"pair-{i:04d}") for i in range(4)]
        rows = [
            annotation_row("pair-0000", "2", who=ANNOTATOR_A),
            annotation_row("pair-0000", "2", who=ANNOTATOR_B),
            annotation_row("pair-0001", "1", who=ANNOTATOR_A),
            annotation_row("pair-0001", "1", who=ANNOTATOR_B),
            annotation_row("pair-0002", "0", who=ANNOTATOR_A),
        ]
        rep = check_missing_annotations(pairs, rows, required_annotators=2)
        self.assertEqual(rep["pairs_total"], 4)
        self.assertEqual(rep["pairs_fully_annotated"], 2)
        self.assertEqual(rep["pairs_missing_annotations"], 2)
        got = {m["pair_id"]: m["annotations_received"] for m in rep["missing_detail"]}
        self.assertEqual(got, {"pair-0002": 1, "pair-0003": 0})
        self.assertIn("不填补", rep["note"])

    def test_p4_no_default_label_is_synthesized(self):
        pairs = [make_pair(0, pid="pair-0000")]
        rep = check_missing_annotations(pairs, [], required_annotators=2)
        self.assertEqual(rep["pairs_fully_annotated"], 0)
        self.assertEqual(rep["missing_detail"][0]["annotations_received"], 0)

    def test_p4_single_annotator_is_incomplete(self):
        pairs = [make_pair(i, pid=f"pair-{i:04d}") for i in range(3)]
        rows = [annotation_row(f"pair-{i:04d}", "1", who=ANNOTATOR_A) for i in range(3)]
        rep = check_missing_annotations(pairs, rows, required_annotators=2)
        self.assertEqual(rep["pairs_fully_annotated"], 0)
        self.assertEqual(rep["pairs_missing_annotations"], 3)


class P4TestUnjudgeableProtection(unittest.TestCase):
    def test_p4_unjudgeable_not_forced_without_arbitration(self):
        rows = [annotation_row("pair-0000", "unjudgeable", who=ANNOTATOR_A),
                annotation_row("pair-0000", "unjudgeable", who=ANNOTATOR_B)]
        finals = [{"pair_id": "pair-0000", "final_relevance": "1", "arbitrator_id": ""}]
        problems = check_unjudgeable_not_forced(finals, rows)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["code"], "unjudgeable_forced")

    def test_p4_unjudgeable_allowed_with_arbitration(self):
        rows = [annotation_row("pair-0000", "unjudgeable", who=ANNOTATOR_A),
                annotation_row("pair-0000", "unjudgeable", who=ANNOTATOR_B)]
        finals = [{"pair_id": "pair-0000", "final_relevance": "unjudgeable",
                   "arbitrator_id": ""}]
        self.assertEqual(check_unjudgeable_not_forced(finals, rows), [])

    def test_p4_unjudgeable_never_coerced_by_metrics(self):
        from job_matching.independent_eval.metrics import prepare_human_labels
        gains, stats = prepare_human_labels(["2", "unjudgeable", "0"])
        self.assertEqual(list(gains), [2.0, 0.0])
        self.assertEqual(stats["unjudgeable"], 1)
        self.assertEqual(stats["judgeable"], 2)
        with self.assertRaises(ValueError):
            prepare_human_labels(["3"])
        with self.assertRaises(ValueError):
            prepare_human_labels(["maybe"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
