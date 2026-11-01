# -*- coding: utf-8 -*-
"""OAuth 安全原语（Phase8-A / M5）：state、摘要、浏览器绑定 Cookie、重定向白名单、PKCE。

设计要点：
  * state / 一次性票据 / 浏览器绑定凭据全部来自 CSPRNG（secrets），
    服务端只落 SHA-256 摘要；明文只在内存与 HttpOnly Cookie 中流转；
  * 浏览器绑定按**事务隔离**（每笔授权独立 Cookie 名 jm_oauth_bb_<rid>），
    多标签页并发授权互不覆盖；
  * Cookie 语义：HttpOnly + SameSite=Lax + 受限 Path（/api/v1/auth/oauth），
    HTTPS 部署时 Secure=True。OAuth 回调是第三方站点发起的**顶级 GET 导航**，
    SameSite=Lax 恰好允许携带既有绑定 Cookie —— 这是浏览器绑定可行的前提；
  * return_path 只允许站内白名单路由（标准解析 + 解码检查，不是 startswith 草率匹配），
    协议相对 URL、反斜杠混淆、编码外跳一律 OAUTH_INVALID_REDIRECT；
  * PKCE（S256）辅助函数齐备，但是否启用由 Provider 官方契约决定
    （微信/QQ/微博网站授权流程的支持情况登记为 PROVIDER_VERIFICATION_PENDING）。
"""
from __future__ import annotations

import hashlib
import re
import secrets
from base64 import urlsafe_b64encode
from urllib.parse import unquote, urlsplit

from .exceptions import InvalidRedirect

# ---- Cookie 名称（受限 Path；名称本身不含敏感信息）----
# 绑定凭据与票据 Cookie 均按**事务 rid** 隔离（jm_oauth_bb_<rid> / jm_oauth_ticket_<rid>），
# 多标签页并发授权互不覆盖单个全局 Cookie。
BINDING_COOKIE_PREFIX = "jm_oauth_bb_"
TICKET_COOKIE_PREFIX = "jm_oauth_ticket_"
OAUTH_COOKIE_PATH = "/api/v1/auth/oauth"

# 票据明文熵：32 字节 = 256 位（≥128 位要求）
TICKET_BYTES = 32
STATE_BYTES = 32
BINDING_BYTES = 32

# return_path 允许的站内路由前缀（Hash 路由的 path 部分）
_ALLOWED_RETURN_PREFIXES = (
    "/dashboard", "/resume", "/profile", "/jobs", "/job/", "/matching",
    "/history", "/feedback", "/settings",
)
_MAX_RETURN_PATH_LEN = 256
_RETURN_RE = re.compile(r"^/[A-Za-z0-9._~/%\-]*$")


# ---------------------------------------------------------------- 随机与摘要
def digest(value: str) -> str:
    """服务端落库口径统一使用 SHA-256 摘要（state / ticket / binding）。"""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def new_state(random_source=None) -> str:
    """授权 state：CSPRNG、不可预测、不接受自定义长度（固定 32 字节）。"""
    if random_source is None:
        return secrets.token_urlsafe(STATE_BYTES)
    return random_source(STATE_BYTES)


def new_binding_secret(random_source=None) -> str:
    """浏览器绑定凭据（每笔授权事务独立）。"""
    if random_source is None:
        return secrets.token_urlsafe(BINDING_BYTES)
    return random_source(BINDING_BYTES)


def new_ticket(random_source=None) -> str:
    """一次性登录票据明文（≥128 位熵；只在 HttpOnly Cookie 中流转一次）。"""
    if random_source is None:
        return secrets.token_urlsafe(TICKET_BYTES)
    return random_source(TICKET_BYTES)


def new_rid() -> str:
    """事务短标识（进 URL 用于前端定位 Cookie 名；**不是**安全凭据）。"""
    return secrets.token_hex(8)


# ---------------------------------------------------------------- PKCE
def pkce_verifier(random_source=None) -> str:
    if random_source is None:
        return secrets.token_urlsafe(64)
    return random_source(64)


