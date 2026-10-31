# -*- coding: utf-8 -*-
"""Phase7 预注册协议锁定测试（防 HARKing 的软件契约）。

这些测试**不依赖**真实人工数据：它们锁定「评价口径本身」，
确保任何人在看到 blind_test 结果后无法悄悄修改主指标 / 切分 / 通过条件。
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from _util import ROOT

import verify_preregistration as vp  # noqa: E402  (scripts/phase7 已入 sys.path)

PROTOCOL = ROOT / "configs" / "phase7-preregistered-protocol-v1.json"
LOCKFILE = ROOT / "configs" / "phase7-preregistered-protocol-v1.sha256"

#: 预注册文件的**钉死哈希**。修改协议必须新建版本文件 + 走 amendment，
#: 并在 code review 中显式更新本常量——从而让「事后改口径」永远留下可见痕迹。
PINNED_SHA256 = "7112e151e2553f52bf16530ab717ad2bf4278b3660b97dfbfd252b2b95eb65f5"


class TestPreregistrationLock(unittest.TestCase):
    def test_protocol_file_exists(self):
        self.assertTrue(PROTOCOL.exists(), "预注册协议文件必须存在")

    def test_pinned_hash_matches_file(self):
        digest = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
        self.assertEqual(
            PINNED_SHA256, digest,
            "预注册协议被修改：必须新建版本文件并走 amendment，不得覆盖 v1")

    def test_sidecar_lock_matches_file(self):
        recorded = LOCKFILE.read_text(encoding="utf-8").strip().split()[0]
        digest = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
        self.assertEqual(recorded.lower(), digest.lower())

    def test_protocol_id_and_status_locked(self):
        proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertEqual("phase7-eval-protocol-v1", proto["protocol_id"])
        self.assertEqual("preregistered_locked", proto["status"])

    def test_primary_metric_is_ndcg_at_10(self):
        proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertEqual("NDCG@10", proto["metrics"]["primary"])

    def test_blind_test_unlock_requires_locked_model(self):
        proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertTrue(proto["model_selection_rule"]["lock_before_blind_test"])
        self.assertIn("selected_model_id", proto["model_selection_rule"]["lock_fields"])
        self.assertIn("06-model-selection", proto["data_boundaries"]["blind_test"]["unlock_condition"])

    def test_split_is_group_level_by_resume(self):
        proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertIn("resume_id", proto["data_boundaries"]["split_unit"])
        self.assertEqual("paired bootstrap", proto["statistical_method"]["method"])
        self.assertEqual("查询组（resume_id）", proto["statistical_method"]["resampling_unit"])

    def test_not_computable_policy_forbids_fabrication(self):
        proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertEqual("not_computable", proto["not_computable_policy"]["status_value"])
        self.assertIn("填充 0", proto["not_computable_policy"]["forbidden"])

    def test_no_downgrade_rule_present(self):
        proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        self.assertIn("no_downgrade_rule", proto["pass_criteria"])

    def test_verify_script_passes(self):
        rc = vp.main([])
        self.assertEqual(0, rc, "verify_preregistration 必须整体通过")

    def test_verify_script_detects_tampering(self):
        """负向测试：临时改动协议副本必须被哈希/不变式校验拦下。"""
        import tempfile
        import shutil
        import os
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            shutil.copy(PROTOCOL, td / PROTOCOL.name)
            shutil.copy(LOCKFILE, td / LOCKFILE.name)
            bad = json.loads(PROTOCOL.read_text(encoding="utf-8"))
            bad["metrics"]["primary"] = "Precision@5"   # 事后改主指标
            (td / PROTOCOL.name).write_text(json.dumps(bad, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
            old_root = vp.ROOT
            try:
                vp.ROOT = td
                vp.PROTOCOL = td / PROTOCOL.name
                vp.LOCKFILE = td / LOCKFILE.name
                self.assertNotEqual(0, vp.main([]), "篡改后的协议必须被判 FAIL")
            finally:
                vp.ROOT = old_root
                vp.PROTOCOL = ROOT / "configs" / PROTOCOL.name
                vp.LOCKFILE = ROOT / "configs" / LOCKFILE.name

    def test_no_blind_test_outputs_exist(self):
        hits = vp.find_premature_blind_outputs()
        self.assertEqual([], hits, f"blind_test 结果产物提前存在: {hits}")


if __name__ == "__main__":
    unittest.main()
