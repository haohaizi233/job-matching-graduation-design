# -*- coding: utf-8 -*-
"""S19~S22：PII 日志脱敏 / API 正常异常边界 / 模型加载时机 / 确定性结果。"""
from __future__ import annotations

import io
import logging
import unittest

from _util import StubMatchPredictor

from job_matching.service import ModelRegistration, ModelRegistry, parse_resume_text
from job_matching.service.logging_utils import get_service_logger
from job_matching.service.matching import MatchingService

PII_RESUME = (
    "求职意向：Java开发工程师\n"
    "联系方式：13812345678\n"
    "邮箱：zhangsan@example.com\n"
    "专业技能：Java、MySQL\n"
)


def make_client():
    from fastapi.testclient import TestClient
    from job_matching.service.api import create_app, make_services
    return TestClient(create_app(make_services()))


def capture_logs(names=("job_matching.service", "job_matching.service.api",
                        "job_matching.service.matching")):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    loggers = []
    for name in names:
        lg = get_service_logger(name)
        lg.setLevel(logging.DEBUG)
        lg.addHandler(handler)
        loggers.append(lg)
    return stream, handler, loggers


class S19PiiLogScrubbing(unittest.TestCase):
    """场景 19：敏感内容不入日志。"""

    def test_logger_scrubs_pii(self):
        stream, handler, loggers = capture_logs()
        try:
            loggers[0].info("contact 13812345678 zhangsan@example.com")
            out = stream.getvalue()
        finally:
            for lg in loggers:
                lg.removeHandler(handler)
        self.assertNotIn("13812345678", out)
        self.assertNotIn("zhangsan@example.com", out)
        self.assertIn("***", out)

    def test_parse_endpoint_logs_no_raw_pii(self):
        client = make_client()
        stream, handler, loggers = capture_logs()
        try:
            r = client.post("/api/v1/profiles/resume/parse",
                            json={"text": PII_RESUME, "profile_id": "stu_pii"})
            out = stream.getvalue()
        finally:
            for lg in loggers:
                lg.removeHandler(handler)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("13812345678", out)
        self.assertNotIn("zhangsan@example.com", out)

    def test_profile_evidence_masked(self):
        profile = parse_resume_text(PII_RESUME, profile_id="stu_pii2", is_synthetic=True)
        blob = str(profile.to_dict())
        self.assertNotIn("13812345678", blob)
        self.assertNotIn("zhangsan@example.com", blob)
        self.assertTrue(any("pii_masked" in w for w in profile.warnings))


