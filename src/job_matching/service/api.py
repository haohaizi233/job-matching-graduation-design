# -*- coding: utf-8 -*-
"""Phase5-1 最小业务 API（模块 E，FastAPI）。

端点（v1）：
  GET  /api/v1/health
  POST /api/v1/profiles/resume/parse
  POST /api/v1/profiles/job/parse
  POST /api/v1/matching/rank
  GET  /api/v1/models
  GET  /api/v1/models/{model_id}/status

必须满足：
  * Pydantic 请求/响应验证 + 统一响应信封（request_id 全链路）；
  * 稳定错误码（service/errors.py），版本号 / 模型版本记录；
  * 推理超时保护、批量上限（默认 200 个岗位）；
  * 敏感内容不入日志（日志层 PII 掩码 + 不记录正文）；
  * 模型缺失 -> 显式错误或透明降级（allow_fallback）；
  * OpenAPI 文档（/docs、/openapi.json）；
  * 可测试依赖注入（app.state.services 可整体替换）。

依赖说明：fastapi/pydantic 延迟导入业务核心不依赖 Web 框架；
当前环境（python 3.13）已具备 fastapi 0.120 / pydantic 2.9 / httpx，可直接运行。
"""
from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core import ROOT
from .contracts import JobProfile, StudentProfile
from .errors import ServiceError, error_catalog
from .job_parser import JobEducationResolver, parse_job_text
from .logging_utils import get_service_logger, new_request_id
from .matching import MatchingService, RankOptions
from .model_registry import ModelRegistry, register_builtin_models
from .resume_parser import parse_resume_text
from .settings import DEFAULT_DEPLOYMENT_NOTE, DEFAULT_MATCHING_RUN_DIR, ServiceSettings
from .text_extract import (MAX_EXTRACT_TEXT_CHARS, MAX_UPLOAD_BYTES,
                           extract_document_bytes)

API_VERSION = "v1"
APP_VERSION = "phase5-1-0.1.0"
MAX_JOBS = 200
MAX_TEXT_CHARS = MAX_EXTRACT_TEXT_CHARS

# ---- 请求边界与安全上限（Phase5-1R F-007，开发阶段必要防护）----
MAX_REQUEST_BYTES = 8 * 1024 * 1024       # JSON 请求体上限（解析前检查）
MAX_BASE64_CHARS = 5_600_000              # Base64 字符串上限（≈4MB 解码后）
MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES       # 解码后文件上限（复用 text_extract 口径）
DEFAULT_RATE_LIMIT_PER_MINUTE = 300       # 单客户端每分钟请求上限（默认宽松）
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")   # 客户端 X-Request-ID 白名单

log = get_service_logger("job_matching.service.api")


# ------------------------------------------------------------------ 服务容器
@dataclass
class Services:
    """业务依赖容器（测试可整体替换 -> 依赖注入）。"""
    registry: ModelRegistry
    matching: MatchingService
    education_resolver: JobEducationResolver
    config: dict = field(default_factory=dict)
    settings: ServiceSettings | None = None   # 类型化配置（config 是其兼容视图）


def make_services(*, matching_run_dir: str | Path | None = DEFAULT_MATCHING_RUN_DIR,
                  education_run_dir: str | Path | None = None,
                  registry: ModelRegistry | None = None,
                  settings: ServiceSettings | None = None) -> Services:
    st = settings or ServiceSettings.from_env()
    reg = registry or ModelRegistry()
    register_builtin_models(
        reg,
        matching_run_dir=(ROOT / matching_run_dir) if matching_run_dir and not Path(matching_run_dir).is_absolute()
        else matching_run_dir,
        education_run_dir=education_run_dir)
    return Services(
        registry=reg,
        matching=MatchingService(reg),
        education_resolver=JobEducationResolver(education_run_dir),
        config=st.to_config_dict(),
        settings=st,
    )


