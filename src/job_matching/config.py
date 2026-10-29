# -*- coding: utf-8 -*-
"""配置加载：configs/*.yaml -> 强类型访问器。所有随机种子与路径只从这里取。

数据根目录重定向（Phase5-2 / Batch 0）：
  环境变量 `JM_DATA_ROOT` 非空时，所有 data/ 路径改从该根目录解析。
  用途只有一个——让"使用临时合成夹具的数据质量测试"能在干净临时目录里
  验证门禁逻辑本身，而不需要真实原始数据 / 训练产物。
  默认（未设置）行为与历史完全一致：解析到项目根。配置文件本身始终读取
  项目内 configs/，不随数据根重定向。
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from .core import ROOT

CONFIG_DIR = ROOT / "configs"


def _load(name: str) -> dict:
    p = CONFIG_DIR / name
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def data_root() -> Path:
    """数据根目录：JM_DATA_ROOT 优先，否则项目根。"""
    override = os.environ.get("JM_DATA_ROOT", "").strip()
    return Path(override).resolve() if override else ROOT


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
        return data_root()

    def path(self, key: str) -> Path:
        return self.root / self.pipeline["paths"][key]

    def src(self, group: str, key: str) -> Path:
        return self.root / self.pipeline["sources"][group][key]

    def out(self, key: str) -> Path:
        return self.root / self.pipeline["outputs"][key]

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
_CFG_KEY: str | None = None


def reset_config() -> None:
    """清空配置缓存（合成夹具测试在切换 JM_DATA_ROOT 后必须调用）。"""
    global _CFG, _CFG_KEY
    _CFG = None
    _CFG_KEY = None


def get_config() -> Config:
    global _CFG, _CFG_KEY
    key = os.environ.get("JM_DATA_ROOT", "").strip()
    if _CFG is None or _CFG_KEY != key:
        _CFG = Config()
        _CFG_KEY = key
    return _CFG