class S20ApiNormalAndBoundary(unittest.TestCase):
    """场景 20：API 正常、异常和边界场景。"""

    @classmethod
    def setUpClass(cls):
        cls.client = make_client()

    def test_health(self):
        r = self.client.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["data"]["status"], "ok")
        self.assertIn("request_id", d)
        self.assertIn("baseline", d["data"]["modes"])

    def test_resume_and_job_parse_and_rank(self):
        r1 = self.client.post("/api/v1/profiles/resume/parse",
                              json={"text": PII_RESUME, "profile_id": "stu_a"})
        self.assertEqual(r1.status_code, 200)
        profile = r1.json()["data"]["profile"]
        self.assertEqual(profile["parse_status"], "ok")

        r2 = self.client.post("/api/v1/profiles/job/parse",
                              json={"text": "职位名称：Java开发工程师\n任职要求：\n1. 本科及以上学历\n2. 熟悉 Java、MySQL\n岗位职责：\n1. 负责开发",
                                    "job_id": "job_a"})
        self.assertEqual(r2.status_code, 200)
        job = r2.json()["data"]["job_profile"]
        self.assertTrue(job["required_skills"])

        r3 = self.client.post("/api/v1/matching/rank",
                              json={"resume_profile": profile,
                                    "jobs": [{"profile": job}],
                                    "options": {"mode": "baseline"}})
        self.assertEqual(r3.status_code, 200)
        ranking = r3.json()["data"]["ranking"]
        self.assertEqual(ranking["score_type"], "heuristic_score")
        self.assertEqual(ranking["results"][0]["job_id"], "job_a")

    def test_request_id_passthrough(self):
        r = self.client.get("/api/v1/health", headers={"X-Request-ID": "req_custom_1"})
        self.assertEqual(r.headers.get("X-Request-ID"), "req_custom_1")

    def test_missing_text_is_empty_input(self):
        r = self.client.post("/api/v1/profiles/resume/parse", json={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "EMPTY_INPUT")

    def test_invalid_base64_rejected(self):
        r = self.client.post("/api/v1/profiles/resume/parse",
                             json={"file_name": "a.txt", "content_base64": "!!!"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_unsupported_format_rejected(self):
        r = self.client.post("/api/v1/profiles/resume/parse",
                             json={"file_name": "a.doc", "content_base64": "aGVsbG8="})
        self.assertEqual(r.status_code, 415)
        self.assertEqual(r.json()["error"]["code"], "UNSUPPORTED_FORMAT")

    def test_empty_jobs_rejected(self):
        r = self.client.post("/api/v1/matching/rank",
                             json={"resume_text": "求职意向：Java", "jobs": []})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_batch_limit_boundary(self):
        job = {"job_id": "j", "text": "职位名称：Java开发工程师\n任职要求：熟悉 Java"}
        ok = self.client.post("/api/v1/matching/rank",
                              json={"resume_text": "求职意向：Java\n专业技能：Java",
                                    "jobs": [dict(job, job_id=f"j{i}") for i in range(200)],
                                    "options": {"mode": "baseline"}})
        self.assertEqual(ok.status_code, 200)
        too_many = self.client.post("/api/v1/matching/rank",
                                    json={"resume_text": "求职意向：Java\n专业技能：Java",
                                          "jobs": [dict(job, job_id=f"j{i}") for i in range(201)],
                                          "options": {"mode": "baseline"}})
        self.assertEqual(too_many.status_code, 422)
        self.assertEqual(too_many.json()["error"]["code"], "INVALID_REQUEST")

    def test_bad_mode_returns_error_code(self):
        r = self.client.post("/api/v1/matching/rank",
                             json={"resume_text": "求职意向：Java", "jobs": [{"text": "职位名称：A"}],
                                   "options": {"mode": "unknown_mode"}})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_models_endpoints(self):
        r = self.client.get("/api/v1/models")
        self.assertEqual(r.status_code, 200)
        ids = [m["model_id"] for m in r.json()["data"]["models"]]
        self.assertIn("baseline_skill_text_v1", ids)
        self.assertIn("chinese_match_future_v1", ids)

        r2 = self.client.get("/api/v1/models/baseline_skill_text_v1/status")
        self.assertEqual(r2.status_code, 200)
        status = r2.json()["data"]["model_status"]
        self.assertIn("checksum_check", status)
        self.assertIn("load_state", status)

        r3 = self.client.get("/api/v1/models/not_registered/status")
        self.assertEqual(r3.status_code, 503)
        self.assertEqual(r3.json()["error"]["code"], "MODEL_MISSING")

    def test_openapi_document(self):
        r = self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 200)
        paths = r.json()["paths"]
        for p in ("/api/v1/health", "/api/v1/profiles/resume/parse",
                  "/api/v1/profiles/job/parse", "/api/v1/matching/rank",
                  "/api/v1/models", "/api/v1/models/{model_id}/status"):
            self.assertIn(p, paths)


class S21ModelLoadCaching(unittest.TestCase):
    """场景 21：模型加载仅在初始化或缓存失效时进行。"""

    def _service(self) -> tuple[MatchingService, ModelRegistry]:
        reg = ModelRegistry(loader_impl=lambda r: StubMatchPredictor())
        reg.register(ModelRegistration(
            model_id="legacy_match_proxy_v1", model_version="stub-v1",
            task_type="match_ranking", training_data_version="stub",
            evaluation_status="research_only_proxy_labels", supported_languages=["en"],
            artifacts=[], checksum="stub", limitations=[], loader="legacy_match"))
        return MatchingService(reg), reg

    def test_loaded_once_then_cached(self):
        from job_matching.service import parse_job_text, parse_resume_text as prt
        from job_matching.service.job_parser import JobEducationResolver
        service, reg = self._service()
        student = prt("求职意向：Java开发工程师\n专业技能：Java", profile_id="s",
                      is_synthetic=True)
        job = parse_job_text("职位名称：Java开发工程师\n任职要求：熟悉 Java", job_id="j",
                             resolver=JobEducationResolver(None), is_synthetic=True)
        opts = {"mode": "experimental_model", "model_id": "legacy_match_proxy_v1"}
        service.rank(student, [job], opts)
        service.rank(student, [job], opts)
        self.assertEqual(reg.load_count, 1, "第二次调用必须走缓存")
        self.assertGreaterEqual(reg.cache_hits, 1)
        reg.cache_clear()
        service.rank(student, [job], opts)
        self.assertEqual(reg.load_count, 2, "缓存失效后才允许重新加载")

    def test_registry_info_records_model_version(self):
        _, reg = self._service()
        info = reg.describe_all()[0]
        for key in ("model_id", "model_version", "task_type", "training_data_version",
                    "input_schema_version", "evaluation_status", "supported_languages",
                    "artifacts", "checksum", "limitations"):
            self.assertIn(key, info)


class S22Determinism(unittest.TestCase):
    """场景 22：同输入 + 同模型版本 -> 确定性结果。"""

    @classmethod
    def setUpClass(cls):
        cls.client = make_client()

    def _rank(self):
        r = self.client.post("/api/v1/matching/rank",
                             json={"resume_text": "求职意向：Java开发工程师\n教育背景\n2027届 本科 计算机科学与技术\n专业技能：Java、MySQL",
                                   "jobs": [
                                       {"job_id": "job_x", "text": "职位名称：Java开发工程师\n任职要求：熟悉 Java、MySQL"},
                                       {"job_id": "job_y", "text": "职位名称：测试工程师\n任职要求：熟悉 Python"},
                                       {"job_id": "job_z", "text": "职位名称：Java开发工程师\n任职要求：熟悉 Java"},
                                   ],
                                   "options": {"mode": "baseline"}})
        self.assertEqual(r.status_code, 200)
        return r.json()["data"]["ranking"]

    def test_same_input_same_output(self):
        a, b = self._rank(), self._rank()
        self.assertEqual(a["score_type"], b["score_type"])
        self.assertEqual(a["model_version"], b["model_version"])
        self.assertEqual([(x["job_id"], x["score"], x["rank"]) for x in a["results"]],
                         [(x["job_id"], x["score"], x["rank"]) for x in b["results"]])


if __name__ == "__main__":
    unittest.main()
