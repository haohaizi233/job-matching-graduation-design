# -*- coding: utf-8 -*-
"""Phase5-2 业务后端 API（认证、画像、岗位、推荐、反馈）。

集成方式：复用 Phase5-1 `create_app()`（保持既有端点与中间件完全兼容），
在其上挂载业务路由（/api/v1/auth、/api/v1/students、/api/v1/resumes、
/api/v1/jobs、/api/v1/recommendations）。

统一约定：
  * 成功响应统一信封 {request_id, api_version, app_version, data, warnings}；
  * 失败响应统一错误体 {error: {code, message, request_id, detail}}（错误码见 errors.py）；
  * 未认证 401（AUTH_REQUIRED / AUTH_TOKEN_EXPIRED / AUTH_INVALID_CREDENTIALS），
    越权/非本人资源 404（防资源枚举），角色不足 403（FORBIDDEN）；
  * 分页统一 {items, page, page_size, total}，page_size 上限 100；
  * 密码哈希、Token 明文绝不进入响应或日志；日志只记元信息。

部署边界：Phase5-1 的解析/排序端点仍属本地开发演示接口；本模块的业务接口
一律要求认证，公网部署前还必须通过独立安全验收（见 settings.check_deployment_safety）。

注：本文件**不**使用 `from __future__ import annotations` —— 路由请求模型定义在
工厂函数内，FastAPI 需要在定义时解析注解（字符串注解会解析失败）。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..infra.persistence import DbSettings, get_session_factory
from .accounts import AccountService
from .errors import ServiceError
from .file_store import DEFAULT_STORAGE_ROOT, PrivateFileStore
from .job_store import JobService
from .profile_store import StudentDataService
from .reco_store import FEEDBACK_TYPES, RecommendationService
from .settings import ServiceSettings

API_VERSION = "v1"
APP_VERSION = "phase5-2-0.1.0"


# ------------------------------------------------------------------ 服务容器
@dataclass
class BusinessServices:
    """业务依赖容器（测试可整体替换 -> 依赖注入）。"""

    accounts: AccountService
    students: StudentDataService
    jobs: JobService
    recommendations: RecommendationService
    core: Any                      # Phase5-1 Services（评分/解析复用入口）
    store: PrivateFileStore
    settings: ServiceSettings
    db_settings: DbSettings
    config: dict = field(default_factory=dict)


def make_business_services(*, database_url: str | None = None,
                           storage_root: Path | str | None = None,
                           settings: ServiceSettings | None = None,
                           core_services: Any = None,
                           session_factory: Callable | None = None) -> BusinessServices:
    """构建业务服务容器（连接串/存储根全部可注入，禁止写死）。"""
    import os
    if database_url:
        os.environ["JM_DATABASE_URL"] = str(database_url)
    st = settings or ServiceSettings.from_env()
    db = DbSettings.from_env()
    sf = session_factory or get_session_factory(db)
    store = PrivateFileStore(storage_root or DEFAULT_STORAGE_ROOT)

    if core_services is None:
        from .api import make_services
        core_services = make_services(settings=st)

    accounts = AccountService(session_factory=sf)
    students = StudentDataService(store=store, session_factory=sf,
                                  max_upload_bytes=st.max_upload_bytes)
    jobs = JobService(services=core_services, session_factory=sf)
    reco = RecommendationService(services=core_services, job_service=jobs,
                                 profile_service=students, session_factory=sf)
    return BusinessServices(accounts=accounts, students=students, jobs=jobs,
                            recommendations=reco, core=core_services, store=store,
                            settings=st, db_settings=db,
                            config=st.to_config_dict())


# ------------------------------------------------------------------ 应用
def create_business_app(business: BusinessServices | None = None):
    """Phase5-1 服务 + Phase5-2 业务路由（单一 app，OpenAPI 合并输出）。"""
    from fastapi import (APIRouter, Body, Depends, File, Form, Header,
                         Request, UploadFile)
    from pydantic import BaseModel, ConfigDict, Field as PField

    from .api import _envelope, create_app, new_request_id

    app = create_app()
    biz = business or make_business_services()
    app.state.business = biz

    # ---------------------------------------------------------- 依赖
    def get_biz(request: Request) -> BusinessServices:
        return request.app.state.business

    def bearer_token(request: Request) -> str:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return ""

    def current_user(request: Request, biz: BusinessServices = Depends(get_biz)) -> dict:
        token = bearer_token(request)
        if not token:
            raise ServiceError("AUTH_REQUIRED", "缺少访问令牌（Authorization: Bearer <token>）")
        return biz.accounts.resolve_token(token)

    def current_admin(user: dict = Depends(current_user)) -> dict:
        if user.get("role") != "admin":
            raise ServiceError("FORBIDDEN", "需要管理员权限")
        return user

    # ---------------------------------------------------------- 请求模型
    class RegisterIn(BaseModel):
        username: str = PField(..., min_length=3, max_length=64)
        password: str = PField(..., min_length=1, max_length=128)
        email: str | None = None

    class LoginIn(BaseModel):
        username: str
        password: str

    class ProfileEditIn(BaseModel):
        edits: dict | None = None
        confirm: bool = False
        note: str | None = None
        expected_version: int | None = None

    class ResumeJsonIn(BaseModel):
        file_name: str
        content_base64: str
        is_synthetic: bool = False

    class JobCreateIn(BaseModel):
        model_config = ConfigDict(protected_namespaces=())
        title: str
        job_description: str
        source: str = "manual"
        source_license: str = "UNKNOWN"
        status: str = "published"
        structured_profile: dict | None = None
        is_synthetic: bool = False

    class JobUpdateIn(BaseModel):
        model_config = ConfigDict(protected_namespaces=())
        title: str | None = None
        job_description: str | None = None
        source: str | None = None
        source_license: str | None = None
        status: str | None = None
        job_category: str | None = None
        city: str | None = None
        education_min: str | None = None

    class JobStatusIn(BaseModel):
        status: str

    class JobImportIn(BaseModel):
        items: list[dict]

    class RecommendIn(BaseModel):
        model_config = ConfigDict(protected_namespaces=())
        mode: str = "baseline"
        top_k: int | None = None
        job_ids: list[str] | None = None
        category: str | None = None
        city: str | None = None
        model_id: str | None = None
        allow_fallback: bool = True

    class FeedbackIn(BaseModel):
        item_id: str
        feedback_type: str
        note: str | None = None

    # ---------------------------------------------------------- 认证
    auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @auth_router.post("/register")
    def register(body: RegisterIn, request: Request,
                 biz: BusinessServices = Depends(get_biz)):
        # 公开注册只允许 student（管理员经内部种子创建，不开放公开注册）
        user = biz.accounts.register(username=body.username, password=body.password,
                                     email=body.email, role="student")
        return _envelope(request.state.request_id, {"user": user})

    @auth_router.post("/login")
    def login(body: LoginIn, request: Request,
              biz: BusinessServices = Depends(get_biz)):
        user = biz.accounts.authenticate(username=body.username, password=body.password)
        token, meta = biz.accounts.create_session(
            user_id=user["id"], user_agent=request.headers.get("user-agent"))
        # Token 只在此处出现一次，绝不写日志
        return _envelope(request.state.request_id,
                         {"token": token, "user": user, **meta})

    @auth_router.post("/logout")
    def logout(request: Request, biz: BusinessServices = Depends(get_biz),
               user: dict = Depends(current_user)):
        revoked = biz.accounts.logout(bearer_token(request))
        return _envelope(request.state.request_id, {"revoked": revoked})

    @auth_router.get("/me")
    def me(request: Request, user: dict = Depends(current_user)):
        return _envelope(request.state.request_id, {"user": user})

    # ---------------------------------------------------------- 学生画像
    profile_router = APIRouter(prefix="/api/v1/students/me", tags=["students"])

    @profile_router.get("/profile")
    def get_profile(request: Request, biz: BusinessServices = Depends(get_biz),
                    user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"profile": biz.students.latest_profile(user)})

    @profile_router.put("/profile")
    def put_profile(body: ProfileEditIn, request: Request,
                    biz: BusinessServices = Depends(get_biz),
                    user: dict = Depends(current_user)):
        saved = biz.students.save_profile(user, body.edits, confirm=body.confirm,
                                          note=body.note,
                                          expected_version=body.expected_version)
        return _envelope(request.state.request_id, {"profile": saved})

    @profile_router.get("/profile/versions")
    def profile_versions(request: Request, biz: BusinessServices = Depends(get_biz),
                         user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"versions": biz.students.profile_history(user)})

    @profile_router.get("/profile/versions/{version}")
    def profile_version(version: int, request: Request,
                        biz: BusinessServices = Depends(get_biz),
                        user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"profile": biz.students.get_profile_version(user, version)})

    # ---------------------------------------------------------- 简历
    resumes_router = APIRouter(prefix="/api/v1/resumes", tags=["resumes"])

    @resumes_router.post("")
    def upload_resume(request: Request,
                      biz: BusinessServices = Depends(get_biz),
                      user: dict = Depends(current_user),
                      file: UploadFile = File(...),
                      is_synthetic: bool = Form(False)):
        content = file.file.read()
        out = biz.students.upload_resume(user, filename=file.filename or "upload.txt",
                                         content=content, is_synthetic=is_synthetic)
        return _envelope(request.state.request_id, out)

    @resumes_router.post("/json")
    def upload_resume_json(body: ResumeJsonIn, request: Request,
                           biz: BusinessServices = Depends(get_biz),
                           user: dict = Depends(current_user)):
        """JSON Base64 上传（无 multipart 的客户端使用；同样受大小/格式限制）。"""
        import base64
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except Exception as e:  # noqa: BLE001
            raise ServiceError("INVALID_REQUEST", f"content_base64 非法: {e}") from e
        out = biz.students.upload_resume(user, filename=body.file_name,
                                         content=content,
                                         is_synthetic=body.is_synthetic)
        return _envelope(request.state.request_id, out)

    @resumes_router.get("")
    def list_resumes(request: Request, biz: BusinessServices = Depends(get_biz),
                     user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"items": biz.students.list_resumes(user)})

    @resumes_router.get("/{resume_id}")
    def get_resume(resume_id: str, request: Request,
                   biz: BusinessServices = Depends(get_biz),
                   user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"resume": biz.students.get_resume(user, resume_id)})

    @resumes_router.delete("/{resume_id}")
    def delete_resume(resume_id: str, request: Request,
                      biz: BusinessServices = Depends(get_biz),
                      user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         biz.students.delete_resume(user, resume_id))

    @resumes_router.post("/{resume_id}/reparse")
    def reparse_resume(resume_id: str, request: Request,
                       biz: BusinessServices = Depends(get_biz),
                       user: dict = Depends(current_user),
                       body: dict | None = Body(None)):
        is_synthetic = bool((body or {}).get("is_synthetic", False))
        return _envelope(request.state.request_id,
                         biz.students.reparse_resume(user, resume_id,
                                                     is_synthetic=is_synthetic))

    # ---------------------------------------------------------- 岗位
    jobs_router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

    @jobs_router.get("")
    def list_jobs(request: Request, biz: BusinessServices = Depends(get_biz),
                  user: dict = Depends(current_user),
                  category: str | None = None, city: str | None = None,
                  q: str | None = None, education_min: str | None = None,
                  skills: str | None = None, include_unpublished: bool = False,
                  page: int = 1, page_size: int = 20):
        skill_list = [s for s in (skills or "").split(",") if s.strip()]
        return _envelope(request.state.request_id,
                         biz.jobs.list_jobs(user, category=category, city=city, q=q,
                                            education_min=education_min,
                                            skills=skill_list or None,
                                            include_unpublished=include_unpublished,
                                            page=page, page_size=page_size))

    @jobs_router.get("/{job_id}")
    def get_job(job_id: str, request: Request,
                biz: BusinessServices = Depends(get_biz),
                user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"job": biz.jobs.get_job(user, job_id,
                                                  include_unpublished=True)})

    @jobs_router.post("")
    def create_job(body: JobCreateIn, request: Request,
                   biz: BusinessServices = Depends(get_biz),
                   admin: dict = Depends(current_admin)):
        out = biz.jobs.create_job(admin, title=body.title,
                                  job_description=body.job_description,
                                  source=body.source,
                                  source_license=body.source_license,
                                  status=body.status,
                                  structured_profile=body.structured_profile)
        return _envelope(request.state.request_id, {"job": out})

    @jobs_router.post("/import")
    def import_jobs(body: JobImportIn, request: Request,
                    biz: BusinessServices = Depends(get_biz),
                    admin: dict = Depends(current_admin)):
        return _envelope(request.state.request_id, biz.jobs.import_jobs(admin, body.items))

    @jobs_router.patch("/{job_id}")
    def update_job(job_id: str, body: JobUpdateIn, request: Request,
                   biz: BusinessServices = Depends(get_biz),
                   admin: dict = Depends(current_admin)):
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        return _envelope(request.state.request_id,
                         {"job": biz.jobs.update_job(admin, job_id, fields)})

    @jobs_router.post("/{job_id}/status")
    def set_job_status(job_id: str, body: JobStatusIn, request: Request,
                       biz: BusinessServices = Depends(get_biz),
                       admin: dict = Depends(current_admin)):
        return _envelope(request.state.request_id,
                         {"job": biz.jobs.set_status(admin, job_id, body.status)})

    @jobs_router.post("/{job_id}/parse")
    def parse_job(job_id: str, request: Request,
                  biz: BusinessServices = Depends(get_biz),
                  admin: dict = Depends(current_admin)):
        return _envelope(request.state.request_id,
                         {"job": biz.jobs.parse_profile(admin, job_id)})

    # ---------------------------------------------------------- 推荐
    reco_router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

    @reco_router.post("")
    def run_recommendation(request: Request,
                           biz: BusinessServices = Depends(get_biz),
                           user: dict = Depends(current_user),
                           body: RecommendIn | None = None,
                           idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        b = body or RecommendIn()
        out = biz.recommendations.run(
            user, mode=b.mode, top_k=b.top_k, job_ids=b.job_ids,
            category=b.category, city=b.city, model_id=b.model_id,
            allow_fallback=b.allow_fallback, idempotency_key=idempotency_key)
        return _envelope(request.state.request_id, out)

    @reco_router.get("")
    def recommendation_history(request: Request,
                               biz: BusinessServices = Depends(get_biz),
                               user: dict = Depends(current_user),
                               page: int = 1, page_size: int = 20):
        return _envelope(request.state.request_id,
                         biz.recommendations.history(user, page=page, page_size=page_size))

    @reco_router.get("/feedback")
    def list_feedback(request: Request, biz: BusinessServices = Depends(get_biz),
                      user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"items": biz.recommendations.list_feedback(user)})

    @reco_router.get("/{run_id}")
    def get_run(run_id: str, request: Request,
                biz: BusinessServices = Depends(get_biz),
                user: dict = Depends(current_user)):
        return _envelope(request.state.request_id,
                         {"run": biz.recommendations.get_run(user, run_id)})

    @reco_router.post("/{run_id}/feedback")
    def submit_feedback(run_id: str, body: FeedbackIn, request: Request,
                        biz: BusinessServices = Depends(get_biz),
                        user: dict = Depends(current_user)):
        out = biz.recommendations.submit_feedback(
            user, run_id=run_id, item_id=body.item_id,
            feedback_type=body.feedback_type, note=body.note)
        return _envelope(request.state.request_id, {"feedback": out})

    for r in (auth_router, profile_router, resumes_router, jobs_router, reco_router):
        app.include_router(r)

    # OpenAPI 说明（分数语义与隐私边界随文档可见）
    app.description = (app.description or "") + (
        "\n\nPhase5-2 业务后端：认证（Argon2id + 服务端会话）、学生画像版本化、"
        "简历私有存储、岗位管理、推荐快照与反馈闭环。"
        "所有分数为排序参考分（heuristic_score / model_raw_score），不是录用概率；"
        "推荐反馈是用户业务反馈，不得当作人工 Gold 标签。")
    return app
