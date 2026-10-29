# -*- coding: utf-8 -*-
"""学历训练数据集构建（第四阶段 4.2）。

数据来源（第三阶段产物，只读）：
  * data/splits/education/{train,validation,gold_holdout}.csv   —— 切分清单（只有键）
  * data/processed/education/education_inputs.csv               —— 输入字段
  * data/processed/education/education_labels.csv               —— 标签字段

实验口径（docs 与任务书要求区分两种实验）：
  * 实验 A（已知表达分布）：沿用第三阶段 train/validation 切分，输入文本互斥。
    注意：切分按 user_hash（整条输入文本）分组，**槽位表达在 train/validation 之间高度重叠**，
    因此实验 A 度量的是"已见过的学历表达"上的归一化性能。
  * 实验 B（未见过表达泛化）：按 slot_education_norm 分组的留出实验，只在 train 内部构造，
    留出的槽位表达在训练中完全不可见。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import ROOT
from .labels import LABEL_ORDER, multi_hot_matrix_from_strings

SPLITS_DIR = ROOT / "data" / "splits" / "education"
PROC_DIR = ROOT / "data" / "processed" / "education"

LABEL_COLS = ["label_tokens_json", "label_multi_hot", "label_status",
              "unresolved_tokens_json", "label_provenance", "is_gold"]
INPUT_COLS = ["slot_education_norm", "job_title_norm", "slot_present", "user_len"]

_DTYPES = {"record_key": str, "user_hash": str, "job_id": str,
           "label_multi_hot": str, "label_tokens_json": str,
           "slot_education_norm": str, "job_title_norm": str}


def load_split_frame(split: str) -> pd.DataFrame:
    """读取一个切分（train / validation / gold_holdout），拼上输入与标签列。"""
    sp = pd.read_csv(SPLITS_DIR / f"{split}.csv", dtype=str, encoding="utf-8")
    if len(sp) == 0:
        raise ValueError(f"{split} 切分为空")
    inputs = pd.read_csv(PROC_DIR / "education_inputs.csv", dtype=_DTYPES,
                         encoding="utf-8", low_memory=False)
    labels = pd.read_csv(PROC_DIR / "education_labels.csv", dtype=_DTYPES,
                         encoding="utf-8", low_memory=False)
    df = sp.merge(inputs[["record_key"] + INPUT_COLS], on="record_key", how="left")
    # label_provenance / is_gold 以切分清单为准，标签表只取标签列，避免 merge 后缀歧义
    df = df.merge(labels[["record_key", "label_tokens_json", "label_multi_hot",
                          "label_status", "unresolved_tokens_json"]],
                  on="record_key", how="left")
    if df["label_tokens_json"].isna().any():
        raise ValueError(f"{split}: {int(df['label_tokens_json'].isna().sum())} 行标签缺失")
    if df["slot_education_norm"].isna().any():
        df["slot_education_norm"] = df["slot_education_norm"].fillna("")
    df["label_tokens"] = [json.loads(x) for x in df["label_tokens_json"].astype(str)]
    df["Y"] = list(multi_hot_matrix_from_strings(df["label_multi_hot"].astype(str)))
    df["n_labels"] = [len(t) for t in df["label_tokens"]]
    df["slot"] = df["slot_education_norm"].astype(str)
    df["slot_len"] = df["slot"].str.len()
    return df.reset_index(drop=True)


def load_dev_sets() -> dict[str, pd.DataFrame]:
    """实验 A 的固定数据：train / validation / gold_holdout。"""
    return {s: load_split_frame(s) for s in ("train", "validation", "gold_holdout")}


def multi_hot(df: pd.DataFrame) -> np.ndarray:
    return np.stack(df["Y"].to_numpy()).astype(np.int8)


# ------------------------------------------------------------------ 实验 B
def slot_holdout_split(df_train: pd.DataFrame, holdout_every: int = 4,
                       skip_top: int = 8) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """按槽位表达分组的留出切分（实验 B）。

    规则（完全确定性，不需要随机种子）：
      1. 槽位按 (支持度降序, 表达字典序) 排名；
      2. 前 skip_top 名（最常见表达）不参与留出，保证训练集覆盖核心词表；
      3. 其余槽位按排名每 holdout_every 个取 1 个进入 holdout。
    返回 (train_part, holdout_part, info)。
    """
    sizes = df_train.groupby("slot").size().sort_values(ascending=False, kind="mergesort")
    ranked = list(sizes.index)  # 已按支持度降序；同支持度按出现顺序
    holdout_slots = [s for i, s in enumerate(ranked[skip_top:], start=skip_top)
                     if (i - skip_top) % holdout_every == 0]
    hold_set = set(holdout_slots)
    ho = df_train[df_train["slot"].isin(hold_set)].reset_index(drop=True)
    tr = df_train[~df_train["slot"].isin(hold_set)].reset_index(drop=True)
    info = {
        "strategy": f"rank_interleaved(holdout_every={holdout_every}, skip_top={skip_top})",
        "unique_slots_total": int(df_train["slot"].nunique()),
        "unique_slots_holdout": int(len(hold_set)),
        "rows_train": int(len(tr)),
        "rows_holdout": int(len(ho)),
        "holdout_slots": sorted(hold_set),
        "train_label_support": {LABEL_ORDER[i]: int(tr["Y"].map(lambda v: v[i]).sum())
                                for i in range(len(LABEL_ORDER))},
        "holdout_label_support": {LABEL_ORDER[i]: int(ho["Y"].map(lambda v: v[i]).sum())
                                  for i in range(len(LABEL_ORDER))},
    }
    return tr, ho, info


def slot_weights(df: pd.DataFrame) -> np.ndarray:
    """按槽位表达平衡的样本权重：每个唯一表达的总权重 = 1。"""
    sizes = df.groupby("slot")["slot"].transform("size").to_numpy().astype(np.float64)
    w = 1.0 / sizes
    return w / w.mean()


def conflict_aware_weights(df: pd.DataFrame) -> np.ndarray:
    """冲突感知样本权重（逐行条件比例权重）：只用传入集合统计，均值归一到 1。

    实现口径（历史实验基于此算法，不得静默更改）：
      1) share_i = count(slot_i, label_combo_i) / count(slot_i)
         —— 第 i 行**自身标签组合**在该槽位内的条件比例；
      2) w_i = clip(share_i, 0.05, 1.0)；
      3) 返回 w / w.mean()。

    直觉：样本自身的标签组合在槽位内越常见（条件比例越高），权重越大；
    处于 50/50 歧义区的槽位（如 `本科`、`大专`）里两派样本的条件比例都约为 0.5，
    权重一起被压低，避免噪声主导训练。

    注意：本函数计算的是「逐行自身标签组合的条件比例」，**不是**「槽位内众数占比」——
    多数组合的样本恰好拿到众数占比，少数派组合的样本拿到的是更低的自身占比。
    如需改为真正的众数占比加权，应作为新算法单独立项实验验证，不在本函数内修改。
    """
    pair = df.groupby(["slot", "label_tokens_json"])["label_tokens_json"].transform("size")
    total = df.groupby("slot")["label_tokens_json"].transform("size")
    share = (pair / total).to_numpy().astype(np.float64)
    w = np.clip(share, 0.05, 1.0)
    return w / w.mean()


def high_confidence_subset(df: pd.DataFrame, min_share: float = 0.90
                           ) -> tuple[pd.DataFrame, dict]:
    """高置信度子集：槽位非空 且 label_status=='ok' 且 P(标签组合|槽位) 众数占比 >= min_share。

    置信度来源是**训练集内部的标签-槽位条件一致性**，与任何模型预测无关；
    gold_holdout 不参与定义（任务书 2.2 的约束）。
    """
    share = np.zeros(len(df), dtype=np.float64)
    for _slot, sub in df.groupby("slot", sort=False):
        vc = sub["label_tokens_json"].value_counts()
        modal_share = float(vc.iloc[0]) / float(len(sub))
        share[sub.index.to_numpy()] = modal_share
    non_empty = df["slot"].astype(str).str.len().to_numpy() > 0
    status_ok = (df["label_status"].astype(str).to_numpy() == "ok") \
        if "label_status" in df.columns else np.ones(len(df), dtype=bool)
    mask = non_empty & status_ok & (share >= float(min_share))
    kept = df[mask].reset_index(drop=True)
    # 丢弃原因按优先级互斥统计，保证三类之和 == rows_before - rows_after
    dropped_empty = ~non_empty
    dropped_status = non_empty & ~status_ok
    dropped_share = non_empty & status_ok & (share < float(min_share))
    modal_combo = {}
    for slot, sub in df[mask].groupby("slot", sort=False):
        modal_combo[slot] = str(sub["label_tokens_json"].value_counts().index[0])
    kept_non_modal = int(sum(1 for _, r in kept.iterrows()
                             if str(r["label_tokens_json"]) != modal_combo.get(str(r["slot"]))))
    info = {
        "rule": (f"label_status=='ok' 且 槽位非空 且 P(标签组合|槽位) 众数占比 >= {min_share}"
                 "（只用 train 统计）"),
        "min_modal_share": float(min_share),
        "stats_source": "train_only",
        "rows_before": int(len(df)),
        "rows_after": int(len(kept)),
        "dropped": {
            "empty_slot": int(dropped_empty.sum()),
            "status_not_ok": int(dropped_status.sum()),
            "modal_share_below_threshold": int(dropped_share.sum()),
        },
        "kept_non_modal_rows": kept_non_modal,
        "kept_unique_slots": int(kept["slot"].nunique()) if len(kept) else 0,
        "note": "高置信度来自训练集内部一致性，非模型自评；gold_holdout 不参与定义",
    }
    return kept, info


def class_weights(df: pd.DataFrame) -> np.ndarray:
    """按标签频率的类别权重（用于 BCE pos_weight），返回 shape=(6,)。"""
    Y = multi_hot(df)
    n = float(len(Y))
    pos = Y.sum(axis=0).astype(np.float64)
    pos = np.maximum(pos, 1.0)
    return (n - pos) / pos
