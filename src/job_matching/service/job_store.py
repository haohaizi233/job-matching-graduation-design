# -*- coding: utf-8 -*-
"""岗位管理与检索（Phase5-2 / Batch 4.1，Phase5-2R 业务一致性修订）。

权限：
  * 管理员：新增 / 更新 / 下架 / 批量导入 / 触发岗位画像解析；
  * 学生：查看已发布岗位，按类别 / 城市 / 技能 / 学历 / 关键词检索；
  * 学生不可见 draft / offline 岗位（查询条件内强制，不靠前端过滤）。

Phase5-2R 修订（P0-01 / P1-03 / P1-07）：
  * **岗位画像失效**：title / job_description 变更 -> job_content_hash 变化 ->
    structured_profile 立即标记 needs_reparse；在重新解析成功前不得作为可信画像参与推荐。
    判定依据是**内容哈希**，不用 updated_at（后者无法证明内容一致性）。
  * **解析版本与状态**：profile_status ∈ unparsed | parsed | needs_reparse | failed，
    附 parser_version / profile_error；解析失败显式落失败状态，不用旧画像伪装成功。
  * **解析并发保护**：解析期间岗位原文被修改 -> 解析结果作废（409 CONFLICT），
    不允许旧结果覆盖新版本。
  * **数据来源**：synthetic | user_provided | licensed_dataset | unknown 从数据来源层确定，
    解析器不再硬编码 is_synthetic；来源声明可审计；更新/重新解析不静默改写来源。
  * **筛选先于分页**：技能等应用层条件先过滤全集再算 total 与分页，杜绝"页内过滤导致
    total 错误 / 跨页漏项"（不引入 Elasticsearch）。

检索口径：本阶段用常规数据库查询 + 必要索引（status/category/city/profile_status），
技能等 JSON 内条件在应用层过滤；当前数据规模下"先查合法候选再分页"是简单且正确的方案。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Callable

from ..infra.persistence import Job, get_session_factory, session_scope
from .contracts import JobProfile
from .errors import ServiceError
from .job_parser import JOB_PARSER_VERSION

VALID_STATUSES = ("draft", "published", "offline")
MAX_IMPORT_ROWS = 200
MAX_PAGE_SIZE = 100

# ---- P1-03 数据来源语义（唯一事实来源）----
DATA_SOURCES = ("synthetic", "user_provided", "licensed_dataset", "unknown")
# 由来源/许可可**确定**为合成的关键词
_SYNTHETIC_TOKENS = ("synthetic", "synth", "mock", "fake", "合成", "演示数据", "模拟数据")
# 许可"不明确"的取值：出现这些值一律不得当作授权数据
_UNKNOWN_LICENSES = ("", "UNKNOWN", "UNLICENSED", "NONE", "N/A", "NA", "无", "不明确")
# 管理员人工录入类来源（is_synthetic 显式为 False 且无授权声明 -> user_provided）
_MANUAL_SOURCE_TOKENS = ("manual", "admin", "hand", "人工", "录入", "import", "upload")

# ---- P0-01 影响结构化画像的字段（改这些才需要重新解析）----
PROFILE_AFFECTING_FIELDS = ("title", "job_description")


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


def job_content_hash(title: str, job_description: str) -> str:
    """影响画像的原文指纹（P0-01）。

    规范化 JSON（sort_keys + 固定分隔符）后取 SHA-256 —— 不依赖字典插入顺序或
    非确定性对象表示。只纳入真正影响结构化画像的字段：title + job_description。
    """
    payload = json.dumps({"title": str(title or ""), "job_description": str(job_description or "")},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_data_source(*, is_synthetic: bool | None = None,
                        source: str = "", source_license: str = "",
                        explicit: str | None = None) -> tuple[str, bool]:
    """从数据来源层确定 `data_source`，返回 (data_source, 是否显式声明)。

    判定顺序（**确定性、可审计、不冒充**）：
      1. 调用方显式给出 `data_source` -> 采用（显式声明，记审计）；
      2. `is_synthetic is True` 或来源字段含合成关键词 -> `synthetic`；
      3. `is_synthetic is False`（**显式声明非合成**）：
           许可明确 -> `licensed_dataset`；许可不明确 -> `user_provided`
           （人工/管理员录入，但**不**声称有授权）；
      4. 什么都没声明：
           许可明确 -> `licensed_dataset`；否则 -> `unknown`（不臆造来源）。
    """
    if explicit is not None:
        v = str(explicit).strip().lower()
        if v not in DATA_SOURCES:
            raise ServiceError("INVALID_REQUEST",
                               f"data_source 只允许 {DATA_SOURCES}",
                               {"field": "data_source"})
        return v, True

    blob = f"{source} {source_license}".lower()
    if is_synthetic is True or any(t in blob for t in _SYNTHETIC_TOKENS):
        return "synthetic", bool(is_synthetic is True)

    license_known = str(source_license or "").strip().upper() not in _UNKNOWN_LICENSES
    if is_synthetic is False:
        if license_known:
            return "licensed_dataset", False
        return "user_provided", False

    # 未声明：许可明确才敢称授权数据集，否则保留 unknown
    return ("licensed_dataset" if license_known else "unknown"), False


class JobService:
    """岗位仓储服务（复用 Phase5-1 的岗位画像解析，不重写解析逻辑）。"""

    def __init__(self, *, services, session_factory: Callable | None = None):
        self._services = services            # Phase5-1 Services（解析/评分复用入口）
        self._session_factory = session_factory or get_session_factory()

    # ============================================================ 管理端
    def create_job(self, user: dict, *, title: str, job_description: str,
                   source: str = "manual", source_license: str = "UNKNOWN",
                   status: str = "published", structured_profile: dict | None = None,
                   is_synthetic: bool | None = None,
                   data_source: str | None = None) -> dict:
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

        title_s = str(title).strip()[:255]
        jd_s = str(job_description)
        ds, declared = resolve_data_source(
            is_synthetic=is_synthetic, source=str(source or ""),
            source_license=str(source_license or ""), explicit=data_source)
        now = _now()
        audit = [{"at": now.isoformat(), "by": str(user.get("username") or user.get("id") or ""),
                  "from": None, "to": ds,
                  "reason": ("explicit_declaration" if declared
                             else "derived_from_source_fields")}]

        row = Job(title=title_s, job_description=jd_s,
                  source=str(source)[:128] or "manual",
                  source_license=str(source_license)[:64] or "UNKNOWN",
                  status=status, structured_profile=structured_profile,
                  job_content_hash=job_content_hash(title_s, jd_s),
                  profile_status="unparsed",
                  parser_version=None,
                  data_source=ds, data_source_declared=1 if declared else 0,
                  data_source_declared_by=(str(user.get("username") or user.get("id") or "")[:64]
                                           if declared else None),
                  data_source_declared_at=(now if declared else None),
                  source_audit=audit)
        if structured_profile:
            # 调用方直接提供结构化画像：按"与当前原文同源"登记（生成方即为解析方）
            row.profile_status = "parsed"
            row.profile_source_hash = row.job_content_hash
            row.parser_version = JOB_PARSER_VERSION
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
                   "status", "job_category", "city", "education_min", "data_source"}
        unknown = [k for k in fields if k not in allowed]
        if unknown:
            raise ServiceError("INVALID_REQUEST", f"不允许更新的字段: {unknown}")
        if "status" in fields and fields["status"] not in VALID_STATUSES:
            raise ServiceError("INVALID_REQUEST", f"status 只允许 {VALID_STATUSES}")
        if "data_source" in fields:
            v = str(fields["data_source"] or "").strip().lower()
            if v not in DATA_SOURCES:
                raise ServiceError("INVALID_REQUEST", f"data_source 只允许 {DATA_SOURCES}")

        with session_scope(self._session_factory) as s:
            row = self._owned_job(job_id, session=s, any_status=True)
            # P0-01：先看影响画像的字段是否变化 -> 计算新内容哈希 -> 判定画像是否失效
            content_changed = False
            new_hash = row.job_content_hash
            for k, v in fields.items():
                if k in PROFILE_AFFECTING_FIELDS:
                    content_changed = True
            if content_changed:
                new_title = fields.get("title", row.title)
                new_jd = fields.get("job_description", row.job_description)
                new_hash = job_content_hash(new_title, new_jd)

            # P1-03：来源只在显式声明时改写，并记审计（更新不得静默改变数据来源）
            audit = list(row.source_audit or [])
            if "data_source" in fields:
                old_ds = row.data_source
                new_ds = str(fields["data_source"]).strip().lower()
                if new_ds != old_ds:
                    audit.append({"at": _now().isoformat(),
                                  "by": str(user.get("username") or user.get("id") or ""),
                                  "from": old_ds, "to": new_ds,
                                  "reason": "explicit_update"})
                    row.data_source = new_ds
                row.data_source_declared = 1
                row.data_source_declared_by = str(
                    user.get("username") or user.get("id") or "")[:64]
                row.data_source_declared_at = _now()
            row.source_audit = audit

            for k, v in fields.items():
                if k == "data_source":
                    continue
                setattr(row, k, v)

            row.job_content_hash = new_hash
            if content_changed:
                # 原文已变：旧画像立即失效（不用 updated_at 证明一致性）
                if row.structured_profile is not None:
                    row.profile_status = "needs_reparse"
                else:
                    row.profile_status = "unparsed"
                row.profile_source_hash = None
                row.profile_error = None
            s.flush()
            s.refresh(row)
            return self._job_row(row, include_profile=True)

    def set_status(self, user: dict, job_id: str, status: str) -> dict:
        return self.update_job(user, job_id, {"status": status})

    def parse_profile(self, user: dict, job_id: str) -> dict:
        """触发岗位画像解析（复用 service/job_parser.parse_job_text）。

        事务边界（P0-01 #6）：
          T1 读取原文 + 当前 job_content_hash -> 解析（事务外，不占连接）
          T2 校验 job_content_hash 未变 -> 写入画像 + 状态（同一事务）
        解析期间原文被修改 -> 结果作废并 409，**不允许旧结果覆盖新版本**。
        """
        self._require_admin(user)
        with session_scope(self._session_factory) as s:
            row = self._owned_job(job_id, session=s, any_status=True)
            text = row.job_description
            title = row.title
            source, license_ = row.source, row.source_license
            data_source = row.data_source
            captured_hash = row.job_content_hash

        error: str | None = None
        d: dict | None = None
        warnings: list[str] = []
        try:
            profile = self._parse_job_profile(text, job_id=job_id, title=title,
                                              source=source, source_license=license_,
                                              data_source=data_source)
            d = profile.to_dict()
            warnings = list(profile.warnings)
        except Exception as e:  # noqa: BLE001  解析失败必须显式落失败状态
            error = f"{type(e).__name__}: {e}"[:500]

        with session_scope(self._session_factory) as s:
            row = self._owned_job(job_id, session=s, any_status=True)
            if row.job_content_hash != captured_hash:
                # 解析期间原文被修改 -> 本次解析结果不可信，作废
                raise ServiceError("CONFLICT",
                                   "岗位原文在解析期间被修改，本次解析结果已作废，请重新解析",
                                   {"job_id": job_id})
            if error is not None:
                # 失败：清空旧画像并显式记录失败状态（禁止旧画像伪装成功）
                row.structured_profile = None
                row.profile_source_hash = None
                row.profile_status = "failed"
                row.profile_error = error
                row.parser_version = JOB_PARSER_VERSION
            else:
                row.structured_profile = d
                self._apply_profile_columns(row, d)
                row.profile_source_hash = row.job_content_hash   # 与当前原文一致
                row.profile_status = "parsed"
                row.profile_error = None
                row.parser_version = JOB_PARSER_VERSION
            s.flush()
            s.refresh(row)
            out = self._job_row(row, include_profile=True)
        out["warnings"] = warnings
        if error is not None:
            out["warnings"] = warnings + [f"parse_failed:{error}"]
        return out

    def import_jobs(self, user: dict, items: list[dict]) -> dict:
        """批量导入合法数据：逐行校验，合法行入库，非法行逐条登记（不半途崩溃）。

        标题容错语义（缺列 ≠ 空值）：
          * `title` 键缺失或为 null -> 从 job_description 首个非空行派生标题
            （外部数据源常出现缺列，导入不得整批失败）；
          * `title` 显式为空字符串/纯空白 -> 视为数据错误，该行拒绝并登记原因。
        来源语义（P1-03）：`is_synthetic` 未提供时**不**当作 False，
        交给 resolve_data_source 按来源/许可推导，避免"没声明 = 非合成"的臆造。
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
                raw_synth = item.get("is_synthetic", None)
                row_out = self.create_job(
                    user,
                    title=str(title or ""),
                    job_description=str(item.get("job_description") or ""),
                    source=str(item.get("source") or "import"),
                    source_license=str(item.get("source_license") or "UNKNOWN"),
                    status=str(item.get("status") or "published"),
                    is_synthetic=(bool(raw_synth) if raw_synth is not None else None),
                    data_source=item.get("data_source"))
                created.append({"index": i, "job_id": row_out["id"],
                                "data_source": row_out.get("data_source")})
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
            # P1-07：**先筛选后分页**。技能条件落在结构化画像（JSON）里，
            # 数据库层无法精确表达；当前规模（批量导入上限 200/批）下
            # "取回合法候选 -> 应用层过滤 -> 再算 total 与分页"是简单且正确的方案。
            # 不为分页语义引入 Elasticsearch（无性能证据前不加基础设施）。
            rows = (query.order_by(Job.updated_at.desc(), Job.id.asc()).all())
            need_profile = bool(skills)
            candidates = [self._job_row(r, include_profile=need_profile) for r in rows]
        finally:
            session.close()

        if skills:
            wanted = {s.strip().lower() for s in skills if s and s.strip()}
            items_all = [it for it in candidates if self._skill_matches(it, wanted)]
        else:
            items_all = candidates

        total = len(items_all)                       # 全部符合条件的数量
        start = (page - 1) * page_size
        items = items_all[start:start + page_size]   # 分页边界不漏项、不越界
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
        """供推荐服务取用：已发布 + **画像与当前原文一致**的岗位（P0-01）。

        三个条件缺一不可：
          1. structured_profile 存在；
          2. profile_status == 'parsed'（needs_reparse / failed / unparsed 一律排除）；
          3. profile_source_hash == job_content_hash（画像确实依据当前原文）。
        """
        session = self._session_factory()
        try:
            query = session.query(Job).filter(Job.status == "published")
            if job_ids:
                query = query.filter(Job.id.in_(job_ids))
            out = []
            for row in query.order_by(Job.updated_at.desc(), Job.id.asc()).all():
                if not row.structured_profile:
                    continue
                if row.profile_status != "parsed":
                    continue
                if not row.profile_source_hash or row.profile_source_hash != row.job_content_hash:
                    continue
                try:
                    out.append((row, JobProfile.from_dict(row.structured_profile)))
                except Exception:  # noqa: BLE001  坏画像行跳过并由告警体现
                    continue
            return out
        finally:
            session.close()

    def job_profile_consistency(self, job_id: str) -> dict:
        """诊断口径：画像是否与当前原文一致（供测试/运维核对，不改状态）。"""
        session = self._session_factory()
        try:
            row = session.query(Job).filter(Job.id == job_id).first()
            if row is None:
                raise ServiceError("NOT_FOUND", "岗位不存在")
            return {"job_id": job_id,
                    "job_content_hash": row.job_content_hash,
                    "profile_source_hash": row.profile_source_hash,
                    "profile_status": row.profile_status,
                    "profile_current": bool(
                        row.structured_profile
                        and row.profile_status == "parsed"
                        and row.profile_source_hash == row.job_content_hash),
                    "parser_version": row.parser_version,
                    "data_source": row.data_source}
        finally:
            session.close()

    # ============================================================ 内部
    def _parse_job_profile(self, text: str, *, job_id: str, title: str,
                           source: str, source_license: str,
                           data_source: str = "unknown") -> JobProfile:
        from .job_parser import parse_job_text
        # P1-03：is_synthetic 由**数据来源**决定，解析器不再硬编码
        return parse_job_text(
            f"{title}\n{text}" if title and title not in text else text,
            job_id=job_id, source=source, source_license=source_license,
            is_synthetic=(data_source == "synthetic"),
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
               "profile_parsed": j.structured_profile is not None,
               # ---- Phase5-2R 新增（只加不减，历史字段语义不变）----
               "job_content_hash": j.job_content_hash,
               "profile_source_hash": j.profile_source_hash,
               "profile_status": j.profile_status,
               "profile_error": j.profile_error,
               "parser_version": j.parser_version,
               "profile_current": bool(
                   j.structured_profile and j.profile_status == "parsed"
                   and j.profile_source_hash == j.job_content_hash),
               "data_source": j.data_source,
               "data_source_declared": bool(j.data_source_declared),
               "source_audit": list(j.source_audit or [])}
        if include_profile:
            out["structured_profile"] = j.structured_profile
        return out
