# -*- coding: utf-8 -*-
"""第四阶段 4.2 评估入口：对已保存模型重新评估并产出错误分析明细。

用法：
  python scripts/education_training/evaluate.py --run-dir models/education/<model>/<run_id>

行为：
  * 重载模型，重新预测 validation / gold（及实验 B 的留出集）；
  * 与训练时保存的 predictions_*.npz 逐行比对（重载一致性）；
  * 产出 evaluation.json：指标 + 逐槽位错误明细 + 重点表达专项分析。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import eval_frame, prepare_experiment_a, prepare_experiment_b, setup_train_logging  # noqa: E402
from job_matching.core import ROOT, jdump, rel  # noqa: E402
from job_matching.education.dataset import multi_hot  # noqa: E402
from job_matching.education.labels import LABEL_ORDER  # noqa: E402
from job_matching.education.predictor import EducationNormalizer  # noqa: E402

FOCUS_PATTERNS = [
    ("本科及以上", ["本科及以上"]),
    ("硕士及以上", ["硕士及以上", "硕士研究生及以上"]),
    ("大专/专科", ["大专", "专科", "中专"]),
    ("学历不限", ["不限", "学历不限"]),
    ("学历不明/空槽位", ["", "无", "无要求"]),
    ("应届/在校/实习", None),  # 按正则匹配
]
import re  # noqa: E402

FOCUS_REGEX = {"应届/在校/实习": re.compile(r"应届|在校|实习")}


def _eval_sets(run_meta: dict, data_a: dict, data_b: dict | None) -> dict[str, pd.DataFrame]:
    out = {"validation_pseudo": data_a["validation"], "gold_holdout_human": data_a["gold"]}
    if run_meta.get("experiment") == "B" and data_b is not None:
        out["holdout_unseen_slots_pseudo"] = data_b["validation"]
    return out


def _input_texts(df: pd.DataFrame, mode: str) -> list[str]:
    if mode == "slot":
        return df["slot"].astype(str).tolist()
    return [f"{s} ‖ {t}" for s, t in zip(df["slot"].astype(str),
                                         df["job_title_norm"].astype(str))]


def _slot_error_table(df: pd.DataFrame, Y_pred: np.ndarray) -> list[dict]:
    Y_true = multi_hot(df)
    rows = []
    for slot, sub in df.groupby("slot", sort=False):
        idx = sub.index.to_numpy()
        yt, yp = Y_true[idx], Y_pred[idx]
        em = np.all(yt == yp, axis=1)
        rows.append({
            "slot": slot, "rows": int(len(sub)),
            "exact_match_ratio": round(float(em.mean()), 6),
            "missing_label_counts": {LABEL_ORDER[i]: int(((yt[:, i] == 1) & (yp[:, i] == 0)).sum())
                                     for i in range(len(LABEL_ORDER))},
            "extra_label_counts": {LABEL_ORDER[i]: int(((yt[:, i] == 0) & (yp[:, i] == 1)).sum())
                                   for i in range(len(LABEL_ORDER))},
        })
    rows.sort(key=lambda r: (r["exact_match_ratio"], -r["rows"]))
    return rows


def _focus_analysis(df: pd.DataFrame, Y_pred: np.ndarray) -> dict:
    Y_true = multi_hot(df)
    out = {}
    slots = df["slot"].astype(str)
    for name, forms in FOCUS_PATTERNS:
        if forms is None:
            mask = slots.str.contains(FOCUS_REGEX[name])
        else:
            mask = slots.isin(forms)
        if not mask.any():
            out[name] = {"samples": 0}
            continue
        idx = np.where(mask.to_numpy())[0]
        yt, yp = Y_true[idx], Y_pred[idx]
        out[name] = {
            "samples": int(len(idx)),
            "exact_match_ratio": round(float(np.all(yt == yp, axis=1).mean()), 6),
            "top_slots": slots.iloc[idx].value_counts().head(6).to_dict(),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--log-name", default="")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    meta = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    log = setup_train_logging(args.log_name or f"evaluate-{meta['run_id']}")

    normalizer = EducationNormalizer.from_model_dir(run_dir, fallback_to_rules=False)
    data_a = prepare_experiment_a()
    data_b = prepare_experiment_b() if meta.get("experiment") == "B" else None
    sets = _eval_sets(meta, data_a, data_b)

    t0 = time.time()
    result = {"run_id": meta["run_id"], "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "sets": {}, "label_order": list(LABEL_ORDER)}
    stored = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    reload_diffs = {}
    for name, df in sets.items():
        texts = _input_texts(df, meta["input_mode"])
        if meta["model_type"] == "tfidf_char_ovr_logreg":
            proba = normalizer.model.predict_proba(texts)
        else:
            import torch
            from job_matching.education.trainer import evaluate_proba
            proba = evaluate_proba(normalizer.model, normalizer.tokenizer.transform(texts),
                                   torch.device("cpu"))
        pred = (proba >= normalizer.thresholds.reshape(1, -1)).astype(np.int8)
        prov = "human_gold" if "gold" in name else "pseudo_online"
        m = eval_frame(df, pred, name, prov)
        # 重载一致性：与训练时落盘的预测逐行比对
        npz_name = {"validation_pseudo": "validation_pseudo",
                    "gold_holdout_human": "gold_holdout_human",
                    "holdout_unseen_slots_pseudo": "holdout_unseen_slots"}.get(name)
        npz = run_dir / f"predictions_{npz_name}.npz" if npz_name else None
        if npz is not None and npz.exists():
            old = np.load(npz, allow_pickle=False)
            d = float(np.abs(old["proba"].astype(np.float64) - proba.astype(np.float64)).max())
            same_keys = bool((old["record_key"].astype(str) ==
                              df["record_key"].astype(str).to_numpy()).all())
            reload_diffs[name] = {"max_abs_diff": d, "record_keys_aligned": same_keys}
        m["slot_error_table"] = _slot_error_table(df, pred)
        m["focus_analysis"] = _focus_analysis(df, pred)
        result["sets"][name] = m
        log.info("[评估] %s exact=%.4f microF1=%.4f", name,
                 m["exact_match_ratio"], m["micro_f1"])
    result["reload_consistency"] = reload_diffs
    result["stored_metrics_match"] = {
        name: {"exact_match_delta": round(abs(result["sets"][name]["exact_match_ratio"]
                                              - stored[name]["exact_match_ratio"]), 9)}
        for name in result["sets"] if name in stored}
    result["seconds"] = round(time.time() - t0, 2)
    jdump(result, run_dir / "evaluation.json")
    log.info("[完成] %s -> %s", meta["run_id"], rel(run_dir / "evaluation.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
