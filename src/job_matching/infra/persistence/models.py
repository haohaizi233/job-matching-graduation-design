# -*- coding: utf-8 -*-
"""业务领域实体 ORM 映射（Phase5-2 / Batch 1 最小领域模型）。

设计纪律：
  * 只建当前业务用得到的表，不为"企业级"提前铺表；
  * 每张表保留必要的外键、唯一约束、索引与数据版本信息；
  * JSON 字段使用可移植类型（SQLite: JSON / PostgreSQL: JSONB 变体），
    JSON 语义差异必须由 PostgreSQL 集成测试覆盖；
  * 时间统一 UTC naive（datetime.utcnow），由应用层保证时区口径；
  * 业务标识使用字符串 UUID（36 字符），避免后端差异。

隐私边界：
  * `resumes.storage_key` 只存**受控存储键**，绝不存本机绝对路径；
  * `users.password_hash` 任何 API 响应/日志都不得输出；
  * 真实简历原文只进私有文件存储，数据库只留元数据。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects import postgresql

from .base import Base

# JSON 可移植类型：SQLite 用 JSON 文本，PostgreSQL 用 JSONB（可索引/可查询）
JSON_TYPE = JSON().with_variant(postgresql.JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class User(Base):
    """用户账号（角色最小化：student / admin）。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="student")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # 登录失败限制（连续失败计数 + 锁定截止时间）
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_users_role_status", "role", "status"),
    )


class AuthSession(Base):
    """服务端会话（不透明 Bearer Token 的服务端状态，登出即失效）。"""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    # 只存 Token 的 SHA-256，不存 Token 明文（数据库泄漏不直接等于会话泄漏）
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),
    )


class StudentProfile(Base):
    """学生画像版本（每次确认/编辑产生新版本，旧版本保留可追溯）。"""

    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # profile_data 结构：{"profile": <StudentProfile.to_dict()>,
    #                     "user_edits": {字段: {value, edited_at, note}},
    #                     "evidence_policy": ...}
    # 人工修改进 user_edits 覆盖层，原始抽取证据保留在 profile 内（不静默覆盖）
    profile_data: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    resume_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0/1
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("user_id", "profile_version", name="uq_student_profiles_user_version"),
        Index("ix_student_profiles_user_confirmed", "user_id", "confirmed"),
    )


class Resume(Base):
    """简历文件元数据（原文在私有文件存储，此处只留安全存储键）。"""

    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # 受控存储键（相对存储根），绝不存本机绝对路径
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # pending | ok | partial | empty_text | ocr_required | failed
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    parse_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ---- P1-03 数据来源（Phase5-2R）：synthetic | user_provided | licensed_dataset | unknown
    # 由上传/声明推导一次后固化；重新解析**不得**静默改写
    data_source: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    data_source_declared: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_audit: Mapped[list] = mapped_column(JSON_TYPE, nullable=False, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        # 同一用户重复上传同一文件 -> 幂等返回既有简历（不重复存文件）
        UniqueConstraint("user_id", "file_sha256", name="uq_resumes_user_sha256"),
        Index("ix_resumes_user_uploaded", "user_id", "uploaded_at"),
        # 文件生命周期：孤儿扫描/引用检查按 storage_key 定位
        Index("ix_resumes_storage_key", "storage_key"),
    )


class Job(Base):
    """岗位（管理员维护；学生只看已发布）。"""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    # 结构化岗位画像（JobProfile.to_dict()）；未解析时为空
    structured_profile: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="manual")
    source_license: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    # draft | published | offline
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published")
    # 检索用冗余列（来自结构化画像；保持与 structured_profile 同步更新）
    job_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    education_min: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # ---- P0-01 岗位画像版本与失效（Phase5-2R）----
    # job_content_hash：影响画像的原文指纹（title + job_description 规范化 SHA-256）
    job_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # profile_source_hash：结构化画像**实际依据**的原文指纹；与 job_content_hash 不等即视为过期
    profile_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # unparsed | parsed | needs_reparse | failed
    profile_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unparsed")
    profile_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # ---- P1-03 数据来源（Phase5-2R）：synthetic | user_provided | licensed_dataset | unknown
    data_source: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    # 来源是否由管理员显式声明（0=由来源/许可推导，1=显式声明）
    data_source_declared: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_source_declared_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_source_declared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 来源声明审计流水（只追加）：[{at, by, from, to, reason}]
    source_audit: Mapped[list] = mapped_column(JSON_TYPE, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_jobs_status_category", "status", "job_category"),
        Index("ix_jobs_status_city", "status", "city"),
        Index("ix_jobs_status_updated", "status", "updated_at"),
        # 推荐取用"可匹配岗位"的过滤条件（status + profile_status + 哈希一致性）
        Index("ix_jobs_status_profile_status", "status", "profile_status"),
    )


