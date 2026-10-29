# -*- coding: utf-8 -*-
"""基础设施层（Infrastructure/Adapters）：外部技术实现适配器。

只承载"外部格式/外部系统"适配，不含业务规则（业务规则在 `job_matching.domain`）：
  * documents —— PDF/DOCX/TXT 文本抽取适配器（外部格式）。

依赖方向：infra -> domain（允许），domain -> infra（禁止）。
"""
from .documents import ResumeIntakeError, SUPPORTED_FORMATS, extract_text

__all__ = ["ResumeIntakeError", "SUPPORTED_FORMATS", "extract_text"]
