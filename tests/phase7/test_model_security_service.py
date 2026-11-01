# -*- coding: utf-8 -*-
"""Phase7-B / B4：推理安全回归（服务级契约）。

验证（任务书 7.4）：
  - 哈希不一致时返回 HTTP 503（MODEL_ARTIFACT_TAMPERED），且**不允许降级**；
  - 权重损坏/不受信时**不触发反序列化**（loader 从未被调用）；
  - 不登记成功的 load_event；
  - 非法错误码不会吞掉原始故障（构造即拒绝 / 原始异常保留在 __cause__）；
  - 前端正确展示模型不可用或降级状态（真实组件契约静态核对）。

全部使用 tempfile 合成夹具，不触碰真实权重文件。
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from _util import ROOT  # noqa: F401

from job_matching.service.errors import ERROR_CODES, ServiceError
from job_matching.service.model_registry import ModelRegistration, ModelRegistry


def _make_artifact(dirpath: Path, name: str, payload: bytes, *,
                   sha256: str | None = None) -> dict:
    p = dirpath / name
    p.write_bytes(payload)
    return {"path": str(p), "bytes": len(payload),
            "sha256": sha256 or hashlib.sha256(payload).hexdigest()}


class _LoaderSpy:
    def __init__(self, *, raise_exc: BaseException | None = None):
        self.calls = 0
        self.raise_exc = raise_exc

    def __call__(self, reg):
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return {"model": reg.model_id, "stub": True}


class TestArtifactGuardServiceContract(unittest.TestCase):
    """服务级：哈希门禁的错误码 / HTTP 契约 / 反序列化时序。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _tampered_registry(self) -> tuple[ModelRegistry, _LoaderSpy]:
        spy = _LoaderSpy()
        reg = ModelRegistry(loader_impl=spy)
        # manifest 登记的 sha256 与磁盘文件**不一致**（权重被替换/篡改）
        art = _make_artifact(self.dir, "w.pkl", b"trusted", sha256="0" * 64)
        reg.register(ModelRegistration(
            model_id="tamper_demo_v1", model_version="v0", task_type="matching",
            training_data_version="none", artifacts=[art], loader="legacy_match"))
        return reg, spy

    def test_tampered_checksum_maps_to_503(self):
        """哈希不一致 -> MODEL_ARTIFACT_TAMPERED，HTTP 503。"""
        reg, _spy = self._tampered_registry()
        with self.assertRaises(ServiceError) as cm:
            reg.load("tamper_demo_v1")
        err = cm.exception
        self.assertEqual("MODEL_ARTIFACT_TAMPERED", err.code)
        self.assertEqual(503, err.http_status)
        self.assertEqual(503, ERROR_CODES["MODEL_ARTIFACT_TAMPERED"][0])
        self.assertEqual("artifact_checksum_mismatch",
                         err.detail.get("failure_kind"))
        self.assertEqual("MODEL_ARTIFACT_TAMPERED",
                         err.to_dict("rid")["error"]["code"])

    def test_corrupt_weights_never_deserialized(self):
        """权重哈希不通过时 loader（反序列化入口）**一次都不能被调用**。"""
        reg, spy = self._tampered_registry()
        with self.assertRaises(ServiceError):
            reg.load("tamper_demo_v1")
        self.assertEqual(0, spy.calls, "不受信权重不得进入反序列化")
        # 缺失产物同样不触发反序列化
        art = _make_artifact(self.dir, "gone.pkl", b"x")
        (self.dir / "gone.pkl").unlink()
        reg.register(ModelRegistration(
            model_id="missing_demo_v1", model_version="v0", task_type="matching",
            training_data_version="none", artifacts=[art], loader="legacy_match"))
        with self.assertRaises(ServiceError):
            reg.load("missing_demo_v1")
        self.assertEqual(0, spy.calls)

    def test_no_successful_load_event_on_tamper(self):
        """被拒绝的加载不登记成功 load_event。"""
        reg, _spy = self._tampered_registry()
        with self.assertRaises(ServiceError):
            reg.load("tamper_demo_v1")
        self.assertEqual([], reg.load_events)
        self.assertEqual(0, reg.load_count)
        self.assertFalse(reg.is_loaded("tamper_demo_v1"))

    def test_illegal_error_code_not_swallowed(self):
        """非法错误码在构造期即被拒绝，原始故障不被吞掉。"""
        with self.assertRaises(ValueError) as cm:
            ServiceError("NOT_A_REGISTERED_CODE", "x")
        self.assertIn("NOT_A_REGISTERED_CODE", str(cm.exception))
        # loader 原始异常必须保留在 __cause__（可追溯），且分类为 MODEL_CORRUPT
        spy = _LoaderSpy(raise_exc=RuntimeError("weights bytes corrupted"))
        reg = ModelRegistry(loader_impl=spy)
        art = _make_artifact(self.dir, "c.pkl", b"good-hash")
        reg.register(ModelRegistration(
            model_id="corrupt_demo_v1", model_version="v0", task_type="matching",
            training_data_version="none", artifacts=[art], loader="legacy_match"))
        with self.assertRaises(ServiceError) as cm:
            reg.load("corrupt_demo_v1")
        err = cm.exception
        self.assertEqual("MODEL_CORRUPT", err.code)
        self.assertEqual(503, err.http_status)
        self.assertIsInstance(err.__cause__, RuntimeError)
        self.assertIn("weights bytes corrupted", str(err.__cause__))
        self.assertEqual("artifact_corrupt_or_load_failed",
                         err.detail.get("failure_kind"))

    def test_env_incompatible_distinct_from_missing(self):
        """环境不兼容与权重缺失是不同失败类型（不互相冒充）。"""
        spy = _LoaderSpy(raise_exc=ImportError("No module named 'sklearn.__old'"))
        reg = ModelRegistry(loader_impl=spy)
        art = _make_artifact(self.dir, "e.pkl", b"env")
        reg.register(ModelRegistration(
            model_id="env_demo_v1", model_version="v0", task_type="matching",
            training_data_version="none", artifacts=[art], loader="legacy_match"))
        with self.assertRaises(ServiceError) as cm:
            reg.load("env_demo_v1")
        self.assertEqual("MODEL_ENV_INCOMPATIBLE", cm.exception.code)
        self.assertEqual("env_incompatible", cm.exception.detail.get("failure_kind"))


