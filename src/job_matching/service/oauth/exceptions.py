# -*- coding: utf-8 -*-
"""OAuth 错误类型：全部挂在 service/errors.py 已登记的稳定错误码上。

纪律：
  * 禁止抛出未登记错误码（ServiceError 构造时会强校验，重现
    MODEL_ARTIFACT_TAMPERED 类问题在测试阶段即被拦下）；
  * Provider 层的网络/协议异常（ProviderHttpError 等）**不是** ServiceError，
    由 service 层映射成 OAUTH_PROVIDER_UNAVAILABLE / OAUTH_TOKEN_EXCHANGE_FAILED，
    保证"外部 Provider 异常"绝不伪装成"密码错误"之类的本站错误。
"""
from __future__ import annotations

from ..errors import ServiceError


class OAuthServiceError(ServiceError):
    """OAuth 业务错误基类（错误码固定，调用方不得随意改码）。"""

    default_code = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: dict | None = None,
                 code: str | None = None):
        super().__init__(code or self.default_code, message, detail)


class ProviderNotConfigured(OAuthServiceError):
    default_code = "OAUTH_PROVIDER_NOT_CONFIGURED"


class ProviderDisabled(OAuthServiceError):
    default_code = "OAUTH_PROVIDER_DISABLED"


class InvalidState(OAuthServiceError):
    default_code = "OAUTH_INVALID_STATE"


class StateExpired(OAuthServiceError):
    default_code = "OAUTH_STATE_EXPIRED"


class CallbackReplay(OAuthServiceError):
    default_code = "OAUTH_CALLBACK_REPLAY"


class AccessDenied(OAuthServiceError):
    default_code = "OAUTH_ACCESS_DENIED"


class TokenExchangeFailed(OAuthServiceError):
    default_code = "OAUTH_TOKEN_EXCHANGE_FAILED"


class ProviderUnavailable(OAuthServiceError):
    default_code = "OAUTH_PROVIDER_UNAVAILABLE"


class InvalidIdentity(OAuthServiceError):
    default_code = "OAUTH_INVALID_IDENTITY"


class IdentityConflict(OAuthServiceError):
    default_code = "OAUTH_IDENTITY_CONFLICT"


class BindRequiresAuth(OAuthServiceError):
    default_code = "OAUTH_BIND_REQUIRES_AUTH"


class SessionChanged(OAuthServiceError):
    default_code = "OAUTH_SESSION_CHANGED"


class TicketExpired(OAuthServiceError):
    default_code = "OAUTH_TICKET_EXPIRED"


class TicketAlreadyUsed(OAuthServiceError):
    default_code = "OAUTH_TICKET_ALREADY_USED"


class LastLoginMethod(OAuthServiceError):
    default_code = "OAUTH_LAST_LOGIN_METHOD"


class InvalidRedirect(OAuthServiceError):
    default_code = "OAUTH_INVALID_REDIRECT"


# ---------------------------------------------------------------- Provider 层异常
class ProviderHttpError(Exception):
    """Provider HTTP 层异常（状态码异常 / 响应体超限）。不直接对外。"""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ProviderTimeout(Exception):
    """Provider 请求超时（连接/读取/总预算）。"""


class ProviderProtocolError(Exception):
    """Provider 响应格式非法（非 JSON、字段缺失、JSONP 无法安全解析等）。"""
