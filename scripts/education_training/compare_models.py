# -*- coding: utf-8 -*-
"""第四阶段 4.2 模型对照：规则 / 经验映射 / TF-IDF / 字符 CNN 统一比较。

比较口径（任务书第五部分）：
  * 同一数据、同一指标定义（Exact Match / Micro / Macro P-R-F1 / Hamming / 组合错误率）；
  * 规则与经验映射基线重新计算（不手工转录历史数字），历史 gold 分数只作参考；
  * 模型 vs 经验映射基线给查询组（槽位表达）级 Bootstrap 置信区间。

产出：reports/education-training/experiment-comparison.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (MODELS_DIR, REPORT_DIR, eval_frame, prepare_experiment_a,  # noqa: E402
                    prepare_experiment_b, setup_train_logging, texts_of)
from job_matching.core import ROOT, jdump, rel  # noqa: E402
from job_matching.education.rules import (empirical_labels_from_mapping,  # noqa: E402
                                           empirical_slot_mapping, rule_labels)
from job_matching.education.dataset import multi_hot  # noqa: E402
from job_matching.education.labels import LABEL_ORDER  # noqa: E402
from job_matching.education.predictor import EducationNormalizer  # noqa: E402

BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 20261031


def _model_pred(run_dir: Path, texts: list[str]) -> np.ndarray:
    nz = EducationNormalizer.from_model_dir(run_dir, fallback_to_rules=False)
    if nz.model_type == "tfidf_char_ovr_logreg":
        proba = nz.model.predict_proba(texts)
    else:
        import torch
        from job_matching.education.trainer import evaluate_proba
        proba = evaluate_proba(nz.model, nz.tokenizer.transform(texts), torch.device("cpu"))
    return (proba >= nz.thresholds.reshape(1, -1)).astype(np.int8)


def _bootstrap_diff(y_true: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray,
                    groups: np.ndarray, n: int = BOOTSTRAP_N) -> dict:
    """按输入组（槽位表达）重采样，比较 A 相对 B 的 micro-F1 / exact-match 差异。"""
    from job_matching.education.evaluator import education_metrics
    keys = np.unique(groups)
    idx_by_key = {k: np.where(groups == k)[0] for k in keys}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    diffs_f1, diffs_em = [], []
    for _ in range(n):
        pick = rng.choice(keys, size=len(keys), replace=True)
        idx = np.concatenate([idx_by_key[k] for k in pick])
        ma = education_metrics(y_true[idx], pred_a[idx])
        mb = education_metrics(y_true[idx], pred_b[idx])
        diffs_f1.append(ma["micro_f1"] - mb["micro_f1"])
        diffs_em.append(ma["exact_match_ratio"] - mb["exact_match_ratio"])
    def ci(a):
        a = np.asarray(a, dtype=np.float64)
        return {"mean": round(float(a.mean()), 6),
                "ci95": [round(float(np.percentile(a, 2.5)), 6),
                         round(float(np.percentile(a, 97.5)), 6)]}
    return {"n_resamples": int(n), "unit": "input_group(slot expression)",
            "micro_f1_diff": ci(diffs_f1), "exact_match_diff": ci(diffs_em)}


def _latency(nz: EducationNormalizer, texts: list[str], repeats: int = 3) -> dict:
    import time as _t
    ts = []
    for _ in range(repeats):
        t0 = _t.perf_counter()
        nz.batch(texts)
        ts.append(_t.perf_counter() - t0)
    per = [t / len(texts) * 1000 for t in ts]
    return {"samples": len(texts), "repeats": repeats,
            "mean_ms_per_sample": round(float(np.mean(per)), 4),
            "total_seconds_mean": round(float(np.mean(ts)), 3)}


def main() -> int:
    log = setup_train_logging("compare_models")
    data_a = prepare_experiment_a()
    data_b = prepare_experiment_b()
    va, gold = data_a["validation"], data_a["gold"]
    tr = data_a["train"]

    t0 = time.time()
    result = {"generated_by": "scripts/education_training/compare_models.py",
              "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "label_order": list(LABEL_ORDER),
              "methods": {}, "bootstrap": {},
              "history_note": ("第三阶段基线数字见 reports/baselines/education-baselines.md，"
                               "本表为同口径重算；gold 为一次性评估参考，不用于模型选择。")}

    eval_sets = {"validation_pseudo": va, "gold_holdout_human": gold,
                 "holdout_unseen_slots_pseudo": data_b["validation"]}

    # ---- 基线（规则 / 经验映射），只在 train 上统计经验映射
    mapping = empirical_slot_mapping(tr, slot_col="slot", label_col="label_tokens_json")
    for name, fn in [("rule_baseline", rule_labels),
                     ("empirical_slot_baseline",
                      lambda s: empirical_labels_from_mapping(s, mapping))]:
        entry = {}
        for set_name, df in eval_sets.items():
            if set_name == "holdout_unseen_slots_pseudo" and name == "empirical_slot_baseline":
                pass  # 经验映射对未见槽位会回退规则，正好体现泛化能力，保留
            pred = fn(texts_of(df))
            prov = "human_gold" if "gold" in set_name else "pseudo_online"
            entry[set_name] = eval_frame(df, pred, set_name, prov)
        result["methods"][name] = {"type": "baseline", "sets": entry}
        log.info("[基线] %s val exact=%.4f microF1=%.4f", name,
                 entry["validation_pseudo"]["exact_match_ratio"],
                 entry["validation_pseudo"]["micro_f1"])

    emp_val_pred = empirical_labels_from_mapping(texts_of(va), mapping)
    y_va = multi_hot(va)
    groups_va = va["slot"].to_numpy()

    # ---- 训练模型
    for model_dir in sorted(MODELS_DIR.glob("*/*")):
        if not (model_dir / "manifest.json").exists():
            continue
        meta = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
        if "smoke" in meta["run_id"]:
            continue
        nz = EducationNormalizer.from_model_dir(model_dir, fallback_to_rules=False)
        entry = {"type": "trained_model", "model_type": meta["model_type"],
                 "run_id": meta["run_id"], "experiment": meta["experiment"],
                 "input_mode": meta["input_mode"],
                 "sample_weight_strategy": meta["sample_weight_strategy"],
                 "model_bytes": int((model_dir / ("model.pkl" if meta["model_type"].startswith("tfidf")
                                                  else "model.pt")).stat().st_size),
                 "n_parameters": meta.get("n_parameters") or
                 meta.get("model_description", {}).get("n_parameters"),
                 "sets": {}}
        for set_name, df in eval_sets.items():
            if meta["experiment"] != "B" and set_name == "holdout_unseen_slots_pseudo":
                continue
            if meta["experiment"] == "B" and set_name == "validation_pseudo":
                pass
            texts = (df["slot"].astype(str).tolist() if meta["input_mode"] == "slot"
                     else [f"{s} ‖ {t}" for s, t in zip(df["slot"].astype(str),
                                                        df["job_title_norm"].astype(str))])
            pred = _model_pred(model_dir, texts)
            prov = "human_gold" if "gold" in set_name else "pseudo_online"
            entry["sets"][set_name] = eval_frame(df, pred, set_name, prov)
        # 延迟：固定 200 条输入
        probe = texts_of(va)[:200]
        entry["inference_latency"] = _latency(nz, probe)
        # Bootstrap：模型 vs 经验映射（validation，按输入组重采样）
        va_texts = (texts_of(va) if meta["input_mode"] == "slot"
                    else [f"{s} ‖ {t}" for s, t in zip(va["slot"].astype(str),
                                                       va["job_title_norm"].astype(str))])
        pred_va = _model_pred(model_dir, va_texts)
        result["bootstrap"][meta["run_id"]] = _bootstrap_diff(
            y_va, pred_va, emp_val_pred, groups_va)
        result["methods"][meta["run_id"]] = entry
        log.info("[模型] %s val exact=%.4f microF1=%.4f gold exact=%.4f",
                 meta["run_id"], entry["sets"]["validation_pseudo"]["exact_match_ratio"],
                 entry["sets"]["validation_pseudo"]["micro_f1"],
                 entry["sets"]["gold_holdout_human"]["exact_match_ratio"])

    result["seconds"] = round(time.time() - t0, 2)
    jdump(result, REPORT_DIR / "experiment-comparison.json")
    log.info("[完成] 对照实验汇总 -> %s（%.1fs）", rel(REPORT_DIR / "experiment-comparison.json"),
             result["seconds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
