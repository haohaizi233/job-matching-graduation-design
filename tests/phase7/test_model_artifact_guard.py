# -*- coding: utf-8 -*-
"""Phase7 / P7-5：模型产物可信哈希门禁（加载前强制校验）与负向测试。

背景：`joblib.load` / `pickle.load` / `torch.load` 均可执行任意代码。
在反序列化**之前**做 sha256 可信校验是最小代价的防线。
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _util import ROOT  # noqa: F401

from job_matching.service.errors import ServiceError
from job_matching.service.model_registry import ModelRegistration, ModelRegistry


def _make_artifact(dirpath: Path, name: str, payload: bytes) -> dict:
    p = dirpath / name
    p.write_bytes(payload)
    return {"path": str(p), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


class TestModelArtifactGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _reg(self, artifacts, **kw):
        return ModelRegistration(
            model_id="t_model", model_version="v0", task_type="test",
            training_data_version="none", artifacts=artifacts,
            loader="none", **kw)

    def test_load_ok_when_checksum_matches(self):
        art = _make_artifact(self.dir, "model.pkl", b"trusted-bytes")
        loaded = []
        reg = ModelRegistry(loader_impl=lambda r: loaded.append(r) or "OBJ")
        reg.register(self._reg([art]))
        self.assertEqual("OBJ", reg.load("t_model"))
        self.assertEqual(1, len(loaded))

    def test_load_refused_when_checksum_mismatched(self):
        art = _make_artifact(self.dir, "model.pkl", b"trusted-bytes")
        art["sha256"] = "0" * 64        # 篡改后的"期望值"
        loaded = []
        reg = ModelRegistry(loader_impl=lambda r: loaded.append(r) or "OBJ")
        reg.register(self._reg([art]))
        with self.assertRaises(ServiceError) as cm:
            reg.load("t_model")
        self.assertEqual("MODEL_ARTIFACT_TAMPERED", cm.exception.code)
        self.assertEqual([], loaded, "哈希不匹配时绝不允许触发反序列化加载")

    def test_load_refused_when_artifact_missing(self):
        art = {"path": str(self.dir / "absent.pkl"), "bytes": 1,
               "sha256": "1" * 64}
        loaded = []
        reg = ModelRegistry(loader_impl=lambda r: loaded.append(r) or "OBJ")
        reg.register(self._reg([art]))
        with self.assertRaises(ServiceError) as cm:
            reg.load("t_model")
        self.assertEqual("MODEL_ARTIFACT_TAMPERED", cm.exception.code)
        self.assertEqual([], loaded)

    def test_content_tamper_detected_after_registration(self):
        """登记后文件被改写也必须被拦下（不是只校验登记时刻）。"""
        art = _make_artifact(self.dir, "model.pkl", b"original")
        reg = ModelRegistry(loader_impl=lambda r: "OBJ")
        reg.register(self._reg([art]))
        (self.dir / "model.pkl").write_bytes(b"tampered-payload")
        with self.assertRaises(ServiceError) as cm:
            reg.load("t_model")
        self.assertEqual("MODEL_ARTIFACT_TAMPERED", cm.exception.code)

    def test_no_artifacts_registered_skips_check(self):
        """未登记 artifact 的模型保持既有行为（兼容性最小改动）。"""
        reg = ModelRegistry(loader_impl=lambda r: "OBJ")
        reg.register(self._reg([]))
        self.assertEqual("OBJ", reg.load("t_model"))

    def test_no_sha256_registered_skips_check(self):
        art = {"path": str(self.dir / "model.pkl"), "bytes": 1}
        (self.dir / "model.pkl").write_bytes(b"x")
        reg = ModelRegistry(loader_impl=lambda r: "OBJ")
        reg.register(self._reg([art]))
        self.assertEqual("OBJ", reg.load("t_model"))

    def test_verify_can_be_disabled_explicitly(self):
        art = _make_artifact(self.dir, "model.pkl", b"trusted-bytes")
        art["sha256"] = "0" * 64
        reg = ModelRegistry(loader_impl=lambda r: "OBJ", verify_before_load=False)
        reg.register(self._reg([art]))
        self.assertEqual("OBJ", reg.load("t_model"))

    def test_load_event_not_recorded_on_refusal(self):
        art = _make_artifact(self.dir, "model.pkl", b"trusted-bytes")
        art["sha256"] = "0" * 64
        reg = ModelRegistry(loader_impl=lambda r: "OBJ")
        reg.register(self._reg([art]))
        with self.assertRaises(ServiceError):
            reg.load("t_model")
        self.assertEqual(0, reg.load_count)
        self.assertEqual([], reg.load_events)

    def test_untrusted_source_documented(self):
        """纪律：不受信来源权重禁止加载，必须有书面说明。"""
        doc = (ROOT / "models" / "LICENSE-MODELS.md").read_text(encoding="utf-8")
        self.assertIn("禁止加载", doc)
        self.assertIn("UNKNOWN", doc)


if __name__ == "__main__":
    unittest.main()
