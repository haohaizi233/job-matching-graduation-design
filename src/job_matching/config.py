# -*- coding: utf-8 -*-
"""配置加载：configs/*.yaml -> 强类型访问器。所有随机种子与路径只从这里取。"""
from __future__ import annotations

from pathlib import Path

import yaml

from .core import ROOT

CONFIG_DIR = ROOT / "configs"


def _load(name: str) -> dict:
    p = CONFIG_DIR / name
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Config:
    """集中式配置对象。缺键立即抛错，避免参数散落在代码里。"""

    def __init__(self) -> None:
        self.pipeline: dict = _load("data_pipeline.yaml")
        self.policy: dict = _load("feature_policy.yaml")
        self.splits: dict = _load("matching_splits.yaml")
        self.edu_labels: dict = _load("education_labels.yaml")
        self.skills: dict = _load("skills.yaml")

    # ---------------- 路径
    @property
    def root(self) -> Path:
        return ROOT

    def path(self, key: str) -> Path:
        return ROOT / self.pipeline["paths"][key]

    def src(self, group: str, key: str) -> Path:
        return ROOT / self.pipeline["sources"][group][key]

    def out(self, key: str) -> Path:
        return ROOT / self.pipeline["outputs"][key]

    # ---------------- 种子
    def seed(self, key: str) -> int:
        s = self.pipeline["seeds"]
        if key not in s:
            raise KeyError(f"未登记的随机种子: {key}")
        return int(s[key])

    # ---------------- 格式 / 资源
    @property
    def float_format(self) -> str:
        return self.pipeline["formats"]["table_float_format"]

    @property
    def csv_chunk_rows(self) -> int:
        return int(self.pipeline["io"]["csv_chunk_rows"])

    @property
    def cosine_block_rows(self) -> int:
        return int(self.pipeline["io"]["cosine_block_rows"])

    @property
    def pipeline_version(self) -> str:
        return self.pipeline["pipeline_version"]

    # ---------------- 任务策略
    def task(self, task_name: str) -> dict:
        t = self.policy["tasks"].get(task_name)
        if t is None:
            raise KeyError(f"未登记的任务: {task_name}")
        return t

    def always_forbidden(self) -> list[str]:
        return list(self.policy["global"]["always_forbidden_as_features"])

    def id_like_columns(self) -> list[str]:
        return list(self.policy["global"]["id_like_columns"])

    def derived_score_chain(self) -> list[str]:
        return list(self.policy["global"]["derived_score_chain"])

    # ---------------- 切分
    def protocol(self, protocol_id: str) -> dict:
        p = self.splits["protocols"].get(protocol_id)
        if p is None:
            raise KeyError(f"未登记的切分协议: {protocol_id}")
        return p

    @property
    def min_group_size_for_ranking(self) -> int:
        return int(self.splits["min_group_size_for_ranking"])

    # ---------------- 学历标签
    @property
    def label_order(self) -> list[str]:
        return list(self.edu_labels["label_order"])

    def label_index(self) -> dict[str, int]:
        return dict(self.edu_labels["label_index"])


_CFG: Config | None = None


def get_config() -> Config:
    global _CFG
    if _CFG is None:
        _CFG = Config()
    return _CFG
