# -*- coding: utf-8 -*-
"""E6：实验管理与既有成果保护（manifest 关联 / 4.1 产物未受影响 / pip check）。"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from _util import MATCHING_MODELS, ROOT, all_run_dirs, jload


class E6Experiments(unittest.TestCase):
    def test_run_manifests_reference_config_and_data(self):
        runs = all_run_dirs(include_smoke=True)
        self.assertGreaterEqual(len(runs), 1, "没有找到任何实验 run 目录")
        for run in runs:
            meta = jload(run / "manifest.json")
            for key in ("run_id", "label_order", "thresholds", "threshold_selected_on",
                        "gold_policy", "data", "input_mode", "experiment"):
                self.assertIn(key, meta, f"{run.name} 缺少 {key}")
            self.assertTrue((run / "config.json").exists(), f"{run.name} 缺 config.json")
            self.assertTrue((run / "thresholds.json").exists(), f"{run.name} 缺 thresholds.json")
            self.assertEqual(meta["label_order"],
                             ["博士", "硕士", "本科", "大专", "学历不限", "学历不明"])

    def test_gold_never_used_for_selection(self):
        for run in all_run_dirs(include_smoke=True):
            meta = jload(run / "manifest.json")
            self.assertNotIn("gold", meta["threshold_selected_on"])
            self.assertIn("gold_holdout", meta["gold_policy"])

    def test_metrics_sets_are_labelled_with_provenance(self):
        for run in all_run_dirs(include_smoke=False) or all_run_dirs(include_smoke=True):
            metrics = jload(run / "metrics.json")
            for set_name, m in metrics.items():
                if not isinstance(m, dict):
                    continue
                self.assertIn("label_provenance", m, f"{run.name}/{set_name} 未标注标签来源")
                self.assertIn(m["label_provenance"], ("pseudo_online", "human_gold"))

    def test_matching_phase41_artifacts_untouched(self):
        """4.1 的模型与报告必须仍然存在且自洽（本阶段只新增，不覆盖）。"""
        runs = [p for p in MATCHING_MODELS.glob("*/*/*") if (p / "manifest.json").exists()]
        self.assertGreaterEqual(len(runs), 12, "4.1 匹配模型目录数量异常")
        results = ROOT / "reports" / "model-training" / "results.json"
        tests = ROOT / "reports" / "model-training" / "model-tests.json"
        self.assertTrue(results.exists(), "4.1 results.json 丢失")
        self.assertTrue(tests.exists(), "4.1 model-tests.json 丢失")
        t = jload(tests)
        self.assertTrue(t["ok"], "4.1 测试报告状态被改动")
        self.assertEqual(t["totals"]["fail"], 0)

    def test_pip_check_passes(self):
        out = subprocess.run([sys.executable, "-m", "pip", "check"],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, f"pip check 失败:\n{out.stdout}\n{out.stderr}")

    def test_raw_data_not_written_by_education_training(self):
        raw = ROOT / "data" / "raw"
        forbidden = {".npy", ".npz", ".parquet", ".pkl", ".pt"}
        offenders = [str(p.relative_to(ROOT)) for p in raw.rglob("*")
                     if p.is_file() and p.suffix.lower() in forbidden
                     and ".cache" not in str(p)]
        self.assertEqual(offenders, [], f"data/raw 出现训练产物: {offenders}")


if __name__ == "__main__":
    unittest.main()
