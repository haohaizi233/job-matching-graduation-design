# -*- coding: utf-8 -*-
"""盲标注保护与标注员独立性门禁（Phase4-3A-2 模块 D / 测试场景 8、9）。

硬性规则：
  * 标注员视图按字段白名单构建：只给去标识化简历、岗位 JD 与标注辅助字段；
  * 模型预测 / 旧系统评分（final_score、label_strength、candidate_rank 等）绝不进入标注视图；
  * 抽样难度层、配对来源、split、Gold 资格等「预期匹配类别」信息同样对标注员隐藏；
  * 两位标注员必须独立：同一标注员不得冒充两名独立标注员（共享 ID 或整表镜像直接拒收）。
"""
from __future__ import annotations

from .pii import pii_field_violations
from .schema import AnnotationError, MODEL_OUTPUT_COLUMNS, has_model_output_columns

# 标注员可见字段白名单（去标识化简历 + JD + 标注辅助字段）
ANNOTATION_VIEW_COLUMNS = (
    "pair_id",
    "job_id",
    "resume_text",
    "job_text",
    "job_title",
    "job_category",
    "required_skills",
    "preferred_skills",
    "education_requirement",
    "experience_requirement",
    "resume_target_position",
    "resume_skills",
    "resume_education_level",
    "resume_years_experience",
    "graduation_cohort",
    "employment_type",
    "language",
)

# 源配对记录中一出现即拒收的列（模型预测 / 旧评分 → 不是人工标签依据）
_SOURCE_REJECTED_COLUMNS = tuple(sorted(set(MODEL_OUTPUT_COLUMNS)))

# 必须从标注员视图中剔除的流水线元数据列（抽样类别 / 来源 / 切分 / 他人答案）
_VIEW_HIDDEN_COLUMNS = (
    "difficulty_tier", "difficulty_factors", "pair_provenance", "split",
    "eligible_for_gold", "usable_for_chinese_gold", "is_synthetic",
    "resume_id", "resume_source", "job_source", "dataset_version",
    "content_hash", "quarantine_reason", "blind_eligible", "training_overlap",
    "final_relevance", "final_source", "final_confidence",
    "annotator_a_relevance", "annotator_b_relevance", "annotator_a_id", "annotator_b_id",
    "relevance_a", "relevance_b", "_relevance_a", "_relevance_b", "_reason_a", "_reason_b",
)


def check_annotation_view(row: dict) -> list[str]:
    """检查一份「标注员可见记录」是否违规。返回违规描述列表；为空才允许下发。"""
    problems: list[str] = []
    for col in has_model_output_columns(list(row.keys())):
        problems.append(f"字段 {col} 是模型预测/旧评分列，禁止展示给标注员")
    for key in row:
        if key in _SOURCE_REJECTED_COLUMNS or key in _VIEW_HIDDEN_COLUMNS:
            if not any(key in p for p in problems):
                problems.append(f"字段 {key} 属于盲标隐藏列（模型预测/抽样类别/他人答案），禁止展示给标注员")
    for bad in pii_field_violations(row):
        problems.append(f"字段 {bad} 属于个人信息字段，禁止进入标注视图")
    return sorted(set(problems))


def build_annotation_view(pair: dict) -> dict:
    """按白名单构建标注员视图。

    源配对记录含模型预测/旧评分列时**直接报错**（数据污染必须被发现，不做静默丢弃）；
    抽样难度层等流水线元数据按白名单剔除，产出的视图再过一次检查。
    """
    rejected = has_model_output_columns(list(pair.keys()))
    if rejected:
        raise AnnotationError(
            "model_output_columns",
            f"配对记录含模型预测/旧评分列，拒绝生成标注视图: {sorted(rejected)}")
    view = {k: pair[k] for k in ANNOTATION_VIEW_COLUMNS if k in pair}
    problems = check_annotation_view(view)
    if problems:
        raise AnnotationError("annotation_view_violation", "；".join(problems))
    return view


