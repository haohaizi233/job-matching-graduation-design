# -*- coding: utf-8 -*-
"""OAuth 身份与本站账号的关联业务（Phase8-A / M4.1-M4.4）。

账号合并纪律（M5.3，写死在代码与测试里）：
  * 只按 (provider, client_id, subject) 关联账号；昵称/头像/邮箱**永不**参与识别；
  * 禁止"微信昵称 == 本站用户名 → 自动绑定"、"QQ 昵称 == 微信昵称 → 自动合并"、
    "微博邮箱 == 本站邮箱 → 自动绑定"、"头像相同 → 自动合并"；
  * 未验证邮箱不作为已验证邮箱，也不用于自动绑定既有账号；
  * 未登录的第三方身份与现有账号疑似重复时，只创建独立新用户（或提示用户
    用原账号主动绑定），**绝不**默默合并。

绑定策略（本项目明确约定）：
  * 同一 (provider, client_id, subject) 只能绑定一个本站用户（DB 唯一约束）；
  * 一个本站账号在同一 Provider 下最多绑定 1 个身份（service 层强制，超出报
    OAUTH_IDENTITY_CONFLICT）；不同 Provider 可多个；
  * 解绑后若账号将失去全部登录方式（无密码 + 无其它第三方身份）-> OAUTH_LAST_LOGIN_METHOD。

OAuth-only 账号：
  * password_hash=NULL、role=student、status=active；
  * username 形如 `qq_a1b2c3d4`（provider 前缀 + 随机后缀，唯一），
    **不用**第三方昵称当 username。
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Callable

from sqlalchemy.exc import IntegrityError

from ..errors import ServiceError
from ...infra.persistence import OAuthIdentity, User, get_session_factory
from .exceptions import IdentityConflict, InvalidIdentity, LastLoginMethod
from .identity_repository import OAuthIdentityRepository

MAX_USERNAME_ATTEMPTS = 8


def _now() -> datetime:
    return datetime.utcnow()


class OAuthIdentityService:
    """身份解析/创建/绑定/解绑（依赖注入便于测试）。"""

    def __init__(self, session_factory: Callable | None = None,
                 identities: OAuthIdentityRepository | None = None,
                 clock: Callable[[], datetime] = _now):
        self._session_factory = session_factory or get_session_factory()
        self._repo = identities or OAuthIdentityRepository(
            session_factory=self._session_factory, clock=clock)
        self._clock = clock

    # ---------------------------------------------------------- 登录解析
    def resolve_or_create_user(self, identity) -> dict:
        """第三方登录：已绑定 -> 取回本站用户；未绑定 -> 事务内创建 student 用户 + 映射。

        账号创建与身份插入在**同一事务**：要么同时成功，要么整体回滚，
        不产生"有用户没映射"的孤儿账号。
        """
        subject = getattr(identity, "subject", "") or ""
        if not subject:
            raise InvalidIdentity("第三方身份缺少 subject，拒绝创建账号")
        existing = self._repo.get(provider=identity.provider,
                                  client_id=identity.client_id,
                                  subject=subject)
        if existing:
            self._repo.touch_login(
                existing["id"],
                display_name=identity.display_name if identity.profile_fetched else None,
                avatar_url=identity.avatar_url if identity.profile_fetched else None,
                union_id=identity.union_id)
            return {"user_id": existing["user_id"], "identity_id": existing["id"],
                    "created": False}

        return self._create_user_with_identity(identity)

    def _create_user_with_identity(self, identity) -> dict:
        now = self._clock()
        for _attempt in range(MAX_USERNAME_ATTEMPTS):
            username = self._generate_username(identity.provider)
            session = self._session_factory()
            try:
                user = User(username=username, email=None,
                            password_hash=None,        # 纯 OAuth：无占位密码
                            role="student", status="active",
                            failed_login_count=0,
                            created_at=now, updated_at=now)
                session.add(user)
                session.flush()     # 先拿 user.id（同一事务内）
                row_id = None
                ident_row = OAuthIdentity(
                    user_id=user.id, provider=identity.provider,
                    client_id=identity.client_id, subject=identity.subject,
                    union_id=identity.union_id,
                    display_name=identity.display_name if identity.profile_fetched else None,
                    avatar_url=identity.avatar_url if identity.profile_fetched else None,
                    created_at=now, updated_at=now, last_login_at=now)
                session.add(ident_row)
                session.commit()
                session.refresh(user)
                session.refresh(ident_row)
                row_id = ident_row.id
                return {"user_id": user.id, "identity_id": row_id, "created": True}
            except IntegrityError:
                # 并发重复注册/唯一约束冲突：整体回滚后重新查找既有映射
                session.rollback()
                existing = self._repo.get(provider=identity.provider,
                                          client_id=identity.client_id,
                                          subject=identity.subject)
                if existing:
                    return {"user_id": existing["user_id"],
                            "identity_id": existing["id"], "created": False}
                # 冲突来自 username 撞名 -> 换后缀重试
                continue
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        raise IdentityConflict("无法生成唯一用户名，请重试")

    @staticmethod
    def _generate_username(provider: str) -> str:
        prefix = "".join(c for c in str(provider).lower() if c.isalnum())[:12] or "oauth"
        return f"{prefix}_{secrets.token_hex(4)}"[:64]

    # ---------------------------------------------------------- 绑定
    def bind_identity(self, *, user_id: str, identity) -> dict:
        """已登录用户主动绑定第三方身份（发起与完成都要求同一会话，见 service）。"""
        if not getattr(identity, "subject", ""):
            raise InvalidIdentity("第三方身份缺少 subject，拒绝绑定")
        existing = self._repo.get(provider=identity.provider,
                                  client_id=identity.client_id,
                                  subject=identity.subject)
        if existing:
            if existing["user_id"] == user_id:
                return {"identity": existing, "already_bound": True}
            # 第三方账号抢绑定 / 已绑他人：显式冲突，不静默转移
            raise IdentityConflict("该第三方身份已绑定其他本站账号",
                                   {"provider": identity.provider})
        # 同一 Provider 每账号最多一个身份（明确策略，超出显式冲突）
        for item in self._repo.list_for_user(user_id):
            if item["provider"] == identity.provider:
                raise IdentityConflict(
                    f"该账号已绑定一个 {identity.provider} 身份，请先解绑后再绑定",
                    {"provider": identity.provider, "identity_id": item["id"]})
        created = self._repo.insert(
            user_id=user_id, provider=identity.provider,
            client_id=identity.client_id, subject=identity.subject,
            union_id=identity.union_id,
            display_name=identity.display_name if identity.profile_fetched else None,
            avatar_url=identity.avatar_url if identity.profile_fetched else None)
        return {"identity": created, "already_bound": False}

    # ---------------------------------------------------------- 解绑
    def unbind_identity(self, *, user_id: str, provider: str | None = None,
                        identity_id: str | None = None) -> dict:
        """解绑本人身份；不得使账号永久无法登录（OAUTH_LAST_LOGIN_METHOD）。"""
        target = None
        if identity_id:
            target = self._repo.get_by_id(identity_id)
            if target and target["user_id"] != user_id:
                target = None     # 非本人 -> 404 防枚举
        elif provider:
            for item in self._repo.list_for_user(user_id):
                if item["provider"] == provider:
                    target = item
                    break
        if not target:
            raise ServiceError("NOT_FOUND", "未找到要解绑的第三方身份")

        # 最后登录方式保护
        has_password = self._user_has_password(user_id)
        others = self._repo.count_for_user(user_id, exclude_id=target["id"])
        if not has_password and others == 0:
            raise LastLoginMethod(
                "该身份是账号唯一登录方式，解绑将导致账号无法登录；"
                "请先设置本站密码或绑定其它登录方式")

        deleted = self._repo.delete_for_user(user_id=user_id, identity_id=target["id"])
        return {"unbound": bool(deleted), "identity": deleted}

    # ---------------------------------------------------------- 查询
    def list_identities(self, user_id: str) -> dict:
        items = self._repo.list_for_user(user_id)
        return {"items": items,
                "password_login_available": self._user_has_password(user_id)}

    # ---------------------------------------------------------- 内部
    def _user_has_password(self, user_id: str) -> bool:
        session = self._session_factory()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return bool(user is not None and user.password_hash)
        finally:
            session.close()
