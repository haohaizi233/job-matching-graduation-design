# -*- coding: utf-8 -*-
"""P16 场景 14–15：盲测保护 / 数据冻结后哈希校验（Phase4-3A-2 模块 E）。

纪律：冻结与哈希复验完成前 blind_test 不得被标记正式通过；
冻结后任何文件改动必须被 verify_freeze 检出，修改必须升版本号。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from job_matching.annotation import gold_gate
from job_matching.annotation.freeze import (
    FreezeError, freeze_dataset, mutual_exclusivity_checks, verify_freeze,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _pairs_rows():
    return [
        {"pair_id": "pair-0001", "resume_id": "resume_a", "job_id": "job_1",
         "split": "dev_validation", "is_synthetic": False},
        {"pair_id": "pair-0002", "resume_id": "resume_a", "job_id": "job_2",
         "split": "dev_validation", "is_synthetic": False},
        {"pair_id": "pair-0003", "resume_id": "resume_b", "job_id": "job_3",
         "split": "blind_test", "is_synthetic": False},
    ]


class P16TestBlindProtection(unittest.TestCase):
    """场景 14：盲测集在冻结前不可被标记正式通过。"""

    def test_p16_blind_pass_before_freeze_rejected(self):
        res = gold_gate.check_blind_status(freeze_verified=False, blind_claimed_pass=True)
        self.assertFalse(res["ok"])
        self.assertEqual(res["violations"][0]["code"], "blind_pass_before_freeze")

    def test16_blind_pass_after_freeze_allowed(self):
        res = gold_gate.check_blind_status(freeze_verified=True, blind_claimed_pass=True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["violations"], [])

    def test_p16_not_claimed_needs_no_freeze(self):
        res = gold_gate.check_blind_status(freeze_verified=False, blind_claimed_pass=False)
        self.assertTrue(res["ok"])


class P16TestFreezeGate(unittest.TestCase):
    """evalset 冻结门禁：人工标注未完成不得冻结。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _files(self):
        pairs = self.dir / "pairs.jsonl"
        _write(pairs, "\n".join(json.dumps(r, ensure_ascii=False) for r in _pairs_rows())
               + "\n")
        labels = self.dir / "final_labels.csv"
        _write(labels, "pair_id,final_relevance\npair-0001,2\n")
        return {"pairs": pairs, "final_labels": labels}, pairs

    def test_p16_evalset_freeze_rejected_when_annotation_incomplete(self):
        files, pairs = self._files()
        with self.assertRaises(FreezeError):
            freeze_dataset(
                stage="evalset", out_dir=self.dir / "out", pairs_file=pairs, files=files,
                dataset_version="evalset-test", source_stats={},
                annotation_quality={"annotation_status": "in_progress",
                                    "open_disagreements": 0, "unjudgeable_forced": 0,
                                    "synthetic_pairs_included": 0},
                responsibility={"annotators": ["annotator_A", "annotator_B"]})

    def test_p16_evalset_freeze_rejected_with_open_disagreements(self):
        files, pairs = self._files()
        with self.assertRaises(FreezeError):
            freeze_dataset(
                stage="evalset", out_dir=self.dir / "out", pairs_file=pairs, files=files,
                dataset_version="evalset-test", source_stats={},
                annotation_quality={"annotation_status": "complete",
                                    "open_disagreements": 2, "unjudgeable_forced": 0,
                                    "synthetic_pairs_included": 0},
                responsibility={"annotators": ["annotator_A", "annotator_B"]})

    def test_p16_evalset_freeze_rejected_with_synthetic(self):
        files, pairs = self._files()
        with self.assertRaises(FreezeError):
            freeze_dataset(
                stage="evalset", out_dir=self.dir / "out", pairs_file=pairs, files=files,
                dataset_version="evalset-test", source_stats={},
                annotation_quality={"annotation_status": "complete",
                                    "open_disagreements": 0, "unjudgeable_forced": 0,
                                    "synthetic_pairs_included": 3},
                responsibility={"annotators": ["annotator_A", "annotator_B"]})


class P16TestHashVerification(unittest.TestCase):
    """场景 15：数据冻结后哈希校验。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _freeze(self):
        pairs = self.dir / "pairs.jsonl"
        _write(pairs, "\n".join(json.dumps(r, ensure_ascii=False) for r in _pairs_rows())
               + "\n")
        extra = self.dir / "extra.csv"
        _write(extra, "a,b\n1,2\n")
        files = {"pairs": pairs, "extra": extra}
        manifest = freeze_dataset(
            stage="pool", out_dir=self.dir / "out", pairs_file=pairs, files=files,
            dataset_version="pool-test", source_stats={"jobs": 3})
        return manifest, pairs, extra

    def test_p16_freeze_then_verify_passes(self):
        self._freeze()
        res = verify_freeze(self.dir / "out" / "manifest.json")
        self.assertTrue(res["ok"], res)
        self.assertTrue(all(f["match"] for f in res["files"]))

    def test_p16_tampering_detected_after_freeze(self):
        _, pairs, _ = self._freeze()
        with open(pairs, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"pair_id": "pair-9999", "resume_id": "resume_x",
                                "job_id": "job_x", "split": "dev_validation",
                                "is_synthetic": False}, ensure_ascii=False) + "\n")
        res = verify_freeze(self.dir / "out" / "manifest.json")
        self.assertFalse(res["ok"])
        self.assertTrue(any(not f["match"] for f in res["files"]))

    def test_p16_manifest_records_sha256_for_every_file(self):
        manifest, _, _ = self._freeze()
        for key in ("pairs", "extra"):
            self.assertIn(key, manifest["files"])
            self.assertEqual(len(manifest["files"][key]["sha256"]), 64)
        self.assertTrue(manifest["manifest_sha256"])

    def test_p16_mutual_exclusivity_detects_split_overlap(self):
        rows = _pairs_rows()
        rows.append({"pair_id": "pair-0004", "resume_id": "resume_b", "job_id": "job_4",
                     "split": "dev_validation", "is_synthetic": False})
        checks = mutual_exclusivity_checks(rows)
        self.assertFalse(checks["split_isolation_ok"])
        self.assertTrue(checks["split_resume_overlap"])
        self.assertTrue(all(v > 0 for v in checks["split_resume_overlap"].values()))


if __name__ == "__main__":
    unittest.main()
