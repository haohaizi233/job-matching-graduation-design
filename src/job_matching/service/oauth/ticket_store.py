# -*- coding: utf-8 -*-
"""一次性登录/绑定票据存储（Phase8-A / M4.3）。

安全语义（逐条对应 M5）：
  * 票据明文 ≥128 位熵（默认 secrets.token_urlsafe(32) = 256 位），**只**经短期
    HttpOnly Cookie 交给同一浏览器，不进 URL、不进 localStorage、不进日志；
  * 库里只存 SHA-256 摘要；TTL 30-60 秒；
  * 原子消费（UPDATE ... WHERE consumed_at IS NULL）：并发双交换只成功一次；
  * 未知/过期票据返回同一错误（OAUTH_TICKET_EXPIRED），**不泄露用户 ID**；
  * 重放（已消费）-> OAUTH_TICKET_ALREADY_USED；
  * 浏览器绑定凭据不匹配 -> 通用票据错误（不提供存在性预言机）；
  * 历史已消费票据定期清理（cleanup）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from ...infra.persistence import OAuthLoginTicket, get_session_factory
from .exceptions import TicketAlreadyUsed, TicketExpired
from .security import digest, new_ticket


def _now() -> datetime:
    return datetime.utcnow()


class OAuthTicketStore:
    """一次性票据存取（依赖注入 session_factory / clock 便于测试）。"""

    def __init__(self, session_factory: Callable | None = None,
                 clock: Callable[[], datetime] = _now):
        self._session_factory = session_factory or get_session_factory()
        self._clock = clock

    # ---------------------------------------------------------- 签发
    def issue(self, *, mode: str, user_id: str,
              browser_binding_digest: str, browser_binding_key: str,
              payload: dict | None = None,
              ttl_seconds: int = 60, random_source=None) -> str:
        """签发票据，返回**明文**（调用方只允许写入 HttpOnly Cookie）。"""
        if mode not in ("login", "bind"):
            raise ValueError(f"未知票据模式: {mode}")
        ticket = new_ticket(random_source)
        now = self._clock()
        session = self._session_factory()
        try:
            row = OAuthLoginTicket(
                ticket_digest=digest(ticket), mode=mode, user_id=user_id,
                browser_binding_digest=browser_binding_digest,
                browser_binding_key=browser_binding_key,
                payload_json=dict(payload) if payload else None,
                created_at=now, expires_at=now + timedelta(seconds=int(ttl_seconds)))
            session.add(row)
            session.commit()
            return ticket
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------------------------------------------------------- 原子消费
    def consume(self, *, ticket: str, browser_binding_digest: str | None = None,
                browser_binding_key: str | None = None) -> dict:
        """消费票据（一次成功）；返回票据负载（mode/user_id/payload）。

        失败一律抛 OAUTH_TICKET_EXPIRED / OAUTH_TICKET_ALREADY_USED，
        消息固定、不携带 user_id（错误票据不得泄露账号信息）。
        """
        if not ticket or not isinstance(ticket, str):
            raise TicketExpired("票据无效或已过期")
        d = digest(ticket)
        now = self._clock()
        session = self._session_factory()
        try:
            row = (session.query(OAuthLoginTicket)
                   .filter(OAuthLoginTicket.ticket_digest == d).first())
            if row is None:
                raise TicketExpired("票据无效或已过期")
            if row.consumed_at is not None:
                raise TicketAlreadyUsed("票据已被消费，拒绝重放")
            if row.expires_at <= now:
                raise TicketExpired("票据无效或已过期")
            if browser_binding_key is not None and \
                    str(browser_binding_key) != str(row.browser_binding_key):
                raise TicketExpired("票据无效或已过期")
            if browser_binding_digest is not None and \
                    str(browser_binding_digest) != str(row.browser_binding_digest):
                raise TicketExpired("票据无效或已过期")
            # 原子消费：并发双交换只允许一个赢家
            updated = (session.query(OAuthLoginTicket)
                       .filter(OAuthLoginTicket.id == row.id,
                               OAuthLoginTicket.consumed_at.is_(None))
                       .update({"consumed_at": now}, synchronize_session=False))
            session.commit()
            if updated != 1:
                raise TicketAlreadyUsed("票据已被并发消费，拒绝重放")
            return {"id": row.id, "mode": row.mode, "user_id": row.user_id,
                    "payload": dict(row.payload_json or {}),
                    "browser_binding_digest": row.browser_binding_digest,
                    "browser_binding_key": row.browser_binding_key,
                    "created_at": row.created_at, "expires_at": row.expires_at}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------------------------------------------------------- 清理
    def cleanup(self, *, older_than_seconds: int = 3600) -> int:
        """删除已消费/过期超过窗口的票据（防表膨胀，票据本就短命）。"""
        cutoff = self._clock() - timedelta(seconds=int(older_than_seconds))
        session = self._session_factory()
        try:
            rows = (session.query(OAuthLoginTicket)
                    .filter(OAuthLoginTicket.expires_at < cutoff)
                    .delete(synchronize_session=False))
            session.commit()
            return int(rows or 0)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
