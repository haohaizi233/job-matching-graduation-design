# -*- coding: utf-8 -*-
"""统一推理接口（第四阶段 4.1 / 十一）。

    predict_score(resume, job) -> float
    rank_jobs(resume, jobs) -> list[dict]

硬性保证：
  * 只依赖白名单原始字段（target_position_norm / skills_canonical_json /
    inferred_category / years_experience / job_title_norm / category），
    不读取 final_score、raw_score、candidate_rank、candidate_rank_pct、label_strength
    或 matches.csv 的任何目标值；
  * 支持 CPU 推理（torch 权重用 map_location="cpu" 加载）；
  * 输入校验：缺字段立即报错；数值缺失按 train 统计填充（FeatureMap 内处理）；
  * 排序稳定：分数相同按输入顺序（稳定排序），结果可重复。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..training.feature_map import FeatureMap, compute_pair_raw_features


class MatchPredictor:
    def __init__(self, run_dir: Path | str, device: str = "cpu"):
        self.run_dir = Path(run_dir)
        if not (self.run_dir / "manifest.json").exists():
            raise FileNotFoundError(f"模型目录缺少 manifest.json: {self.run_dir}")
        with open(self.run_dir / "manifest.json", "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        self.model_name = self.manifest["model_name"]
        self.feature_map = FeatureMap.load(self.run_dir / "feature_map.json")
        self.model = self._load_model()
        self.device = device

    # ---------------- 加载
    def _load_model(self):
        if self.model_name in ("ridge", "gradient_boosting"):
            from ..models.ridge import RidgeModel
            from ..models.gradient_boosting import GradientBoostingModel
            cls = RidgeModel if self.model_name == "ridge" else GradientBoostingModel
            return cls.load(self.run_dir)
        if self.model_name == "mlp":
            from ..models.mlp import MLPModel
            return MLPModel.load(self.run_dir)
        if self.model_name == "ranknet":
            from ..models.ranknet import RankNetModel
            return RankNetModel.load(self.run_dir)
        raise ValueError(f"未登记的模型类型: {self.model_name}")

    # ---------------- 单 pair 特征与打分
    def build_features(self, resume: dict, job: dict) -> dict:
        """构建单 pair 原始特征（与 features_pairs.csv 同口径），不接触任何目标值。"""
        return compute_pair_raw_features(resume, job)

    def _encode(self, resume: dict, job: dict) -> np.ndarray:
        raw = self.build_features(resume, job)
        return self.feature_map.transform_raw(raw)

    def predict_score(self, resume: dict, job: dict) -> float:
        X = self._encode(resume, job)
        if hasattr(self.model, "predict"):
            try:
                score = self.model.predict(X, device=self.device)
            except TypeError:
                score = self.model.predict(X)
        else:
            raise RuntimeError("模型不支持 predict")
        return float(np.asarray(score).ravel()[0])

    def rank_jobs(self, resume: dict, jobs: list[dict]) -> list[dict]:
        """对多个岗位打分并稳定排序（分数相同保持输入顺序）。"""
        if not isinstance(jobs, (list, tuple)):
            raise ValueError("jobs 必须是 list")
        rows = []
        for pos, job in enumerate(jobs):
            rows.append({"input_position": pos, "job": job,
                         "score": self.predict_score(resume, job)})
        # 稳定排序：-score 主键，输入顺序次键
        rows.sort(key=lambda d: (-d["score"], d["input_position"]))
        out = []
        for rank, r in enumerate(rows, start=1):
            out.append({"rank": rank, "score": round(float(r["score"]), 8),
                        "job_id": r["job"].get("job_id"), "job": r["job"]})
        return out

    # ---------------- 元信息
    def info(self) -> dict:
        return {
            "run_id": self.manifest.get("run_id"),
            "model_name": self.model_name,
            "protocol": self.manifest.get("protocol"),
            "dataset_version": self.manifest.get("dataset_version"),
            "feature_groups_enabled": self.feature_map.groups_enabled,
            "n_features": self.feature_map.n_features,
            "requires_labels": False,
            "supports_cpu": True,
        }
