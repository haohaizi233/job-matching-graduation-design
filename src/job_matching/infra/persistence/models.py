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
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        # 同一用户重复上传同一文件 -> 幂等返回既有简历（不重复存文件）
        UniqueConstraint("user_id", "file_sha256", name="uq_resumes_user_sha256"),
        Index("ix_resumes_user_uploaded", "user_id", "uploaded_at"),
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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_jobs_status_category", "status", "job_category"),
        Index("ix_jobs_status_city", "status", "city"),
        Index("ix_jobs_status_updated", "status", "updated_at"),
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
    # 请求指纹（重复提交幂等）：同一用户相同画像版本 + 相同岗位集合 + 相同参数
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # completed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    error_detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # 重复提交处理：同一用户同一请求指纹只落一条运行记录
        UniqueConstraint("user_id", "request_fingerprint", name="uq_reco_runs_user_fingerprint"),
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
    # 岗位快照版本（岗位更新后历史解释仍可追溯）
    job_snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
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


__all__ = ["User", "AuthSession", "StudentProfile", "Resume", "Job",
           "RecommendationRun", "RecommendationItem", "RecommendationFeedback"]
