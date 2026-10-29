# -*- coding: utf-8 -*-
"""Phase5-1 业务画像契约（模块 A / 模块 B）。

设计原则：
  1. StudentProfile / JobProfile 是**业务层协议**，不是 src/job_matching/schema.py 的
     原始 CSV 表结构，两者刻意解耦（CSV Schema 属数据工程，禁止直接当线上契约）；
  2. 每个抽取字段都带三件套：fact_source（值的来源等级）/ evidence_text（原文证据）/
     extraction_method（抽取手段），支持后续人工修正；
  3. confidence 一律显式声明含义：它是**抽取/归一化的启发式置信度**，
     不是技能掌握概率、不是模型校准后的正确概率、不是录用概率；
  4. 不凭空补充项目成果、工作年限、技能熟练度：证据缺失就保留 unknown / 空列表。

来源等级（fact_source，四个必选项 + unknown）：
  stated_in_source  —— 原文（简历/JD）明确书写的事实
  rule_parsed       —— 规则/词典解析推得（未在原文以键值形式明示）
  model_inferred    —— 机器学习模型推断
  human_corrected   —— 用户或管理员修正
  unknown           —— 未知/缺失
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# ------------------------------------------------------------------ 常量
FACT_SOURCES = ("stated_in_source", "rule_parsed", "model_inferred",
                "human_corrected", "unknown")

VERIFICATION_STATUSES = ("self_reported", "extracted_from_resume",
                         "assessment_supported", "manually_verified", "unknown")

FIELD_STATUSES = ("ok", "unknown", "ocr_required", "needs_review", "rejected")

CONFIDENCE_MEANING = (
    "confidence 是抽取/归一化过程的启发式置信度（词典命中强度、键值显式程度、"
    "证据长度的组合），仅用于排序参考；它不是技能掌握概率、不是模型校准后的"
    "正确概率、不是录用成功概率。"
)

EDU_CONFIDENCE_MEANING = (
    "学历模型 confidence 是模型分数在预测标签上的均值，未经校准，不是真实正确概率。"
)

PROFILE_VERSION = "phase5-1-profile-v1"
INPUT_SCHEMA_VERSION = "phase5-1-input-v1"


# ------------------------------------------------------------------ 字段
@dataclass
class Field:
    """带证据与来源等级的业务字段。"""
    value: Any = None
    status: str = "unknown"                 # FIELD_STATUSES
    fact_source: str = "unknown"            # FACT_SOURCES
    extraction_method: str = ""
    evidence_text: str = ""
    model_version: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Field":
        return cls(value=d.get("value"), status=d.get("status", "unknown"),
                   fact_source=d.get("fact_source", "unknown"),
                   extraction_method=d.get("extraction_method", ""),
                   evidence_text=d.get("evidence_text", ""),
                   model_version=d.get("model_version"),
                   note=d.get("note", ""))

    @classmethod
    def unknown(cls, note: str = "") -> "Field":
        return cls(value=None, status="unknown", fact_source="unknown", note=note)


# ------------------------------------------------------------------ 技能
@dataclass
class SkillEntry:
    """技能对象：保留原文证据与归一化映射，verification_status 明确可信度层级。"""
    skill_id: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    evidence_source: str = "unknown"        # FACT_SOURCES
    evidence_text: str = ""
    confidence: float | None = None
    confidence_meaning: str = CONFIDENCE_MEANING
    verification_status: str = "unknown"    # VERIFICATION_STATUSES
    raw_form: str = ""
    extraction_method: str = ""
    needs_review: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SkillEntry":
        if not isinstance(d, dict):
            raise ValueError("SkillEntry.from_dict 需要 dict")
        for key in ("skill_id", "canonical_name"):
            if not d.get(key):
                raise ValueError(f"SkillEntry 缺少必要字段: {key}")
        return cls(
            skill_id=d["skill_id"], canonical_name=d["canonical_name"],
            aliases=list(d.get("aliases") or []),
            evidence_source=d.get("evidence_source", "unknown"),
            evidence_text=d.get("evidence_text", ""),
            confidence=d.get("confidence"),
            confidence_meaning=d.get("confidence_meaning", CONFIDENCE_MEANING),
            verification_status=d.get("verification_status", "unknown"),
            raw_form=d.get("raw_form", ""),
            extraction_method=d.get("extraction_method", ""),
            needs_review=bool(d.get("needs_review", False)),
        )


# ------------------------------------------------------------------ 经历
@dataclass
class ExperienceEntry:
    """项目 / 实习 / 证书条目：只保留原文摘录，不生成成果数字与熟练度。"""
    entry_id: str
    kind: str                               # project | internship | certificate
    title: str = ""
    period: str = ""
    excerpt: str = ""                       # 原文摘录（证据）
    fact_source: str = "unknown"
    extraction_method: str = ""
    quantified_achievements: list[str] = field(default_factory=list)
    note: str = "quantified_achievements 本阶段只接受原文出现的量化表述，禁止推断补齐"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExperienceEntry":
        return cls(entry_id=d["entry_id"], kind=d["kind"], title=d.get("title", ""),
                   period=d.get("period", ""), excerpt=d.get("excerpt", ""),
                   fact_source=d.get("fact_source", "unknown"),
                   extraction_method=d.get("extraction_method", ""),
                   quantified_achievements=list(d.get("quantified_achievements") or []),
                   note=d.get("note", ""))


# ------------------------------------------------------------------ 经验约束
@dataclass
class ExperienceRequirement:
    """岗位经验要求。

    status 语义（Phase5-1R F-006 统一口径）：
      ok             —— 存在明确年限要求（years_min 为规则解析结果）
      none_required  —— 明确表述经验不限/无经验要求/接受应届
      preference_only —— 仅加分/偏好表述（如“实习经验优先”），无硬性年限要求
      unknown        —— JD 未提供经验要求或无法解析
    """
    raw: str = ""
    years_min: float | None = None
    status: str = "unknown"   # ok | none_required | preference_only | unknown
    source: str = "unknown"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExperienceRequirement":
        return cls(raw=d.get("raw", ""), years_min=d.get("years_min"),
                   status=d.get("status", "unknown"), source=d.get("source", "unknown"),
                   note=d.get("note", ""))


# ------------------------------------------------------------------ 毕业届别约束
COHORT_RULES = ("exact_year", "year_set", "year_range", "year_and_after",
                "fresh_graduate", "past_graduate", "unrestricted", "unclear")

_COHORT_YEAR_MIN, _COHORT_YEAR_MAX = 2000, 2100


@dataclass
class CohortRequirement:
    """规范化毕业届别约束（Phase5-1R F-005）。

    rule 取值（COHORT_RULES）：
      exact_year      —— 仅限某届（如“仅限2027届”）；years=[2027]
      year_set        —— 多个指定届（如“2026届及2027届”）；years=[2026, 2027]
      year_range      —— 届别区间（如“2026—2028届”）；year_min/year_max
      year_and_after  —— 某届及以后（如“2027届及以后”）；year_min
      fresh_graduate  —— 应届毕业生（未说明具体年度）
      past_graduate   —— 往届毕业生
      unrestricted    —— 不限毕业届别
      unclear         —— 要求不明确 / 无法解析 / 年份非法

    判定一律走 match_year()，禁止用字符串相等覆盖所有情况。
    """
    raw: str = ""
    rule: str = "unclear"
    years: list[int] = field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None
    status: str = "unclear"       # ok | unclear
    source: str = "unknown"       # rule | stated_in_source | human_corrected | absent
    evidence_text: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CohortRequirement":
        return cls(raw=d.get("raw", ""), rule=d.get("rule", "unclear"),
                   years=[int(y) for y in d.get("years") or []],
                   year_min=d.get("year_min"), year_max=d.get("year_max"),
                   status=d.get("status", "unclear"), source=d.get("source", "unknown"),
                   evidence_text=d.get("evidence_text", ""), note=d.get("note", ""))

    def match_year(self, graduation_year: int | None) -> str:
        """返回 CONSTRAINT 状态之一：satisfied / not_satisfied /
        insufficient_evidence / requirement_unclear。

        硬性规则：
          * 学生毕业年份缺失 -> insufficient_evidence（绝不猜测）；
          * 应届/往届属于政策性身份，禁止只凭毕业年份推断校招资格
            -> insufficient_evidence（需人工复核）；
          * 要求不明确（rule=unclear）-> requirement_unclear（先于学生侧证据判断）；
          * 不限届别 -> 恒 satisfied。
        """
        if self.rule == "unclear" or self.status != "ok":
            return "requirement_unclear"
        if self.rule == "unrestricted":
            return "satisfied"
        if graduation_year is None:
            return "insufficient_evidence"
        year = int(graduation_year)
        if self.rule in ("fresh_graduate", "past_graduate"):
            return "insufficient_evidence"
        if self.rule == "exact_year":
            return "satisfied" if year in self.years else "not_satisfied"
        if self.rule == "year_set":
            return "satisfied" if year in self.years else "not_satisfied"
        if self.rule == "year_range":
            if self.year_min is None or self.year_max is None:
                return "requirement_unclear"
            return ("satisfied" if self.year_min <= year <= self.year_max
                    else "not_satisfied")
        if self.rule == "year_and_after":
            if self.year_min is None:
                return "requirement_unclear"
            return "satisfied" if year >= self.year_min else "not_satisfied"
        return "requirement_unclear"  # pragma: no cover - COHORT_RULES 已穷举


# ------------------------------------------------------------------ 学历约束
@dataclass
class EducationRequirement:
    """岗位学历要求（模型 / 规则解析结果 + 拒识/复核状态）。"""
    raw: str = ""
    tokens: list[str] = field(default_factory=list)   # 6 token 子集
    status: str = "unknown"   # ok | rules_only | model | rejected | needs_review | unknown
    source: str = "unknown"   # rule | model | stated_in_source | human_corrected | absent
    model_version: str | None = None
    expression_seen_in_train: bool | None = None
    confidence: float | None = None
    confidence_meaning: str = EDU_CONFIDENCE_MEANING
    rule: str | None = None
    needs_human_review: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EducationRequirement":
        known = {k: d.get(k) for k in cls.__dataclass_fields__}
        known["tokens"] = list(d.get("tokens") or [])
        return cls(**known)


# ------------------------------------------------------------------ 学生画像
@dataclass
class StudentProfile:
    """统一学生能力画像（业务协议，非 CSV Schema）。"""
    profile_id: str
    education_level: Field = field(default_factory=Field.unknown)
    major: Field = field(default_factory=Field.unknown)
    graduation_year: Field = field(default_factory=Field.unknown)
    employment_intention: Field = field(default_factory=Field.unknown)
    preferred_cities: Field = field(default_factory=Field.unknown)   # value: list[str]
    employment_type: Field = field(default_factory=Field.unknown)
    skills: list[SkillEntry] = field(default_factory=list)
    project_experiences: list[ExperienceEntry] = field(default_factory=list)
    internship_experiences: list[ExperienceEntry] = field(default_factory=list)
    certificates: list[ExperienceEntry] = field(default_factory=list)
    source_evidence: dict = field(default_factory=dict)
    profile_version: str = PROFILE_VERSION
    parse_status: str = "ok"   # ok | ocr_required | empty_text | partial | needs_review
    is_synthetic: bool = False
    label_source: str = "synthetic_or_unlabeled"
    demo: bool = True
    formal_evaluation: bool = False
    warnings: list[str] = field(default_factory=list)
    source_document: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StudentProfile":
        if not isinstance(d, dict):
            raise ValueError("StudentProfile.from_dict 需要 dict")
        if not d.get("profile_id"):
            raise ValueError("StudentProfile 缺少必要字段: profile_id")

        def fld(name: str) -> Field:
            v = d.get(name)
            return Field.from_dict(v) if isinstance(v, dict) else Field.unknown()

        return cls(
            profile_id=d["profile_id"],
            education_level=fld("education_level"), major=fld("major"),
            graduation_year=fld("graduation_year"),
            employment_intention=fld("employment_intention"),
            preferred_cities=fld("preferred_cities"), employment_type=fld("employment_type"),
            skills=[SkillEntry.from_dict(s) for s in d.get("skills") or []],
            project_experiences=[ExperienceEntry.from_dict(e)
                                 for e in d.get("project_experiences") or []],
            internship_experiences=[ExperienceEntry.from_dict(e)
                                    for e in d.get("internship_experiences") or []],
            certificates=[ExperienceEntry.from_dict(e) for e in d.get("certificates") or []],
            source_evidence=dict(d.get("source_evidence") or {}),
            profile_version=d.get("profile_version", PROFILE_VERSION),
            parse_status=d.get("parse_status", "ok"),
            is_synthetic=bool(d.get("is_synthetic", False)),
            label_source=d.get("label_source", "synthetic_or_unlabeled"),
            demo=bool(d.get("demo", True)),
            formal_evaluation=bool(d.get("formal_evaluation", False)),
            warnings=list(d.get("warnings") or []),
            source_document=d.get("source_document", ""),
        )


# ------------------------------------------------------------------ 岗位画像
@dataclass
class JobProfile:
    """统一岗位画像（业务协议）。缺失字段保留 unknown 状态，不做无证据补齐。"""
    job_id: str
    job_title: Field = field(default_factory=Field.unknown)
    job_category: Field = field(default_factory=Field.unknown)
    employer: Field = field(default_factory=Field.unknown)
    city: Field = field(default_factory=Field.unknown)
    employment_type: Field = field(default_factory=Field.unknown)
    graduation_cohort: Field = field(default_factory=Field.unknown)   # 如 "2027"
    cohort_requirement: CohortRequirement = field(default_factory=CohortRequirement)
    salary: Field = field(default_factory=Field.unknown)
    education_requirement: EducationRequirement = field(default_factory=EducationRequirement)
    experience_requirement: ExperienceRequirement = field(default_factory=ExperienceRequirement)
    required_skills: list[SkillEntry] = field(default_factory=list)
    preferred_skills: list[SkillEntry] = field(default_factory=list)
    responsibilities: Field = field(default_factory=Field.unknown)    # value: list[str]
    source: str = ""
    source_license: str = "UNKNOWN"
    source_evidence: dict = field(default_factory=dict)
    profile_version: str = PROFILE_VERSION
    parse_status: str = "ok"
    is_synthetic: bool = False
    label_source: str = "synthetic_or_unlabeled"
    demo: bool = True
    formal_evaluation: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JobProfile":
        if not isinstance(d, dict):
            raise ValueError("JobProfile.from_dict 需要 dict")
        if not d.get("job_id"):
            raise ValueError("JobProfile 缺少必要字段: job_id")

        def fld(name: str) -> Field:
            v = d.get(name)
            return Field.from_dict(v) if isinstance(v, dict) else Field.unknown()

        return cls(
            job_id=d["job_id"],
            job_title=fld("job_title"), job_category=fld("job_category"),
            employer=fld("employer"), city=fld("city"),
            employment_type=fld("employment_type"),
            graduation_cohort=fld("graduation_cohort"),
            cohort_requirement=CohortRequirement.from_dict(
                d.get("cohort_requirement") or {}), salary=fld("salary"),
            education_requirement=EducationRequirement.from_dict(
                d.get("education_requirement") or {}),
            experience_requirement=ExperienceRequirement.from_dict(
                d.get("experience_requirement") or {}),
            required_skills=[SkillEntry.from_dict(s) for s in d.get("required_skills") or []],
            preferred_skills=[SkillEntry.from_dict(s) for s in d.get("preferred_skills") or []],
            responsibilities=fld("responsibilities"),
            source=d.get("source", ""), source_license=d.get("source_license", "UNKNOWN"),
            source_evidence=dict(d.get("source_evidence") or {}),
            profile_version=d.get("profile_version", PROFILE_VERSION),
            parse_status=d.get("parse_status", "ok"),
            is_synthetic=bool(d.get("is_synthetic", False)),
            label_source=d.get("label_source", "synthetic_or_unlabeled"),
            demo=bool(d.get("demo", True)),
            formal_evaluation=bool(d.get("formal_evaluation", False)),
            warnings=list(d.get("warnings") or []),
        )


# ------------------------------------------------------------------ 校验
def check_verification_status(value: str) -> str:
    if value not in VERIFICATION_STATUSES:
        raise ValueError(f"非法 verification_status: {value!r}，合法值 {VERIFICATION_STATUSES}")
    return value


def check_fact_source(value: str) -> str:
    if value not in FACT_SOURCES:
        raise ValueError(f"非法 fact_source: {value!r}，合法值 {FACT_SOURCES}")
    return value
