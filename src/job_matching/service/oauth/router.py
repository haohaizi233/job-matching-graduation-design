# -*- coding: utf-8 -*-
"""OAuth HTTP 路由（Phase8-A / M6）：/api/v1/auth/oauth/*

  GET    /api/v1/auth/oauth/providers                  平台状态（不返回 Secret）
  POST   /api/v1/auth/oauth/start                      发起授权（login/bind）
  GET    /api/v1/auth/oauth/{provider}/callback        Provider 回调（302 到前端完成页）
  POST   /api/v1/auth/oauth/exchange                   一次性票据交换本站会话
  GET    /api/v1/auth/oauth/identities                 已绑定身份列表
  DELETE /api/v1/auth/oauth/identities/{identity_ref}  解绑（identity_id 或 provider）
  POST   /api/v1/auth/oauth/set-password               纯 OAuth 账号补设本站密码

契约纪律：
  * 成功/失败结构沿用项目统一信封与错误体（errors.py）；
  * callback 错误路径同样只跳**固定可信**前端地址，绝不把 code/state/token
    传播到前端 URL；
  * exchange 成功返回结构与 /auth/login 的 data 一致（token/user/token_type/
    expires_at/session_id），复用既有 Bearer 会话，不自创 JWT；
  * 限流：start / callback 失败 / exchange 分别计数（单进程内存实现，
    多实例部署需网关侧再加一层）。

注：本文件**不**使用 `from __future__ import annotations` —— 请求模型定义在工厂
函数内，FastAPI 需要在定义时解析注解（字符串注解会解析失败）。
"""

import os
import time
from typing import Any, Callable

from ..errors import ServiceError

# 限流参数（每客户端每分钟）。上限可经环境变量覆盖（与 JM_REGISTER_RATE_LIMIT 同口径）：
# E2E 隔离环境（tests/e2e/serve_backend.py）放宽到不阻塞套件的量级，
# 限流代码路径保持生效；生产默认值不变。
_START_LIMIT = max(1, int(os.environ.get("JM_OAUTH_START_RATE_LIMIT", "30")))
_CALLBACK_FAIL_LIMIT = max(1, int(os.environ.get("JM_OAUTH_CALLBACK_RATE_LIMIT", "30")))
_EXCHANGE_LIMIT = max(1, int(os.environ.get("JM_OAUTH_EXCHANGE_RATE_LIMIT", "60")))


