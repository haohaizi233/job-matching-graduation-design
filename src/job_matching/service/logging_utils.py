# -*- coding: utf-8 -*-
"""服务日志与请求 ID（模块 E：敏感内容不入日志）。

约束：
  * 所有业务日志先过 PII 掩码（复用 domain/pii_masking.mask_matches）再落盘/落控制台；
  * 不记录请求正文，只记录 request_id / 路径 / 计数 / 耗时；
  * request_id 由调用方注入或随机生成，全链路可追踪。
"""
from __future__ import annotations

import logging
import re
import uuid

from ..domain.pii_masking import mask_matches
from .errors import redact_local_paths

LOGGER_NAME = "job_matching.service"

# 错误/日志文本里的凭证样式片段（password=xxx / token: xxx）一律遮蔽
_SECRET_TEXT_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization)\b"
    r"(\s*[=:：]\s*)(\S+)")


def scrub_sensitive_text(msg: str) -> str:
    """日志/错误文本脱敏：PII 掩码 + 本地路径遮蔽 + 凭证片段遮蔽。"""
    out = mask_matches(str(msg))
    out = redact_local_paths(out)
    out = _SECRET_TEXT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", out)
    return out


class PiiScrubFilter(logging.Filter):
    """日志脱敏过滤器：命中片段替换为 ***，绝不输出原始号码/邮箱/身份证/凭证/本机路径。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - 日志格式化异常兜底
            return True
        scrubbed = scrub_sensitive_text(msg)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        return True


def get_service_logger(name: str = LOGGER_NAME) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, PiiScrubFilter) for f in logger.filters):
        logger.addFilter(PiiScrubFilter())
    for h in logger.handlers:
        if not any(isinstance(f, PiiScrubFilter) for f in h.filters):
            h.addFilter(PiiScrubFilter())
    return logger


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:16]
