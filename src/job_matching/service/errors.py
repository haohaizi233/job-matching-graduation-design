# -*- coding: utf-8 -*-
"""Phase5-1 业务服务错误体系（模块 E 错误码的唯一事实来源）。

约束：
  * 每个错误都有稳定 error_code，API 层原样返回，不吞错、不伪装成功；
  * message 不携带原文 PII（由调用方保证，日志层另有脱敏兜底）。
"""
from __future__ import annotations

import re

from ..core import ROOT

# ---- 错误码登记表（code -> (HTTP 状态, 含义)）----
ERROR_CODES: dict[str, tuple[int, str]] = {
    "INVALID_REQUEST": (422, "请求字段缺失或取值非法"),
    "UNSUPPORTED_FORMAT": (415, "简历/岗位文件格式不支持"),
    "EMPTY_INPUT": (400, "输入正文为空"),
    "OCR_REQUIRED": (422, "扫描版或无文本层 PDF，需要 OCR 预处理"),
    "PARSE_FAILED": (422, "文档解析失败"),
    "PAYLOAD_TOO_LARGE": (413, "请求体/上传文件/解析文本超过大小上限"),
    "RATE_LIMITED": (429, "请求频率超过限制"),
    "BATCH_LIMIT_EXCEEDED": (400, "批量条数超过上限"),
    "INFERENCE_TIMEOUT": (408, "推理超过时间预算"),
    "MODEL_MISSING": (503, "模型权重或清单缺失"),
    "MODEL_CORRUPT": (503, "模型文件损坏或加载失败"),
    "MODEL_ARTIFACT_TAMPERED": (503, "模型产物哈希校验失败或产物缺失，拒绝加载（可信哈希门禁 P7-5）"),
    "MODEL_ENV_INCOMPATIBLE": (503, "模型与当前运行环境不兼容（历史 checkpoint 依赖旧版依赖栈）"),
    "MODEL_INAPPLICABLE": (422, "当前业务输入无法合法构建该模型所需特征"),
    "MODEL_FORMAL_USE_FORBIDDEN": (422, "该模型未通过中文正式用途验证，拒绝正式模式"),
    "FUTURE_MODEL_UNAVAILABLE": (503, "future_verified 模式暂无已验证中文模型"),
    "LEAKAGE_GUARD": (422, "输入携带目标值/派生评分等禁用字段"),
    "INTERNAL_ERROR": (500, "服务内部错误"),
    # ---- Phase5-2 业务后端（Batch 2 认证与权限 / Batch 3-5 业务资源）----
    "AUTH_REQUIRED": (401, "未认证：缺少或非法的访问令牌"),
    "AUTH_INVALID_CREDENTIALS": (401, "认证失败，凭证无效"),
    "AUTH_TOKEN_EXPIRED": (401, "访问令牌已过期"),
    "AUTH_ACCOUNT_LOCKED": (423, "登录失败次数过多，账号已临时锁定"),
    "FORBIDDEN": (403, "权限不足或资源不属于当前用户"),
    "NOT_FOUND": (404, "资源不存在"),
    "CONFLICT": (409, "资源冲突（重复创建/并发修改）"),
    # ---- Phase8-A 统一 OAuth 2.0（错误码只做加法，不动既有映射）----
    # HTTP 状态纪律：400=非法 OAuth 请求；401=需要本站身份验证；403=操作被禁止；
    # 409=身份/会话冲突；429=限流（复用 RATE_LIMITED）；502=外部 Provider 响应异常；
    # 503=Provider 未配置或服务不可用。
    "OAUTH_PROVIDER_NOT_CONFIGURED": (503, "该第三方平台尚未配置（缺 AppID/AppSecret/回调地址）"),
    "OAUTH_PROVIDER_DISABLED": (503, "该第三方平台已显式禁用"),
    "OAUTH_INVALID_STATE": (400, "OAuth state 缺失或不匹配（疑似 CSRF/伪造回调）"),
    "OAUTH_STATE_EXPIRED": (400, "OAuth 授权事务已过期"),
    "OAUTH_CALLBACK_REPLAY": (400, "OAuth 回调已消费，拒绝重放"),
    "OAUTH_ACCESS_DENIED": (400, "用户在第三方平台取消或拒绝授权"),
    "OAUTH_TOKEN_EXCHANGE_FAILED": (502, "第三方平台 code 换 token 失败或响应格式非法"),
    "OAUTH_PROVIDER_UNAVAILABLE": (502, "第三方平台超时/限流/服务异常"),
    "OAUTH_INVALID_IDENTITY": (502, "第三方平台未返回可用的稳定身份标识"),
    "OAUTH_IDENTITY_CONFLICT": (409, "该第三方身份已绑定其他本站账号"),
    "OAUTH_BIND_REQUIRES_AUTH": (401, "绑定第三方账号需要先登录本站"),
    "OAUTH_SESSION_CHANGED": (409, "发起授权与完成授权的本站会话不一致，绑定已取消"),
    "OAUTH_TICKET_EXPIRED": (400, "一次性登录票据已过期"),
    "OAUTH_TICKET_ALREADY_USED": (400, "一次性登录票据已被消费，拒绝重放"),
    "OAUTH_LAST_LOGIN_METHOD": (403, "该身份是账号唯一登录方式，解绑将导致账号无法登录"),
    "OAUTH_INVALID_REDIRECT": (400, "return_path / 回调地址非法（疑似开放重定向）"),
}

_ABS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'，。；]*")

# 敏感字段名（小写比较，前缀/子串命中即视为敏感）：这些键的**取值**一律不回显。
SENSITIVE_KEY_TOKENS = ("password", "passwd", "pwd", "secret", "token", "api_key",
                        "apikey", "access_key", "authorization", "session",
                        "cookie", "private_key", "credential", "otp")
REDACTED = "***REDACTED***"


def _is_sensitive_key(key) -> bool:
    k = str(key).strip().lower()
    return any(t in k for t in SENSITIVE_KEY_TOKENS)


def redact_secrets(value):
    """敏感字段取值脱敏（Phase5-2 / Batch 0：响应过滤）。

    只遮蔽**取值**，保留字段名，便于调用方定位问题；
    与 redact_local_paths 互补，两者都必须在错误响应与日志上生效。
    """
    if isinstance(value, dict):
        return {k: (REDACTED if _is_sensitive_key(k) else redact_secrets(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_secrets(v) for v in value]
    return value


def redact_local_paths(value):
    """错误详情脱敏：本地绝对路径不得进入错误响应（Phase5-1R F-007）。"""
    if isinstance(value, str):
        out = value.replace(str(ROOT), "<project_root>")
        return _ABS_PATH_RE.sub("<local_path>", out)
    if isinstance(value, dict):
        return {k: redact_local_paths(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_local_paths(v) for v in value]
    return value


def redact_all(value):
    """完整脱敏链：先遮敏感字段取值，再遮本地绝对路径。"""
    return redact_local_paths(redact_secrets(value))


class ServiceError(Exception):
    """业务层/API 层统一错误。"""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        if code not in ERROR_CODES:
            raise ValueError(f"未登记的错误码: {code}")
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.detail = dict(detail or {})
        self.http_status = ERROR_CODES[code][0]

    def to_dict(self, request_id: str = "") -> dict:
        return {"error": {"code": self.code,
                          "message": redact_all(self.message),
                          "request_id": request_id,
                          "detail": redact_all(self.detail)}}


def error_catalog() -> list[dict]:
    return [{"code": c, "http_status": s, "meaning": m}
            for c, (s, m) in sorted(ERROR_CODES.items())]