class RecommendationRun(Base):
    """一次推荐运行（完整快照，保证历史可解释）。"""

    __tablename__ = "recommendation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    resume_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # baseline_heuristic | research_model ...
    scoring_method: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scoring_config_version: Mapped[str] = mapped_column(String(64), nullable=False,
                                                        default="scoring_config_v1")
    # 参与匹配的岗位集合快照：[{job_id, title, updated_at, profile_version}]
    job_set_snapshot: Mapped[list] = mapped_column(JSON_TYPE, nullable=False, default=list)
    # 请求指纹（自然去重）：**规范化 JSON 全量有效输入** 的 SHA-256
    # （用户 / 画像版本与内容指纹 / 岗位集合与各岗位内容与画像版本 / 排序模式 /
    #   模型 ID 与版本 / 评分配置版本 / top_k / 筛选条件 / allow_fallback）。
    # 调用方提供 Idempotency-Key 时，指纹额外绑定幂等键命名空间（同 Key 同语义 = 同一请求）。
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # 请求语义指纹：只反映有效输入，与是否携带 Idempotency-Key 无关
    # （用于"同 Key 不同语义 -> 409"的冲突判定）
    request_semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 调用方显式幂等键（可空）；同一用户下唯一，重复键但语义不同 -> 409 CONFLICT
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 画像内容指纹（推荐时刻的画像不可变摘要；不是 updated_at）
    profile_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 降级快照（Phase5-3 / M5）：模型不可用显式降级时记录
    # {degraded, reason_code, failure_kind, requested_model_id, actual_scoring_method}；
    # 未降级为 NULL（不乐观回填）
    degradation_info: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    # completed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # 重复提交处理：同一用户同一请求指纹只落一条运行记录
        UniqueConstraint("user_id", "request_fingerprint", name="uq_reco_runs_user_fingerprint"),
        # 显式幂等键唯一：同 Key 不同语义不得静默合并（应用层判 409）。
        # 用**唯一索引**表达（与迁移一致）：SQLite 的 ALTER TABLE 不支持 ADD CONSTRAINT，
        # 而 batch 重建表存在被 recommendation_items 外键引用的结构风险。
        Index("uq_reco_runs_user_idem_key", "user_id", "idempotency_key", unique=True),
        Index("ix_reco_runs_user_created", "user_id", "created_at"),
    )


class RecommendationItem(Base):
    """推荐结果条目（排序 + 分数 + 解释快照）。"""

    __tablename__ = "recommendation_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recommendation_runs.id", ondelete="CASCADE"),
        nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"),
                                        nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # heuristic_score | model_raw_score（calibrated_score 本轮禁用）
    score_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 匹配解释快照（运行时刻的解释，不随岗位后续修改而变）
    explanation_snapshot: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    # 岗位快照版本（岗位更新后历史解释仍可追溯）：
    #   "{job_id}:{job_content_hash[:16]}" —— 内容哈希口径，不依赖 updated_at
    job_snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # 条目证据快照：当时岗位内容指纹 + 画像状态（历史可解释的最小证据，不复制 JD 原文）
    job_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_status_at_run: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("run_id", "rank", name="uq_reco_items_run_rank"),
        UniqueConstraint("run_id", "job_id", name="uq_reco_items_run_job"),
    )


class RecommendationFeedback(Base):
    """用户对推荐条目的业务反馈（**不等于**人工 Gold 标签）。"""

    __tablename__ = "recommendation_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    recommendation_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recommendation_items.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # interested | not_interested | applied | interview | irrelevant
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        # 一个用户对一个推荐条目只保留一条反馈（再次提交为更新，不堆历史垃圾）
        UniqueConstraint("user_id", "recommendation_item_id",
                         name="uq_reco_feedback_user_item"),
        Index("ix_reco_feedback_user_created", "user_id", "created_at"),
    )


class UserSetting(Base):
    """用户级设置（服务端持久化；主题等纯客户端显示偏好不入库）。

    payload 结构（服务端严格校验，见 settings_store.UserSettingsService）：
      {
        "basic":        {nickname, school, major, enrollYear, graduateYear, region},
        "notifications": {siteMessage, emailNotice, matchAlert, weeklyReport},
        "resume_prefs": {autoParse, ocrImages},
        "privacy":      {publicResume, companyView, hideSalary},
        "job_intent":   {intentTags: [...]},
      }
    隐私边界：设置只属于 user_id 本人；API 层强制按当前登录用户隔离。
    """

    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)


__all__ = ["User", "AuthSession", "UserSetting", "StudentProfile", "Resume", "Job",
           "RecommendationRun", "RecommendationItem", "RecommendationFeedback"]
