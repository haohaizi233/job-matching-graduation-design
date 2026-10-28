# -*- coding: utf-8 -*-
"""人岗 pair 级特征构造（第三阶段 3.1.2 / 3.3.1 Baseline 2）。

只用真实原始特征独立计算，绝不使用 skill_score / raw_score / final_score /
candidate_rank 等派生评分字段。
禁止用子串匹配判断技能包含关系（Java != JavaScript）。
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from .config import get_config
from .preprocess_skills import jaccard, overlap_ratio

_TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z0-9+#\.]*|[\u4e00-\u9fff]")

# 特征列 -> 角色（写入 feature_schema.json）
FEATURE_ROLES = {
    "skill_jaccard": ("numeric", "allowed"),
    "skill_overlap_ratio_cv": ("numeric", "allowed"),
    "skill_overlap_ratio_job": ("numeric", "allowed"),
    "position_token_overlap": ("numeric", "allowed"),
    "category_match": ("numeric", "allowed"),
    "years_experience": ("numeric", "allowed"),
    "both_skills_empty": ("flag", "allowed"),
    "target_position_norm": ("categorical_text", "allowed"),
    "inferred_category": ("categorical", "allowed"),
    "job_title_norm": ("categorical_text", "allowed"),
    "job_category": ("categorical", "allowed"),
    "cv_skills_canonical_json": ("set", "allowed"),
    "job_skills_canonical_json": ("set", "allowed"),
}

NUMERIC_FEATURE_COLUMNS = [
    "skill_jaccard",
    "skill_overlap_ratio_cv",
    "skill_overlap_ratio_job",
    "position_token_overlap",
    "category_match",
    "years_experience",
]

SET_FEATURE_COLUMNS = ["cv_skills_canonical_json", "job_skills_canonical_json"]


def title_tokens(s: str) -> set[str]:
    """职位/岗位名称的独立词元化：ASCII 取单词，CJK 取单字。"""
    if not isinstance(s, str) or not s:
        return set()
    return {t.lower() for t in _TOKEN_RX.findall(s) if len(t.strip()) >= 1}


def _skill_sets(series: pd.Series) -> list[set[str]]:
    out = []
    for v in series:
        try:
            lst = json.loads(v) if isinstance(v, str) and v else []
        except Exception:
            lst = []
        out.append(set(lst))
    return out


def build_pair_features(matches: pd.DataFrame,
                        resume_norm: pd.DataFrame,
                        job_norm: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """按 matches 的 (candidate_id, job_id) 组合构造 pair 特征。

    返回 (features_df, stats)。features_df 只含 ID 键与白名单特征，不含任何目标/派生评分。
    """
    r = resume_norm.set_index("candidate_id")
    j = job_norm.set_index("job_id")

    cand_ids = matches["candidate_id"].astype(str).to_numpy()
    job_ids_int = matches["job_id"].to_numpy()
    job_ids = matches["job_id"].astype(str).to_numpy()

    r_skills = _skill_sets(r.loc[cand_ids, "skills_canonical_json"])
    j_skills = _skill_sets(j.loc[job_ids_int, "skills_canonical_json"])
    r_title = r.loc[cand_ids, "target_position_norm"].astype(str).tolist()
    j_title = j.loc[job_ids_int, "job_title_norm"].astype(str).tolist()
    r_cat = r.loc[cand_ids, "inferred_category"].astype(str).tolist()
    j_cat = j.loc[job_ids_int, "category"].astype(str).tolist()
    r_years = pd.to_numeric(r.loc[cand_ids, "years_experience"], errors="coerce").to_numpy()

    n = len(matches)
    skill_j = np.zeros(n, dtype=np.float64)
    ratio_cv = np.zeros(n, dtype=np.float64)
    ratio_job = np.zeros(n, dtype=np.float64)
    pos_ov = np.zeros(n, dtype=np.float64)
    cat_match = np.zeros(n, dtype=np.float64)

    for i in range(n):
        a, b = r_skills[i], j_skills[i]
        skill_j[i] = jaccard(a, b)
        ratio_cv[i] = overlap_ratio(a, b)
        ratio_job[i] = overlap_ratio(b, a)
        ta, tb = title_tokens(r_title[i]), title_tokens(j_title[i])
        pos_ov[i] = jaccard(ta, tb)
        cat_match[i] = 1.0 if r_cat[i] == j_cat[i] else 0.0

    feats = pd.DataFrame({
        "candidate_id": matches["candidate_id"].astype(str).to_numpy(),
        "job_id": pd.to_numeric(matches["job_id"], errors="coerce").astype("int64").to_numpy(),
        "skill_jaccard": skill_j,
        "skill_overlap_ratio_cv": ratio_cv,
        "skill_overlap_ratio_job": ratio_job,
        "position_token_overlap": pos_ov,
        "category_match": cat_match,
        "years_experience": r_years,
        "target_position_norm": r_title,
        "inferred_category": r_cat,
        "job_title_norm": j_title,
        "job_category": j_cat,
        "cv_skills_canonical_json": [json.dumps(sorted(s), ensure_ascii=False) for s in r_skills],
        "job_skills_canonical_json": [json.dumps(sorted(s), ensure_ascii=False) for s in j_skills],
    })

    # 技能重合为空的对（双方技能均为空）需要单独标记，避免 jaccard=0 被误读为"不匹配"
    both_empty = np.array([(len(a) == 0 and len(b) == 0) for a, b in zip(r_skills, j_skills)])
    feats["both_skills_empty"] = both_empty.astype(np.int8)

    stats = {
        "rows": int(n),
        "numeric_feature_columns": NUMERIC_FEATURE_COLUMNS,
        "all_feature_columns": [c for c in feats.columns
                                if c not in ("candidate_id", "job_id")],
        "derived_score_columns_used": [],
        "numeric_summary": {
            c: {
                "min": float(feats[c].min()), "max": float(feats[c].max()),
                "mean": float(feats[c].mean()), "std": float(feats[c].std()),
            } for c in NUMERIC_FEATURE_COLUMNS
        },
        "both_skills_empty_pairs": int(both_empty.sum()),
        "position_token_overlap_zero_pairs": int((pos_ov == 0).sum()),
    }
    return feats, stats


def numeric_matrix(features_df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    cols = [c for c in NUMERIC_FEATURE_COLUMNS if c in features_df.columns]
    X = features_df[cols].to_numpy(dtype=np.float32)
    return X, cols


def assert_no_forbidden_columns(columns: list[str]) -> None:
    cfg = get_config()
    forbidden = set(cfg.always_forbidden()) | set(cfg.derived_score_chain())
    hit = sorted(set(columns) & forbidden)
    if hit:
        raise ValueError(f"特征列命中黑名单: {hit}")
