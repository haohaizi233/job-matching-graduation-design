# -*- coding: utf-8 -*-
"""P3 模型登记 / checkpoint 真实存在 / 缺失与不兼容处理。

纪律（任务书 3.1 / 4.2）：
  * 报告里有 checkpoint 路径 != 机器上有可加载的模型，必须逐个真实探测；
  * 缺少模型文件登记 NOT_RUN，依赖不兼容登记 ENV_INCOMPATIBLE，不得虚报 PASS；
  * 登记过程只读扫描 models/，不得改写历史 checkpoint。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "phase4_3b"))

REGISTRY = ROOT / "reports/phase4-3b/model-registry.json"
MODELS_ROOT = ROOT / "models"

VALID_STATUS = {"LOADED", "LOAD_FAILED", "ENV_INCOMPATIBLE", "NOT_RUN"}


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


class P3ModelRegistry(unittest.TestCase):
    def test_registry_file_exists_and_parses(self):
        self.assertTrue(REGISTRY.exists(), "模型登记表必须落盘")
        reg = _registry()
        self.assertGreater(len(reg.get("records", [])), 0)
        self.assertEqual("scripts/phase4_3b/build_model_registry.py", reg.get("generated_by"))

    def test_registry_is_read_only_scan(self):
        reg = _registry()
        self.assertIn("read_only_notice", reg, "登记必须声明只读扫描、未改动历史 checkpoint")

    def test_totals_match_records(self):
        reg = _registry()
        records = reg["records"]
        totals = reg["totals"]
        self.assertEqual(totals["runs"], len(records))
        by_model: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for r in records:
            by_model[r["model_id"]] = by_model.get(r["model_id"], 0) + 1
            st = r.get("inference_status") or r.get("load_status")
            by_status[st] = by_status.get(st, 0) + 1
        self.assertEqual(totals["by_model_id"], by_model)
        self.assertEqual(totals["by_inference_status"], by_status)

    def test_every_checkpoint_claimed_exists_with_matching_hash(self):
        """checkpoint_present=true 的记录必须真实存在且 SHA-256 一致。"""
        from build_model_registry import sha256_file
        reg = _registry()
        checked = 0
        for r in reg["records"]:
            if not r.get("checkpoint_present"):
                continue
            p = MODELS_ROOT / r["checkpoint_path"]
            self.assertTrue(p.exists(), f"登记声称存在但文件缺失: {r['checkpoint_path']}")
            self.assertEqual(r["checkpoint_sha256"], sha256_file(p),
                             f"{r['checkpoint_path']} 哈希与登记不一致")
            self.assertGreater(r.get("checkpoint_bytes", 0), 0)
            checked += 1
        self.assertGreater(checked, 0, "至少应有一条真实 checkpoint 记录")

    def test_missing_checkpoint_is_never_reported_loaded(self):
        for r in _registry()["records"]:
            if not r.get("checkpoint_present"):
                self.assertNotIn(r.get("inference_status"), ("LOADED",),
                                 "缺失 checkpoint 不得登记为 LOADED")
                self.assertIn(r.get("inference_status"), VALID_STATUS)

    def test_inference_status_values_are_honest(self):
        for r in _registry()["records"]:
            self.assertIn(r.get("inference_status"), VALID_STATUS,
                          f"非法推理状态: {r.get('inference_status')}")
            if r.get("inference_status") == "ENV_INCOMPATIBLE":
                self.assertTrue(r.get("load_error") or r.get("error"),
                                "ENV_INCOMPATIBLE 必须带错误证据")

    def test_find_checkpoint_returns_none_when_absent(self):
        from build_model_registry import find_checkpoint
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(find_checkpoint(Path(td)))

    def test_probe_load_missing_file_is_structured_failure(self):
        from build_model_registry import probe_load
        with tempfile.TemporaryDirectory() as td:
            res = probe_load(Path(td) / "absent.pkl", "matching.ridge")
            self.assertIn(res["load_status"], ("LOAD_FAILED", "ENV_INCOMPATIBLE"))
            self.assertIsNone(res["loaded_type"])
            self.assertTrue(res["error"])

    def test_probe_load_corrupt_file_is_structured_failure(self):
        from build_model_registry import probe_load
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "corrupt.pkl"
            bad.write_bytes(b"not a real pickle")
            res = probe_load(bad, "matching.ridge")
            self.assertIn(res["load_status"], ("LOAD_FAILED", "ENV_INCOMPATIBLE"))
            self.assertTrue(res["error"])

    def test_probe_load_missing_torch_checkpoint_is_structured_failure(self):
        from build_model_registry import probe_load
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "corrupt.pt"
            bad.write_bytes(b"\x00\x01not a torch checkpoint")
            res = probe_load(bad, "education.charcnn")
            self.assertIn(res["load_status"], ("LOAD_FAILED", "ENV_INCOMPATIBLE"))
            self.assertTrue(res["error"])

    def test_discover_enumerates_only_under_models_root(self):
        from build_model_registry import discover, MODELS_ROOT as MR
        runs = discover()
        self.assertTrue(str(MR).startswith(str(MODELS_ROOT)))
        for r in runs:
            self.assertTrue(str(r.resolve()).startswith(str(MODELS_ROOT.resolve())),
                            f"发现的运行目录必须位于 models/ 之下: {r}")

    def test_registry_covers_all_families_found_on_disk(self):
        from build_model_registry import discover
        on_disk = {str(p.relative_to(MODELS_ROOT)).replace("\\", "/")
                   for p in discover()}
        registered = {r["run_dir"] for r in _registry()["records"]}
        missing = on_disk - registered
        self.assertEqual(set(), missing, f"磁盘上存在但未登记的运行目录: {sorted(missing)[:5]}")


if __name__ == "__main__":
    unittest.main()
