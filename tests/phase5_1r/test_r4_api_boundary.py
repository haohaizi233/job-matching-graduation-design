# -*- coding: utf-8 -*-
"""R4：API 边界与安全加固回归（Phase5-1R F-007）。

业务不变量：
  * 高资源消耗操作（Base64 解码、文档解析）之前完成全部可行的前置检查；
  * JSON 请求体 / Base64 字符串 / 解码后文件 / 解析后文本 四级大小上限全部生效；
  * 文件格式白名单：非 txt/docx/pdf 明确拒绝（415），不落临时文件解析；
  * X-Request-ID 受限字符集 + 长度白名单，非法值服务端重新生成（防日志注入）；
  * 错误响应不携带本地绝对路径、不泄露堆栈；
  * 默认部署定位为本地开发（无认证），文档口径不得宣称生产安全达标。
"""
from __future__ import annotations

import base64
import io
import logging
import unittest

import _util as U  # noqa: F401

from job_matching.service import api as api_mod
from job_matching.service.errors import ERROR_CODES, ServiceError, redact_local_paths
from job_matching.service.logging_utils import get_service_logger
from job_matching.service.text_extract import (MAX_UPLOAD_BYTES, SUPPORTED_EXTENSIONS,
                                               extract_document_bytes)


def make_client(**config_over):
    from fastapi.testclient import TestClient
    svc = api_mod.make_services()
    svc.config.update(config_over)
    return TestClient(api_mod.create_app(svc))


def capture_logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    lg = get_service_logger("job_matching.service")
    lg.setLevel(logging.DEBUG)
    lg.addHandler(handler)
    return stream, handler, lg


