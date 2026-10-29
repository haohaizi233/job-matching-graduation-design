# -*- coding: utf-8 -*-
"""P14 场景 10–12：人工标注完整性（Phase4-3A-2 模块 D）。

纪律：非法标签值与混用协议版本拒收；unjudgeable 不得被强行归类为 0/1/2；
仲裁记录必须保留原始两份标注，不得静默覆盖。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import ANNOTATOR_A, ANNOTATOR_B, ARBITRATOR, PV, TS, write_csv

from job_matching.annotation import arbitration as arbitration_mod
from job_matching.annotation import importer as importer_mod
from job_matching.annotation.schema import ANNOTATION_FIELDS, ARBITRATION_FIELDS

KNOWN = {"pair-0001", "pair-0002", "pair-0003"}


def ann(pid: str, relevance: str, *, who: str = ANNOTATOR_A, **extra) -> dict:
    row = {"annotator_id": who, "pair_id": pid, "relevance": relevance,
           "confidence": "high", "reason": "1,2 必备技能满足",
           "evidence": "简历：技能 python；JD：任职要求 python",
           "annotation_timestamp": TS, "protocol_version": PV}
    row.update(extra)
    return row


class P14TestLabelAndProtocolValidation(unittest.TestCase):
    """场景 10：非法标签值与协议版本混用必须拒绝。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_p14_invalid_relevance_rejected(self):
        rows = [ann("pair-0001", "2"), ann("pair-0002", "3")]
        p = write_csv(rows, ANNOTATION_FIELDS, self.dir / "a.csv")
        rep = importer_mod.validate_annotation_file(p, known_pairs=KNOWN)
        codes = [e["code"] for e in rep["errors"]]
        self.assertIn("invalid_relevance", codes)
        self.assertEqual(len(rep["rows_valid"]), 1)

    def test_p14_protocol_version_mix_rejected(self):
        rows = [ann("pair-0001", "2"), ann("pair-0002", "1",
                                           protocol_version="phase4-3a-annotation-v2")]
        p = write_csv(rows, ANNOTATION_FIELDS, self.dir / "a.csv")
        rep = importer_mod.validate_annotation_file(p, known_pairs=KNOWN)
        codes = [e["code"] for e in rep["errors"]]
        self.assertIn("protocol_version_mismatch", codes)

    def test_p14_model_output_column_rejects_file(self):
        rows = [{"annotator_id": ANNOTATOR_A, "pair_id": "pair-0001",
                 "relevance": "2", "confidence": "high", "reason": "1,2",
                 "evidence": "简历：python", "annotation_timestamp": TS,
                 "protocol_version": PV, "final_score": 0.9}]
        p = write_csv(rows, list(ANNOTATION_FIELDS) + ["final_score"], self.dir / "b.csv")
        rep = importer_mod.validate_annotation_file(p, known_pairs=KNOWN)
        codes = [e["code"] for e in rep["errors"]]
        self.assertIn("model_output_columns", codes)
        self.assertEqual(rep["rows_valid"], [])

    def test_p14_conflicting_duplicate_not_silently_deduped(self):
        rows = [ann("pair-0001", "2"), ann("pair-0001", "0")]
        p = write_csv(rows, ANNOTATION_FIELDS, self.dir / "c.csv")
        rep = importer_mod.validate_annotation_file(p, known_pairs=KNOWN)
        codes = [e["code"] for e in rep["errors"]]
        self.assertIn("duplicate_conflict", codes)
        self.assertEqual(len(rep["rows_valid"]), 1, "冲突重复记录不得自行择一")

    def test_p14_unknown_pair_rejected(self):
        p = write_csv([ann("pair-9999", "2")], ANNOTATION_FIELDS, self.dir / "d.csv")
        rep = importer_mod.validate_annotation_file(p, known_pairs=KNOWN)
        self.assertEqual([e["code"] for e in rep["errors"]], ["unknown_pair"])


