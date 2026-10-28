# -*- coding: utf-8 -*-
"""第四阶段 4.2 第一/二部分：任务可学习性与标签噪声分析。

产出：
  reports/education-training/learnability.json
  reports/education-training/label-noise.json
  reports/education-training/logs/analyze_learnability.log

约束：只读数据；不改写任何数据文件；不使用 gold_holdout 做任何拟合或规则选择。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import REPORT_DIR, prepare_experiment_a, setup_train_logging, texts_of  # noqa: E402
from job_matching.core import ROOT, jdump  # noqa: E402
from job_matching.education.dataset import multi_hot  # noqa: E402
from job_matching.education.labels import LABEL_ORDER  # noqa: E402
from job_matching.education.rules import rule_predict  # noqa: E402

CONFIDENCE = {"human_gold": "high", "pseudo_online": "low", "model_new": "unusable"}


def _length_stats(vals: list[int]) -> dict:
    a = np.asarray(vals, dtype=np.float64)
    return {"n": int(a.size), "min": int(a.min()), "max": int(a.max()),
            "mean": round(float(a.mean()), 3), "median": float(np.median(a)),
            "p90": float(np.percentile(a, 90)), "p99": float(np.percentile(a, 99))}


def _expr_pattern_stats(slots: pd.Series) -> dict:
    s = slots.astype(str)
    return {
        "contains_及以上": int(s.str.contains("及以上").sum()),
        "contains_以上": int(s.str.contains("以上").sum()),
        "contains_或以上": int(s.str.contains("或以上").sum()),
        "contains_不限": int(s.str.contains("不限").sum()),
        "contains_不明/未知/无法确定": int(s.str.contains("不明|未知|无法确定").sum()),
        "contains_应届/在校/实习": int(s.str.contains("应届|在校|实习").sum()),
        "contains_研究生": int(s.str.contains("研究生").sum()),
        "empty_slot": int((s.str.len() == 0).sum()),
    }


def _slot_conflicts(df: pd.DataFrame) -> dict:
    """同一槽位表达 -> 多个标签组合的冲突统计。"""
    rows = []
    for slot, sub in df.groupby("slot", sort=False):
        combos = Counter(sub["label_tokens_json"].astype(str))
        if len(combos) > 1:
            total = int(len(sub))
            top, top_n = combos.most_common(1)[0]
            rows.append({
                "slot": slot, "rows": total, "distinct_label_combos": int(len(combos)),
                "top_label_combo": top, "top_ratio": round(top_n / total, 6),
                "label_counts": {k: int(v) for k, v in combos.most_common(6)},
            })
    rows.sort(key=lambda r: -r["rows"])
    n_rows = int(sum(r["rows"] for r in rows))
    return {
        "unique_slots": int(df["slot"].nunique()),
        "conflicting_slots": int(len(rows)),
        "rows_in_conflicting_slots": n_rows,
        "rows_in_conflicting_slots_ratio": round(n_rows / max(len(df), 1), 6),
        "top_conflicts": rows[:15],
        "interpretation": (
            "同一槽位表达对应多个标签组合 = 仅凭 <学历描述> 槽位无法辨识标签；"
            "冲突来源可能是上下文缺失（岗位名称/描述）或伪标签噪声，二者无法从本表单独区分。"),
    }


def _context_check(df: pd.DataFrame) -> dict:
    """冲突是否可由上下文（岗位名称）解释：比较槽位内 vs 槽位+岗位名称 的标签纯度。"""
    g1 = df.groupby("slot")["label_tokens_json"].nunique()
    g2 = df.groupby(["slot", "job_title_norm"])["label_tokens_json"].nunique()
    slot_purity = float((g1 == 1).mean())
    pair_purity = float((g2 == 1).mean())
    return {
        "slot_level_unique_label_ratio": round(slot_purity, 6),
        "slot_title_level_unique_label_ratio": round(pair_purity, 6),
        "group_sizes_slot": int(len(g1)),
        "group_sizes_slot_title": int(len(g2)),
        "note": ("组内唯一标签占比越高越『纯』。若 (槽位,岗位名称) 明显更纯，说明冲突部分来自"
                 "上下文缺失；但组规模差异很大，该对比只能作为方向性证据。"),
    }


def _pseudo_label_stats(df: pd.DataFrame) -> dict:
    Y = multi_hot(df)
    combo = Counter(df["label_tokens_json"].astype(str))
    n = len(df)
    per_label = {LABEL_ORDER[i]: int(Y[:, i].sum()) for i in range(len(LABEL_ORDER))}
    multi_ratio = float((Y.sum(axis=1) >= 2).mean())
    cooc = {}
    for i in range(len(LABEL_ORDER)):
        for j in range(i + 1, len(LABEL_ORDER)):
            k = f"{LABEL_ORDER[i]}+{LABEL_ORDER[j]}"
            cooc[k] = int(((Y[:, i] == 1) & (Y[:, j] == 1)).sum())
    return {
        "rows": int(n),
        "label_provenance": df["label_provenance"].value_counts().to_dict(),
        "label_confidence": {k: CONFIDENCE.get(k, "unknown")
                             for k in df["label_provenance"].unique()},
        "label_combo_distribution": {k: int(v) for k, v in combo.most_common(20)},
        "distinct_label_combos": int(len(combo)),
        "per_label_support": per_label,
        "multi_label_row_ratio": round(multi_ratio, 6),
        "single_label_rows": int((Y.sum(axis=1) == 1).sum()),
        "label_cooccurrence_top": dict(sorted(cooc.items(), key=lambda kv: -kv[1])[:10]),
        "empty_label_rows": int((Y.sum(axis=1) == 0).sum()),
        "exclusivity_check": {
            "rows_with_level_and_terminal": int(
                ((Y[:, :4].sum(axis=1) > 0) & (Y[:, 4:].sum(axis=1) > 0)).sum()),
            "rows_with_both_terminals": int(((Y[:, 4] == 1) & (Y[:, 5] == 1)).sum()),
            "policy": "configs/education_labels.yaml：学历不限/学历不明 为互斥终态 token",
        },
    }


def _rule_bias_stats(df: pd.DataFrame, max_rows: int = 60000) -> dict:
    """规则解析器 vs 伪标签的系统性偏差（诊断伪标签噪声方向）。"""
    sub = df.sample(n=min(max_rows, len(df)), random_state=20261031) if len(df) > max_rows else df
    Y = multi_hot(sub)
    pred = np.zeros_like(Y)
    for r, slot in enumerate(texts_of(sub)):
        for t in rule_predict(slot)["tokens"]:
            if t in LABEL_ORDER:
                pred[r, LABEL_ORDER.index(t)] = 1
    out = {}
    for i, name in enumerate(LABEL_ORDER):
        tp = int(((Y[:, i] == 1) & (pred[:, i] == 1)).sum())
        fp = int(((Y[:, i] == 0) & (pred[:, i] == 1)).sum())
        fn = int(((Y[:, i] == 1) & (pred[:, i] == 0)).sum())
        out[name] = {"rule_over_pred": tp + fp, "pseudo_positive": tp + fn,
                     "agreement": tp, "rule_missing_vs_pseudo": fn,
                     "rule_extra_vs_pseudo": fp}
    return {
        "sample_rows": int(len(sub)),
        "per_label": out,
        "note": ("比较对象是**伪标签**（旧线上系统输出），不是人工真值；"
                 "差值方向反映伪标签与确定性规则的系统性差异，可用于设计加权/清洗，"
                 "不能解释为规则的错误率。"),
    }


def _expr_overlaps(train: pd.DataFrame, val: pd.DataFrame, gold: pd.DataFrame) -> dict:
    tr, va, go = set(train["slot"]), set(val["slot"]), set(gold["slot"])
    return {
        "train_unique_slots": len(tr), "validation_unique_slots": len(va),
        "gold_unique_slots": len(go),
        "train_val_slot_overlap": len(tr & va),
        "val_slot_seen_in_train_ratio": round(len(va & tr) / max(len(va), 1), 6),
        "gold_slot_seen_in_train_ratio": round(len(go & tr) / max(len(go), 1), 6),
        "gold_unseen_slots": sorted(go - tr),
        "note": ("实验 A 的切分按整条输入文本(user_hash)分组，槽位表达在 train/validation 之间"
                 "高度重叠，因此实验 A 度量的是『已知表达分布』性能；未见表达泛化必须用实验 B。"),
    }


def main() -> int:
    log = setup_train_logging("analyze_learnability")
    t0 = time.time()
    data = prepare_experiment_a()
    tr, va, gold = data["train"], data["validation"], data["gold"]

    learn = {
        "generated_by": "scripts/education_training/analyze_learnability.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "task_scope": ("<学历描述> 短槽位表达的规范化/多标签归一；"
                       "不是从完整 JD 端到端抽取学历信息"),
        "inputs": {
            "primary_input_field": "slot_education_norm",
            "context_fields": ["job_title_norm", "slot_present", "user_len"],
            "raw_full_text_stored": False,
            "note": "第三阶段产物只保留槽位与脱敏字段，未保存 user 全文（隐私约束）",
        },
        "outputs": {"label_order": LABEL_ORDER, "type": "multi_label_6_tokens"},
        "counts": {
            "train_rows": int(len(tr)), "validation_rows": int(len(va)),
            "gold_rows": int(len(gold)),
            "train_unique_slots": int(tr["slot"].nunique()),
            "validation_unique_slots": int(va["slot"].nunique()),
            "gold_unique_slots": int(gold["slot"].nunique()),
            "distinct_label_combos_train": int(tr["label_tokens_json"].nunique()),
        },
        "text_length": {
            "slot_len_train": _length_stats(tr["slot_len"].tolist()),
            "user_len_train": _length_stats(tr["user_len"].astype(int).tolist()),
        },
        "expression_patterns_train": _expr_pattern_stats(tr["slot"]),
        "slot_conflicts_train": _slot_conflicts(tr),
        "slot_conflicts_validation": _slot_conflicts(va),
        "context_purity_check": _context_check(tr),
        "experiment_a_vs_b": _expr_overlaps(tr, va, gold),
    }

    noise = {
        "generated_by": "scripts/education_training/analyze_learnability.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "train_pseudo_labels": _pseudo_label_stats(tr),
        "validation_pseudo_labels": _pseudo_label_stats(va),
        "gold_labels_reference_only": _pseudo_label_stats(gold),
        "rule_vs_pseudo_bias": _rule_bias_stats(tr),
        "high_confidence_subset_definition": {
            "chosen_rule": "label_status == 'ok' 且 槽位非空 且 P(标签组合|槽位) 众数占比 >= 0.90（只用 train 统计）",
            "rationale": ("置信度来自训练集内部的标签-槽位条件一致性，与任何模型预测无关；"
                          "gold_holdout 不参与定义。"),
        },
    }

    jdump(learn, REPORT_DIR / "learnability.json")
    jdump(noise, REPORT_DIR / "label-noise.json")
    log.info("[可学习性] train=%d val=%d gold=%d 唯一槽位=%d 冲突槽位=%d",
             len(tr), len(va), len(gold), learn["counts"]["train_unique_slots"],
             learn["slot_conflicts_train"]["conflicting_slots"])
    log.info("[完成] 分析耗时 %.1fs -> %s", time.time() - t0, REPORT_DIR)
    print(json.dumps({"learnability": str(REPORT_DIR / "learnability.json"),
                      "label_noise": str(REPORT_DIR / "label-noise.json"),
                      "seconds": round(time.time() - t0, 2)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
