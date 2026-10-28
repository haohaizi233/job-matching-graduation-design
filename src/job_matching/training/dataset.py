# -*- coding: utf-8 -*-
"""匹配数据加载与切分访问（第四阶段 4.1）。

只读取第三阶段已落盘产物：
  * data/processed/matching/features_pairs.csv   （特征，白名单 13 列）
  * data/processed/matching/targets_pairs.csv    （目标与代理相关性，物理隔离）
  * data/splits/matching/<protocol>/<subset>.csv （pair_index 索引，绝不重新切分）
目标列只用于构造训练目标与评估相关性，绝不进入特征矩阵。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import ROOT

TARGET_COLUMNS = ["pair_index", "candidate_id", "job_id", "label_strength", "final_score",
                  "candidate_rank", "candidate_rank_pct", "label_ordinal"]


@dataclass
class MatchingPairs:
    """全量 pair 表（特征 + 目标 + 键），行按 pair_index 升序。"""
    frame: pd.DataFrame

    @property
    def n(self) -> int:
        return len(self.frame)

    def subset(self, pair_index: np.ndarray) -> pd.DataFrame:
        idx = np.asarray(pair_index, dtype=np.int64)
        df = self.frame.set_index("pair_index", drop=False)
        missing = np.setdiff1d(idx, df.index.to_numpy())
        if missing.size:
            raise ValueError(f"切分索引中有 {missing.size} 个 pair_index 不在特征表中")
        return df.loc[idx].reset_index(drop=True)


def load_pairs(features_file: Path | None = None,
               targets_file: Path | None = None,
               with_skill_json: bool = False) -> MatchingPairs:
    features_file = Path(features_file or ROOT / "data/processed/matching/features_pairs.csv")
    targets_file = Path(targets_file or ROOT / "data/processed/matching/targets_pairs.csv")

    usecols = ["candidate_id", "job_id",
               "skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
               "position_token_overlap", "category_match", "years_experience",
               "target_position_norm", "inferred_category", "job_title_norm",
               "job_category", "both_skills_empty"]
    if with_skill_json:
        usecols += ["cv_skills_canonical_json", "job_skills_canonical_json"]
    feats = pd.read_csv(features_file, usecols=usecols, encoding="utf-8", low_memory=False)
    targets = pd.read_csv(targets_file, usecols=TARGET_COLUMNS, encoding="utf-8",
                          low_memory=False)

    feats["candidate_id"] = feats["candidate_id"].astype(str)
    targets["candidate_id"] = targets["candidate_id"].astype(str)
    feats["job_id"] = feats["job_id"].astype(np.int64)
    targets["job_id"] = targets["job_id"].astype(np.int64)

    merged = targets.merge(feats, on=["candidate_id", "job_id"], how="inner",
                           validate="one_to_one", sort=False)
    if len(merged) != len(targets):
        raise ValueError(f"特征/目标未完全对齐：targets={len(targets)} merged={len(merged)}")
    if not merged["pair_index"].is_unique:
        raise ValueError("pair_index 不唯一")
    merged = merged.sort_values("pair_index", kind="mergesort").reset_index(drop=True)
    return MatchingPairs(frame=merged)


def load_split_index(protocol: str, subset: str,
                     splits_dir: Path | None = None) -> np.ndarray:
    splits_dir = Path(splits_dir or ROOT / "data/splits/matching")
    path = splits_dir / protocol / f"{subset}.csv"
    if not path.exists():
        raise FileNotFoundError(f"切分文件不存在: {path}")
    df = pd.read_csv(path, usecols=["pair_index"], encoding="utf-8", low_memory=False)
    idx = df["pair_index"].to_numpy(dtype=np.int64)
    if not np.array_equal(idx, np.sort(idx)):
        idx = np.sort(idx)
    return idx


def load_protocol(protocol: str, splits_dir: Path | None = None) -> dict[str, np.ndarray]:
    """返回 {subset_name: pair_index 数组}，subset ∈ train/validation/test。"""
    return {s: load_split_index(protocol, s, splits_dir)
            for s in ("train", "validation", "test")}


def build_xy(df: pd.DataFrame, feature_map, y_col: str = "final_score") -> tuple[np.ndarray, np.ndarray]:
    X = feature_map.transform(df)
    y = pd.to_numeric(df[y_col], errors="coerce").to_numpy(dtype=np.float32)
    if np.isnan(y).any():
        raise ValueError(f"目标列 {y_col} 存在缺失值")
    return X, y
