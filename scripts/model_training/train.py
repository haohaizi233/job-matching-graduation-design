# -*- coding: utf-8 -*-
"""第四阶段 4.1：训练单个匹配模型（Ridge / GradientBoosting / MLP / RankNet）。

用法：
    python scripts/model_training/train.py --model ridge --protocol candidate_cold
    python scripts/model_training/train.py --model mlp --protocol candidate_cold --smoke
    python scripts/model_training/train.py --model ranknet --protocol candidate_cold \
        --drop-group skill --tag ablation-skill
    python scripts/model_training/train.py --model mlp --protocol candidate_cold \
        --resume models/matching/mlp/candidate_cold/<run_id>

纪律：
  * 超参数只在 train/validation 上搜索，训练流程不读取 test；
  * 特征只来自 configs/feature_policy.yaml 任务白名单（policy 强制检查）；
  * 每个 run_id 一个独立输出目录，互不覆盖。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402
from common import (  # noqa: E402
    prepare_data, predict_scores, setup_train_logging, write_run_record,
)
from job_matching.core import ROOT, jdump, sha256_file  # noqa: E402
from job_matching.models.base import get_model_module  # noqa: E402
from job_matching.training import checkpoints as CK  # noqa: E402
from job_matching.training.config_train import get_train_config  # noqa: E402
from job_matching.training.trainer import resolve_device, set_seed  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="训练匹配模型")
    ap.add_argument("--model", required=True,
                    choices=["ridge", "gradient_boosting", "mlp", "ranknet"])
    ap.add_argument("--protocol", required=True,
                    choices=["candidate_cold", "job_cold", "double_cold"])
    ap.add_argument("--tag", default="final")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--drop-group", action="append", default=[],
                    help="消融：整体移除一个特征组（skill/position/category/experience）")
    ap.add_argument("--smoke", action="store_true", help="小批量冒烟测试（2000 行 / 2 epoch）")
    ap.add_argument("--resume", default="", help="从已有 run 目录恢复训练")
    args = ap.parse_args()

    log_name = f"{args.model}-{args.protocol}-{args.tag}"
    log = setup_train_logging(log_name)
    cfg = get_train_config(args.model)
    seed = cfg.seed("global")
    set_seed(seed)

    drop_groups = tuple(args.drop_group)
    smoke_rows = 2000 if args.smoke else None
    if args.smoke:
        cfg.model["search_limit"] = 1
        if args.model in ("mlp", "ranknet"):
            # torch 系模型才使用 epoch / 早停参数；sklearn 估计器不认识这些键
            cfg.model.setdefault("params", {})
            cfg.model["params"]["epochs"] = 2
            cfg.model["params"]["early_stopping_patience"] = 2

    rid = args.run_id or CK.run_id(args.model, args.protocol,
                                   args.tag + ("-smoke" if args.smoke else ""))
    run_dir = CK.run_dir_for(args.model, args.protocol, rid)
    log.info("[run] id=%s model=%s protocol=%s drop=%s smoke=%s", rid, args.model,
             args.protocol, drop_groups or "-", bool(args.smoke))

    t0 = time.time()
    data = prepare_data(cfg, args.protocol, drop_groups=drop_groups, smoke_rows=smoke_rows)
    log.info("[data] train=%d val=%d features=%d groups=%s",
             len(data["train_frame"]), len(data["val_frame"]),
             data["feature_map"].n_features, data["feature_map"].groups_enabled)

    device = resolve_device(prefer_gpu=bool(cfg.common["resources"]["prefer_gpu"]),
                            gpu_budget_mb=int(cfg.common["resources"]["gpu_budget_mb"]))
    log.info("[device] %s", device)

    mod = get_model_module(args.model)
    result = mod.train_model(
        model_cfg=cfg.model,
        X_train=data["X_train"], y_train=data["y_train"],
        X_val=data["X_val"], groups_train=data["groups_train"],
        groups_val=data["groups_val"], val_frame=data["val_frame"],
        feature_map=data["feature_map"], train_cfg=cfg,
        device=device, run_dir=run_dir, seed=seed,
        resume_from=(Path(args.resume) / "checkpoint_best.pt") if args.resume else None,
    )

    # ---- 产物保存
    model = result["model"]
    model_files = model.save(run_dir)
    data["feature_map"].save(run_dir / "feature_map.json")
    CK.save_config_snapshot(run_dir, cfg.model, cfg.common)
    if result.get("history"):
        jdump(result["history"], run_dir / "history.json")
    val_report = result["val_report"]
    metrics = {
        "selection_metric": cfg.selection_metric,
        "selection_value": result["selection_value"],
        "best_params": result.get("best_params"),
        "search": result.get("search"),
        "validation": val_report,
        "smoke": bool(args.smoke),
    }
    jdump(metrics, run_dir / "metrics.json")

    rows = {"train": int(len(data["train_frame"])), "validation": int(len(data["val_frame"]))}
    manifest = CK.write_manifest(
        run_dir, run_id_=rid, model_name=args.model, protocol=args.protocol,
        dataset_version=cfg.dataset_version,
        feature_map_summary={"groups_enabled": list(data["feature_map"].groups_enabled),
                             "groups_dropped": list(drop_groups),
                             "n_features": data["feature_map"].n_features,
                             "raw_columns": data["feature_map"].raw_columns_},
        rows=rows, params_count=int(model.param_count()), seed=seed,
        seconds=result["train_seconds"],
        extra={"device": (str(device) if args.model in ("mlp", "ranknet") else "cpu"),
               "best_epoch": result.get("best_epoch"),
               "ablation_dropped_groups": list(drop_groups),
               "smoke": bool(args.smoke)},
    )

    record = {
        "run_id": rid,
        "model_name": args.model,
        "protocol": args.protocol,
        "tag": args.tag,
        "ablation_dropped_groups": list(drop_groups),
        "smoke": bool(args.smoke),
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "selection_metric": cfg.selection_metric,
        "selection_value": result["selection_value"],
        "best_params": result.get("best_params"),
        "train_seconds": result["train_seconds"],
        "device": (str(device) if args.model in ("mlp", "ranknet") else "cpu"),
        "rows": rows,
        "n_features": data["feature_map"].n_features,
        "model_parameters": int(model.param_count()),
        "validation": {
            "ndcg_at_5_score": val_report["gain_modes"]["score"]["size_ge_2"]["ndcg@5"],
            "ndcg_at_10_score": val_report["gain_modes"]["score"]["size_ge_2"]["ndcg@10"],
            "ndcg_at_5_ordinal": val_report["gain_modes"]["ordinal"]["size_ge_2"]["ndcg@5"],
            "ndcg_at_10_ordinal": val_report["gain_modes"]["ordinal"]["size_ge_2"]["ndcg@10"],
            "pairwise_accuracy": val_report["pairwise"]["pairwise_accuracy"],
        },
        "evaluations": {},
        "model_files": model_files,
        "manifest_sha256": sha256_file(run_dir / "manifest.json"),
        "test_used_during_training": False,
    }
    write_run_record(record)
    log.info("[done] %s selection=%s（%.6f） train_seconds=%.1f -> %s",
             rid, cfg.selection_metric, result["selection_value"],
             result["train_seconds"], record["run_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
