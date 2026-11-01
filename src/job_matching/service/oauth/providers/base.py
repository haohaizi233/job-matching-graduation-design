# -*- coding: utf-8 -*-
"""OAuthProvider 统一协议与适配器基类（Phase8-A / M1-M2）。

约束（业务层反依赖检查）：
  * 业务层（service/identity_*）**不得**出现 `if provider == "wechat"` 之类分支；
  * 业务层不解析 QQ JSONP、不认微信 openid 字段名、不知道微博 UID 来源；
  * 平台差异（端点、参数、响应格式、错误码、字段名）全部封装在 providers/ 内；
  * 端点是**受控常量**，禁止请求侧传入 URL 动态创建 Provider（SSRF 防线）；
  * PKCE 是否启用以平台官方契约为准：三家网站授权流程的支持情况未获官方明确
    文档确认前一律 `supports_pkce = False`（登记 PROVIDER_VERIFICATION_PENDING），
    不假设标准 PKCE 参数会被接受。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...errors import ServiceError
from ..http_client import OAuthHttpClient, redact_url
from ..schemas import OAuthIdentity, OAuthTokenResponse


@runtime_checkable
class OAuthProvider(Protocol):
    """第三方授权提供方统一协议（同步实现，与既有同步服务层一致）。"""

    provider_id: str
    label: str
    supports_pkce: bool

    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        """构造授权入口 URL（state/redirect_uri 编码由实现负责）。"""
        ...

    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        """授权码换 Token（**单次**、无重试；code 一旦消费不可重放）。"""
        ...

    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        """取回并映射统一身份（资料缺失时不得伪造身份关联）。"""
        ...


class BaseOAuthProvider:
    """适配器公共骨架：client_id/Secret、HTTP 客户端、错误映射与安全解析辅助。"""

    provider_id: str = ""
    label: str = ""
    supports_pkce: bool = False          # 平台契约未确认前一律 False
    identity_without_profile_allowed: bool = True   # UID/OpenID 已核验即可登录
    scope: str = ""

    def __init__(self, *, client_id: str, client_secret: str,
                 http: OAuthHttpClient, scope: str | None = None):
        if not client_id or not client_secret:
            raise ServiceError("OAUTH_PROVIDER_NOT_CONFIGURED",
                               f"{self.provider_id} 缺少 client_id/client_secret")
        self.client_id = client_id
        self._client_secret = client_secret
        self._http = http
        if scope is not None:
            self.scope = scope

    # ---------------------------------------------------------- 构造
    @classmethod
    def from_config(cls, cfg, http: OAuthHttpClient) -> "BaseOAuthProvider":
        """从 OAuthProviderConfig 构造（配置唯一来源，禁止散落构造参数）。"""
        return cls(client_id=cfg.client_id, client_secret=cfg.client_secret, http=http)

    # ---------------------------------------------------------- 协议默认实现
    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        raise NotImplementedError

    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        raise NotImplementedError

    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        raise NotImplementedError

    # ---------------------------------------------------------- 辅助
    def _require(self, value, field: str, url: str):
        if value is None or str(value).strip() == "":
            from .exceptions import ProviderProtocolError
            raise ProviderProtocolError(
                f"{self.provider_id} 响应缺少必要字段 {field} @ {redact_url(url)}")
        return value