def create_oauth_router(*, get_biz: Callable, current_user: Callable,
                        bearer_token: Callable):
    """构造 OAuth 路由（依赖由 business_api 注入，保持单一 app / 单一依赖体系）。"""
    from fastapi import APIRouter, Body, Depends, Request, Response
    from fastapi.responses import RedirectResponse
    from pydantic import BaseModel, Field as PField

    from ..api import _envelope

    router = APIRouter(prefix="/api/v1/auth/oauth", tags=["oauth"])

    # ---------------------------------------------------------- 请求模型
    class OAuthStartIn(BaseModel):
        provider: str = PField(..., min_length=1, max_length=32)
        mode: str = PField("login", description="login | bind")
        return_path: str | None = PField(None, max_length=256)

    class OAuthExchangeIn(BaseModel):
        rid: str | None = PField(None, max_length=32)

    class SetPasswordIn(BaseModel):
        new_password: str = PField(..., min_length=1, max_length=128)

    # ---------------------------------------------------------- 限流（内存固定窗口）
    buckets: dict[str, list[float]] = {}

    def _rate_limited(key: str, limit: int, now_ts: float) -> bool:
        if limit <= 0:
            return False
        if len(buckets) > 10000:   # pragma: no cover - 防内存膨胀
            buckets.clear()
        window = buckets.setdefault(key, [])
        cutoff = now_ts - 60.0
        window[:] = [t for t in window if t > cutoff]
        if len(window) >= int(limit):
            return True
        window.append(now_ts)
        return False

    def _client(request: Request) -> str:
        return (request.client.host if request.client else "unknown") or "unknown"

    def _oauth(biz):
        svc = getattr(biz, "oauth", None)
        if svc is None:
            raise ServiceError("OAUTH_PROVIDER_NOT_CONFIGURED",
                               "OAuth 服务未装配（当前构建未启用 OAuth）")
        return svc

    def _completion_redirect(svc, *, rid: str, mode: str, status: str,
                             reason: str | None = None,
                             return_path: str | None = None) -> RedirectResponse:
        url = svc.completion_redirect(rid=rid or "-", mode=mode, status=status,
                                      reason=reason, return_path=return_path)
        resp = RedirectResponse(url=url, status_code=302)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ================================================================ 状态
    @router.get("/providers")
    def providers(request: Request, biz=Depends(get_biz)):
        svc = _oauth(biz)
        return _envelope(request.state.request_id,
                         {"providers": svc.list_provider_status()})

    # ================================================================ 发起
    @router.post("/start")
    def start(body: OAuthStartIn, request: Request, response: Response,
              biz=Depends(get_biz)):
        svc = _oauth(biz)
        client = _client(request)
        if _rate_limited(f"oauth_start:{client}", _START_LIMIT, time.monotonic()):
            raise ServiceError("RATE_LIMITED",
                               f"OAuth 发起频率超过限制（{_START_LIMIT}/分钟）")
        token = bearer_token(request)
        user = current_user(request, biz) if token else None
        out = svc.start_authorization(
            provider=body.provider, mode=body.mode,
            return_path=body.return_path, user=user, bearer_token=token or None)
        svc.apply_start_cookies(response, out)
        return _envelope(request.state.request_id, {
            "authorization_url": out["authorization_url"],
            "expires_in": out["expires_in"],
            "rid": out["rid"],
            "mode": out["mode"],
            "return_path": out["return_path"],
        })

    # ================================================================ 回调
    @router.get("/{provider}/callback")
    def callback(provider: str, request: Request):
        biz = request.app.state.business
        svc = _oauth(biz)
        params = request.query_params
        rid = "-"
        mode = "login"
        try:
            out = svc.handle_callback(
                provider=provider,
                code=params.get("code"), state=params.get("state"),
                error=params.get("error"),
                error_description=params.get("error_description"),
                cookies=dict(request.cookies))
            rid, mode = out["rid"], out["mode"]
            resp = _completion_redirect(
                svc, rid=rid, mode=mode, status="ok",
                return_path=out["return_path"])
            svc.apply_callback_cookies(resp, out)
            return resp
        except ServiceError as e:
            client = _client(request)
            if _rate_limited(f"oauth_cb:{client}", _CALLBACK_FAIL_LIMIT,
                             time.monotonic()):
                e = ServiceError("RATE_LIMITED", "OAuth 回调失败次数过多")
            # 错误路径同样只跳固定可信地址；不传播 code/state/Token
            resp = _completion_redirect(svc, rid=rid, mode=mode, status="error",
                                        reason=e.code)
            return resp

    # ================================================================ 票据交换
    @router.post("/exchange")
    def exchange(body: OAuthExchangeIn, request: Request, response: Response,
                 biz=Depends(get_biz)):
        svc = _oauth(biz)
        client = _client(request)
        if _rate_limited(f"oauth_ex:{client}", _EXCHANGE_LIMIT, time.monotonic()):
            raise ServiceError("RATE_LIMITED",
                               f"票据交换频率超过限制（{_EXCHANGE_LIMIT}/分钟）")
        rid = (body.rid or "").strip() or None
        ticket = None
        binding_secret = None
        if rid:
            from .security import binding_cookie_name, ticket_cookie_name
            try:
                ticket = request.cookies.get(ticket_cookie_name(rid)) or None
                binding_secret = request.cookies.get(binding_cookie_name(rid)) or None
            except Exception:  # noqa: BLE001 - rid 非法时按缺票据处理
                ticket, binding_secret = None, None
        token = bearer_token(request)
        user = current_user(request, biz) if token else None
        out = svc.exchange_login_ticket(
            rid=rid, ticket=ticket, browser_binding_secret=binding_secret,
            user=user, bearer_token=token or None,
            origin=request.headers.get("origin"))
        svc.apply_exchange_cleanup(response, rid)
        if out.get("mode") == "login":
            # 结构与 /auth/login 的 data 完全一致（前端 useAuth 复用同一 LoginResult）
            return _envelope(request.state.request_id, {
                "token": out["token"], "user": out["user"],
                "token_type": out["token_type"], "expires_at": out["expires_at"],
                "session_id": out["session_id"]})
        return _envelope(request.state.request_id, {
            "bound": out["bound"], "identity": out["identity"],
            "already_bound": out["already_bound"]})

    # ================================================================ 绑定管理
    @router.get("/identities")
    def identities(request: Request, biz=Depends(get_biz),
                   user: dict = Depends(current_user)):
        svc = _oauth(biz)
        return _envelope(request.state.request_id, svc.list_identities(user))

    @router.delete("/identities/{identity_ref}")
    def unbind(identity_ref: str, request: Request, response: Response,
               biz=Depends(get_biz), user: dict = Depends(current_user)):
        svc = _oauth(biz)
        token = bearer_token(request)
        ref = str(identity_ref or "").strip()
        known_providers = {p["id"] for p in svc.list_provider_status()}
        kwargs = ({"provider": ref} if ref in known_providers
                  else {"identity_id": ref})
        out = svc.unbind_identity(user=user, bearer_token=token, **kwargs)
        return _envelope(request.state.request_id, out)

    # ============================================== 纯 OAuth 账号补设密码
    @router.post("/set-password")
    def set_password(body: SetPasswordIn, request: Request,
                     biz=Depends(get_biz), user: dict = Depends(current_user)):
        out = biz.accounts.set_password(user_id=user["id"],
                                        new_password=body.new_password,
                                        keep_token=bearer_token(request))
        return _envelope(request.state.request_id, out)

    return router
