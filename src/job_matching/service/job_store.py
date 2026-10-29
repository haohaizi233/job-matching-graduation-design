# -*- coding: utf-8 -*-
"""岗位管理与检索（Phase5-2 / Batch 4.1）。

权限：
  * 管理员：新增 / 更新 / 下架 / 批量导入 / 触发岗位画像解析；
  * 学生：查看已发布岗位，按类别 / 城市 / 技能 / 学历 / 关键词检索；
  * 学生不可见 draft / offline 岗位（查询条件内强制，不靠前端过滤）。

检索口径：本阶段用常规数据库查询 + 必要索引（status/category/city），
技能等 JSON 内条件在应用层过滤；**不引入 Elasticsearch**（无性能证据前不加基础设施）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..infra.persistence import Job, get_session_factory, session_scope
from .contracts import JobProfile
from .errors import ServiceError

VALID_STATUSES = ("draft", "published", "offline")
MAX_IMPORT_ROWS = 200
MAX_PAGE_SIZE = 100


def _now() -> datetime:
    return datetime.utcnow()


def _derive_title(job_description: str) -> str:
    """批量导入缺列容错：取 JD 首个非空行作为标题（截断 255），无可用文本时回落默认值。"""
    for line in str(job_description or "").splitlines():
        s = line.strip()
        if s:
            return s[:255]
    return "未命名岗位"


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class JobService:
    """岗位仓储服务（复用 Phase5-1 的岗位画像解析，不重写解析逻辑）。"""

    def __init__(self, *, services, session_factory: Callable | None = None):
        self._services = services            # Phase5-1 Services（解析/评分复用入口）
        self._session_factory = session_factory or get_session_factory()

    # ============================================================ 管理端
    def create_job(self, user: dict, *, title: str, job_description: str,
                   source: str = "manual", source_license: str = "UNKNOWN",
                   status: str = "published", structured_profile: dict | None = None,
                   is_synthetic: bool = False) -> dict:
        self._require_admin(user)
        problems = []
        if not title or not str(title).strip():
            problems.append("title 不能为空")
        if not job_description or not str(job_description).strip():
            problems.append("job_description 不能为空")
        if status not in VALID_STATUSES:
            problems.append(f"status 只允许 {VALID_STATUSES}")
        if problems:
            raise ServiceError("INVALID_REQUEST", "；".join(problems))

        row = Job(title=str(title).strip()[:255], job_description=str(job_description),
                  source=str(source)[:128] or "manual",
                  source_license=str(source_license)[:64] or "UNKNOWN",
                  status=status, structured_profile=structured_profile)
        if structured_profile:
            self._apply_profile_columns(row, structured_profile)
        with session_scope(self._session_factory) as s:
            s.add(row)
            s.flush()
            s.refresh(row)
            out = self._job_row(row, include_profile=True)
        return out

    def update_job(self, user: dict, job_id: str, fields: dict) -> dict:
        self._require_admin(user)
        allowed = {"title", "job_description", "source", "source_license",
                   "status", "job_category", "city", "education_min"}
        unknown = [k for k in fields if k not in allowed]
        if unknown:
            raise ServiceError("INVALID_REQUEST", f"不允许更新的字段: {unknown}")
        if "status" in fields and fields["status"] not in VALID_STATUSES:
            raise ServiceError("INVALID_REQUEST", f"status 只允许 {VALID_STATUSES}")
        with session_scope(self._session_factory) as s:
            row = self._owned_job(job_id, session=s, any_status=True)
            for k, v in fields.items():
                setattr(row, k, v)
            s.flush()
            s.refresh(row)
            return self._job_row(row, include_profile=True)

    def set_status(self, user: dict, job_id: str, status: str) -> dict:
        return self.update_job(user, job_id, {"status": status})

    def parse_profile(self, user: dict, job_id: str) -> dict:
        """触发岗位画像解析（复用 service/job_parser.parse_job_text）。"""
        self._require_admin(user)
        with session_scope(self._session_factory) as s:
            row = self._owned_job(job_id, session=s, any_status=True)
            text = row.job_description
            title = row.title
            source, license_ = row.source, row.source_license
        profile = self._parse_job_profile(text, job_id=job_id, title=title,
                                          source=source, source_license=license_)
        d = profile.to_dict()
        with session_scope(self._session_factory) as s:
            row = self._owned_job(job_id, session=s, any_status=True)
            row.structured_profile = d
            self._apply_profile_columns(row, d)
            s.flush()
            s.refresh(row)
            out = self._job_row(row, include_profile=True)
        out["warnings"] = list(profile.warnings)
        return out

    def import_jobs(self, user: dict, items: list[dict]) -> dict:
        """批量导入合法数据：逐行校验，合法行入库，非法行逐条登记（不半途崩溃）。

        标题容错语义（缺列 ≠ 空值）：
          * `title` 键缺失或为 null -> 从 job_description 首个非空行派生标题
            （外部数据源常出现缺列，导入不得整批失败）；
          * `title` 显式为空字符串/纯空白 -> 视为数据错误，该行拒绝并登记原因。
        """
        self._require_admin(user)
        if not isinstance(items, list) or not items:
            raise ServiceError("INVALID_REQUEST", "items 必须是非空列表")
        if len(items) > MAX_IMPORT_ROWS:
            raise ServiceError("BATCH_LIMIT_EXCEEDED",
                               f"批量导入上限 {MAX_IMPORT_ROWS} 行")
        created, errors = [], []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({"index": i, "error": "行必须是对象"})
                continue
            try:
                raw_title = item.get("title")
                title = (raw_title if ("title" in item and raw_title is not None)
                         else _derive_title(str(item.get("job_description") or "")))
                row_out = self.create_job(
                    user,
                    title=str(title or ""),
                    job_description=str(item.get("job_description") or ""),
                    source=str(item.get("source") or "import"),
                    source_license=str(item.get("source_license") or "UNKNOWN"),
                    status=str(item.get("status") or "published"),
                    is_synthetic=bool(item.get("is_synthetic", False)))
                created.append({"index": i, "job_id": row_out["id"]})
            except ServiceError as e:
                errors.append({"index": i, "error": f"[{e.code}] {e.message}"})
        return {"created": created, "errors": errors,
                "created_count": len(created), "error_count": len(errors)}

    # ============================================================ 查询
    def list_jobs(self, user: dict, *, category: str | None = None,
                  city: str | None = None, q: str | None = None,
                  education_min: str | None = None, skills: list[str] | None = None,
                  include_unpublished: bool = False, page: int = 1,
                  page_size: int = 20) -> dict:
        page = max(1, int(page))
        page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
        session = self._session_factory()
        try:
            query = session.query(Job)
            if not (include_unpublished and user.get("role") == "admin"):
                query = query.filter(Job.status == "published")
            if category:
                query = query.filter(Job.job_category == category)
            if city:
                query = query.filter(Job.city == city)
            if q:
                like = f"%{q}%"
                query = query.filter((Job.title.like(like)) | (Job.job_description.like(like)))
            if education_min:
                query = query.filter(Job.education_min == education_min)
            total = query.count()
            rows = (query.order_by(Job.updated_at.desc())
                    .offset((page - 1) * page_size).limit(page_size).all())
            items = [self._job_row(r, include_profile=bool(skills)) for r in rows]
        finally:
            session.close()

        if skills:
            wanted = {s.strip().lower() for s in skills if s and s.strip()}
            items = [it for it in items if self._skill_matches(it, wanted)]
            total = len(items)   # 技能过滤在应用层（当前规模无需搜索引擎）
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def get_job(self, user: dict, job_id: str, *,
                include_unpublished: bool = False) -> dict:
        session = self._session_factory()
        try:
            any_status = bool(include_unpublished and user.get("role") == "admin")
            row = self._owned_job(job_id, session=session, any_status=any_status)
            return self._job_row(row, include_profile=True)
        finally:
            session.close()

    def matchable_jobs(self, job_ids: list[str] | None = None) -> list[tuple[Job, JobProfile]]:
        """供推荐服务取用：已发布 + 已解析画像的岗位。"""
        session = self._session_factory()
        try:
            query = session.query(Job).filter(Job.status == "published")
            if job_ids:
                query = query.filter(Job.id.in_(job_ids))
            out = []
            for row in query.order_by(Job.updated_at.desc()).all():
                if not row.structured_profile:
                    continue
                try:
                    out.append((row, JobProfile.from_dict(row.structured_profile)))
                except Exception:  # noqa: BLE001  坏画像行跳过并由告警体现
                    continue
            return out
        finally:
            session.close()

    # ============================================================ 内部
    def _parse_job_profile(self, text: str, *, job_id: str, title: str,
                           source: str, source_license: str) -> JobProfile:
        from .job_parser import parse_job_text
        return parse_job_text(
            f"{title}\n{text}" if title and title not in text else text,
            job_id=job_id, source=source, source_license=source_license,
            is_synthetic=True,
            resolver=self._services.education_resolver)

    @staticmethod
    def _apply_profile_columns(row: Job, profile: dict) -> None:
        """检索冗余列与结构化画像同步（同一来源，防止两处口径漂移）。"""
        def field_value(name):
            f = profile.get(name) or {}
            return f.get("value") if isinstance(f, dict) else None

        row.job_category = (str(field_value("job_category"))[:64]
                            if field_value("job_category") else None)
        row.city = (str(field_value("city"))[:64] if field_value("city") else None)
        edu = profile.get("education_requirement") or {}
        row.education_min = (str(edu.get("raw"))[:32] if isinstance(edu, dict) and edu.get("raw")
                             else None)

    @staticmethod
    def _skill_matches(job_row_dict: dict, wanted: set[str]) -> bool:
        prof = job_row_dict.get("structured_profile") or {}
        have = set()
        for key in ("required_skills", "preferred_skills"):
            for s in prof.get(key) or []:
                name = str((s or {}).get("canonical_name") or "").lower()
                if name:
                    have.add(name)
        return bool(wanted & have)

    def _require_admin(self, user: dict) -> None:
        if user.get("role") != "admin":
            raise ServiceError("FORBIDDEN", "需要管理员权限")

    def _owned_job(self, job_id: str, *, session, any_status: bool = False):
        query = session.query(Job).filter(Job.id == job_id)
        if not any_status:
            query = query.filter(Job.status == "published")
        row = query.first()
        if row is None:
            raise ServiceError("NOT_FOUND", "岗位不存在或未发布")
        return row

    @staticmethod
    def _job_row(j: Job, include_profile: bool = False) -> dict:
        out = {"id": j.id, "title": j.title,
               "job_description": j.job_description,
               "source": j.source, "source_license": j.source_license,
               "status": j.status, "job_category": j.job_category,
               "city": j.city, "education_min": j.education_min,
               "created_at": _iso(j.created_at), "updated_at": _iso(j.updated_at),
               "profile_parsed": j.structured_profile is not None}
        if include_profile:
            out["structured_profile"] = j.structured_profile
        return out
