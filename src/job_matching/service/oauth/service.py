# -*- coding: utf-8 -*-
"""OAuthService：统一 OAuth 业务编排（Phase8-A / M4-M5）。

链路（登录）：
  start_authorization -> 授权事务 + 浏览器绑定 Cookie -> 浏览器跳第三方
  -> handle_callback（state/TTL/一次性消费/绑定校验 -> code 换身份）
  -> 事务内 resolve_or_create_user -> 短时一次性票据（HttpOnly Cookie）
  -> 302 前端 /#/oauth/complete -> exchange_login_ticket（原子消费票据）
  -> 复用 AccountService.create_session() 签发**全新**本站会话（防会话固定）

链路（绑定）：
  start_authorization(mode=bind, 已登录) -> 记录发起用户与会话摘要
  -> handle_callback -> 票据（payload=身份快照 + 会话摘要）
  -> exchange_login_ticket（当前会话必须仍是发起会话，否则 OAUTH_SESSION_CHANGED）
  -> bind_identity（冲突显式 409）

安全纪律：
  * code/state/ticket/Provider Token 绝不进 URL（重定向剥离）与日志；
  * 消费全部原子（UPDATE ... WHERE consumed_at IS NULL）；
  * 票据错误消息固定，不泄露用户 ID；
  * 日志只记 request_id/provider/flow/outcome/reason/duration 等白名单字段。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from ..accounts import AccountService
from ..errors import ServiceError
from ..logging_utils import get_service_logger
from .config import OAuthSettings
from .exceptions import (AccessDenied, BindRequiresAuth, InvalidRedirect,
                         InvalidState, ProviderHttpError, ProviderProtocolError,
                         ProviderTimeout, ProviderUnavailable, SessionChanged,
                         TokenExchangeFailed)
from .identity_service import OAuthIdentityService
from .registry import OAuthProviderRegistry
from .schemas import OAuthIdentity
from .security import (clear_binding_cookie, clear_ticket_cookie, digest,
                       is_trusted_frontend_origin, new_binding_secret, new_rid,
                       new_state, pkce_challenge_s256, pkce_verifier,
                       sanitize_return_path, set_binding_cookie,
                       set_ticket_cookie)
from .ticket_store import OAuthTicketStore
from .transaction_store import OAuthTransactionStore

log = get_service_logger("job_matching.service.oauth")

PROVIDER_ERROR_REDIRECT_DEFAULT = "/#/oauth/complete"


class OAuthService:
    """统一 OAuth 编排（依赖注入：settings/registry/http/accounts/stores/clock）。"""

    def __init__(self, *, settings: OAuthSettings,
                 registry: OAuthProviderRegistry, http,
                 accounts: AccountService,
                 identities: OAuthIdentityService | None = None,
                 transactions: OAuthTransactionStore | None = None,
                 tickets: OAuthTicketStore | None = None,
                 clock: Callable[[], datetime] = None,
                 random_source=None):
        self.settings = settings
        self.registry = registry
        self._http = http
        self.accounts = accounts
        self.identities = identities or OAuthIdentityService()
        self.transactions = transactions or OAuthTransactionStore()
        self.tickets = tickets or OAuthTicketStore()
        self._clock = clock or (lambda: datetime.utcnow())
        self._random_source = random_source

    # ================================================================ 状态
    def list_provider_status(self) -> list[dict]:
        """平台状态（disabled / configured_pending_verification / available）。"""
        return self.registry.describe_all()

    # ================================================================ 发起授权
    def start_authorization(self, *, provider: str, mode: str = "login",
                            return_path: str | None = None,
                            user: dict | None = None,
                            bearer_token: str | None = None) -> dict:
        t0 = time.monotonic()
        try:
            if mode not in ("login", "bind"):
                raise ServiceError("INVALID_REQUEST", "mode 只允许 login / bind")
            prov = self.registry.get(provider)     # 未配置/已禁用 -> OAUTH_* 错误
            path = sanitize_return_path(return_path)
            redirect_uri = self.settings.callback_url(prov.provider_id)
            if not redirect_uri:
                raise ServiceError("OAUTH_PROVIDER_NOT_CONFIGURED",
                                   "回调地址不可解析（缺 public_base_url）")

            initiator_user_id = None
            initiator_session_digest = None
            if mode == "bind":
                if not user or not bearer_token:
                    raise BindRequiresAuth("绑定第三方账号需要先登录本站")
                initiator_user_id = user["id"]
                initiator_session_digest = AccountService.session_fingerprint(bearer_token)

            state = new_state(self._random_source)
            binding_secret = new_binding_secret(self._random_source)
            rid = new_rid()
            code_verifier = None
            code_challenge = None
            if getattr(prov, "supports_pkce", False):
                # 仅在 Provider 官方契约支持时启用 PKCE（S256）
                code_verifier = pkce_verifier(self._random_source)
                code_challenge = pkce_challenge_s256(code_verifier)

            auth_url = prov.build_authorization_url(
                state=state, redirect_uri=redirect_uri,
                code_challenge=code_challenge)

            tx = self.transactions.create(
                rid=rid, provider=prov.provider_id, mode=mode, state=state,
                browser_binding_digest=digest(binding_secret),
                browser_binding_key=rid,
                redirect_uri=redirect_uri, return_path=path,
                initiator_user_id=initiator_user_id,
                initiator_session_digest=initiator_session_digest,
                code_verifier=code_verifier,
                ttl_seconds=self.settings.state_ttl_seconds)
            self.transactions.cleanup(older_than_seconds=3600)
            self._log("oauth_start", provider=prov.provider_id, flow=mode,
                      outcome="OK", t0=t0)
            return {
                "authorization_url": auth_url,
                "expires_in": int(self.settings.state_ttl_seconds),
                "rid": rid,
                "mode": mode,
                "return_path": path,
                # 浏览器绑定凭据：只进 HttpOnly Cookie（由路由层设置），绝不进响应体
                "browser_binding_secret": binding_secret,
                "transaction_id": tx["id"],
            }
        except ServiceError as e:
            self._log("oauth_start", provider=str(provider), flow=str(mode),
                      outcome="ERR", reason=e.code, t0=t0)
            raise

    # ================================================================ 回调
    def handle_callback(self, *, provider: str, code: str | None = None,
                        state: str | None = None,
                        error: str | None = None,
                        error_description: str | None = None,
                        cookies: dict | None = None) -> dict:
        """Provider 回调处理：校验 -> 换身份 -> 签发票据 -> 返回重定向指令。"""
        t0 = time.monotonic()
        cookies = dict(cookies or {})
        rid = ""
        mode = "login"
        try:
            prov = self.registry.get(provider)
            pid = prov.provider_id

            # 平台侧错误（用户取消/拒绝）：先消费事务防重放，再给明确错误
            if error:
                if not state:
                    raise InvalidState("回调缺少 state")
                tx_err = self.transactions.consume(state=state, provider=pid)
                rid, mode = tx_err["rid"], tx_err["mode"]
                raise AccessDenied(
                    "用户在第三方平台取消或拒绝授权",
                    {"provider_error": str(error)[:64],
                     "error_description": str(error_description or "")[:120]})

            if not code:
                raise InvalidState("回调缺少 code")
            if not state:
                raise InvalidState("回调缺少 state")

            tx = self.transactions.consume(state=state, provider=pid)
            rid, mode = tx["rid"], tx["mode"]

            # 浏览器绑定校验（跨浏览器/跨标签窃取事务 -> 拒绝）
            binding_cookie = cookies.get(f"jm_oauth_bb_{rid}") or ""
            if not binding_cookie or digest(binding_cookie) != tx["browser_binding_digest"]:
                raise InvalidState("浏览器绑定校验失败（授权事务与浏览器不匹配）",
                                   {"rid": rid})

            # code 换 token（单次、无重试）
            try:
                token = prov.exchange_code(
                    code=code, redirect_uri=tx["redirect_uri"],
                    code_verifier=(tx["code_verifier"]
                                   if getattr(prov, "supports_pkce", False) else None))
            except (ProviderTimeout, ProviderHttpError) as e:
                raise ProviderUnavailable(f"第三方平台暂不可用：{type(e).__name__}",
                                          {"provider": pid}) from e
            except ProviderProtocolError as e:
                raise TokenExchangeFailed("第三方平台响应格式非法",
                                          {"provider": pid}) from e

            identity = prov.get_identity(token)
            if not isinstance(identity, OAuthIdentity) or not identity.subject:
                raise ServiceError("OAUTH_INVALID_IDENTITY",
                                   "第三方平台未返回可用的稳定身份标识")

            if mode == "login":
                resolved = self.identities.resolve_or_create_user(identity)
                ticket = self.tickets.issue(
                    mode="login", user_id=resolved["user_id"],
                    browser_binding_digest=tx["browser_binding_digest"],
                    browser_binding_key=rid,
                    payload={"identity_id": resolved["identity_id"],
                             "created": resolved["created"]},
                    ttl_seconds=self.settings.ticket_ttl_seconds,
                    random_source=self._random_source)
            else:
                if not tx["initiator_user_id"]:
                    raise BindRequiresAuth("绑定事务缺少发起用户，拒绝继续")
                ticket = self.tickets.issue(
                    mode="bind", user_id=tx["initiator_user_id"],
                    browser_binding_digest=tx["browser_binding_digest"],
                    browser_binding_key=rid,
                    payload={"identity": identity.to_dict(),
                             "session_digest": tx["initiator_session_digest"]},
                    ttl_seconds=self.settings.ticket_ttl_seconds,
                    random_source=self._random_source)

            self._log("oauth_callback", provider=pid, flow=mode, outcome="OK", t0=t0)
            return {
                "rid": rid,
                "mode": mode,
                "return_path": tx["return_path"],
                "ticket": ticket,          # 只进 HttpOnly Cookie，绝不进 URL/响应体
                "browser_binding_secret": binding_cookie,
            }
        except ServiceError as e:
            self._log("oauth_callback", provider=str(provider), flow=str(mode),
                      outcome="ERR", reason=e.code, t0=t0, rid=rid)
            raise

    # ================================================================ 票据交换
    def exchange_login_ticket(self, *, rid: str | None, ticket: str | None,
                              browser_binding_secret: str | None,
                              user: dict | None = None,
                              bearer_token: str | None = None,
                              origin: str | None = None) -> dict:
        """原子消费一次性票据 -> 签发本站会话（login）或完成绑定（bind）。"""
        t0 = time.monotonic()
        try:
            # CSRF：浏览器发起的交换必须来自可信前端 Origin
            if origin and not is_trusted_frontend_origin(
                    origin, self.settings.frontend_origins):
                raise InvalidRedirect("请求 Origin 不在可信白名单",
                                      {"field": "origin"})
            if not ticket:
                raise ServiceError("OAUTH_TICKET_EXPIRED", "票据无效或已过期")
            data = self.tickets.consume(
                ticket=ticket,
                browser_binding_digest=(digest(browser_binding_secret)
                                        if browser_binding_secret else None),
                browser_binding_key=rid or None)
            mode = data["mode"]

            if mode == "login":
                token, meta = self.accounts.create_session(user_id=data["user_id"])
                u = self.accounts.resolve_token(token)   # 安全投影（无 password_hash）
                self._log("oauth_exchange", provider="login", flow=mode,
                          outcome="OK", t0=t0)
                return {"mode": "login", "token": token, "user": u, **meta}

            # bind 模式：发起会话与完成会话必须一致（防登录态切换后错绑）
            if not user or not bearer_token:
                raise BindRequiresAuth("完成绑定需要本站登录态")
            payload = data.get("payload") or {}
            expected_digest = payload.get("session_digest") or ""
            if (str(user.get("id")) != str(data["user_id"])
                    or digest(bearer_token) != expected_digest):
                raise SessionChanged("发起绑定与完成绑定的会话不一致，绑定已取消")
            identity = OAuthIdentity.from_dict(payload.get("identity") or {})
            bound = self.identities.bind_identity(user_id=user["id"], identity=identity)
            self._log("oauth_exchange", provider=identity.provider, flow=mode,
                      outcome="OK", t0=t0)
            return {"mode": "bind", "bound": True,
                    "identity": bound["identity"],
                    "already_bound": bound["already_bound"]}
        except ServiceError as e:
            self._log("oauth_exchange", provider="-", flow="exchange",
                      outcome="ERR", reason=e.code, t0=t0)
            raise

    # ================================================================ 绑定管理
    def list_identities(self, user: dict) -> dict:
        return self.identities.list_identities(user["id"])

    def unbind_identity(self, *, user: dict, provider: str | None = None,
                        identity_id: str | None = None,
                        bearer_token: str | None = None) -> dict:
        """解绑（安全敏感：要求近期重新认证的会话，不依赖长期旧登录态）。"""
        # 近期重认证窗口（分钟）：解绑前会话必须是新近签发的
        self.accounts.require_recent_session(bearer_token or "",
                                             window_minutes=30)
        return self.identities.unbind_identity(user_id=user["id"],
                                               provider=provider,
                                               identity_id=identity_id)

    # ================================================================ Cookie 指令
    def apply_start_cookies(self, response, start_result: dict) -> None:
        set_binding_cookie(
            response, start_result["rid"], start_result["browser_binding_secret"],
            max_age=self.settings.state_ttl_seconds,
            secure=self.settings.cookie_secure)

    def apply_callback_cookies(self, response, callback_result: dict) -> None:
        set_ticket_cookie(
            response, callback_result["rid"], callback_result["ticket"],
            max_age=self.settings.ticket_ttl_seconds,
            secure=self.settings.cookie_secure)

    def apply_exchange_cleanup(self, response, rid: str | None) -> None:
        if rid:
            clear_binding_cookie(response, rid, secure=self.settings.cookie_secure)
            clear_ticket_cookie(response, rid, secure=self.settings.cookie_secure)

    # ================================================================ 辅助
    def completion_redirect(self, *, rid: str, mode: str, status: str,
                            reason: str | None = None,
                            return_path: str | None = None) -> str:
        """前端完成页地址（**只**携带非秘密信息：rid/mode/status/reason）。"""
        base = (self.settings.frontend_origins[0] if self.settings.frontend_origins
                else "")
        if not base:
            raise InvalidRedirect("缺少可信前端 Origin 配置")
        params = [f"rid={rid}", f"mode={mode}", f"status={status}"]
        if reason:
            params.append(f"reason={reason}")
        if return_path:
            params.append(f"return_path={_urlquote(return_path)}")
        return f"{base}{PROVIDER_ERROR_REDIRECT_DEFAULT}?" + "&".join(params)

    def _log(self, event: str, *, provider: str, flow: str, outcome: str,
             t0: float, reason: str = "", rid: str = "") -> None:
        """安全日志：只记白名单元信息（无 code/state/token/票据/Secret）。"""
        log.info("oauth_event event=%s provider=%s flow=%s outcome=%s reason=%s "
                 "duration_ms=%.1f rid=%s",
                 event, provider, flow, outcome, reason or "-",
                 (time.monotonic() - t0) * 1000.0, rid or "-")


def _urlquote(value: str) -> str:
    from urllib.parse import quote
    return quote(str(value), safe="/._~-")
