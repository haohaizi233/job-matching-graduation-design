# -*- coding: utf-8 -*-
"""领域层（Domain）：与研究/训练/HTTP 无关的纯业务规则。

约束（Phase5-1A 依赖规则，见 docs/architecture/phase5-1a-dependency-rules.md）：
  * 不依赖 FastAPI / Pydantic / Pandas / NumPy / PyTorch / joblib；
  * 不访问文件系统、不做模型加载、不读配置文件；
  * 不依赖 annotation（研究标注层）、training、independent_eval。

模块：
  * skills_lexicon —— 技能启发式词表与边界匹配（唯一入口）；
  * job_rules      —— 岗位类别 / JD 偏好段落 / 语言判定等纯规则（唯一入口）；
  * pii_masking    —— 个人信息检测与掩码（安全基础能力；掩码 ≠ 不可逆匿名化）。

历史兼容：`annotation.pool` / `annotation.pii` 仍可作为旧导入路径（re-export），
但业务代码一律从本层导入。
"""
from .job_rules import (
    CATEGORY_KEYWORDS,
    CATEGORY_OTHER,
    PREFERRED_MARKERS,
    SECTION_MARKERS,
    classify_job_category,
    detect_language,
    preferred_segment,
)
from .pii_masking import (
    MASK,
    check_export,
    detect_pii,
    mask_matches,
    pii_field_violations,
    scrub_record,
)
from .skills_lexicon import (
    SKILL_LEXICON,
    boundary_regex,
    extract_skills,
    lexicon_patterns,
)

__all__ = [
    "CATEGORY_KEYWORDS", "CATEGORY_OTHER", "PREFERRED_MARKERS", "SECTION_MARKERS",
    "classify_job_category", "detect_language", "preferred_segment",
    "MASK", "check_export", "detect_pii", "mask_matches", "pii_field_violations",
    "scrub_record",
    "SKILL_LEXICON", "boundary_regex", "extract_skills", "lexicon_patterns",
]
