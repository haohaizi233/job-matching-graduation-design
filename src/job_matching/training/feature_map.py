# -*- coding: utf-8 -*-
"""训练/推理共用特征映射（第四阶段 4.1）。

职责：
  1. 把 features_pairs.csv 的白名单原始列 -> 数值特征矩阵（可复现、可序列化）；
  2. 只在 train 上拟合类别词表与标准化统计（间接泄漏规则 IL-1 / IL-2）；
  3. 提供单 pair 原始特征计算（复用第三阶段 pair_features 的原始函数），
     支持推理时对任意 (resume, job) 组合独立建特征，不查询任何历史目标值。

特征分组（消融实验按组整体移除）：
  skill      : skill_jaccard / skill_overlap_ratio_cv / skill_overlap_ratio_job / both_skills_empty
  position   : position_token_overlap / target_position_norm(one-hot)
  category   : category_match / inferred_category(one-hot) / job_category(one-hot)
  experience : years_experience（train 统计标准化）
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .. import policy
from ..pair_features import title_tokens
from ..preprocess_skills import canonicalize_skills, jaccard, overlap_ratio

NUMERIC_BY_GROUP: dict[str, list[str]] = {
    "skill": ["skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
              "both_skills_empty"],
    "position": ["position_token_overlap"],
    "category": ["category_match"],
    "experience": ["years_experience"],
}
CATEGORICAL_BY_GROUP: dict[str, list[str]] = {
    "skill": [],
    "position": ["target_position_norm"],
    "category": ["inferred_category", "job_category"],
    "experience": [],
}
STANDARDIZE_COLUMNS = ("years_experience",)   # 其余数值列本身已是 [0,1] 比率/0-1 标志
OOV = "__OOV__"

# 单 pair 原始特征计算所需的两侧输入字段（与 data/interim 规范化表字段一致）
RESUME_FIELDS = ("target_position_norm", "skills_canonical_json", "inferred_category",
                 "years_experience")
JOB_FIELDS = ("job_title_norm", "category", "skills_canonical_json")


def _skill_set(value) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return set(map(str, value))
    if not isinstance(value, str) or not value:
        return set()
    try:
        lst = json.loads(value)
    except Exception:
        return set()
    return set(map(str, lst)) if isinstance(lst, list) else set()


def compute_pair_raw_features(resume: dict, job: dict) -> dict:
    """单 pair 原始特征（与第三阶段 features_pairs.csv 同口径）。

    只读取两侧原始/规范化字段，不读取 matches.csv、final_score、label_strength
    或任何派生评分字段。输入缺字段立即报错（输入校验）。
    """
    missing_r = [f for f in RESUME_FIELDS if f not in resume and
                 not (f == "skills_canonical_json" and "clean_skills" in resume)]
    missing_j = [f for f in JOB_FIELDS if f not in job and
                 not (f == "skills_canonical_json" and "clean_skills" in job)]
    if missing_r:
        raise ValueError(f"resume 缺少必要字段: {missing_r}")
    if missing_j:
        raise ValueError(f"job 缺少必要字段: {missing_j}")

    if "skills_canonical_json" in resume:
        r_skills = _skill_set(resume["skills_canonical_json"])
    else:
        r_skills = set(canonicalize_skills(resume["clean_skills"])["skills_canonical"])
    if "skills_canonical_json" in job:
        j_skills = _skill_set(job["skills_canonical_json"])
    else:
        j_skills = set(canonicalize_skills(job["clean_skills"])["skills_canonical"])

    r_title = str(resume.get("target_position_norm") or "")
    j_title = str(job.get("job_title_norm") or "")
    try:
        years = float(resume.get("years_experience"))
    except (TypeError, ValueError):
        years = float("nan")

    return {
        "skill_jaccard": float(jaccard(r_skills, j_skills)),
        "skill_overlap_ratio_cv": float(overlap_ratio(r_skills, j_skills)),
        "skill_overlap_ratio_job": float(overlap_ratio(j_skills, r_skills)),
        "both_skills_empty": 1.0 if (not r_skills and not j_skills) else 0.0,
        "position_token_overlap": float(jaccard(title_tokens(r_title), title_tokens(j_title))),
        "category_match": 1.0 if str(resume.get("inferred_category")) == str(job.get("category")) else 0.0,
        "years_experience": years,
        "target_position_norm": r_title,
        "inferred_category": str(resume.get("inferred_category") or ""),
        "job_category": str(job.get("category") or ""),
    }


class FeatureMap:
    """白名单原始列 -> 数值矩阵。fit 只能用 train（IL-1 / IL-2）。"""

    def __init__(self, groups_enabled: list[str] | tuple[str, ...] | None = None,
                 group_order: tuple[str, ...] = ("skill", "position", "category", "experience"),
                 task: str = "match_ranking"):
        self.task = task
        self.group_order = tuple(group_order)
        enabled = tuple(groups_enabled) if groups_enabled else self.group_order
        self.groups_enabled = tuple(g for g in self.group_order if g in enabled)
        self.cat_vocabs: dict[str, list[str]] = {}
        self.num_stats: dict[str, dict[str, float]] = {}
        self.feature_names_: list[str] = []
        self.raw_columns_: list[str] = []
        self.fitted_ = False

    # ---------------- fit / transform
    def fit(self, df: pd.DataFrame) -> "FeatureMap":
        raw_cols: list[str] = []
        names: list[str] = []
        for g in self.groups_enabled:
            raw_cols.extend(NUMERIC_BY_GROUP[g])
            raw_cols.extend(CATEGORICAL_BY_GROUP[g])
        # 白名单 / 黑名单强制检查（派生评分链 10 字段与 label_strength 无法通过）
        policy.check_feature_columns(self.task, raw_cols, raise_on_violation=True)
        self.raw_columns_ = raw_cols

        for g in self.groups_enabled:
            for col in NUMERIC_BY_GROUP[g]:
                vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=np.float64)
                if col in STANDARDIZE_COLUMNS:
                    mean = float(np.nanmean(vals)) if vals.size else 0.0
                    std = float(np.nanstd(vals)) if vals.size else 1.0
                    if not np.isfinite(std) or std <= 0:
                        std = 1.0
                    self.num_stats[col] = {"mean": mean, "std": std}
                else:
                    self.num_stats[col] = {"mean": 0.0, "std": 1.0}
                names.append(col)
            for col in CATEGORICAL_BY_GROUP[g]:
                vocab = sorted({str(v) for v in df[col].fillna(OOV).astype(str).unique()})
                self.cat_vocabs[col] = vocab + [OOV]
                names.extend([f"{col}={v}" for v in self.cat_vocabs[col]])
        self.feature_names_ = names
        self.fitted_ = True
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        self._check_fitted()
        n = len(df)
        X = np.zeros((n, len(self.feature_names_)), dtype=np.float32)
        col_pos = 0
        for g in self.groups_enabled:
            for col in NUMERIC_BY_GROUP[g]:
                vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=np.float64)
                st = self.num_stats[col]
                vals = np.nan_to_num(vals, nan=st["mean"], posinf=st["mean"], neginf=st["mean"])
                X[:, col_pos] = ((vals - st["mean"]) / st["std"]).astype(np.float32)
                col_pos += 1
            for col in CATEGORICAL_BY_GROUP[g]:
                vocab = self.cat_vocabs[col]
                index = {v: i for i, v in enumerate(vocab)}
                values = df[col].fillna(OOV).astype(str).to_numpy()
                rows = np.arange(n)
                cols = np.array([index.get(v, index[OOV]) for v in values], dtype=np.int64)
                X[rows, col_pos + cols] = 1.0
                col_pos += len(vocab)
        return X

    def transform_raw(self, raw: dict) -> np.ndarray:
        """对单 pair 的原始特征 dict（compute_pair_raw_features 输出）编码为 1 x d 矩阵。"""
        df = pd.DataFrame([{c: raw.get(c) for c in self.raw_columns_}])
        return self.transform(df)

    # ---------------- 元信息
    @property
    def n_features(self) -> int:
        return len(self.feature_names_)

    def group_of_feature(self) -> dict[str, str]:
        """feature_name -> 特征组（消融/系数归因用）。"""
        out: dict[str, str] = {}
        for g in self.groups_enabled:
            for col in NUMERIC_BY_GROUP[g]:
                out[col] = g
            for col in CATEGORICAL_BY_GROUP[g]:
                for v in self.cat_vocabs[col]:
                    out[f"{col}={v}"] = g
        return out

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "group_order": list(self.group_order),
            "groups_enabled": list(self.groups_enabled),
            "raw_columns": self.raw_columns_,
            "cat_vocabs": self.cat_vocabs,
            "num_stats": self.num_stats,
            "feature_names": self.feature_names_,
            "standardize_columns": list(STANDARDIZE_COLUMNS),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeatureMap":
        fm = cls(groups_enabled=d["groups_enabled"], group_order=tuple(d["group_order"]),
                 task=d.get("task", "match_ranking"))
        fm.cat_vocabs = {k: list(v) for k, v in d["cat_vocabs"].items()}
        fm.num_stats = {k: dict(v) for k, v in d["num_stats"].items()}
        fm.feature_names_ = list(d["feature_names"])
        fm.raw_columns_ = list(d["raw_columns"])
        fm.fitted_ = True
        return fm

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        return path

    @classmethod
    def load(cls, path: Path) -> "FeatureMap":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def _check_fitted(self) -> None:
        if not self.fitted_:
            raise RuntimeError("FeatureMap 未 fit：词表与标准化统计只能来自 train")
