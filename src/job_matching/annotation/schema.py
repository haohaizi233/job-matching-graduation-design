# -*- coding: utf-8 -*-
"""配对 / 标注 / 仲裁记录的字段定义与合法性校验（协议第一、二、四节）。

原则：
  * 校验只做「结构与约束」检查，不生成任何标签；
  * 所有非法输入抛 AnnotationError（带 code），不静默修正；
  * 标签枚举含独立状态 unjudgeable，禁止把缺失信息归为 0。
"""
from __future__ import annotations

import re
from datetime import datetime

PROTOCOL_VERSION = "phase4-3a-annotation-v1"
PROTOCOL_DOC = "docs/evaluation/phase4-3a-protocol.md"

# 标签：0/1/2 有序相关性 + 独立不可判定状态
RELEVANCE_VALUES = ("0", "1", "2", "unjudgeable")
RELEVANCE_ORDERED = ("0", "1", "2")
CONFIDENCE_VALUES = ("high", "medium", "low")

# 候选池难度层（协议 3.3）
DIFFICULTY_TIERS = (
    "high_skill_overlap",
    "medium_skill_overlap",
    "same_direction_diff_duties",
    "hard_requirement_gap",
    "cross_category_negative",
)

# 评价单位字段（协议 4.1）
PAIR_FIELDS = (
    "pair_id", "resume_id", "job_id", "resume_source", "job_source",
    "resume_text", "job_text", "job_category", "job_category_source", "language",
    "graduation_cohort", "employment_type", "required_skills", "preferred_skills",
    "education_requirement", "experience_requirement", "city", "salary_expectation",
    "resume_target_position", "resume_skills", "resume_education_level",
    "resume_years_experience", "job_title",
    "difficulty_tier", "content_hash", "dataset_version", "is_synthetic",
    "pair_provenance", "eligible_for_gold", "split",
)

# 双人标注记录字段（协议 4.1）
ANNOTATION_FIELDS = (
    "annotator_id", "pair_id", "relevance", "confidence", "reason",
    "evidence", "annotation_timestamp", "protocol_version",
)

# 仲裁记录字段（协议 4.2）
ARBITRATION_FIELDS = (
    "arbitrator_id", "pair_id", "final_relevance", "final_confidence", "reason",
    "evidence", "annotation_timestamp", "protocol_version",
)

# 最终标签记录字段（保留原始标注，不覆盖）
FINAL_LABEL_FIELDS = (
    "pair_id", "final_relevance", "final_source", "final_confidence",
    "annotator_a_id", "annotator_a_relevance", "annotator_b_id", "annotator_b_relevance",
    "arbitrator_id", "reason", "evidence", "annotation_timestamp", "protocol_version",
)

# 明确禁止出现在标注文件中的列（模型输出 / 旧系统评分 -> 不是人工标签）
MODEL_OUTPUT_COLUMNS = (
    "model_score", "pred_score", "prediction", "predicted", "pred_relevance",
    "final_score", "raw_score", "label_strength", "candidate_rank", "candidate_rank_pct",
    "semantic_score", "llm_score", "gpt_score", "auto_label",
)

_ANNOTATOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{1,31}$")
_MACHINE_ID_RE = re.compile(r"(?i)(model|llm|gpt|auto|bot|machine|pred|infer|score)")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")


class AnnotationError(ValueError):
    """标注数据非法。code 用于测试与报告分类。"""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def norm_relevance(value) -> str:
    """标签值规范化：接受 '0'/'1'/'2'/'unjudgeable'（大小写不敏感、允许空白）。"""
    s = "" if value is None else str(value).strip().lower()
    if s in ("u", "unjudgeable"):
        s = "unjudgeable"
    if s in ("", "nan", "none", "null"):
        raise AnnotationError("invalid_relevance", f"标签值缺失: {value!r}")
    if s not in RELEVANCE_VALUES:
        raise AnnotationError(
            "invalid_relevance",
            f"标签值非法: {value!r}，合法值为 {RELEVANCE_VALUES}")
    return s


def norm_confidence(value) -> str:
    s = "" if value is None else str(value).strip().lower()
    if s not in CONFIDENCE_VALUES:
        raise AnnotationError(
            "invalid_confidence",
            f"置信度非法: {value!r}，合法值为 {CONFIDENCE_VALUES}")
    return s


