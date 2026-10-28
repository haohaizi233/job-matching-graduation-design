# -*- coding: utf-8 -*-
"""简历数据规范化（第三阶段 3.1.3）。

只读 data/raw；输出 data/interim/matching/resume_normalized.csv。
日志与统计中不输出简历正文、联系方式。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .core import norm_text, sha256_text, write_csv
from .preprocess_skills import canonicalize_skills

# 注意：不读 embedding 列（由 embeddings.py 单独处理），避免无谓内存占用。
USECOLS = ["candidate_id", "source_row", "target_position", "resume_text",
           "clean_skills", "clean_skills_json", "education_text", "experience_text",
           "years_experience", "inferred_category"]


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


def normalize_resume(cv_path: Path) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(cv_path, usecols=USECOLS, encoding="utf-8-sig",
                     low_memory=False)
    n0 = len(df)

    # ---- 主键校验
    assert df["candidate_id"].is_unique, "cv.candidate_id 不是唯一主键"

    # ---- 文本规范化
    for col in ("target_position", "resume_text", "education_text", "experience_text"):
        df[col + "_norm"] = df[col].map(norm_text)

    changed = {c: int((df[c].astype(str) != df[c + "_norm"]).sum())
               for c in ("target_position", "resume_text", "education_text", "experience_text")}

    df["resume_text_len"] = df["resume_text_norm"].str.len()
    df["resume_text_hash"] = df["resume_text_norm"].map(sha256_text)

    # ---- 技能解析与规范化（保留原值与映射）
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

    # ---- 学历 / 年限
    df["education_text_hash"] = df["education_text_norm"].map(sha256_text)
    df["years_experience_flag"] = df["years_experience"].map(_flag_years)

    df["row_status"] = "ok"
    df.loc[df["skills_count"] == 0, "row_status"] = "empty_skills"
    df.loc[df["skills_needs_review"], "row_status"] = "skills_needs_review"

    out_cols = [
        "candidate_id", "source_row", "target_position_norm", "resume_text_norm",
        "resume_text_len", "resume_text_hash", "skills_canonical_json",
        "skills_raw_json", "skills_unmapped_json", "skills_mapping_json",
        "skills_count", "skills_needs_review", "education_text_norm",
        "education_text_hash", "experience_text_norm", "years_experience",
        "years_experience_flag", "inferred_category", "row_status",
    ]
    out = df[out_cols].sort_values("candidate_id", kind="mergesort").reset_index(drop=True)

    stats = {
        "source": str(cv_path).replace("\\", "/"),
        "rows_before": n0,
        "rows_after": int(len(out)),
        "columns_before": list(USECOLS),
        "columns_after": out_cols,
        "primary_key_unique": True,
        "text_changed_by_normalization": changed,
        "skills": {
            "rows_with_zero_skills": int((df["skills_count"] == 0).sum()),
            "rows_needs_review": int(df["skills_needs_review"].sum()),
            "unique_canonical_skills": int(len(set(
                s for lst in skill_rows for s in lst["skills_canonical"]))),
            "unique_raw_skills": int(len(set(
                s for lst in skill_rows for s in lst["skills_raw"]))),
        },
        "years_experience_flag_counts": df["years_experience_flag"].value_counts().to_dict(),
        "inferred_category_counts": df["inferred_category"].value_counts().to_dict(),
        "row_status_counts": df["row_status"].value_counts().to_dict(),
    }
    return out, stats
