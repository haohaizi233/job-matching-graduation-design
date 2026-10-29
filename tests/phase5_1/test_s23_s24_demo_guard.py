# -*- coding: utf-8 -*-
"""S23~S24：离线闭环演示运行成功 / 不触碰 Phase4 历史模型与 Gold 盲测数据。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _util import (HERE, ROOT, diff_snapshots, find_protected_write_calls,
                   guard_snapshot)

DEMO_SCRIPT = ROOT / "scripts" / "phase5_1" / "demo_offline.py"

# 模块导入即取指纹（先于任何测试执行），用于 S24 前后对比
BASELINE_SNAPSHOT = guard_snapshot()


class S23OfflineDemoPipeline(unittest.TestCase):
    """场景 23：离线闭环演示（简历 -> 画像 -> 排序 -> 解释 -> JSON）。"""

    def test_demo_runs_end_to_end(self):
        with tempfile.TemporaryDirectory(prefix="ph51_s23_") as td:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(DEMO_SCRIPT), "--out-dir", td],
                capture_output=True, text=True, cwd=str(ROOT), timeout=300)
            self.assertEqual(proc.returncode, 0,
                             f"演示失败: {proc.stderr[-800:]}")
            out_dir = Path(td)
            demo = json.loads((out_dir / "demo-output.json").read_text(encoding="utf-8"))
            integration = json.loads(
                (out_dir / "integration-results.json").read_text(encoding="utf-8"))

            self.assertTrue(demo["demo"])
            self.assertEqual(demo["label_source"], "synthetic_or_unlabeled")
            self.assertFalse(demo["formal_evaluation"])
            self.assertTrue(demo["input"]["resume_is_synthetic"])

            ranking = demo["ranking"]
            self.assertEqual(ranking["score_type"], "heuristic_score")
            self.assertEqual(len(ranking["results"]), 4)
            self.assertEqual([r["rank"] for r in ranking["results"]], [1, 2, 3, 4])
            for r in ranking["results"]:
                self.assertTrue(r["evidence"] or r["warnings"])
                self.assertIn(r["education_constraint"]["status"],
                              ("satisfied", "not_satisfied", "insufficient_evidence",
                               "requirement_unclear"))

            self.assertTrue(integration["demo"])
            self.assertFalse(integration["formal_evaluation"])
            self.assertEqual(integration["h2_status"].split("（")[0], "BLOCKED")
            self.assertEqual(len(integration["pipeline"]), 4)

    def test_demo_output_is_not_gold_label(self):
        with tempfile.TemporaryDirectory(prefix="ph51_s23b_") as td:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(DEMO_SCRIPT), "--out-dir", td],
                capture_output=True, text=True, cwd=str(ROOT), timeout=300)
            self.assertEqual(proc.returncode, 0)
            demo = json.loads((Path(td) / "demo-output.json").read_text(encoding="utf-8"))
            blob = json.dumps(demo, ensure_ascii=False)
            for banned in ("人工正确结果", "gold_label", "human_gold_label", "calibrated_score"):
                self.assertNotIn(banned, blob)


class S24HistoryAssetsUntouched(unittest.TestCase):
    """场景 24：不触碰 Phase4 历史模型与 Gold 盲测数据。"""

    def test_model_and_gold_files_unchanged(self):
        after = guard_snapshot()
        changed = diff_snapshots(BASELINE_SNAPSHOT, after)
        self.assertEqual(changed, [], f"历史模型/Gold 数据被改动: {changed[:10]}")

    def test_no_write_calls_targeting_history_assets(self):
        sources = [DEMO_SCRIPT,
                   *(ROOT / "scripts" / "phase5_1").glob("*.py"),
                   *(ROOT / "src" / "job_matching" / "service").glob("*.py"),
                   *(HERE).glob("*.py")]
        problems = find_protected_write_calls(sources)
        self.assertEqual(problems, [])

    def test_service_never_writes_model_checkpoints(self):
        from job_matching.service import model_registry
        src = (ROOT / "src" / "job_matching" / "service" / "model_registry.py").read_text(
            encoding="utf-8")
        for banned in ("torch.save", "joblib.dump", "model.save(", ".fit("):
            self.assertNotIn(banned, src)
        self.assertTrue(hasattr(model_registry, "ModelRegistry"))


if __name__ == "__main__":
    unittest.main()
