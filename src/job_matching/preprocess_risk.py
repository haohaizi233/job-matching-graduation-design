# -*- coding: utf-8 -*-
"""招聘风险数据（all_df.csv）的规范化与元数据登记（第三阶段，2.4）。

本阶段只做：
  * 整行去重（实测 25,433 行重复，10.12%），保留去重映射；
  * 文本规范化；
  * 数值字段异常标记；
  * scam_probability 的性质登记（非人工真值）。
不纳入核心监督训练任务。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .core import norm_text, sha256_text

USECOLS = ["job_name", "company_name", "job_salary", "work_experience",
           "educational_requirements", "company_address", "job_type", "scam_probability"]


def normalize_risk(risk_path: Path) -> tuple[pd.DataFrame, dict]:
    df = pd.read_csv(risk_path, usecols=USECOLS, encoding="utf-8-sig", low_memory=False)
    n0 = len(df)

    for col in ("job_name", "company_name", "work_experience",
                "educational_requirements", "company_address"):
        df[col + "_norm"] = df[col].map(norm_text)

    # ---- 整行去重：保留首条，登记 duplicate_group_id 与 is_duplicate
    key_cols = [c for c in USECOLS]
    row_key = df[key_cols].astype(str).agg("\x1f".join, axis=1).map(sha256_text)
    df["row_key"] = row_key
    first_seen = {}
    group_id = []
    for k in row_key:
        if k not in first_seen:
            first_seen[k] = f"g{len(first_seen):07d}"
        group_id.append(first_seen[k])
    df["duplicate_group_id"] = group_id
    df["is_duplicate"] = df["row_key"].duplicated(keep="first")

    # ---- 数值异常标记
    sal = pd.to_numeric(df["job_salary"], errors="coerce")
    p99 = float(np.nanpercentile(sal.to_numpy(dtype=float), 99))
    df["salary_flag"] = "ok"
    df.loc[sal > p99, "salary_flag"] = "extreme_high"
    df.loc[sal <= 0, "salary_flag"] = "non_positive"

    scam = pd.to_numeric(df["scam_probability"], errors="coerce")
    df["scam_probability_flag"] = "upstream_score_not_ground_truth"
    df["scam_probability_is_decile"] = (scam % 10 == 0)

    out_cols = ["row_key", "duplicate_group_id", "is_duplicate",
                "job_name_norm", "company_name_norm", "job_salary", "salary_flag",
                "work_experience_norm", "educational_requirements_norm",
                "company_address_norm", "job_type", "scam_probability",
                "scam_probability_flag", "scam_probability_is_decile"]
    out = df[out_cols].sort_values("row_key", kind="mergesort").reset_index(drop=True)

    stats = {
        "source": str(risk_path).replace("\\", "/"),
        "rows_before": n0,
        "rows_after": int(len(out)),
        "rows_dropped_as_duplicate": int(df["is_duplicate"].sum()),
        "duplicate_ratio": round(float(df["is_duplicate"].mean()), 6),
        "columns_before": list(USECOLS),
        "columns_after": out_cols,
        "salary_flag_counts": df["salary_flag"].value_counts().to_dict(),
        "salary_max": float(sal.max()),
        "scam_probability": {
            "unique_values": sorted(int(v) for v in scam.dropna().unique()),
            "all_multiples_of_10": bool(df["scam_probability_is_decile"].all()),
            "verdict": "非人工真值；实测仅 9 个 10 的倍数取值，无任何人工复核列",
            "action": "仅登记为上游风险分数，本阶段不作为监督标签使用",
        },
        "task_decision": "本阶段仅规范化与元数据登记，不纳入核心监督训练任务",
    }
    return out, stats