def pkce_challenge_s256(verifier: str) -> str:
    raw = hashlib.sha256(verifier.encode("ascii")).digest()
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# ---------------------------------------------------------------- return_path
def sanitize_return_path(raw: str | None) -> str:
    """站内 return_path 白名单校验（不合法一律 OAUTH_INVALID_REDIRECT）。

    拦截：空值回落默认页；协议相对 URL（//evil）；反斜杠混淆（/\\evil）；
    百分号编码的外跳（/%2F%2Fevil、/%5C）；控制字符；超长；任意主机；
    仅允许 Hash 路由内的白名单业务页。
    """
    if raw is None:
        return "/dashboard"
    path = str(raw).strip()
    if not path:
        return "/dashboard"
    if len(path) > _MAX_RETURN_PATH_LEN:
        raise InvalidRedirect("return_path 过长", {"field": "return_path"})
    if "\\" in path or "\x00" in path or any(ord(c) < 0x20 for c in path):
        raise InvalidRedirect("return_path 含非法字符", {"field": "return_path"})
    decoded = unquote(path)
    if "\\" in decoded or "\x00" in decoded or "://" in decoded:
        raise InvalidRedirect("return_path 解码后含非法跳转", {"field": "return_path"})
    if not decoded.startswith("/") or decoded.startswith("//"):
        raise InvalidRedirect("return_path 必须是站内绝对路径", {"field": "return_path"})
    if not _RETURN_RE.match(decoded):
        raise InvalidRedirect("return_path 含非法字符", {"field": "return_path"})
    # 标准解析：把 path 挂到固定 dummy host 上，host 必须保持不变（防 //evil / @evil）
    parts = urlsplit("https://app.invalid" + decoded)
    if parts.netloc != "app.invalid" or parts.scheme != "https":
        raise InvalidRedirect("return_path 解析出站外地址", {"field": "return_path"})
    normalized = parts.path or "/dashboard"
    segs = normalized.split("/")
    if any(s in ("..", ".") for s in segs):
        raise InvalidRedirect("return_path 含路径穿越片段", {"field": "return_path"})
    if not any(normalized == p.rstrip("/") or normalized.startswith(p)
               for p in _ALLOWED_RETURN_PREFIXES):
        raise InvalidRedirect("return_path 不在允许的站内路由白名单", {"field": "return_path"})
    return normalized


def is_trusted_frontend_origin(origin: str | None, allowed_origins: tuple[str, ...]) -> bool:
    """浏览器 Origin 校验（exchange 等写操作的 CSRF 防线之一）。"""
    if not origin:
        return False
    try:
        o = urlsplit(str(origin).strip().rstrip("/"))
    except ValueError:
        return False
    if not o.scheme or not o.netloc:
        return False
    normalized = f"{o.scheme.lower()}://{o.netloc.lower()}"
    return normalized in {a.lower() for a in allowed_origins}


# ---------------------------------------------------------------- Cookie
def _check_rid(rid: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{8,32}", str(rid or "")):
        raise InvalidRedirect("rid 非法", {"field": "rid"})
    return str(rid)


def binding_cookie_name(rid: str) -> str:
    return BINDING_COOKIE_PREFIX + _check_rid(rid)


def ticket_cookie_name(rid: str) -> str:
    return TICKET_COOKIE_PREFIX + _check_rid(rid)


def _cookie_kwargs(*, max_age: int, secure: bool) -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": bool(secure),
        "path": OAUTH_COOKIE_PATH,
        "max_age": int(max_age),
    }


def set_binding_cookie(response, rid: str, secret: str, *, max_age: int, secure: bool) -> None:
    response.set_cookie(binding_cookie_name(rid), secret, **_cookie_kwargs(
        max_age=max_age, secure=secure))


def clear_binding_cookie(response, rid: str, *, secure: bool) -> None:
    response.delete_cookie(binding_cookie_name(rid), path=OAUTH_COOKIE_PATH,
                           secure=bool(secure), httponly=True, samesite="lax")


def set_ticket_cookie(response, rid: str, value: str, *, max_age: int,
                      secure: bool) -> None:
    response.set_cookie(ticket_cookie_name(rid), value, **_cookie_kwargs(
        max_age=max_age, secure=secure))


def clear_ticket_cookie(response, rid: str, *, secure: bool) -> None:
    response.delete_cookie(ticket_cookie_name(rid), path=OAUTH_COOKIE_PATH,
                           secure=bool(secure), httponly=True, samesite="lax")
