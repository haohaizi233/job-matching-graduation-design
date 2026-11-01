# -*- coding: utf-8 -*-
"""oauth_identities 持久化（Phase8-A / M3.1）。

约束实现口径：
  * 同一平台身份（provider, client_id, subject）只能绑定一个本站用户 —— 由
    UNIQUE(provider, client_id, subject) 数据库约束兜底，**不靠**"先查后插"；
  * 并发绑定产生重复身份记录时捕获 IntegrityError -> OAUTH_IDENTITY_CONFLICT；
  * 事务失败整体回滚，不留半成功记录。
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.exc import IntegrityError

from ...infra.persistence import OAuthIdentity, get_session_factory
from .exceptions import IdentityConflict


def _now() -> datetime:
    return datetime.utcnow()


class OAuthIdentityRepository:
    """第三方身份映射存取（依赖注入 session_factory / clock 便于测试）。"""

    def __init__(self, session_factory: Callable | None = None,
                 clock: Callable[[], datetime] = _now):
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock

    # ---------------------------------------------------------- 查询
    def get(self, *, provider: str, client_id: str, subject: str) -> dict | None:
        session = self._session_factory()
        try:
            row = (session.query(OAuthIdentity)
                   .filter(OAuthIdentity.provider == provider,
                           OAuthIdentity.client_id == client_id,
                           OAuthIdentity.subject == subject).first())
            return _row_to_dict(row) if row else None
        finally:
            session.close()

    def get_by_id(self, identity_id: str) -> dict | None:
        session = self._session_factory()
        try:
            row = (session.query(OAuthIdentity)
                   .filter(OAuthIdentity.id == identity_id).first())
            return _row_to_dict(row) if row else None
        finally:
            session.close()

    def list_for_user(self, user_id: str) -> list[dict]:
        session = self._session_factory()
        try:
            rows = (session.query(OAuthIdentity)
                    .filter(OAuthIdentity.user_id == user_id)
                    .order_by(OAuthIdentity.provider, OAuthIdentity.created_at)
                    .all())
            return [_row_to_dict(r) for r in rows]
        finally:
            session.close()

    def count_for_user(self, user_id: str, *, exclude_id: str | None = None) -> int:
        session = self._session_factory()
        try:
            q = session.query(OAuthIdentity).filter(OAuthIdentity.user_id == user_id)
            if exclude_id:
                q = q.filter(OAuthIdentity.id != exclude_id)
            return int(q.count())
        finally:
            session.close()

    # ---------------------------------------------------------- 写入
    def insert(self, *, user_id: str, provider: str, client_id: str, subject: str,
               union_id: str | None = None, display_name: str | None = None,
               avatar_url: str | None = None) -> dict:
        """插入身份映射（唯一约束冲突 -> IdentityConflict，不静默合并）。"""
        now = self._clock()
        session = self._session_factory()
        try:
            row = OAuthIdentity(
                user_id=user_id, provider=provider, client_id=client_id,
                subject=subject, union_id=union_id,
                display_name=(display_name or None),
                avatar_url=(avatar_url or None),
                created_at=now, updated_at=now, last_login_at=now)
            session.add(row)
            session.commit()
            session.refresh(row)
            return _row_to_dict(row)
        except IntegrityError as e:
            session.rollback()
            raise IdentityConflict(
                "该第三方身份已绑定其他本站账号",
                {"provider": provider, "client_id": client_id}) from e
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def touch_login(self, identity_id: str, *, display_name: str | None = None,
                    avatar_url: str | None = None,
                    union_id: str | None = None) -> None:
        """登录命中既有映射：更新 last_login_at；资料字段只在真实读取到时覆盖。"""
        now = self._clock()
        session = self._session_factory()
        try:
            row = (session.query(OAuthIdentity)
                   .filter(OAuthIdentity.id == identity_id).first())
            if row is None:
                return
            row.last_login_at = now
            row.updated_at = now
            if display_name:
                row.display_name = display_name
            if avatar_url:
                row.avatar_url = avatar_url
            if union_id:
                row.union_id = union_id
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_for_user(self, *, user_id: str, identity_id: str) -> dict | None:
        """删除本人指定身份映射（非本人/不存在一律 None -> 路由层 404 防枚举）。"""
        session = self._session_factory()
        try:
            row = (session.query(OAuthIdentity)
                   .filter(OAuthIdentity.id == identity_id,
                           OAuthIdentity.user_id == user_id).first())
            if row is None:
                return None
            data = _row_to_dict(row)
            session.delete(row)
            session.commit()
            return data
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _row_to_dict(row) -> dict:
    return {"id": row.id, "user_id": row.user_id, "provider": row.provider,
            "client_id": row.client_id, "subject": row.subject,
            "union_id": row.union_id, "display_name": row.display_name,
            "avatar_url": row.avatar_url,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None}
