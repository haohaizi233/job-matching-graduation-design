# -*- coding: utf-8 -*-
"""冻结评估集加载与查询组构造（协议一、六节）。

查询组 = 一份简历（resume_id），组内候选 = 该简历的岗位配对。
unjudgeable 标签不进入指标分母（保留计数，如实报告）。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import ROOT, jload
from ..annotation.freeze import verify_freeze


class GoldUnavailableError(RuntimeError):
    """没有真实人工 Gold：禁止生成正式性能结论。"""


def _read_records(path: Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
    return pd.read_csv(path, dtype=str).fillna("").to_dict("records")


class EvalSet:
    """评估集视图：pairs + 最终标签（人工 Gold）。"""

    def __init__(self, pairs: list[dict], labels: list[dict], meta: dict | None = None):
        self.pairs = pairs
        self.meta = meta or {}
        label_by_pair = {r["pair_id"]: r for r in labels}
        self.rows = []
        for p in pairs:
            lab = label_by_pair.get(p["pair_id"])
            relevance = None
            if lab is not None and str(lab.get("final_relevance") or "").strip() != "":
                relevance = str(lab["final_relevance"]).strip()
            self.rows.append({"pair": p, "label": lab, "relevance": relevance})

    # ---------------- 属性
    @property
    def label_source(self) -> str:
        return str(self.meta.get("label_source", "human_gold"))

    @property
    def n_pairs(self) -> int:
        return len(self.rows)

    @property
    def n_judgeable(self) -> int:
        return sum(1 for r in self.rows if r["relevance"] in ("0", "1", "2"))

    @property
    def n_unjudgeable(self) -> int:
        return sum(1 for r in self.rows if r["relevance"] == "unjudgeable")

    @property
    def n_unlabeled(self) -> int:
        return sum(1 for r in self.rows if r["relevance"] is None)

    def query_groups(self, include_unjudgeable: bool = False) -> dict[str, list[dict]]:
        """按 resume_id 分组；默认剔除 unjudgeable 与未标注样本。"""
        out: dict[str, list[dict]] = {}
        for r in self.rows:
            if not include_unjudgeable and r["relevance"] not in ("0", "1", "2"):
                continue
            out.setdefault(r["pair"]["resume_id"], []).append(r)
        return {k: out[k] for k in sorted(out)}

    def query_ids(self) -> list[str]:
        return sorted(self.query_groups())

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(group_ids, pred_placeholder, relevance) —— 分数由调用方提供。"""
        groups, rels = [], []
        for rid, rows in self.query_groups().items():
            for r in rows:
                groups.append(rid)
                rels.append(float(r["relevance"]))
        return (np.asarray(groups), np.zeros(len(groups)), np.asarray(rels, dtype=np.float64))

    def require_gold(self) -> None:
        """无真实人工 Gold 时抛错——禁止生成正式性能结论。"""
        if self.label_source != "human_gold":
            raise GoldUnavailableError(
                f"标签来源为 {self.label_source!r}，不是人工 Gold，禁止输出正式性能结论")
        if self.n_judgeable == 0:
            raise GoldUnavailableError("没有任何可判定的人工标签，禁止输出正式性能结论")
        if self.meta.get("annotation_status") not in (None, "complete"):
            raise GoldUnavailableError(
                f"annotation_status={self.meta.get('annotation_status')!r}，标注未完成")

    def summary(self) -> dict:
        return {
            "label_source": self.label_source,
            "pairs": self.n_pairs,
            "judgeable": self.n_judgeable,
            "unjudgeable": self.n_unjudgeable,
            "unlabeled": self.n_unlabeled,
            "query_groups": len(self.query_ids()),
            "splits": sorted({str(p.get("split", "")) for p in self.pairs}),
            "synthetic_pairs": sum(1 for p in self.pairs if str(p.get("is_synthetic")) == "True"),
        }


def load_eval_set(pairs_file: Path | str, labels_file: Path | str,
                  meta: dict | None = None, manifest_path: Path | str | None = None
                  ) -> EvalSet:
    if manifest_path is not None:
        verify = verify_freeze(manifest_path)
        if not verify["ok"]:
            raise GoldUnavailableError(f"冻结清单校验失败，文件已被修改: {manifest_path}")
    pairs = _read_records(Path(pairs_file))
    labels = _read_records(Path(labels_file)) if Path(labels_file).exists() else []
    return EvalSet(pairs, labels, meta=meta)


def load_frozen_eval_set(manifest_path: Path | str, meta: dict | None = None) -> EvalSet:
    manifest_path = Path(manifest_path)
    manifest = jload(manifest_path)
    base = manifest_path.parent
    pairs_rec = manifest["files"].get("pairs")
    labels_rec = manifest["files"].get("final_labels")
    if pairs_rec is None or labels_rec is None:
        raise GoldUnavailableError("冻结清单缺少 pairs / final_labels 文件登记")

    def _resolve(rec: dict) -> Path:
        for c in (base / rec["path"], ROOT / rec["path"], base / Path(rec["path"]).name):
            if c.exists():
                return c
        raise FileNotFoundError(rec["path"])

    merged = dict(meta or {})
    # 只有 evalset 阶段的冻结集才允许默认标为 human_gold；
    # pool 阶段（未标注）必须显式降级，防止误当成人工真值。
    default_source = "human_gold" if manifest.get("stage") == "evalset" else "unlabeled_pool"
    merged.setdefault("label_source", default_source)
    merged.setdefault("dataset_version", manifest.get("dataset_version"))
    merged.setdefault("annotation_quality", manifest.get("annotation_quality", {}))
    return load_eval_set(_resolve(pairs_rec), _resolve(labels_rec), meta=merged,
                         manifest_path=manifest_path)
