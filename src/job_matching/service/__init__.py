# -*- coding: utf-8 -*-
"""job_matching.service：Phase5-1 业务推理服务层（模块 A~F）。

与训练/评估工程物理隔离：
  contracts   业务画像契约（StudentProfile / JobProfile，带证据与来源等级）
  text_extract/resume_parser/job_parser  中文文档解析与画像构建
  skills_normalize  技能词典归一化（禁止子串包含判断）
  model_registry    模型注册与惰性加载（future_verified 预留）
  matching          MatchingService.rank 三模式适配层
  explanations      可解释匹配结果（证据四态，不做资格硬判定）
  errors/logging_utils  错误码与 PII 脱敏日志
  api               FastAPI 最小业务 API（延迟导入）
"""
from .contracts import (CONFIDENCE_MEANING, EDU_CONFIDENCE_MEANING, ExperienceEntry,
                        ExperienceRequirement, EducationRequirement, Field, JobProfile,
                        PROFILE_VERSION, SkillEntry, StudentProfile)
from .errors import ERROR_CODES, ServiceError, error_catalog
from .explanations import build_match_result
from .job_parser import JobEducationResolver, parse_job_file, parse_job_text
from .matching import LegacyMatchAdapter, MatchingService, RankOptions
from .model_registry import (ModelRegistration, ModelRegistry,
                             register_builtin_models)
from .resume_parser import parse_resume_file, parse_resume_text
from .skills_normalize import build_skill_entry, normalize_skill_terms, scan_skills_in_text
from .text_extract import extract_document, extract_document_bytes

__all__ = [
    "CONFIDENCE_MEANING", "EDU_CONFIDENCE_MEANING", "ExperienceEntry",
    "ExperienceRequirement", "EducationRequirement", "Field", "JobProfile",
    "PROFILE_VERSION", "SkillEntry", "StudentProfile",
    "ERROR_CODES", "ServiceError", "error_catalog",
    "build_match_result",
    "JobEducationResolver", "parse_job_file", "parse_job_text",
    "LegacyMatchAdapter", "MatchingService", "RankOptions",
    "ModelRegistration", "ModelRegistry", "register_builtin_models",
    "parse_resume_file", "parse_resume_text",
    "build_skill_entry", "normalize_skill_terms", "scan_skills_in_text",
    "extract_document", "extract_document_bytes",
]
