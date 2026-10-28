# -*- coding: utf-8 -*-
"""岗位数据规范化（第三阶段 3.1.4）。

重点处理第二阶段发现的两个问题：
  1) years_required 最大 40、均值 14.3，且含 16.95/20.23 等小数 -> 语义不明
     处置：保留原值 + 标记异常 + **暂时禁用为模型输入**（不确定特征）。
  2) education_text 疑似与 job_description 重复 -> 实测 1167/1167 完全相同
     处置：**不删除**，在规范化表中保留并打 duplicate 标记，禁用为模型输入。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .core import norm_text, sha256_text, write_csv
from .preprocess_skills import canonicalize_skills

USECOLS = ["job_id", "job_title", "category", "job_description", "job_text",
           "clean_skills", "clean_skills_json", "education_text", "years_required"]


def _flag_years(v) -> str:
    try:
        x = float(v)
    except Exception:
        return "non_numeric"
    if x != x:
        return "missing"
    if x < 0:
        return "negative"
    if x != int(x):
        return "fractional"
    if x == 0:
        return "zero"
    if x > 30:
        return "extreme_high"
    return "integer_ok"


def normalize_job(job_path: Path) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(job_path, usecols=USECOLS, encoding="utf-8-sig", low_memory=False)
    n0 = len(df)
    assert df["job_id"].is_unique, "job.job_id 不是唯一主键"

    for col in ("job_title", "job_description", "job_text", "education_text"):
        df[col + "_norm"] = df[col].map(norm_text)

    changed = {c: int((df[c].astype(str) != df[c + "_norm"]).sum())
               for c in ("job_title", "job_description", "job_text", "education_text")}

    # ---- 问题 2：education_text 与 job_description 是否重复（逐行实测）
    dup_mask = (df["education_text_norm"] == df["job_description_norm"])
    df["education_text_dup_of_job_description"] = dup_mask
    n_dup = int(dup_mask.sum())

    # ---- 问题 1：years_required 语义检查
    df["years_required_flag"] = df["years_required"].map(_flag_years)
    df["years_required_enabled"] = False      # 暂时禁用为模型输入

    skill_rows = df["clean_skills"].map(canonicalize_skills)
    df["skills_canonical_json"] = skill_rows.map(
        lambda d: json.dumps(d["skills_canonical"], ensure_ascii=False))
    df["skills_raw_json"] = skill_rows.map(
        lambda d: json.dumps(d["skills_raw"], ensure_ascii=False))
    df["skills_unmapped_json"] = skill_rows.map(
        lambda d: json.dumps(d["skills_unmapped"], ensure_ascii=False))
    df["skills_mapping_json"] = skill_rows.map(
        lambda d: json.dumps(d["skills_mapping"], ensure_ascii=False))
    df["skills_count"] = skill_rows.map(lambda d: d["skills_count"])
    df["skills_needs_review"] = skill_rows.map(lambda d: d["needs_review"])

    df["job_description_hash"] = df["job_description_norm"].map(sha256_text)
    df["job_text_len"] = df["job_text_norm"].str.len()
    df["job_text_truncated_at_3500"] = df["job_description_norm"].str.len() > 3500

    df["row_status"] = "ok"
    df.loc[df["skills_count"] == 0, "row_status"] = "empty_skills"
    df.loc[df["skills_needs_review"], "row_status"] = "skills_needs_review"

    out_cols = [
        "job_id", "job_title_norm", "category", "job_description_norm",
        "job_description_hash", "job_text_norm", "job_text_len",
        "job_text_truncated_at_3500", "skills_canonical_json", "skills_raw_json",
        "skills_unmapped_json", "skills_mapping_json", "skills_count",
        "skills_needs_review", "education_text_norm",
        "education_text_dup_of_job_description", "years_required",
        "years_required_flag", "years_required_enabled", "row_status",
    ]
    out = df[out_cols].sort_values("job_id", kind="mergesort").reset_index(drop=True)

    stats = {
        "source": str(job_path).replace("\\", "/"),
        "rows_before": n0,
        "rows_after": int(len(out)),
        "columns_before": list(USECOLS),
        "columns_after": out_cols,
        "primary_key_unique": True,
        "text_changed_by_normalization": changed,
        "education_text_duplication": {
            "rows_equal_to_job_description": n_dup,
            "rows_total": n0,
            "ratio": round(n_dup / n0, 6),
            "verdict": ("整列复制（1167/1167 逐行相同）"
                        if n_dup == n0 else f"部分重复 {n_dup}/{n0}"),
            "action": "保留原字段 + 打 duplicate 标记 + 禁用为模型输入（不删除）",
        },
        "years_required": {
            "flag_counts": df["years_required_flag"].value_counts().to_dict(),
            "min": float(df["years_required"].min()),
            "max": float(df["years_required"].max()),
            "mean": round(float(df["years_required"].mean()), 4),
            "non_integer_count": int((df["years_required"] % 1 != 0).sum()),
            "verdict": "语义不明（0~40、含小数），不得直接当作真实工作年限",
            "action": "保留原值 + 标记异常 + 暂时禁用为模型输入（uncertain_features）",
        },
        "skills": {
            "rows_with_zero_skills": int((df["skills_count"] == 0).sum()),
            "rows_needs_review": int(df["skills_needs_review"].sum()),
            "unique_canonical_skills": int(len(set(
                s for lst in skill_rows for s in lst["skills_canonical"]))),
            "unique_raw_skills": int(len(set(
                s for lst in skill_rows for s in lst["skills_raw"]))),
        },
        "category_counts": df["category"].value_counts().to_dict(),
        "row_status_counts": df["row_status"].value_counts().to_dict(),
    }
    return out, stats