def norm_timestamp(value) -> str:
    s = "" if value is None else str(value).strip()
    if not _TIMESTAMP_RE.match(s):
        raise AnnotationError("invalid_timestamp", f"时间戳非法: {value!r}")
    # 格式合法 + 可解析（不静默修正）
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            datetime.strptime(s, fmt)
            return s
        except ValueError:
            continue
    raise AnnotationError("invalid_timestamp", f"时间戳无法解析: {value!r}")


def check_annotator_id(value, *, allow_machine: bool = False) -> str:
    s = "" if value is None else str(value).strip()
    if not _ANNOTATOR_RE.match(s):
        raise AnnotationError("invalid_annotator_id", f"标注人员 ID 非法: {value!r}")
    if not allow_machine and _MACHINE_ID_RE.search(s):
        raise AnnotationError(
            "machine_annotator",
            f"标注人员 ID 形似机器/模型输出，禁止冒充人工标注: {value!r}")
    return s


def check_protocol_version(value, expected: str = PROTOCOL_VERSION) -> str:
    s = "" if value is None else str(value).strip()
    if s != expected:
        raise AnnotationError(
            "protocol_version_mismatch",
            f"标注协议版本不一致: {s!r} != {expected!r}（禁止混用不同版本协议）")
    return s


def check_required(row: dict, fields: tuple[str, ...], kind: str) -> None:
    missing = [f for f in fields if f not in row]
    if missing:
        raise AnnotationError("missing_fields", f"{kind} 缺少字段: {missing}")
    empty = [f for f in fields if row.get(f) is None or str(row.get(f)).strip() == ""]
    if empty:
        raise AnnotationError("empty_fields", f"{kind} 字段为空: {empty}")


def validate_annotation_row(row: dict, *, known_pairs: set[str],
                            known_annotators: set[str] | None = None,
                            protocol_version: str = PROTOCOL_VERSION) -> dict:
    """单条标注记录校验，返回规范化后的记录。"""
    check_required(row, ANNOTATION_FIELDS, "标注记录")
    annotator = check_annotator_id(row["annotator_id"])
    if known_annotators is not None and annotator not in known_annotators:
        raise AnnotationError("unknown_annotator", f"未登记的标注人员: {annotator!r}")
    pair_id = str(row["pair_id"]).strip()
    if pair_id not in known_pairs:
        raise AnnotationError("unknown_pair", f"pair_id 不存在: {pair_id!r}")
    out = {
        "annotator_id": annotator,
        "pair_id": pair_id,
        "relevance": norm_relevance(row["relevance"]),
        "confidence": norm_confidence(row["confidence"]),
        "reason": str(row["reason"]).strip(),
        "evidence": str(row["evidence"]).strip(),
        "annotation_timestamp": norm_timestamp(row["annotation_timestamp"]),
        "protocol_version": check_protocol_version(row["protocol_version"], protocol_version),
    }
    if len(out["evidence"]) < 4:
        raise AnnotationError("missing_evidence", "evidence 过短或缺失，标注必须可追溯判断依据")
    return out


def validate_arbitration_row(row: dict, *, known_pairs: set[str],
                             protocol_version: str = PROTOCOL_VERSION) -> dict:
    check_required(row, ARBITRATION_FIELDS, "仲裁记录")
    arbitrator = check_annotator_id(row["arbitrator_id"])
    pair_id = str(row["pair_id"]).strip()
    if pair_id not in known_pairs:
        raise AnnotationError("unknown_pair", f"pair_id 不存在: {pair_id!r}")
    return {
        "arbitrator_id": arbitrator,
        "pair_id": pair_id,
        "final_relevance": norm_relevance(row["final_relevance"]),
        "final_confidence": norm_confidence(row["final_confidence"]),
        "reason": str(row["reason"]).strip(),
        "evidence": str(row["evidence"]).strip(),
        "annotation_timestamp": norm_timestamp(row["annotation_timestamp"]),
        "protocol_version": check_protocol_version(row["protocol_version"], protocol_version),
    }


def has_model_output_columns(columns) -> list[str]:
    """标注文件列名检查：出现模型输出列直接拒收。"""
    bad = []
    lower = {str(c).strip().lower(): c for c in columns}
    for banned in MODEL_OUTPUT_COLUMNS:
        if banned in lower:
            bad.append(str(lower[banned]))
    return bad