# ------------------------------------------------------------------ Pydantic 协议
def _build_pydantic():
    from pydantic import BaseModel, ConfigDict, Field as PField

    class RankOptionsIn(BaseModel):
        model_config = ConfigDict(protected_namespaces=())
        mode: str = PField("baseline", description="baseline | experimental_model | future_verified")
        top_k: int | None = None
        model_id: str | None = None
        allow_fallback: bool = True
        timeout_ms: int | None = PField(30000, ge=0, le=600000)
        formal: bool = False

    class ResumeParseIn(BaseModel):
        text: str | None = PField(None, max_length=MAX_TEXT_CHARS)
        file_name: str | None = None
        content_base64: str | None = PField(None, max_length=MAX_BASE64_CHARS)
        profile_id: str | None = None
        is_synthetic: bool = True
        structured_fields: dict[str, Any] | None = None

    class JobParseIn(BaseModel):
        text: str | None = PField(None, max_length=MAX_TEXT_CHARS)
        file_name: str | None = None
        content_base64: str | None = PField(None, max_length=MAX_BASE64_CHARS)
        job_id: str | None = None
        source: str = "api"
        source_license: str = "UNKNOWN"
        is_synthetic: bool = True
        structured_fields: dict[str, Any] | None = None

    class RankJobIn(BaseModel):
        job_id: str | None = None
        text: str | None = PField(None, max_length=MAX_TEXT_CHARS)
        file_name: str | None = None
        content_base64: str | None = PField(None, max_length=MAX_BASE64_CHARS)
        profile: dict[str, Any] | None = None
        structured_fields: dict[str, Any] | None = None

    class RankIn(BaseModel):
        resume_text: str | None = PField(None, max_length=MAX_TEXT_CHARS)
        resume_profile: dict[str, Any] | None = None
        jobs: list[RankJobIn] = PField(..., min_length=1, max_length=MAX_JOBS)
        options: RankOptionsIn = RankOptionsIn()

    return RankOptionsIn, ResumeParseIn, JobParseIn, RankJobIn, RankIn


(RankOptionsIn, ResumeParseIn, JobParseIn, RankJobIn, RankIn) = _build_pydantic()


# ------------------------------------------------------------------ 工具
def _decode_upload(file_name: str | None, content_base64: str | None) -> bytes | None:
    """Base64 上传前置检查（F-007）：先查字符串长度上限，再解码，再查解码后字节数。

    高资源消耗操作（文档解析）之前完成全部可能的前置检查。
    """
    if content_base64 is None:
        return None
    if not file_name:
        raise ServiceError("INVALID_REQUEST", "提供 content_base64 时必须提供 file_name")
    if len(content_base64) > MAX_BASE64_CHARS:
        raise ServiceError("PAYLOAD_TOO_LARGE",
                           f"content_base64 长度 {len(content_base64)} 超过上限 "
                           f"{MAX_BASE64_CHARS}",
                           {"field": "content_base64"})
    # 解码前估算解码后体积（Base64 膨胀率 3/4），避免先解码大对象
    est = (len(content_base64) * 3) // 4
    if est > MAX_UPLOAD_BYTES:
        raise ServiceError("PAYLOAD_TOO_LARGE",
                           f"上传文件预估解码后 {est} 字节超过上限 {MAX_UPLOAD_BYTES}",
                           {"field": "content_base64"})
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except Exception as e:
        raise ServiceError("INVALID_REQUEST", "content_base64 解码失败") from e
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ServiceError("PAYLOAD_TOO_LARGE",
                           f"上传文件解码后 {len(raw)} 字节超过上限 {MAX_UPLOAD_BYTES}",
                           {"field": "content_base64"})
    return raw


def _require_text_or_upload(text: str | None, file_name: str | None,
                            content_base64: str | None, field_name: str) -> str:
    if text is not None and text.strip():
        if len(text) > MAX_TEXT_CHARS:
            raise ServiceError("PAYLOAD_TOO_LARGE",
                               f"{field_name} 超过长度上限 {MAX_TEXT_CHARS}",
                               {"field": field_name})
        return text
    raw = _decode_upload(file_name, content_base64)
    if raw is not None:
        got = extract_document_bytes(raw, file_name or "", max_bytes=MAX_UPLOAD_BYTES)
        if got["parse_status"] != "ok":
            code = "OCR_REQUIRED" if got["parse_status"] == "ocr_required" else "EMPTY_INPUT"
            raise ServiceError(code, got["note"], {"file_name": file_name})
        if len(got["text"]) > MAX_TEXT_CHARS:
            raise ServiceError("PAYLOAD_TOO_LARGE",
                               f"解析后文本长度 {len(got['text'])} 超过上限 {MAX_TEXT_CHARS}",
                               {"file_name": file_name})
        return got["text"]
    raise ServiceError("EMPTY_INPUT", f"{field_name} 为空：需要 text 或文件上传",
                       {"field": field_name})


def _envelope(request_id: str, data: dict, warnings: list[str] | None = None) -> dict:
    return {"request_id": request_id, "api_version": API_VERSION,
            "app_version": APP_VERSION, "data": data,
            "warnings": list(warnings or [])}