class TestApiLevelSecurityContract(unittest.TestCase):
    """HTTP 层：不受信权重 -> 503 且不允许降级；损坏 -> 显式降级可审计。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _client_with(self, registry: ModelRegistry):
        from fastapi.testclient import TestClient
        from job_matching.service.api import create_app, make_services
        return TestClient(create_app(make_services(registry=registry)))

    @staticmethod
    def _rank_body(model_id: str, allow_fallback: bool) -> dict:
        return {
            "resume_text": "求职意向：Java开发工程师\n专业技能：Java、MySQL",
            "jobs": [{"text": "岗位：Java开发工程师\n任职要求：Java"}],
            "options": {"mode": "experimental_model", "model_id": model_id,
                        "allow_fallback": allow_fallback, "timeout_ms": 30000},
        }

    def test_tampered_hash_http_503_even_with_fallback(self):
        """哈希不一致返回 503；allow_fallback=True 也不得静默降级（不受信即拒绝）。"""
        spy = _LoaderSpy()
        registry = ModelRegistry(loader_impl=spy)
        art = _make_artifact(self.dir, "w.pkl", b"trusted", sha256="1" * 64)
        registry.register(ModelRegistration(
            model_id="tamper_demo_v1", model_version="v0", task_type="matching",
            training_data_version="none", artifacts=[art], loader="legacy_match"))
        client = self._client_with(registry)
        for fallback in (False, True):
            r = client.post("/api/v1/matching/rank",
                            json=self._rank_body("tamper_demo_v1", fallback))
            self.assertEqual(503, r.status_code, f"allow_fallback={fallback}")
            self.assertEqual("MODEL_ARTIFACT_TAMPERED", r.json()["error"]["code"])
        self.assertEqual(0, spy.calls, "HTTP 层同样不得触发反序列化")
        self.assertEqual([], registry.load_events)

    def test_corrupt_weights_degrade_explicitly_when_fallback_allowed(self):
        """允许降级时损坏模型显式降级（reason_code 登记）；拒绝时不降级返回 503。"""
        spy = _LoaderSpy(raise_exc=RuntimeError("weights bytes corrupted"))
        registry = ModelRegistry(loader_impl=spy)
        art = _make_artifact(self.dir, "c.pkl", b"good-hash")
        registry.register(ModelRegistration(
            model_id="corrupt_demo_v1", model_version="v0", task_type="matching",
            training_data_version="none", artifacts=[art], loader="legacy_match"))
        client = self._client_with(registry)

        r = client.post("/api/v1/matching/rank",
                        json=self._rank_body("corrupt_demo_v1", True))
        self.assertEqual(200, r.status_code)
        data = r.json()["data"]["ranking"]
        self.assertTrue(data.get("degradation", {}).get("degraded"))
        self.assertEqual("MODEL_CORRUPT", data["degradation"]["reason_code"])
        self.assertEqual("corrupt_demo_v1", data["degradation"]["requested_model_id"])
        # 降级必须显式可审计：不伪装成模型输出（启发式基线身份如实登记）
        self.assertEqual("heuristic_score", data["score_type"])
        self.assertEqual("baseline_skill_text_v1", data["scoring_method"])

        r2 = client.post("/api/v1/matching/rank",
                         json=self._rank_body("corrupt_demo_v1", False))
        self.assertEqual(503, r2.status_code)
        self.assertEqual("MODEL_CORRUPT", r2.json()["error"]["code"])


class TestFrontendDegradationDisplay(unittest.TestCase):
    """前端模型不可用/降级状态展示（真实组件契约核对）。

    说明：前端无单测基础设施（package.json 仅 typecheck/build），
    运行时展示的浏览器级验证登记 NOT_RUN（建议 Playwright 用例补充）；
    本测试核对真实组件**存在**降级渲染契约，防止展示逻辑被删除。
    """

    def test_matching_view_renders_degradation(self):
        src = (ROOT / "frontend" / "src" / "views" / "MatchingView.vue"
               ).read_text(encoding="utf-8")
        self.assertIn("degradation_info", src)
        self.assertIn("已降级", src)
        self.assertIn("reason_code", src)

    def test_api_types_declare_degradation_snapshot(self):
        src = (ROOT / "frontend" / "src" / "api" / "types.ts"
               ).read_text(encoding="utf-8")
        self.assertIn("degradation_info", src)

    def test_error_codes_exposed_to_frontend(self):
        """错误码目录通过 /api/v1/models 暴露，前端可映射展示。"""
        from job_matching.service.errors import error_catalog
        codes = {c["code"] for c in error_catalog()}
        self.assertIn("MODEL_ARTIFACT_TAMPERED", codes)
        self.assertIn("MODEL_MISSING", codes)


if __name__ == "__main__":
    unittest.main()
