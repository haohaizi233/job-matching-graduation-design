# -*- coding: utf-8 -*-
"""业务持久化层（Phase5-2 / Batch 1，SQLAlchemy 2.x）。

分层归属：`infra/**` 允许依赖外部格式/基础库（SQLAlchemy 属基础设施依赖），
`service/**` 通过本包的 session 工厂访问数据库，禁止在路由里裸写 SQL。

约束：
  * 数据库连接一律来自配置（JM_DATABASE_URL），禁止写死连接串或密码；
  * PostgreSQL 为主力持久化库；SQLite 仅用于本地开发与部分自动化测试；
  * SQLite 通过测试 **不等于** PostgreSQL 兼容（JSON/约束/事务语义有差异），
    涉及这些语义必须补 PostgreSQL 集成测试（tests/phase5_2/test_pg_integration.py）。
"""
from __future__ import annotations

from .base import (Base, DbSettings, dispose_engines, get_engine, get_session,
                   get_session_factory, init_db, session_scope)
from .models import (AuthSession, Job, RecommendationFeedback, RecommendationItem,
                     RecommendationRun, Resume, StudentProfile, User)

__all__ = [
    "Base", "DbSettings", "dispose_engines", "get_engine", "get_session",
    "get_session_factory", "init_db", "session_scope",
    "User", "AuthSession", "StudentProfile", "Resume", "Job",
    "RecommendationRun", "RecommendationItem", "RecommendationFeedback",
]