# ------------------------------------------------------------------ 应用
def create_app(services: Services | None = None):
    from fastapi import FastAPI, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    # 让端点签名里的 Request 注解可被 FastAPI 解析（保持顶层延迟导入）
    globals()["Request"] = Request

    app = FastAPI(
        title="大学生就业岗位画像与简历智能匹配 · 业务推理服务",
        version=APP_VERSION,
        description=(
            "Phase5-1 工程集成：中文简历/岗位解析、业务画像、可解释岗位排序。"
            "本服务所有分数为排序参考分（heuristic_score / model_raw_score），"
            "不是录用概率；Phase5-1 集成通过不代表中文人岗匹配模型效果验收通过。"),
        openapi_url="/openapi.json",
        docs_url="/docs",
    )
    app.state.services = services or make_services()

    def get_services(request: Request) -> Services:
        return request.app.state.services

    # ---------------------------------------------------------- 中间件
    rate_buckets: dict[str, list[float]] = {}

    def _rate_limited(client: str, limit: int, now_ts: float) -> bool:
        """固定窗口（60s）计数；内存有界（超过 10000 客户端时清空重计）。"""
        if limit <= 0:
            return False
        if len(rate_buckets) > 10000:   # pragma: no cover - 防内存膨胀
            rate_buckets.clear()
        window = rate_buckets.setdefault(client, [])
        cutoff = now_ts - 60.0
        window[:] = [t for t in window if t > cutoff]
        if len(window) >= int(limit):
            return True
        window.append(now_ts)
        return False

    @app.middleware("http")
    async def request_tracking(request: Request, call_next):
        cfg = getattr(app.state.services, "config", {}) or {}
        # ---- 请求体大小上限（在任何解析/解码之前）
        cl = request.headers.get("content-length", "")
        max_req = int(cfg.get("max_request_bytes", MAX_REQUEST_BYTES))
        if cl.isdigit() and int(cl) > max_req:
            err = ServiceError("PAYLOAD_TOO_LARGE",
                               f"请求体 {cl} 字节超过上限 {max_req}")
            return JSONResponse(status_code=err.http_status,
                                content=err.to_dict(new_request_id()))
        # ---- X-Request-ID 白名单（受限字符集 + 长度；非法值服务端重新生成）
        raw_rid = request.headers.get("X-Request-ID") or ""
        rid = raw_rid if REQUEST_ID_RE.match(raw_rid) else new_request_id()
        request.state.request_id = rid
        # ---- 请求频率限制（开发阶段基础防护；生产需网关级限流 + 认证）
        limit = int(cfg.get("rate_limit_per_minute", DEFAULT_RATE_LIMIT_PER_MINUTE))
        client = (request.client.host if request.client else "unknown") or "unknown"
        if _rate_limited(client, limit, time.monotonic()):
            err = ServiceError("RATE_LIMITED",
                               f"请求频率超过限制（{limit}/分钟）")
            resp = JSONResponse(status_code=err.http_status,
                                content=err.to_dict(rid))
            resp.headers["X-Request-ID"] = rid
            return resp
        t0 = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_failed request_id=%s path=%s", rid, request.url.path)
            raise
        latency = (time.monotonic() - t0) * 1000
        # 只记录元信息，不记录请求正文（敏感内容不入日志）
        log.info("request request_id=%s method=%s path=%s status=%d latency_ms=%.1f",
                 rid, request.method, request.url.path, response.status_code, latency)
        response.headers["X-Request-ID"] = rid
        response.headers["X-API-Version"] = API_VERSION
        return response

    # ---------------------------------------------------------- 错误处理
    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        rid = getattr(request.state, "request_id", "")
        return JSONResponse(status_code=exc.http_status,
                            content=exc.to_dict(rid))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", "")
        detail = {"issues": [str(e.get("msg", "")) + " @ " + ".".join(
            str(x) for x in e.get("loc", ())) for e in exc.errors()[:10]]}
        err = ServiceError("INVALID_REQUEST", "请求字段缺失或取值非法", detail)
        return JSONResponse(status_code=err.http_status, content=err.to_dict(rid))

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", "")
        log.exception("internal_error request_id=%s", rid)
        err = ServiceError("INTERNAL_ERROR", "服务内部错误")
        return JSONResponse(status_code=err.http_status, content=err.to_dict(rid))

    # ---------------------------------------------------------- 端点
    @app.get("/api/v1/health")
    def health():
        svc = app.state.services
        return _envelope(new_request_id(), {
            "status": "ok",
            "api_version": API_VERSION,
            "modes": ["baseline", "experimental_model", "future_verified"],
            "models_registered": svc.registry.list_ids(),
            "note": "Phase5-1 工程集成服务；中文匹配模型效果未验收（H2 BLOCKED）",
        })

    @app.post("/api/v1/profiles/resume/parse")
    def parse_resume(body: ResumeParseIn, request: Request):
        svc = get_services(request)
        rid = request.state.request_id
        text = _require_text_or_upload(body.text, body.file_name, body.content_base64,
                                       "text")
        profile = parse_resume_text(
            text,
            profile_id=body.profile_id or f"student_{rid[-8:]}",
            is_synthetic=body.is_synthetic,
            source_document=body.file_name or "inline_text",
            structured_fields=body.structured_fields)
        if profile.parse_status == "ocr_required":
            raise ServiceError("OCR_REQUIRED", "扫描版 PDF 需要 OCR 预处理",
                               {"profile_id": profile.profile_id})
        return _envelope(rid, {"profile": profile.to_dict()},
                         warnings=profile.warnings)

    @app.post("/api/v1/profiles/job/parse")
    def parse_job(body: JobParseIn, request: Request):
        svc = get_services(request)
        rid = request.state.request_id
        text = _require_text_or_upload(body.text, body.file_name, body.content_base64,
                                       "text")
        profile = parse_job_text(
            text,
            job_id=body.job_id or f"job_{rid[-8:]}",
            source=body.source, source_license=body.source_license,
            is_synthetic=body.is_synthetic,
            resolver=svc.education_resolver,
            structured_fields=body.structured_fields)
        return _envelope(rid, {"job_profile": profile.to_dict()},
                         warnings=profile.warnings)

    @app.post("/api/v1/matching/rank")
    def rank(body: RankIn, request: Request):
        svc = get_services(request)
        rid = request.state.request_id
        if body.resume_profile:
            try:
                student = StudentProfile.from_dict(body.resume_profile)
            except ValueError as e:
                raise ServiceError("INVALID_REQUEST", f"resume_profile 非法: {e}",
                                   {"field": "resume_profile"}) from e
        else:
            text = _require_text_or_upload(body.resume_text, None, None, "resume_text")
            student = parse_resume_text(text, is_synthetic=True,
                                        source_document="api_inline")
        jobs: list[JobProfile] = []
        for i, item in enumerate(body.jobs):
            if item.profile:
                try:
                    jobs.append(JobProfile.from_dict(item.profile))
                except ValueError as e:
                    raise ServiceError("INVALID_REQUEST",
                                       f"jobs[{i}].profile 非法: {e}",
                                       {"field": f"jobs[{i}].profile"}) from e
                continue
            text = _require_text_or_upload(item.text, item.file_name,
                                           item.content_base64, f"jobs[{i}].text")
            jobs.append(parse_job_text(
                text, job_id=item.job_id or f"job_{i:04d}", source="api",
                is_synthetic=True, resolver=svc.education_resolver,
                structured_fields=item.structured_fields))
        opts = RankOptions.from_dict(body.options.model_dump() if hasattr(body.options, "model_dump")
                                     else dict(body.options))
        result = svc.matching.rank(student, jobs, opts)
        result["request_id"] = rid
        result["api_version"] = API_VERSION
        return _envelope(rid, {"ranking": result}, warnings=result.get("warnings"))

    @app.get("/api/v1/models")
    def list_models(request: Request):
        svc = get_services(request)
        return _envelope(request.state.request_id, {
            "models": svc.registry.describe_all(),
            "error_codes": error_catalog(),
            "note": "chinese_match_future_v1 为 future_verified 预留槽位，当前无已验证中文模型",
        })

    @app.get("/api/v1/models/{model_id}/status")
    def model_status(model_id: str, request: Request):
        svc = get_services(request)
        status = svc.registry.status(model_id)   # 未注册 -> MODEL_MISSING
        return _envelope(request.state.request_id, {"model_status": status})

    return app


# ------------------------------------------------------------------ 本地运行入口
def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    """开发阶段默认只绑定回环地址（F-007）。

    本服务**无认证**，仅限本地开发/演示：外网部署必须先接入认证与请求限制，
    并按 docs/api/phase5-1-api.md 的上线阻断项逐条关闭。
    """
    import uvicorn
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":   # pragma: no cover - 手工启动入口
    main()
