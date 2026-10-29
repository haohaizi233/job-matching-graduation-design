# -*- coding: utf-8 -*-
"""P7 场景 9：数据集冻结与 SHA-256 复验（协议第九节）。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import jload, make_pair, write_csv, write_jsonl

from job_matching.annotation.freeze import (
    FREEZE_STAGES, FreezeError, assign_splits, freeze_dataset, mutual_exclusivity_checks,
    verify_freeze,
)
from job_matching.annotation.schema import FINAL_LABEL_FIELDS


def _pairs(n=4, split_a="dev_validation", split_b="blind_test"):
    out = []
    for i in range(n):
        out.append(make_pair(i, pid=f"pair-{i:04d}", rid=f"resume_{i // 2:03d}",
                             jid=f"job_{i:03d}",
                             split=(split_a if i < n // 2 else split_b)))
    return out


def _labels(n=4):
    return [{"pair_id": f"pair-{i:04d}", "final_relevance": str(i % 3),
             "final_source": "both_agree", "final_confidence": "high",
             "annotator_a_id": "annotator_A", "annotator_a_relevance": str(i % 3),
             "annotator_b_id": "annotator_B", "annotator_b_relevance": str(i % 3),
             "arbitrator_id": "", "reason": "1,2", "evidence": "简历：python",
             "annotation_timestamp": "2026-10-29T10:00:00",
             "protocol_version": "phase4-3a-annotation-v1"}
            for i in range(n)]


GOOD_AQ = {
    "annotation_status": "complete",
    "open_disagreements": 0,
    "unjudgeable_forced": 0,
    "synthetic_pairs_included": 0,
}
RESP = {"annotators": ["annotator_A", "annotator_B"], "arbitrator": "arbitrator_1",
        "data_sources": "data/raw/job-education (apache-2.0)"}


class P7TestFreezeGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _files(self):
        p = write_jsonl(_pairs(), self.dir / "pairs.jsonl")
        l = write_csv(_labels(), list(FINAL_LABEL_FIELDS), self.dir / "final_labels.csv")
        return {"pairs": p, "final_labels": l}

    def test_p7_unknown_stage_rejected(self):
        with self.assertRaises(FreezeError):
            freeze_dataset(stage="xxx", out_dir=self.dir / "out", pairs_file=self.dir / "p",
                           files={}, dataset_version="v", source_stats={})

    def test_p7_missing_file_rejected(self):
        with self.assertRaises(FreezeError):
            freeze_dataset(stage="pool", out_dir=self.dir / "out",
                           pairs_file=self.dir / "nope.jsonl",
                           files={"pairs": self.dir / "nope.jsonl"},
                           dataset_version="v", source_stats={})

    def test_p7_evalset_requires_complete_annotation(self):
        files = self._files()
        for bad in ("pending", "in_progress", "invalid"):
            with self.assertRaises(FreezeError) as ctx:
                freeze_dataset(stage="evalset", out_dir=self.dir / f"o_{bad}",
                               pairs_file=files["pairs"], files=files,
                               dataset_version="v", source_stats={},
                               annotation_quality={**GOOD_AQ, "annotation_status": bad},
                               responsibility=RESP)
            self.assertIn("annotation_status", str(ctx.exception))

    def test_p7_evalset_rejects_open_disagreements(self):
        files = self._files()
        with self.assertRaises(FreezeError) as ctx:
            freeze_dataset(stage="evalset", out_dir=self.dir / "o", pairs_file=files["pairs"],
                           files=files, dataset_version="v", source_stats={},
                           annotation_quality={**GOOD_AQ, "open_disagreements": 2},
                           responsibility=RESP)
        self.assertIn("分歧", str(ctx.exception))

    def test_p7_evalset_rejects_unjudgeable_forced(self):
        files = self._files()
        with self.assertRaises(FreezeError) as ctx:
            freeze_dataset(stage="evalset", out_dir=self.dir / "o", pairs_file=files["pairs"],
                           files=files, dataset_version="v", source_stats={},
                           annotation_quality={**GOOD_AQ, "unjudgeable_forced": 1},
                           responsibility=RESP)
        self.assertIn("unjudgeable", str(ctx.exception))

    def test_p7_evalset_rejects_synthetic_pairs(self):
        files = self._files()
        with self.assertRaises(FreezeError) as ctx:
            freeze_dataset(stage="evalset", out_dir=self.dir / "o", pairs_file=files["pairs"],
                           files=files, dataset_version="v", source_stats={},
                           annotation_quality={**GOOD_AQ, "synthetic_pairs_included": 3},
                           responsibility=RESP)
        self.assertIn("合成", str(ctx.exception))

    def test_p7_evalset_requires_responsibility_record(self):
        files = self._files()
        with self.assertRaises(FreezeError) as ctx:
            freeze_dataset(stage="evalset", out_dir=self.dir / "o", pairs_file=files["pairs"],
                           files=files, dataset_version="v", source_stats={},
                           annotation_quality=GOOD_AQ, responsibility=None)
        self.assertIn("责任", str(ctx.exception))

    def test_p7_pool_stage_freezes_without_annotation(self):
        files = self._files()
        man = freeze_dataset(stage="pool", out_dir=self.dir / "pool_out",
                             pairs_file=files["pairs"],
                             files={"pairs": files["pairs"]},
                             dataset_version="pool-v1", source_stats={"note": "unit"})
        self.assertEqual(man["stage"], "pool")
        self.assertIn("pairs", man["files"])
        self.assertRegex(man["files"]["pairs"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue((self.dir / "pool_out" / "manifest.json").exists())


class P7TestFreezeVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _freeze(self):
        p = write_jsonl(_pairs(), self.dir / "pairs.jsonl")
        l = write_csv(_labels(), list(FINAL_LABEL_FIELDS), self.dir / "final_labels.csv")
        files = {"pairs": p, "final_labels": l}
        man = freeze_dataset(stage="evalset", out_dir=self.dir / "evalset_v1",
                             pairs_file=p, files=files, dataset_version="evalset-v1",
                             source_stats={"pairs": 4}, label_distribution={"0": 1, "1": 1, "2": 2},
                             annotation_quality=GOOD_AQ, responsibility=RESP)
        return man, p, l

    def test_p7_freeze_then_verify_ok(self):
        man, _p, _l = self._freeze()
        self.assertEqual(man["dataset_version"], "evalset-v1")
        self.assertEqual(man["annotation_quality"], GOOD_AQ)
        self.assertEqual(man["responsibility"], RESP)
        self.assertIn("frozen_at", man)
        self.assertIn("manifest_sha256", man)
        res = verify_freeze(self.dir / "evalset_v1" / "manifest.json")
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(res["files"]), 2)
        for f in res["files"]:
            self.assertTrue(f["exists"])
            self.assertTrue(f["match"])
            self.assertEqual(f["expected"], f["actual"])

    def test_p7_tampering_detected(self):
        man, p, _l = self._freeze()
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"pair_id": "pair-9999"}, ensure_ascii=False) + "\n")
        res = verify_freeze(self.dir / "evalset_v1" / "manifest.json")
        self.assertFalse(res["ok"])
        by_key = {f["key"]: f for f in res["files"]}
        self.assertFalse(by_key["pairs"]["match"])
        self.assertNotEqual(by_key["pairs"]["expected"], by_key["pairs"]["actual"])

    def test_p7_delete_file_detected(self):
        man, _p, l = self._freeze()
        l.unlink()
        res = verify_freeze(self.dir / "evalset_v1" / "manifest.json")
        self.assertFalse(res["ok"])
        by_key = {f["key"]: f for f in res["files"]}
        self.assertFalse(by_key["final_labels"]["exists"])

    def test_p7_manifest_covers_all_files(self):
        man, _p, _l = self._freeze()
        self.assertEqual(sorted(man["files"]), ["final_labels", "pairs"])
        self.assertEqual(man["mutual_exclusivity"]["pair_id_unique"], True)
        self.assertEqual(man["sample_counts"]["pairs"], 4)
        self.assertEqual(man["sample_counts"]["resumes"], 2)


class P7TestMutualExclusivity(unittest.TestCase):
    def test_p7_unique_and_isolated(self):
        checks = mutual_exclusivity_checks(_pairs(4), _labels(4))
        self.assertTrue(checks["pair_id_unique"])
        self.assertTrue(checks["resume_job_unique"])
        self.assertTrue(checks["split_isolation_ok"])
        self.assertEqual(checks["splits_present"], ["blind_test", "dev_validation"])
        self.assertTrue(checks["final_label_unique"])
        self.assertEqual(checks["final_label_missing_for_pairs"], 0)
        self.assertEqual(checks["final_label_unknown_pairs"], 0)

    def test_p7_duplicate_pair_id_detected(self):
        pairs = _pairs(2) + [_pairs(2)[0]]
        checks = mutual_exclusivity_checks(pairs)
        self.assertFalse(checks["pair_id_unique"])
        self.assertGreater(checks["pair_id_duplicates"], 0)

    def test_p7_split_leakage_detected(self):
        pairs = _pairs(4)
        pairs[0]["split"] = "blind_test"   # resume_000 同时出现在两个 split
        checks = mutual_exclusivity_checks(pairs)
        self.assertFalse(checks["split_isolation_ok"])
        self.assertGreater(checks["split_resume_overlap"]["blind_test__dev_validation"], 0)

    def test_p7_missing_final_labels_counted(self):
        checks = mutual_exclusivity_checks(_pairs(4), _labels(2))
        self.assertEqual(checks["final_label_missing_for_pairs"], 2)
        self.assertEqual(checks["final_label_unknown_pairs"], 0)

    def test_p7_unknown_final_label_pair_counted(self):
        labels = _labels(2) + [{"pair_id": "pair-9999"}]
        checks = mutual_exclusivity_checks(_pairs(4), labels)
        self.assertEqual(checks["final_label_unknown_pairs"], 1)

    def test_p7_split_assignment_is_deterministic(self):
        pairs = _pairs(6)
        a = assign_splits(pairs, seed=20261211, blind_ratio=0.5)
        b = assign_splits(pairs, seed=20261211, blind_ratio=0.5)
        self.assertEqual([p["split"] for p in a], [p["split"] for p in b])
        self.assertEqual(FREEZE_STAGES, ("pool", "evalset"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
