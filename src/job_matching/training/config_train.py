# -*- coding: utf-8 -*-
"""第四阶段训练配置加载：configs/training/*.yaml -> 强类型访问器。

与第三阶段 configs/data_pipeline.yaml 解耦：训练超参数、随机种子、评估口径
集中在 configs/training/ 下，避免与数据流水线配置互相污染。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..core import ROOT

TRAIN_CONFIG_DIR = ROOT / "configs" / "training"
FEATURE_GROUP_ORDER = ("skill", "position", "category", "experience")


class TrainConfig:
    def __init__(self, model_name: str | None = None):
        with open(TRAIN_CONFIG_DIR / "common.yaml", "r", encoding="utf-8") as f:
            self.common: dict = yaml.safe_load(f)
        self.model_name = model_name
        self.model: dict = {}
        if model_name:
            self.load_model(model_name)

    # ---------------- 模型配置
    def load_model(self, model_name: str) -> dict:
        path = TRAIN_CONFIG_DIR / f"{model_name}.yaml"
        if not path.exists():
            raise KeyError(f"未登记的模型配置: {model_name}（期望 {path}）")
        with open(path, "r", encoding="utf-8") as f:
            self.model = yaml.safe_load(f)
        self.model_name = model_name
        return self.model

    # ---------------- 常用访问器
    @property
    def root(self) -> Path:
        return ROOT

    @property
    def task(self) -> str:
        return str(self.common["data"]["task"])

    @property
    def dataset_version(self) -> str:
        return str(self.common["data"]["dataset_version"])

    @property
    def feature_groups(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self.common["feature_groups"].items()}

    def group_order(self) -> tuple[str, ...]:
        return tuple(g for g in FEATURE_GROUP_ORDER if g in self.common["feature_groups"])

    @property
    def selection_metric(self) -> str:
        return str(self.common["evaluation"]["selection_metric"])

    @property
    def ks(self) -> tuple[int, ...]:
        return tuple(int(k) for k in self.common["evaluation"]["ks"])

    @property
    def min_group_size(self) -> int:
        return int(self.common["evaluation"]["min_group_size_for_ranking"])

    @property
    def pairwise_tie_eps(self) -> float:
        return float(self.common["evaluation"]["pairwise"]["tie_eps"])

    @property
    def bootstrap_repeats(self) -> int:
        return int(self.common["evaluation"]["bootstrap"]["repeats"])

    @property
    def query_unit(self) -> str:
        return str(self.common["evaluation"]["query_unit"])

    def seed(self, key: str) -> int:
        s = self.common["seeds"]
        if key not in s:
            raise KeyError(f"未登记的训练随机种子: {key}")
        return int(s[key])

    def path(self, key: str) -> Path:
        return ROOT / self.common["paths"][key]

    @property
    def pair_sampling(self) -> dict:
        merged = dict(self.common.get("pair_sampling", {}))
        merged.update(self.model.get("pair_sampling", {}))
        return merged

    @property
    def protocols(self) -> list[str]:
        return ["candidate_cold", "job_cold", "double_cold"]


def get_train_config(model_name: str | None = None) -> TrainConfig:
    return TrainConfig(model_name)
