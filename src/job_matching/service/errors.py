# -*- coding: utf-8 -*-
"""Phase5-1 业务服务错误体系（模块 E 错误码的唯一事实来源）。

约束：
  * 每个错误都有稳定 error_code，API 层原样返回，不吞错、不伪装成功；
  * message 不携带原文 PII（由调用方保证，日志层另有脱敏兜底）。
"""
from __future__ import annotations

# ---- 错误码登记表（code -> (HTTP 状态, 含义)）----
ERROR_CODES: dict[str, tuple[int, str]] = {
    "INVALID_REQUEST": (422, "请求字段缺失或取值非法"),
    "UNSUPPORTED_FORMAT": (415, "简历/岗位文件格式不支持"),
    "EMPTY_INPUT": (400, "输入正文为空"),
    "OCR_REQUIRED": (422, "扫描版或无文本层 PDF，需要 OCR 预处理"),
    "PARSE_FAILED": (422, "文档解析失败"),
    "BATCH_LIMIT_EXCEEDED": (400, "批量条数超过上限"),
    "INFERENCE_TIMEOUT": (408, "推理超过时间预算"),
    "MODEL_MISSING": (503, "模型权重或清单缺失"),
    "MODEL_INAPPLICABLE": (422, "当前业务输入无法合法构建该模型所需特征"),
    "MODEL_FORMAL_USE_FORBIDDEN": (422, "该模型未通过中文正式用途验证，拒绝正式模式"),
    "FUTURE_MODEL_UNAVAILABLE": (503, "future_verified 模式暂无已验证中文模型"),
    "LEAKAGE_GUARD": (422, "输入携带目标值/派生评分等禁用字段"),
    "INTERNAL_ERROR": (500, "服务内部错误"),
}


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
        return {"error": {"code": self.code, "message": self.message,
                          "request_id": request_id, "detail": self.detail}}


def error_catalog() -> list[dict]:
    return [{"code": c, "http_status": s, "meaning": m}
            for c, (s, m) in sorted(ERROR_CODES.items())]