class R4UploadLimits(unittest.TestCase):
    """四级大小上限 + 格式白名单。"""

    def test_request_body_limit(self):
        client = make_client(max_request_bytes=256)
        r = client.post("/api/v1/profiles/resume/parse",
                        json={"text": "求职意向：Java开发\n" + "技能" * 200})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

    def test_base64_length_limit_unit(self):
        big = "A" * (api_mod.MAX_BASE64_CHARS + 10)
        with self.assertRaises(ServiceError) as cm:
            api_mod._decode_upload("a.txt", big)
        self.assertEqual(cm.exception.code, "PAYLOAD_TOO_LARGE")

    def test_estimated_decoded_size_checked_before_decode(self):
        """预估体积超限必须在 b64decode 之前拒绝：即使字符非法也不会进入解码。"""
        evil = "!" * (MAX_UPLOAD_BYTES // 3 * 4 + 64)   # 非法 base64 字符 + 超大长度
        with self.assertRaises(ServiceError) as cm:
            api_mod._decode_upload("a.txt", evil)
        self.assertEqual(cm.exception.code, "PAYLOAD_TOO_LARGE")   # 而非解码失败

    def test_decoded_bytes_limit(self):
        raw = b"x" * (MAX_UPLOAD_BYTES + 1)
        with self.assertRaises(ServiceError) as cm:
            extract_document_bytes(raw, "a.txt")
        self.assertEqual(cm.exception.code, "PAYLOAD_TOO_LARGE")

    def test_format_whitelist(self):
        self.assertEqual(SUPPORTED_EXTENSIONS, ("txt", "docx", "pdf"))
        with self.assertRaises(ServiceError) as cm:
            extract_document_bytes(b"MZ...", "evil.exe")
        self.assertEqual(cm.exception.code, "UNSUPPORTED_FORMAT")
        with self.assertRaises(ServiceError):
            extract_document_bytes(b"PK...", "noext")

    def test_api_rejects_unsupported_format(self):
        client = make_client()
        payload = {"file_name": "resume.exe",
                   "content_base64": base64.b64encode(b"MZ binary").decode()}
        r = client.post("/api/v1/profiles/resume/parse", json=payload)
        self.assertEqual(r.status_code, 415)
        self.assertEqual(r.json()["error"]["code"], "UNSUPPORTED_FORMAT")

    def test_text_length_limit(self):
        client = make_client()
        r = client.post("/api/v1/profiles/resume/parse",
                        json={"text": "技" * (api_mod.MAX_TEXT_CHARS + 100)})
        self.assertIn(r.status_code, (413, 422))
        self.assertIn(r.json()["error"]["code"], ("PAYLOAD_TOO_LARGE", "INVALID_REQUEST"))

    def test_parse_after_all_preliminary_checks(self):
        """非法 Base64：先过长度/预估检查，再报解码失败（顺序不可颠倒）。"""
        with self.assertRaises(ServiceError) as cm:
            api_mod._decode_upload("a.txt", "!!!not-base64!!!")
        self.assertEqual(cm.exception.code, "INVALID_REQUEST")

    def test_upload_requires_file_name(self):
        with self.assertRaises(ServiceError) as cm:
            api_mod._decode_upload("", "aGVsbG8=")
        self.assertEqual(cm.exception.code, "INVALID_REQUEST")


class R4RequestTracking(unittest.TestCase):
    """X-Request-ID 白名单与请求元信息日志。"""

    def test_valid_request_id_passthrough(self):
        client = make_client()
        r = client.get("/api/v1/health", headers={"X-Request-ID": "req.valid_1-2"})
        self.assertEqual(r.headers.get("X-Request-ID"), "req.valid_1-2")

    def test_malicious_request_id_replaced(self):
        for bad in ("bad\nid: injected", "x" * 200, "id with space", "id\ttab",
                    "id!bad@#$", "id=equals?query"):
            client = make_client()
            r = client.get("/api/v1/health", headers={"X-Request-ID": bad})
            got = r.headers.get("X-Request-ID", "")
            self.assertNotEqual(got, bad, bad)
            self.assertRegex(got, r"^[A-Za-z0-9._-]{1,64}$", bad)

    def test_logs_record_metadata_not_body(self):
        client = make_client()
        stream, handler, lg = capture_logs()
        try:
            client.post("/api/v1/profiles/resume/parse",
                        json={"text": "求职意向：Java\n联系方式：13812345678",
                              "profile_id": "stu_log"})
            out = stream.getvalue()
        finally:
            lg.removeHandler(handler)
        self.assertNotIn("13812345678", out)
        self.assertNotIn("求职意向", out)          # 正文不入日志
        self.assertIn("request", out)              # 元信息保留

    def test_rate_limit(self):
        client = make_client(rate_limit_per_minute=2)
        codes = [client.get("/api/v1/health").status_code for _ in range(3)]
        self.assertEqual(codes[:2], [200, 200])
        self.assertEqual(codes[2], 429)

    def test_rate_limit_returns_error_code(self):
        client = make_client(rate_limit_per_minute=1)
        client.get("/api/v1/health")
        r = client.get("/api/v1/health")
        self.assertEqual(r.json()["error"]["code"], "RATE_LIMITED")


class R4ErrorHygiene(unittest.TestCase):
    """错误响应不泄露本地路径 / 不吞错 / 错误码登记一致。"""

    def test_local_paths_redacted(self):
        payload = {"detail": {"missing": r"D:\desktop\毕业设计\models\x.pt",
                              "nested": [r"C:\Users\me\secret\file.txt"]}}
        out = redact_local_paths(payload)
        blob = str(out)
        self.assertNotIn("D:\\desktop", blob)
        self.assertNotIn("C:\\Users", blob)
        self.assertIn("<local_path>", blob)

    def test_error_catalog_complete(self):
        for code, (status, meaning) in ERROR_CODES.items():
            err = ServiceError(code, "test message")
            self.assertEqual(err.http_status, status)
            self.assertTrue(meaning)
        with self.assertRaises(ValueError):
            ServiceError("NOT_REGISTERED_CODE", "x")

    def test_error_envelope_no_paths(self):
        client = make_client()
        r = client.post("/api/v1/profiles/resume/parse", json={})
        body = r.json()
        self.assertIn("error", body)
        self.assertIn("code", body["error"])
        self.assertNotIn("Traceback", str(body))
        import re
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", str(body)))

    def test_unknown_model_error_is_explicit(self):
        client = make_client()
        r = client.post("/api/v1/matching/rank",
                        json={"resume_text": "求职意向：Java开发工程师",
                              "jobs": [{"text": "Java开发工程师\n任职要求：1年经验"}],
                              "options": {"mode": "experimental_model",
                                          "model_id": "no_such_model",
                                          "allow_fallback": False}})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "MODEL_MISSING")


class R4DeploymentScope(unittest.TestCase):
    """API 暴露范围：开发阶段默认本地使用，不得宣称生产安全达标。"""

    def test_deployment_declared_local_dev_only(self):
        svc = api_mod.make_services()
        dep = str(svc.config.get("deployment", ""))
        self.assertIn("local_dev_only", dep)
        self.assertIn("认证", dep)

    def test_limits_exposed_in_config(self):
        svc = api_mod.make_services()
        for key in ("max_request_bytes", "max_base64_chars", "max_upload_bytes",
                    "max_text_chars", "rate_limit_per_minute"):
            self.assertIn(key, svc.config)

    def test_openapi_documented(self):
        client = make_client()
        r = client.get("/openapi.json")
        self.assertEqual(r.status_code, 200)
        spec = r.json()
        for path in ("/api/v1/health", "/api/v1/profiles/resume/parse",
                     "/api/v1/matching/rank"):
            self.assertIn(path, spec["paths"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
