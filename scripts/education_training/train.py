# -*- coding: utf-8 -*-
"""第四阶段 4.2 训练入口：Model A（TF-IDF+OvR-LR）/ Model B（字符 CNN）。

实验口径：
  --experiment A  已知表达分布（沿用第三阶段 train/validation 切分）
  --experiment B  未见过表达泛化（train 内部按槽位留出）

阈值口径：
  A：阈值只在 validation 上选择（任务书要求），因此 validation 指标相对乐观，
     同时报告固定 0.5 阈值的指标作为对照。
  B：阈值在实验 A 的 validation 上选择，留出的未见表达集合不参与训练与阈值选择。

约束：gold_holdout 只做一次性最终评估，不参与任何拟合/调参/模型选择。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (LABEL_ORDER, MODELS_DIR, eval_frame, model_dir,  # noqa: E402
                    new_run_id, prepare_experiment_a, prepare_experiment_b,
                    setup_train_logging, slot_weight_vec, texts_of, write_run_record)
from job_matching.core import ROOT, jdump, rel  # noqa: E402
from job_matching.education.dataset import (class_weights, high_confidence_subset,  # noqa: E402
                                            multi_hot)
from job_matching.education.neural_model import CharCNN  # noqa: E402
from job_matching.education.tfidf_model import TfidfEducationModel  # noqa: E402
from job_matching.education.tokenizer import CharTokenizer  # noqa: E402
from job_matching.education.trainer import (evaluate_proba, seed_everything,  # noqa: E402
                                            select_thresholds, train_neural)

CFG_TFIDF = ROOT / "configs" / "training" / "education_tfidf.yaml"
CFG_NN = ROOT / "configs" / "training" / "education_neural.yaml"


def _load_yaml(p: Path) -> dict:
    import yaml
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _input_texts(df, mode: str) -> list[str]:
    if mode == "slot":
        return texts_of(df)
    if mode == "slot_title":
        return [f"{s} ‖ {t}" for s, t in zip(df["slot"].astype(str),
                                             df["job_title_norm"].astype(str))]
    raise ValueError(f"未知输入模式: {mode}")


def _pred_metrics(df, Y_pred, set_name, provenance):
    return eval_frame(df, Y_pred, set_name, provenance)


def _save_predictions(out: Path, name: str, record_keys, proba, pred) -> None:
    np.savez_compressed(out / f"predictions_{name}.npz",
                        record_key=np.asarray([str(x) for x in record_keys]),
                        proba=np.asarray(proba, dtype=np.float32),
                        pred=np.asarray(pred, dtype=np.int8))


# ------------------------------------------------------------------ 训练
def train_tfidf(args, data, tune_df, log) -> dict:
    """C 与阈值都只在阈值选择集合（tune_df）上确定；评估集不参与模型选择。"""
    cfg = _load_yaml(CFG_TFIDF)
    tr = data["train"]
    X_tr = _input_texts(tr, args.input)
    Y_tr = multi_hot(tr)
    X_tune, Y_tune = _input_texts(tune_df, args.input), multi_hot(tune_df)
    sw = slot_weight_vec(tr, args.weights)

    best = None
    grid_log = []
    for C in cfg["model"]["classifier"]["C_grid"]:
        m = TfidfEducationModel(ngram_min=cfg["model"]["vectorizer"]["ngram_range"][0],
                                ngram_max=cfg["model"]["vectorizer"]["ngram_range"][1],
                                C=float(C), max_iter=cfg["model"]["classifier"]["max_iter"],
                                min_df=cfg["model"]["vectorizer"]["min_df"])
        t0 = time.time()
        m.fit(X_tr, Y_tr, sample_weight=sw)
        proba_tune = m.predict_proba(X_tune)
        th = select_thresholds(Y_tune, proba_tune)
        pred_tune = (proba_tune >= th["thresholds"].reshape(1, -1)).astype(np.int8)
        micro = _micro_f1(Y_tune, pred_tune)
        grid_log.append({"C": float(C), "seconds": round(time.time() - t0, 2),
                         "tune_micro_f1": round(micro, 6),
                         "thresholds": [round(float(x), 3) for x in th["thresholds"]]})
        log.info("[TF-IDF] C=%.2f 训练 %.1fs tune_microF1=%.4f", float(C),
                 time.time() - t0, micro)
        if best is None or micro > best["micro"]:
            best = {"micro": micro, "C": float(C), "model": m, "th": th}
    assert best is not None
    m, th = best["model"], best["th"]
    m.thresholds = th["thresholds"]
    return {"model": m, "thresholds": th, "grid_log": grid_log,
            "selection": {"metric": "micro_f1_on_threshold_tuning_set",
                          "best_C": best["C"], "best_tune_micro_f1": round(best["micro"], 6)},
            "train_seconds": round(sum(g["seconds"] for g in grid_log), 2)}


def train_charcnn(args, data, tune_df, log, device) -> dict:
    import torch
    cfg = _load_yaml(CFG_NN)
    tr, va = data["train"], data["validation"]
    tok = CharTokenizer(max_len=cfg["model"]["tokenizer"]["max_len"])
    tok.fit(_input_texts(tr, args.input))
    X_tr = torch.from_numpy(tok.transform(_input_texts(tr, args.input)))
    X_va = torch.from_numpy(tok.transform(_input_texts(va, args.input)))
    X_tune = torch.from_numpy(tok.transform(_input_texts(tune_df, args.input)))
    Y_tr, Y_va, Y_tune = multi_hot(tr), multi_hot(va), multi_hot(tune_df)
    sw = slot_weight_vec(tr, args.weights)
    pw = class_weights(tr) if cfg["model"]["class_weight"] == "pos_weight" else None

    seed_everything(cfg["seeds"]["model"])  # 必须在权重初始化之前固定随机源
    model = CharCNN(tok.vocab_size,
                    emb_dim=cfg["model"]["architecture"]["embedding_dim"],
                    n_filters=cfg["model"]["architecture"]["n_filters"],
                    kernel_size=cfg["model"]["architecture"]["kernel_size"],
                    dropout=cfg["model"]["architecture"]["dropout"]).to(device)
    p = cfg["model"]["params"]
    info = train_neural(model, X_tr, torch.from_numpy(Y_tr.astype(np.float32)),
                        X_tune, torch.from_numpy(Y_tune.astype(np.float32)),
                        device=device, epochs=p["epochs"], batch_size=p["batch_size"],
                        lr=p["learning_rate"], weight_decay=p["weight_decay"],
                        patience=p["early_stopping_patience"],
                        monitor=p.get("early_stopping_monitor", "val_loss"),
                        sample_weight=sw, pos_weight=pw,
                        seed=cfg["seeds"]["model"], log=log)
    proba_tune = evaluate_proba(model, X_tune, device)
    th = select_thresholds(Y_tune, proba_tune)
    return {"model": model, "tokenizer": tok, "thresholds": th,
            "train_info": info, "grid_log": [],
            "selection": {"metric": "micro_f1_on_threshold_tuning_set(early_stopping)",
                          "best_tune_micro_f1_fixed05": info["best_val_micro_f1_fixed05"]},
            "train_seconds": info["seconds"]}


def _micro_f1(yt, yp) -> float:
    tp = int(((yt == 1) & (yp == 1)).sum())
    fp = int(((yt == 0) & (yp == 1)).sum())
    fn = int(((yt == 1) & (yp == 0)).sum())
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return 2 * pr * rc / (pr + rc) if pr + rc else 0.0


# ------------------------------------------------------------------ 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["tfidf", "charcnn"], required=True)
    ap.add_argument("--experiment", choices=["A", "B"], default="A")
    ap.add_argument("--input", choices=["slot", "slot_title"], default="slot")
    ap.add_argument("--weights", choices=["none", "slot_balanced", "conflict_aware"],
                    default="none")
    ap.add_argument("--subset", choices=["all", "high_conf"], default="all",
                    help="high_conf=高置信度子集训练（只筛训练集，评估集不变）")
    ap.add_argument("--tag", default="")
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    tag = args.tag or f"{args.model}-{args.input}-{args.weights}-exp{args.experiment}"
    run_id = new_run_id(args.model, tag)
    out = model_dir(args.model, run_id)
    log = setup_train_logging(f"train-{run_id}")
    log.info("[开始] run=%s model=%s exp=%s input=%s weights=%s", run_id,
             args.model, args.experiment, args.input, args.weights)

    data = prepare_experiment_a(smoke_rows=args.smoke or None)
    if args.experiment == "B":
        data_b = prepare_experiment_b(smoke_rows=args.smoke or None)
        train_df, eval_df = data_b["train"], data_b["validation"]
        holdout_info = data_b["holdout_info"]
    else:
        train_df, eval_df = data["train"], data["validation"]
        holdout_info = None
    subset_info = None
    if args.subset == "high_conf":
        train_df, subset_info = high_confidence_subset(train_df)
        log.info("[子集] 高置信度子集训练行数 %d -> %d（丢弃 %d）",
                 subset_info["rows_before"], subset_info["rows_after"],
                 subset_info["rows_before"] - subset_info["rows_after"])
    data_train = {"train": train_df, "validation": eval_df}

    # 阈值选择集合：A 用自身 validation；B 用实验 A 的 validation（与训练/留出均不重叠）
    tune_df = data["validation"] if args.experiment == "B" else eval_df
    tune_name = "validation_pseudo(实验A)" if args.experiment == "B" else "validation_pseudo"

    if args.model == "tfidf":
        fit = train_tfidf(args, data_train, tune_df, log)
    else:
        import torch
        device = torch.device(args.device if (args.device != "cuda"
                                              and torch.cuda.is_available()) else
                              ("cuda" if torch.cuda.is_available() else "cpu"))
        fit = train_charcnn(args, data_train, tune_df, log, device)

    model, th = fit["model"], fit["thresholds"]

    # ---- 保存模型
    if args.model == "tfidf":
        saved = model.save(out)
        artifacts = ["model.pkl"]
    else:
        saved = model.save(out / "model.pt",
                           extra={"run_id": run_id, "thresholds": th["thresholds"].tolist()})
        model.save(out / "checkpoint_best.pt", extra={"kind": "best_checkpoint"})
        fit["tokenizer"].save(out / "tokenizer.json")
        artifacts = ["model.pt", "checkpoint_best.pt", "tokenizer.json"]

    # ---- 评估（validation / 留出 / gold，一次性）
    device = fit.get("train_info", {}).get("device", "cpu")

    def _proba(df):
        texts = _input_texts(df, args.input)
        if args.model == "tfidf":
            return model.predict_proba(texts)
        import torch
        return evaluate_proba(model, fit["tokenizer"].transform(texts), device)

    metrics = {}
    for name, df, prov in [("validation_pseudo", data["validation"], "pseudo_online"),
                           ("gold_holdout_human", data["gold"], "human_gold")]:
        proba = _proba(df)
        pred = (proba >= np.asarray(th["thresholds"]).reshape(1, -1)).astype(np.int8)
        metrics[name] = _pred_metrics(df, pred, name, prov)
        metrics[name]["fixed_05"] = _pred_metrics(
            df, (proba >= 0.5).astype(np.int8), name + "@0.5", prov)
        _save_predictions(out, name, df["record_key"], proba, pred)
    if args.experiment == "B":
        df_ho = data_b["validation"]
        proba = _proba(df_ho)
        pred = (proba >= np.asarray(th["thresholds"]).reshape(1, -1)).astype(np.int8)
        metrics["holdout_unseen_slots_pseudo"] = _pred_metrics(
            df_ho, pred, "holdout_unseen_slots_pseudo", "pseudo_online")
        metrics["holdout_unseen_slots_pseudo"]["fixed_05"] = _pred_metrics(
            df_ho, (proba >= 0.5).astype(np.int8), "holdout_unseen_slots_pseudo@0.5",
            "pseudo_online")
        _save_predictions(out, "holdout_unseen_slots", df_ho["record_key"], proba, pred)

    # ---- manifest / config / 阈值 / 历史
    manifest = {
        "run_id": run_id, "model_type": ("tfidf_char_ovr_logreg" if args.model == "tfidf"
                                         else "char_cnn"),
        "model_version": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "experiment": args.experiment,
        "experiment_meaning": ("A=已知表达分布（第三阶段固定切分）；"
                               "B=未见过槽位表达泛化（train 内部按槽位留出）"),
        "input_mode": args.input,
        "sample_weight_strategy": args.weights,
        "subset": args.subset,
        "subset_info": subset_info,
        "label_order": list(LABEL_ORDER),
        "thresholds": [float(x) for x in th["thresholds"]],
        "threshold_detail": th["detail"],
        "threshold_selected_on": tune_name,
        "selection": fit["selection"],
        "data": {
            "train_rows": int(len(train_df)), "eval_rows": int(len(eval_df)),
            "train_unique_slots": int(train_df["slot"].nunique()),
            "eval_unique_slots": int(eval_df["slot"].nunique()),
            "threshold_tuning_rows": int(len(tune_df)),
            "split_manifest": "data/splits/education/manifest.json",
            "dataset_version_note": "数据版本见 reports/phase3-preprocessing-summary.json（dv-0ce28fa6b560）",
        },
        "holdout_info": holdout_info,
        "train_slot_vocab": sorted(train_df["slot"].astype(str).unique().tolist()),
        "artifacts": artifacts + ["manifest.json", "config.json", "metrics.json",
                                  "thresholds.json", "feature_map.json", "history.json"],
        "saved": saved,
        "gold_policy": "gold_holdout 只做一次性最终评估；未参与训练、阈值选择与模型选择",
    }
    if args.model == "charcnn":
        manifest["train_info"] = fit["train_info"]
        manifest["n_parameters"] = fit["model"].n_parameters
    else:
        manifest["train_seconds"] = fit["train_seconds"]
        manifest["model_description"] = fit["model"].describe()

    jdump(manifest, out / "manifest.json")
    jdump(_load_yaml(CFG_TFIDF if args.model == "tfidf" else CFG_NN), out / "config.json")
    jdump({"thresholds": {LABEL_ORDER[i]: float(th["thresholds"][i])
                          for i in range(len(LABEL_ORDER))},
           "detail": th["detail"], "selected_on": tune_name}, out / "thresholds.json")
    jdump(metrics, out / "metrics.json")
    jdump({"grid_log": fit["grid_log"],
           "train_info": fit.get("train_info", {})}, out / "history.json")
    jdump({"input_mode": args.input, "label_order": list(LABEL_ORDER),
           "feature_source": "slot_education_norm" + (" + job_title_norm" if args.input == "slot_title" else ""),
           "tokenizer_vocab_size": getattr(fit.get("tokenizer"), "vocab_size", None),
           "tfidf_features": fit["model"].describe().get("n_tfidf_features")
           if args.model == "tfidf" else None}, out / "feature_map.json")

    record = {"run_id": run_id, "model": args.model, "experiment": args.experiment,
              "input_mode": args.input, "weights": args.weights,
              "created_at": manifest["created_at"],
              "val_micro_f1": metrics["validation_pseudo"]["micro_f1"],
              "val_exact_match": metrics["validation_pseudo"]["exact_match_ratio"],
              "gold_micro_f1": metrics["gold_holdout_human"]["micro_f1"],
              "gold_exact_match": metrics["gold_holdout_human"]["exact_match_ratio"],
              "model_dir": rel(out)}
    if args.experiment == "B":
        record["holdout_micro_f1"] = metrics["holdout_unseen_slots_pseudo"]["micro_f1"]
        record["holdout_exact_match"] = metrics["holdout_unseen_slots_pseudo"]["exact_match_ratio"]
    write_run_record(record)
    log.info("[完成] run=%s val_microF1=%.4f gold_microF1=%.4f -> %s", run_id,
             record["val_micro_f1"], record["gold_micro_f1"], rel(out))
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
