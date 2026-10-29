# -*- coding: utf-8 -*-
"""Phase4-3A 人工标注与独立评估数据管理（协议 docs/evaluation/phase4-3a-protocol.md）。

模块划分：
  schema      配对/标注/仲裁记录字段、标签枚举、协议版本与校验
  pii         个人信息检测、脱敏与导出检查
  dedup       文本规范化、SHA-256、完全/近似重复检测
  pool        候选样本池构建（分层采样、难度层、清单与覆盖度）
  importer    人工标注导入与合法性校验
  agreement   标注一致性（一致率 / Kappa / Weighted Kappa / 分歧统计）
  arbitration 分歧仲裁与最终标签（保留原始标注）
  freeze      数据集冻结与 SHA-256 复验
"""
from .schema import (  # noqa: F401
    ANNOTATION_FIELDS,
    ARBITRATION_FIELDS,
    CONFIDENCE_VALUES,
    DIFFICULTY_TIERS,
    PAIR_FIELDS,
    PROTOCOL_VERSION,
    RELEVANCE_VALUES,
    AnnotationError,
)
