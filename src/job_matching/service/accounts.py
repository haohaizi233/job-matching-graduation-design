# -*- coding: utf-8 -*-
"""账号、密码与会话（Phase5-2 / Batch 2 最小身份系统）。

选型说明（服务端会话 + 不透明 Bearer Token，而非 JWT）：
  * 登出必须**立即失效**：JWT 无状态令牌只能等过期，服务端会话可删除/撤销；
  * 数据库已在架构内，会话状态存储成本低；
  * Token 只在签发响应中出现一次，服务端只存 SHA-256 摘要（库泄漏不直接等于会话泄漏）；
  * 密码哈希使用 Argon2id（argon2-cffi），不自研密码学。

安全边界：
  * 密码长度/复杂度校验（10 位以上 + 字母 + 数字）；
  * 登录失败限制：连续 5 次失败锁定 15 分钟（账号级，见 MAX_FAILED_LOGINS）；
  * Token 过期 / 撤销 / 不存在一律 401，不区分提示以免探测；
  * password_hash 与 Token 明文绝不进入响应或日志。
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from typing import Callable

from ..infra.persistence import AuthSession, User, get_session_factory
from .errors import ServiceError

try:  # pragma: no cover - 依赖存在性由环境检查覆盖
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
    from argon2.low_level import Type
    _HAS_ARGON2 = True
except ImportError:  # pragma: no cover
    _HAS_ARGON2 = False

# ---- 策略常量（文档/测试同源）----
MIN_PASSWORD_LEN = 10
MAX_PASSWORD_LEN = 128
MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 64
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
SESSION_TTL_HOURS = 12
TOKEN_BYTES = 32

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DIGIT_RE = re.compile(r"\d")
_LETTER_RE = re.compile(r"[A-Za-z]")

_hasher = (PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2,
                          hash_len=32, salt_len=16, type=Type.ID)
           if _HAS_ARGON2 else None)


def _now() -> datetime:
    return datetime.utcnow()


# ------------------------------------------------------------------ 密码
def validate_password(password: str) -> list[str]:
    """密码强度校验，返回问题列表（空列表 = 合格）。"""
    problems: list[str] = []
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        problems.append(f"密码长度不得少于 {MIN_PASSWORD_LEN} 位")
    if isinstance(password, str) and len(password) > MAX_PASSWORD_LEN:
        problems.append(f"密码长度不得超过 {MAX_PASSWORD_LEN} 位")
    if isinstance(password, str):
        if not _LETTER_RE.search(password):
            problems.append("密码必须包含字母")
        if not _DIGIT_RE.search(password):
            problems.append("密码必须包含数字")
    return problems


def validate_username(username: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(username, str) or not (MIN_USERNAME_LEN <= len(username) <= MAX_USERNAME_LEN):
        problems.append(f"用户名长度必须在 {MIN_USERNAME_LEN}-{MAX_USERNAME_LEN} 之间")
        return problems
    if not _USERNAME_RE.match(username):
        problems.append("用户名只允许字母、数字、点、下划线、连字符")
    return problems


def hash_password(password: str) -> str:
    if not _HAS_ARGON2:  # pragma: no cover
        raise ServiceError("INTERNAL_ERROR", "密码哈希依赖 argon2-cffi 缺失")
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not _HAS_ARGON2:  # pragma: no cover
        raise ServiceError("INTERNAL_ERROR", "密码哈希依赖 argon2-cffi 缺失")
    try:
        return bool(_hasher.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


# ------------------------------------------------------------------ 会话
def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_user(user: User) -> dict:
    """用户信息的安全投影：绝不包含 password_hash。"""
    return {"id": user.id, "username": user.username, "email": user.email,
            "role": user.role, "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None}


class AccountService:
    """账号注册 / 登录 / 会话生命周期（依赖注入 session_factory 便于测试）。"""

    def __init__(self, session_factory: Callable | None = None,
                 clock: Callable[[], datetime] = _now):
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock

    # -------------------------------------------------------------- 注册
    def register(self, *, username: str, password: str, email: str | None = None,
                 role: str = "student") -> dict:
        problems = validate_username(username) + validate_password(password)
        if email and not _EMAIL_RE.match(email):
            problems.append("邮箱格式非法")
        if role not in ("student", "admin"):
            problems.append("角色只允许 student / admin")
        if problems:
            raise ServiceError("INVALID_REQUEST", "；".join(problems),
                               {"fields": problems})

        session = self._session_factory()
        try:
            exists = session.query(User).filter(User.username == username).first()
            if not exists and email:
                exists = session.query(User).filter(User.email == email).first()
            if exists:
                raise ServiceError("CONFLICT", "用户名或邮箱已被占用",
                                   {"field": "username"})
            user = User(username=username, email=email or None,
                        password_hash=hash_password(password), role=role,
                        status="active", failed_login_count=0)
            session.add(user)
            session.commit()
            session.refresh(user)
            return _public_user(user)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -------------------------------------------------------------- 登录
    def authenticate(self, *, username: str, password: str) -> dict:
        now = self._clock()
        session = self._session_factory()
        try:
            user = session.query(User).filter(User.username == username).first()
            if user is None:
                # 不区分"用户不存在/密码错误"（防用户枚举）；但不暴露计时差异细节
                raise ServiceError("AUTH_INVALID_CREDENTIALS", "认证失败，凭证无效")
            if user.status != "active":
                raise ServiceError("FORBIDDEN", "账号已停用")
            if user.locked_until and user.locked_until > now:
                raise ServiceError("AUTH_ACCOUNT_LOCKED",
                                   f"登录失败次数过多，账号锁定至 {user.locked_until.isoformat()}Z",
                                   {"locked_until": user.locked_until.isoformat()})

            if not verify_password(user.password_hash, password):
                user.failed_login_count = int(user.failed_login_count or 0) + 1
                if user.failed_login_count >= MAX_FAILED_LOGINS:
                    user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                    user.failed_login_count = 0
                    session.commit()
                    raise ServiceError("AUTH_ACCOUNT_LOCKED",
                                       f"登录失败次数过多，账号锁定 {LOCK_MINUTES} 分钟")
                session.commit()
                raise ServiceError("AUTH_INVALID_CREDENTIALS", "认证失败，凭证无效")

            user.failed_login_count = 0
            user.locked_until = None
            session.commit()
            return _public_user(user)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -------------------------------------------------------------- 会话
    def create_session(self, *, user_id: str, user_agent: str | None = None,
                       ttl_hours: int = SESSION_TTL_HOURS) -> tuple[str, dict]:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        now = self._clock()
        session = self._session_factory()
        try:
            row = AuthSession(user_id=user_id, token_sha256=_token_digest(token),
                              created_at=now, expires_at=now + timedelta(hours=ttl_hours),
                              user_agent=(user_agent or "")[:255] or None)
            session.add(row)
            session.commit()
            session.refresh(row)
            return token, {"token_type": "bearer", "expires_at": row.expires_at.isoformat(),
                           "session_id": row.id}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def resolve_token(self, token: str) -> dict:
        """校验 Token -> 返回用户公开信息；无效/过期/撤销一律 AUTH_* 401。"""
        if not token or not isinstance(token, str):
            raise ServiceError("AUTH_REQUIRED", "缺少或非法的访问令牌")
        now = self._clock()
        session = self._session_factory()
        try:
            row = (session.query(AuthSession)
                   .filter(AuthSession.token_sha256 == _token_digest(token)).first())
            if row is None or row.revoked_at is not None:
                raise ServiceError("AUTH_REQUIRED", "访问令牌无效或已撤销")
            if row.expires_at <= now:
                raise ServiceError("AUTH_TOKEN_EXPIRED", "访问令牌已过期")
            user = session.query(User).filter(User.id == row.user_id).first()
            if user is None or user.status != "active":
                raise ServiceError("FORBIDDEN", "账号不可用")
            row.last_seen_at = now
            session.commit()
            return _public_user(user)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def logout(self, token: str) -> bool:
        """登出：撤销服务端会话（返回是否确实撤销了活跃会话）。"""
        if not token:
            return False
        now = self._clock()
        session = self._session_factory()
        try:
            row = (session.query(AuthSession)
                   .filter(AuthSession.token_sha256 == _token_digest(token)).first())
            if row is None or row.revoked_at is not None:
                return False
            row.revoked_at = now
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
