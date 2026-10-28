# -*- coding: utf-8 -*-
"""正式数据 Schema（第三阶段 3.1.1）。

四个 Schema：Resume / Job / Match / EducationSample。
字段全部来自实际 CSV 表头（2026-10-28 实测），未虚构任何数据库字段。

每个字段声明：
  字段名 / 字段类型 / 是否必需 / 是否可空 / 取值范围 /
  是否属于模型输入 / 是否属于监督标签 / 是否为派生字段 / 数据来源
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: str                    # object | int64 | float64 | bool
    required: bool = True         # 表中必须存在该列
    nullable: bool = False        # 允许出现空值
    value_range: str = ""         # 取值范围描述（空 = 不限）
    is_model_input: bool = False  # 推理时可用的原始特征
    is_target: bool = False       # 监督标签
    is_derived: bool = False      # 派生字段（评分/排名/公式产物）
    source: str = "raw"           # raw | derived | human_gold | model_output
    enum: tuple[str, ...] = field(default_factory=tuple)
    min_value: float | None = None
    max_value: float | None = None
    unique_key: bool = False


@dataclass(frozen=True)
class Schema:
    name: str
    description: str
    fields: tuple[FieldSpec, ...]
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[tuple[str, str, str], ...] = ()   # (列, 目标表, 目标列)

    def columns(self) -> list[str]:
        return [f.name for f in self.fields]

    def spec(self, name: str) -> FieldSpec:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.name}: 未登记字段 {name}")

    def model_input_columns(self) -> list[str]:
        return [f.name for f in self.fields if f.is_model_input]

    def target_columns(self) -> list[str]:
        return [f.name for f in self.fields if f.is_target]

    def derived_columns(self) -> list[str]:
        return [f.name for f in self.fields if f.is_derived]


# ===================================================================== Resume
RESUME_SCHEMA = Schema(
    name="Resume",
    description="cv.csv —— 候选人画像表（9,544 行 × 11 列，2026-10-28 实测）",
    primary_key=("candidate_id",),
    fields=(
        FieldSpec("candidate_id", "object", unique_key=True, value_range="字符串 ID",
                  source="raw"),
        FieldSpec("source_row", "int64", value_range="0 ~ 9543", source="raw"),
        FieldSpec("target_position", "object", is_model_input=True,
                  value_range="28 个唯一值，长度 10~87", source="raw"),
        FieldSpec("resume_text", "object", value_range="长度 493~3000（上游已截断）",
                  source="raw"),
        FieldSpec("clean_skills", "object", is_model_input=True,
                  value_range="字符串化的 list[str]", source="raw"),
        FieldSpec("clean_skills_json", "object", is_model_input=True,
                  value_range="与 clean_skills 等价的 JSON 形式", source="raw"),
        FieldSpec("education_text", "object", is_model_input=True,
                  value_range="长度 18~959", source="raw"),
        FieldSpec("experience_text", "object", value_range="长度 161~1746", source="raw"),
        FieldSpec("years_experience", "float64", is_model_input=True,
                  value_range="0 ~ 31（实测 16 个唯一值，全为整数）",
                  min_value=0.0, max_value=31.0, source="raw"),
        FieldSpec("inferred_category", "object", is_model_input=True,
                  value_range="IT/FINANCE/SALES/BUSINESS-DEV/HR/UNKNOWN",
                  enum=("INFORMATION-TECHNOLOGY", "FINANCE", "SALES",
                        "BUSINESS-DEVELOPMENT", "HR", "UNKNOWN"), source="raw"),
        FieldSpec("embedding", "object", value_range="字符串化的 768 维 float32 向量",
                  is_derived=True, source="derived"),
    ),
)

# ====================================================================== Job
JOB_SCHEMA = Schema(
    name="Job",
    description="job.csv —— 岗位画像表（1,167 行 × 10 列，2026-10-28 实测）",
    primary_key=("job_id",),
    fields=(
        FieldSpec("job_id", "int64", unique_key=True, value_range="整数主键", source="raw"),
        FieldSpec("job_title", "object", is_model_input=True,
                  value_range="720 个唯一值，长度 10~147", source="raw"),
        FieldSpec("category", "object", is_model_input=True,
                  value_range="5 类，接近均匀",
                  enum=("INFORMATION-TECHNOLOGY", "BUSINESS-DEVELOPMENT", "FINANCE",
                        "SALES", "HR"), source="raw"),
        FieldSpec("job_description", "object", value_range="长度 167~13639", source="raw"),
        FieldSpec("job_text", "object", value_range="长度 364~3500（硬截断）", source="raw"),
        FieldSpec("clean_skills", "object", is_model_input=True,
                  value_range="字符串化的 list[str]", source="raw"),
        FieldSpec("clean_skills_json", "object", is_model_input=True, source="raw"),
        # 实测 1167/1167 行与 job_description 完全相同 -> 重复字段，禁用为模型输入
        FieldSpec("education_text", "object", is_derived=True,
                  value_range="实测与 job_description 逐行相同（1167/1167）", source="raw"),
        # 语义不明：0~40，含 15 个非整数值 -> 仅登记，禁用为模型输入
        FieldSpec("years_required", "float64",
                  value_range="0 ~ 40（均值 14.30，含 16.95/20.23 等小数）",
                  min_value=0.0, max_value=40.0, source="raw"),
        FieldSpec("embedding", "object", value_range="字符串化的 768 维 float32 向量",
                  is_derived=True, source="derived"),
    ),
)

# ===================================================================== Match
MATCH_SCHEMA = Schema(
    name="Match",
    description="matches.csv —— 人岗兼容性记录表（122,560 行 × 13 列，2026-10-28 实测）",
    primary_key=("candidate_id", "job_id"),
    foreign_keys=(("candidate_id", "Resume", "candidate_id"),
                  ("job_id", "Job", "job_id")),
    fields=(
        FieldSpec("candidate_id", "object", value_range="9,532 个唯一值，FK -> cv.candidate_id",
                  source="raw"),
        FieldSpec("job_id", "int64", value_range="1,164 个唯一值，FK -> job.job_id", source="raw"),
        FieldSpec("label_strength", "object", is_target=True,
                  value_range="weak_positive / medium_positive / strong_positive",
                  enum=("weak_positive", "medium_positive", "strong_positive"),
                  source="derived"),
        FieldSpec("final_score", "float64", is_derived=True,
                  value_range="0.4300 ~ 0.7561", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("raw_score", "float64", is_derived=True,
                  value_range="0.3060 ~ 0.6516", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("semantic_score", "float64", is_derived=True,
                  value_range="0.5805 ~ 0.9177", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("skill_score", "float64", is_derived=True,
                  value_range="0.0000 ~ 0.6170", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("position_score", "float64", is_derived=True,
                  value_range="0.0229 ~ 1.0000", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("category_score", "float64", is_derived=True,
                  value_range="0.0000 ~ 1.0000", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("experience_score", "float64", is_derived=True,
                  value_range="0.0000 ~ 1.0000", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("education_score", "float64", is_derived=True,
                  value_range="0.3000 ~ 1.0000", min_value=0.0, max_value=1.0, source="derived"),
        FieldSpec("candidate_rank", "int64", is_target=True, is_derived=True,
                  value_range="1 ~ 122（组内 final_score 降序名次）", min_value=1.0, source="derived"),
        FieldSpec("candidate_rank_pct", "float64", is_derived=True,
                  value_range="0.3832 ~ 1.0000", min_value=0.0, max_value=1.0, source="derived"),
    ),
)

# ============================================================ EducationSample
EDUCATION_SCHEMA = Schema(
    name="EducationSample",
    description=("job-education —— 岗位学历解析样本；default 三份 9 列，"
                 "annotated 12 列（2026-10-28 实测）"),
    primary_key=("record_key",),
    fields=(
        FieldSpec("job_id", "object", value_range="非严格唯一主键（train 中 43 个重复）",
                  source="raw"),
        # system / user_short2 只存在于 default/* 三份，annotated 中缺失 -> required=False
        FieldSpec("system", "object", required=False,
                  value_range="常量 '从岗位中提取学历'", source="raw"),
        FieldSpec("user", "object", is_model_input=True,
                  value_range="<岗位名称>…</岗位名称><岗位描述>…</岗位描述><学历描述>…</学历描述>",
                  source="raw"),
        FieldSpec("assistant", "object", is_target=True, nullable=True,
                  value_range="6 token 组合串，如 '博士、硕士、本科'；test/annotated 缺 96.76%",
                  source="pseudo_online"),
        FieldSpec("id", "object", nullable=True,
                  value_range="train 中 12 缺失、11 重复；val/test 唯一", source="raw"),
        FieldSpec("user_short", "object", nullable=True, is_derived=True, source="derived"),
        FieldSpec("ai", "object", required=False, nullable=True, is_derived=True,
                  source="model_output"),
        FieldSpec("diff", "object", nullable=True, is_derived=True,
                  value_range="ai == assistant 的布尔标记，直接泄漏标签", source="derived"),
        FieldSpec("user_short2", "object", required=False, nullable=True, is_derived=True,
                  value_range="实测整列全空（100% NaN）", source="derived"),
        # 以下 6 列只存在于 annotated/2w_0716_eval.csv
        FieldSpec("线上学历-旧的", "object", required=False, is_derived=True, source="model_output"),
        FieldSpec("模型结果-新的", "object", required=False, is_derived=True, source="model_output"),
        FieldSpec("人工正确结果", "object", required=False, is_target=True, nullable=True,
                  value_range="736 条非空", source="human_gold"),
        FieldSpec("【线上学历-旧的】是否正确", "object", required=False, nullable=True,
                  is_derived=True, source="human_gold"),
        FieldSpec("【模型结果-新的】是否正确", "object", required=False, nullable=True,
                  is_derived=True, source="human_gold"),
        FieldSpec("是否英文岗位", "float64", required=False, nullable=True,
                  value_range="仅 33 行为 1", source="human_gold"),
    ),
)

# 各文件的精确列集合（用于区分 default 与 annotated 两个变体）
EDUCATION_EXPECTED_COLUMNS = {
    "default": ["job_id", "system", "user", "assistant", "id", "user_short", "ai",
                "diff", "user_short2"],
    "annotated": ["job_id", "user", "assistant", "线上学历-旧的", "id", "user_short",
                  "模型结果-新的", "diff", "人工正确结果",
                  "【线上学历-旧的】是否正确", "【模型结果-新的】是否正确", "是否英文岗位"],
}

ALL_SCHEMAS: dict[str, Schema] = {
    s.name: s for s in (RESUME_SCHEMA, JOB_SCHEMA, MATCH_SCHEMA, EDUCATION_SCHEMA)
}


# ================================================================== 校验器
def validate_frame(df: pd.DataFrame, schema: Schema,
                   check_values: bool = True) -> dict:
    """对 DataFrame 执行 Schema 校验，返回结构化结果（不抛异常，供门禁聚合）。"""
    issues: list[dict] = []
    cols = set(df.columns)

    # 1) 必需列
    for f in schema.fields:
        if f.required and f.name not in cols:
            issues.append({"code": "MISSING_COLUMN", "field": f.name})

    # 2) 未知列（提示，不算失败）
    unknown = sorted(cols - set(schema.columns()))
    for c in unknown:
        issues.append({"code": "UNKNOWN_COLUMN", "field": c, "severity": "warn"})

    # 3) 主键：单列主键做唯一性检查；复合主键只做组合唯一性检查
    if len(schema.primary_key) == 1:
        for key in schema.primary_key:
            if key in cols:
                dup = int(df[key].duplicated().sum())
                if dup:
                    issues.append({"code": "PRIMARY_KEY_DUPLICATED", "field": key,
                                   "count": dup})
                nnull = int(df[key].isna().sum())
                if nnull:
                    issues.append({"code": "PRIMARY_KEY_NULL", "field": key, "count": nnull})

    if not check_values:
        return {"schema": schema.name, "rows": int(len(df)), "issues": issues,
                "ok": not any(i.get("severity") != "warn" for i in issues)}

    # 4) 逐字段约束
    for f in schema.fields:
        if f.name not in cols:
            continue
        s = df[f.name]
        if not f.nullable:
            nnull = int(s.isna().sum())
            if nnull:
                issues.append({"code": "UNEXPECTED_NULL", "field": f.name, "count": nnull})
        if f.dtype.startswith("int") or f.dtype.startswith("float"):
            num = pd.to_numeric(s, errors="coerce")
            bad = int(num.isna().sum() - s.isna().sum())
            if bad:
                issues.append({"code": "NON_NUMERIC", "field": f.name, "count": bad})
            if f.min_value is not None:
                lo = float(num.min()) if num.notna().any() else None
                if lo is not None and lo < f.min_value:
                    issues.append({"code": "OUT_OF_RANGE_LOW", "field": f.name,
                                   "value": lo, "bound": f.min_value})
            if f.max_value is not None:
                hi = float(num.max()) if num.notna().any() else None
                if hi is not None and hi > f.max_value:
                    issues.append({"code": "OUT_OF_RANGE_HIGH", "field": f.name,
                                   "value": hi, "bound": f.max_value})
        if f.enum:
            vals = set(s.dropna().astype(str).unique().tolist())
            bad = sorted(vals - set(f.enum))
            if bad:
                issues.append({"code": "ILLEGAL_ENUM", "field": f.name,
                               "values": bad[:10], "count": len(bad)})

    # 5) 组合主键
    if len(schema.primary_key) > 1:
        keys = [k for k in schema.primary_key if k in cols]
        if len(keys) == len(schema.primary_key):
            dup = int(df.duplicated(keys).sum())
            if dup:
                issues.append({"code": "COMPOSITE_KEY_DUPLICATED",
                               "fields": keys, "count": dup})

    hard = [i for i in issues if i.get("severity") != "warn"]
    return {"schema": schema.name, "rows": int(len(df)), "issues": issues,
            "hard_issue_count": len(hard), "ok": len(hard) == 0}


def schema_table(schema: Schema) -> pd.DataFrame:
    """导出 Schema 表格（供 docs/feature-schema.md 与报告使用）。"""
    rows = []
    for f in schema.fields:
        rows.append({
            "schema": schema.name,
            "field": f.name,
            "dtype": f.dtype,
            "required": f.required,
            "nullable": f.nullable,
            "value_range": f.value_range,
            "is_model_input": f.is_model_input,
            "is_target": f.is_target,
            "is_derived": f.is_derived,
            "source": f.source,
        })
    return pd.DataFrame(rows)


def vector_field_ok(a: np.ndarray, dim: int = 768) -> bool:
    return a.ndim == 1 and a.size == dim and np.isfinite(a).all()