def check_packet_columns(columns) -> list[str]:
    """导出的标注包列名检查：出现禁列直接拒收。"""
    cols = [str(c) for c in columns]
    problems = []
    for col in has_model_output_columns(cols):
        problems.append(f"标注包含模型预测/旧评分列: {col}")
    for col in cols:
        if col in _VIEW_HIDDEN_COLUMNS and not any(col in p for p in problems):
            problems.append(f"标注包含盲标隐藏列: {col}")
        if col not in ANNOTATION_VIEW_COLUMNS and col not in (
                "annotator_id", "relevance", "confidence", "reason", "evidence",
                "annotation_timestamp", "protocol_version") and not any(col in p for p in problems):
            problems.append(f"标注包含白名单外字段: {col}")
    return sorted(set(problems))


# ------------------------------------------------------------------ 标注员独立性
_MIRROR_KEYS = ("relevance", "confidence", "reason", "evidence", "annotation_timestamp")


def check_annotator_independence(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """两名标注员独立性检查（测试场景 9）。

    违规情形：
      1. shared_annotator_id   两份标注使用同一 annotator_id（一人冒充两人）；
      2. mirrored_annotations  共同样本上逐条内容（标签/置信度/理由/证据/时间戳）完全一致
         —— 独立人工标注不可能逐字镜像，视为同一人重复提交。
    """
    ids_a = sorted({str(r.get("annotator_id", "")) for r in rows_a if str(r.get("annotator_id", ""))})
    ids_b = sorted({str(r.get("annotator_id", "")) for r in rows_b if str(r.get("annotator_id", ""))})
    violations: list[dict] = []
    shared_ids = sorted(set(ids_a) & set(ids_b))
    if shared_ids:
        violations.append({
            "code": "shared_annotator_id", "annotator_ids": shared_ids,
            "message": "两份标注使用同一 annotator_id，同一标注员不得冒充两名独立标注员",
        })
    if not rows_a or not rows_b:
        return {"status": "not_applicable" if (not rows_a and not rows_b) else "single_annotator",
                "annotators_a": ids_a, "annotators_b": ids_b,
                "violations": violations, "mirrored_pairs": 0, "shared_pairs": 0}

    a_by = {str(r.get("pair_id", "")): r for r in rows_a}
    b_by = {str(r.get("pair_id", "")): r for r in rows_b}
    shared = sorted(set(a_by) & set(b_by))
    mirrored = [pid for pid in shared
                if all(str(a_by[pid].get(k, "")) == str(b_by[pid].get(k, "")) for k in _MIRROR_KEYS)]
    if shared and len(mirrored) == len(shared):
        violations.append({
            "code": "mirrored_annotations", "shared_pairs": len(shared),
            "message": "两位标注员在全部共同样本上的记录逐字一致，疑似同一人重复提交，"
                       "不得视为独立双标注",
        })
    elif mirrored:
        violations.append({
            "code": "partially_mirrored_annotations", "mirrored_pairs": len(mirrored),
            "message": "存在逐字一致的标注记录，请核实是否为独立标注",
        })
    return {
        "status": "violation" if violations else "ok",
        "annotators_a": ids_a, "annotators_b": ids_b,
        "violations": violations, "mirrored_pairs": len(mirrored),
        "shared_pairs": len(shared),
    }


def check_final_label_independence(final_rows: list[dict]) -> list[dict]:
    """最终标签记录中 annotator_a_id == annotator_b_id 一律违规。"""
    problems = []
    for r in final_rows:
        a = str(r.get("annotator_a_id", "")).strip()
        b = str(r.get("annotator_b_id", "")).strip()
        if a and a == b:
            problems.append({"code": "shared_annotator_id", "pair_id": r.get("pair_id"),
                             "message": f"最终标签记录中两位标注员为同一人: {a}"})
    return problems
