# -*- coding: utf-8 -*-
"""第四阶段 4.1：对已训练模型做确认评估（validation / test）。

用法：
    python scripts/model_training/evaluate.py --run-dir models/matching/ridge/candidate_cold/<run_id>
    python scripts/model_training/evaluate.py --run-dir ... --subset test

纪律：
  * test 只在模型方案与超参数锁定后评估一次；不在此处调参；
  * 评估口径与第三阶段零训练 Baseline 完全一致（metrics_ranking）；
  * 预测结果落盘 predictions_<subset>.npz，供 Bootstrap 与错误分析复用。
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
from common import predict_scores, setup_train_logging  # noqa: E402
from job_matching.core import ROOT, jdump  # noqa: E402
from job_matching.evaluation.metrics import ranking_report  # noqa: E402
from job_matching.models.base import get_model_module  # noqa: E402
from job_matching.training.config_train import get_train_config  # noqa: E402
from job_matching.training.dataset import load_pairs, load_protocol  # noqa: E402
from job_matching.training.feature_map import FeatureMap  # noqa: E402


def load_model(run_dir: Path, model_name: str):
    mod = get_model_module(model_name)
    cls = {"ridge": "RidgeModel", "gradient_boosting": "GradientBoostingModel",
           "mlp": "MLPModel", "ranknet": "RankNetModel"}[model_name]
    return getattr(mod, cls).load(run_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description="模型确认评估")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--subset", nargs="+", default=["validation", "test"],
                    choices=["validation", "test"])
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    log = setup_train_logging(f"evaluate-{run_dir.parent.parent.name}-{run_dir.name}")

    with open(run_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    model_name = manifest["model_name"]
    protocol = manifest["protocol"]
    cfg = get_train_config(model_name)

    fm = FeatureMap.load(run_dir / "feature_map.json")
    model = load_model(run_dir, model_name)

    pairs = load_pairs()
    idx = load_protocol(protocol)

    runs_dir = ROOT / "reports" / "model-training" / "runs"
    record_path = None
    record = None
    for rec_path in runs_dir.glob("*.json"):
        with open(rec_path, "r", encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("run_id") == manifest["run_id"]:
            record_path, record = rec_path, rec
            break

    for subset in args.subset:
        frame = pairs.subset(idx[subset])
        X = fm.transform(frame)
        t0 = time.time()
        pred = predict_scores(model, X, device=args.device)
        latency = (time.time() - t0) / max(len(frame), 1)

        report = ranking_report(frame["candidate_id"].to_numpy(), pred, frame,
                                ks=cfg.ks, min_group_size=cfg.min_group_size,
                                tie_eps=cfg.pairwise_tie_eps)
        report["rows"] = int(len(frame))
        report["subset"] = subset
        report["protocol"] = protocol
        report["inference_seconds_per_pair"] = round(latency, 8)

        np.savez_compressed(run_dir / f"predictions_{subset}.npz",
                            pair_index=frame["pair_index"].to_numpy(np.int64),
                            pred_scores=pred.astype(np.float64))
        jdump(report, run_dir / f"metrics_{subset}.json")

        if record is not None:
            record.setdefault("evaluations", {})[subset] = {
                "ndcg_at_5_score": report["gain_modes"]["score"]["size_ge_2"]["ndcg@5"],
                "ndcg_at_10_score": report["gain_modes"]["score"]["size_ge_2"]["ndcg@10"],
                "ndcg_at_5_ordinal": report["gain_modes"]["ordinal"]["size_ge_2"]["ndcg@5"],
                "ndcg_at_10_ordinal": report["gain_modes"]["ordinal"]["size_ge_2"]["ndcg@10"],
                "pairwise_accuracy": report["pairwise"]["pairwise_accuracy"],
                "rows": int(len(frame)),
                "queries_evaluated": report["gain_modes"]["score"]["size_ge_2"]["queries_evaluated"],
                "inference_seconds_per_pair": round(latency, 8),
                "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "test_disclosure": ("test 已在第三阶段用于零训练基线比较；"
                                    "本次仅做方案锁定后的确认评估" if subset == "test" else None),
            }
            jdump(record, record_path)

        log.info("[eval] %s %s rows=%d ndcg@5(score)=%s ndcg@5(ordinal)=%s pairwise=%s",
                 manifest["run_id"], subset, len(frame),
                 fmt(report["gain_modes"]["score"]["size_ge_2"]["ndcg@5"]),
                 fmt(report["gain_modes"]["ordinal"]["size_ge_2"]["ndcg@5"]),
                 fmt(report["pairwise"]["pairwise_accuracy"]))
    return 0


def fmt(v) -> str:
    return "不可评估" if v is None else f"{float(v):.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
