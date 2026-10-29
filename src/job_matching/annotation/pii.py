# -*- coding: utf-8 -*-
"""（兼容入口）个人信息（PII）检测、脱敏与导出检查。

Phase5-1A：实现已下沉到 `job_matching.domain.pii_masking`（安全基础能力，
业务层 / 研究层共用同一份规则）。本模块保留旧导入路径与旧符号名（re-export），
历史脚本与测试无需改动。

隐私口径提醒：`mask_matches` 产出的是展示/日志/证据留存用**掩码**，
不等于不可逆匿名化；公开研究产物必须再过 `check_export` 全量校验。
"""
from __future__ import annotations

from ..domain.pii_masking import (  # noqa: F401
    MASK,
    _PATTERNS,
    _PII_FIELD_EXACT,
    _PII_FIELD_TOKENS,
    check_export,
    detect_pii,
    mask_matches,
    pii_field_violations,
    scrub_record,
)

__all__ = [
    "MASK", "check_export", "detect_pii", "mask_matches",
    "pii_field_violations", "scrub_record",
]
