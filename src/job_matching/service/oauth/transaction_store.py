# -*- coding: utf-8 -*-
"""OAuth 授权事务存储（Phase8-A / M4.2）。

安全语义：
  * state 明文只在授权 URL 里给浏览器一次，库里只存 SHA-256 摘要；
  * 每笔事务绑定浏览器绑定凭据（摘要）与模式（login/bind）与 Provider；
  * TTL（默认 300s）+ **一次性消费**（原子 UPDATE ... WHERE consumed_at IS NULL）；
  * 并发回调 / 跨浏览器重放 -> OAUTH_CALLBACK_REPLAY 或 OAUTH_INVALID_STATE；
  * 过期与已消费事务定期清理（cleanup）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from ...infra.persistence import OAuthAuthTransaction, get_session_factory
from .exceptions import CallbackReplay, InvalidState, StateExpired
from .security import digest


def _now() -> datetime:
    return datetime.utcnow()


class OAuthTransactionStore:
    """授权事务存取（依赖注入 session_factory / clock 便于测试）。"""

    def __init__(self, session_factory: Callable | None = None,
                 clock: Callable[[], datetime] = _now):
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock

    # ---------------------------------------------------------- 创建
    def create(self, *, rid: str, provider: str, mode: str, state: str,
               browser_binding_digest: str, browser_binding_key: str,
               redirect_uri: str, return_path: str,
               initiator_user_id: str | None = None,
               initiator_session_digest: str | None = None,
               code_verifier: str | None = None,
               ttl_seconds: int = 300) -> dict:
        now = self._clock()
        session = self._session_factory()
        try:
            row = OAuthAuthTransaction(
                rid=rid, provider=provider, mode=mode,
                state_digest=digest(state),
                browser_binding_digest=browser_binding_digest,
                browser_binding_key=browser_binding_key,
                initiator_user_id=initiator_user_id,
                initiator_session_digest=initiator_session_digest,
                redirect_uri=redirect_uri, return_path=return_path,
                code_verifier=code_verifier,
                created_at=now, expires_at=now + timedelta(seconds=int(ttl_seconds)))
            session.add(row)
            session.commit()
            session.refresh(row)
            return _row_to_dict(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------------------------------------------------------- 一次性消费
    def consume(self, *, state: str, provider: str, mode: str | None = None) -> dict:
        """按 state 摘要定位事务并原子消费（重复回调 -> CallbackReplay）。

        `mode` 仅在调用方明确知晓时传入做一致性校验（错误回调路径未知模式时可省略）。
        """
        if not state or not isinstance(state, str):
            raise InvalidState("state 缺失")
        d = digest(state)
        now = self._clock()
        session = self._session_factory()
        try:
            row = (session.query(OAuthAuthTransaction)
                   .filter(OAuthAuthTransaction.state_digest == d).first())
            if row is None:
                raise InvalidState("state 不匹配（未知授权事务）")
            if row.consumed_at is not None:
                raise CallbackReplay("该授权事务已消费，拒绝重放")
            if row.expires_at <= now:
                raise StateExpired("授权事务已过期，请重新发起授权")
            if row.provider != provider or (mode is not None and row.mode != mode):
                raise InvalidState("state 与 Provider/模式不匹配")
            # 原子消费：并发下只允许一个赢家
            updated = (session.query(OAuthAuthTransaction)
                       .filter(OAuthAuthTransaction.id == row.id,
                               OAuthAuthTransaction.consumed_at.is_(None))
                       .update({"consumed_at": now}, synchronize_session=False))
            session.commit()
            if updated != 1:
                raise CallbackReplay("该授权事务已被并发消费，拒绝重放")
            session.refresh(row)
            return _row_to_dict(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------------------------------------------------------- 清理
    def cleanup(self, *, older_than_seconds: int = 3600) -> int:
        """删除过期/已消费超过窗口的事务（防表膨胀）。"""
        cutoff = self._clock() - timedelta(seconds=int(older_than_seconds))
        session = self._session_factory()
        try:
            rows = (session.query(OAuthAuthTransaction)
                    .filter(OAuthAuthTransaction.expires_at < cutoff)
                    .delete(synchronize_session=False))
            session.commit()
            return int(rows or 0)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _row_to_dict(row) -> dict:
    return {"id": row.id, "rid": row.rid, "provider": row.provider,
            "mode": row.mode, "return_path": row.return_path,
            "redirect_uri": row.redirect_uri,
            "browser_binding_digest": row.browser_binding_digest,
            "browser_binding_key": row.browser_binding_key,
            "initiator_user_id": row.initiator_user_id,
            "initiator_session_digest": row.initiator_session_digest,
            "code_verifier": row.code_verifier,
            "created_at": row.created_at, "expires_at": row.expires_at,
            "consumed_at": row.consumed_at}
