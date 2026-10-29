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
    "MODEL_ENV_INCOMPATIBLE": (503, "模型与当前运行环境不兼容（历史 checkpoint 依赖旧版依赖栈）"),
    "MODEL_INAPPLICABLE": (422, "当前业务输入无法合法构建该模型所需特征"),
    "MODEL_FORMAL_USE_FORBIDDEN": (422, "该模型未通过中文正式用途验证，拒绝正式模式"),
    "FUTURE_MODEL_UNAVAILABLE": (503, "future_verified 模式暂无已验证中文模型"),
    "LEAKAGE_GUARD": (422, "输入携带目标值/派生评分等禁用字段"),
    "INTERNAL_ERROR": (500, "服务内部错误"),
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