class P14TestUnjudgeableProtection(unittest.TestCase):
    """场景 11：unjudgeable 不得被强行归类。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self, relevance="unjudgeable"):
        return [ann("pair-0001", relevance, who=ANNOTATOR_A),
                ann("pair-0001", relevance, who=ANNOTATOR_B)]

    def test_p14_forced_numeric_flagged(self):
        finals = [{"pair_id": "pair-0001", "final_relevance": "0", "arbitrator_id": ""}]
        problems = importer_mod.check_unjudgeable_not_forced(finals, self._rows())
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["code"], "unjudgeable_forced")

    def test_p14_both_unjudgeable_stays_unjudgeable(self):
        pairs = [{"pair_id": "pair-0001"}]
        built = arbitration_mod.build_final_labels(pairs, self._rows(), [])
        self.assertEqual(built["final_rows"][0]["final_relevance"], "unjudgeable")
        self.assertEqual(built["checks"]["unjudgeable_forced"], [])

    def test_p14_arbitration_cannot_force_numeric_on_unjudgeable(self):
        pairs = [{"pair_id": "pair-0001"}]
        arb = [{"arbitrator_id": ARBITRATOR, "pair_id": "pair-0001",
                "final_relevance": "2", "final_confidence": "high",
                "reason": "仲裁改判", "evidence": "JD：任职要求 python",
                "annotation_timestamp": TS, "protocol_version": PV}]
        built = arbitration_mod.build_final_labels(pairs, self._rows(), arb)
        self.assertEqual(len(built["checks"]["unjudgeable_forced"]), 1)

    def test_p14_unjudgeable_vs_numeric_goes_to_arbitration(self):
        pairs = [{"pair_id": "pair-0001"}]
        rows = [ann("pair-0001", "unjudgeable", who=ANNOTATOR_A),
                ann("pair-0001", "0", who=ANNOTATOR_B)]
        built = arbitration_mod.build_final_labels(pairs, rows, [])
        self.assertEqual(built["final_rows"][0]["final_source"], "pending_arbitration")
        self.assertEqual(built["checks"]["pending"], 1)


class P14TestArbitrationRecords(unittest.TestCase):
    """场景 12：仲裁记录不得静默覆盖原始标注。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _arb(self, pid, final="2"):
        return {"arbitrator_id": ARBITRATOR, "pair_id": pid, "final_relevance": final,
                "final_confidence": "high", "reason": "仲裁复核原文后裁定",
                "evidence": "JD：任职要求 python；简历：项目经历含 python",
                "annotation_timestamp": TS, "protocol_version": PV}

    def test_p14_duplicate_arbitration_rejected(self):
        p = write_csv([self._arb("pair-0001"), self._arb("pair-0001", "1")],
                      ARBITRATION_FIELDS, self.dir / "arb.csv")
        rep = importer_mod.validate_arbitration_file(p, known_pairs=KNOWN,
                                                     disputed_pairs={"pair-0001"})
        codes = [e["code"] for e in rep["errors"]]
        self.assertIn("duplicate_conflict", codes)
        self.assertEqual(len(rep["rows_valid"]), 1)

    def test_p14_arbitration_only_for_disputed(self):
        p = write_csv([self._arb("pair-0002")], ARBITRATION_FIELDS, self.dir / "arb.csv")
        rep = importer_mod.validate_arbitration_file(p, known_pairs=KNOWN,
                                                     disputed_pairs={"pair-0001"})
        self.assertEqual([w["code"] for w in rep["warnings"]],
                         ["arbitration_not_disputed"])

    def test_p14_final_labels_keep_original_annotations(self):
        pairs = [{"pair_id": "pair-0001"}]
        rows = [ann("pair-0001", "0", who=ANNOTATOR_A, reason="技能不满足"),
                ann("pair-0001", "2", who=ANNOTATOR_B, reason="技能满足")]
        built = arbitration_mod.build_final_labels(pairs, rows, [self._arb("pair-0001", "1")])
        fin = built["final_rows"][0]
        self.assertEqual(fin["final_relevance"], "1")
        self.assertEqual(fin["final_source"], "arbitration")
        self.assertEqual(fin["annotator_a_relevance"], "0")
        self.assertEqual(fin["annotator_b_relevance"], "2")
        self.assertEqual(built["checks"]["arbitration_used"], 1)


if __name__ == "__main__":
    unittest.main()
