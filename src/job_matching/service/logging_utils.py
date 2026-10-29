# -*- coding: utf-8 -*-
"""服务日志与请求 ID（模块 E：敏感内容不入日志）。

约束：
  * 所有业务日志先过 PII 掩码（复用 domain/pii_masking.mask_matches）再落盘/落控制台；
  * 不记录请求正文，只记录 request_id / 路径 / 计数 / 耗时；
  * request_id 由调用方注入或随机生成，全链路可追踪。
"""
from __future__ import annotations

import logging
import uuid

from ..domain.pii_masking import mask_matches

LOGGER_NAME = "job_matching.service"


class PiiScrubFilter(logging.Filter):
    """日志脱敏过滤器：命中片段替换为 ***，绝不输出原始号码/邮箱/身份证。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - 日志格式化异常兜底
            return True
        scrubbed = mask_matches(msg)
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
