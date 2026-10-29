# -*- coding: utf-8 -*-
"""可信评估程序 CLI（任务书第七节）-> reports/phase4-3a/evaluation-readiness.json。

行为：
  * 无真实人工 Gold 时：blind_evaluation_status=blocked，禁止输出正式性能数值；
  * 取得冻结的人工 Gold 评估集后：计算排序指标 + 配对 Bootstrap，
    保存预测与指标以便复算（--verify 复算校验）；
  * --demo-synthetic：在合成测试池上跑通流水线，产物只写 data/independent_eval/demo/，
    全程标注 label_source=synthetic_demo，绝不冒充正式结果。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import ANNOT_DIR, PAIRS_DIR, now, read_jsonl, write_report  # noqa: E402

import numpy as np  # noqa: E402

from job_matching.annotation.freeze import assign_splits  # noqa: E402
from job_matching.core import ROOT, ensure_dir, jdump  # noqa: E402
from job_matching.independent_eval import baselines as bl  # noqa: E402
from job_matching.independent_eval.bootstrap import (  # noqa: E402
    DEFAULT_N_BOOT, DEFAULT_SEED, paired_bootstrap_vs_baseline, per_query_metric,
)
from job_matching.independent_eval.dataset import EvalSet, GoldUnavailableError  # noqa: E402
from job_matching.independent_eval.metrics import evaluate_ranking_human  # noqa: E402

EVAL_OUT = ROOT / "reports" / "phase4-3a" / "evaluation"
DEMO_OUT = ROOT / "data" / "independent_eval" / "demo"
BASELINE_NAME = "keyword_skill"


def _load_annotation_status() -> dict:
    q_path = ROOT / "reports" / "phase4-3a" / "annotation-quality.json"
    if not q_path.exists():
        return {"annotation_status": "pending", "note": "annotation-quality.json 不存在"}
    from job_matching.core import jload
    q = jload(q_path)
    return {"annotation_status": q.get("annotation_status", "pending"),
            "agreement_status": (q.get("agreement") or {}).get("status"),
            "disagreements": q.get("disagreements", {}).get("count", 0),
            "missing_annotations": q.get("missing_annotations", {})}


def readiness_report() -> dict:
    ann = _load_annotation_status()
    final_file = ANNOT_DIR / "final_labels.csv"
    labels = []
    if final_file.exists():
        import pandas as pd
        labels = pd.read_csv(final_file, dtype=str).fillna("").to_dict("records")
    judgeable = sum(1 for r in labels if str(r.get("final_relevance", "")) in ("0", "1", "2"))
    unjudgeable = sum(1 for r in labels if str(r.get("final_relevance", "")) == "unjudgeable")

    reasons = []
    if ann["annotation_status"] != "complete":
        reasons.append(f"annotation_status={ann['annotation_status']}（双人标注未完成）")
    if judgeable == 0:
        reasons.append("没有任何可判定的人工 Gold 标签")
    if ann.get("disagreements", 0) > 0:
        reasons.append(f"仍有 {ann['disagreements']} 条分歧未仲裁")
    frozen = ROOT / "data" / "independent_eval" / "frozen" / "evalset_v1" / "manifest.json"
    if not frozen.exists():
        reasons.append("正式评估集尚未冻结（data/independent_eval/frozen/evalset_v1）")

    ready = not reasons
    return {
        "generated_by": "scripts/phase4_3a/run_eval.py",
        "created_at": now(),
        "annotation_status": ann["annotation_status"],
        "blind_evaluation_status": "ready" if ready else "blocked",
        "formal_metrics_allowed": bool(ready),
        "blocking_reasons": reasons,
        "gold": {"final_labels": len(labels), "judgeable": judgeable,
                 "unjudgeable": unjudgeable},
        "evaluation_protocol": {
            "query_unit": "resume_id（同一简历下的岗位为一个查询组）",
            "metrics": ["precision@5", "recall@10", "ndcg@5", "ndcg@10", "mrr",
                        "effective_query_count"],
            "relevance_threshold": 1,
            "unjudgeable_policy": "不计入增益与分母，单独统计",
            "min_group_size": 2,
            "bootstrap": {"unit": "query(resume_id)", "n_boot": DEFAULT_N_BOOT,
                          "seed": DEFAULT_SEED,
                          "shared_resampling": True,
                          "stability_rule": "有效查询组 < 20 报告 unstable，禁止声明显著优于 Baseline"},
        },
        "model_selection": {
            "dev_split": "dev_validation", "blind_split": "blind_test",
            "final_model_selection_status": "BLOCKED",
            "note": "不得依据历史伪标签 NDCG 宣布最终生产模型",
        },
        "model_applicability": bl.applicability_report(),
        "frozen_evalset": str(frozen.relative_to(ROOT)).replace("\\", "/") if frozen.exists() else None,
    }


def _evaluate(pairs: list[dict], label_by_pair: dict[str, str], label_source: str,
              out_dir: Path, models: list[str]) -> dict:
    """对给定标签集执行评估 + 配对 Bootstrap，保存预测与指标供复算。"""
    ensure_dir(out_dir)
    eval_set = EvalSet(pairs, [{"pair_id": pid, "final_relevance": lab}
                               for pid, lab in label_by_pair.items()],
                       meta={"label_source": label_source, "annotation_status": "complete"})
    groups = eval_set.query_groups()
    pair_ids = [r["pair"]["pair_id"] for rows in groups.values() for r in rows]
    pair_index = {r["pair"]["pair_id"]: r["pair"] for rows in groups.values() for r in rows}
    group_ids = [rid for rid, rows in groups.items() for _ in rows]
    labels = [r["relevance"] for rows in groups.values() for r in rows]

    scores_by_model: dict[str, dict[str, float]] = {}
    predictions = []
    model_status = {}
    for name in models:
        try:
            scores = bl.score_with(name, [pair_index[pid] for pid in pair_ids])
        except bl.ModelUnavailableError as e:
            model_status[name] = {"status": "unavailable", "reason": str(e)}
            continue
        model_status[name] = {"status": "ok"}
        scores_by_model[name] = dict(zip(pair_ids, scores.tolist()))
        for pid, s in zip(pair_ids, scores.tolist()):
            predictions.append({"pair_id": pid, "model": name, "score": float(s)})

    metrics = {}
    for name, smap in scores_by_model.items():
        pred = [smap[pid] for pid in pair_ids]
        metrics[name] = evaluate_ranking_human(group_ids, pred, labels)

    per_query = {}
    for name, smap in scores_by_model.items():
        pred = [smap[pid] for pid in pair_ids]
        per_query[name] = per_query_metric(group_ids, pred, labels, metric="ndcg", k=5)

    bootstrap = {}
    if BASELINE_NAME in scores_by_model and len(scores_by_model) > 1:
        bootstrap = paired_bootstrap_vs_baseline(per_query, BASELINE_NAME,
                                                 metric="ndcg", k=5)
    elif BASELINE_NAME not in scores_by_model:
        bootstrap = {"status": "not_computable", "reason": f"{BASELINE_NAME} 不在可用模型集合"}

    jdump({"label_source": label_source, "predictions": predictions,
           "pair_order": pair_ids, "created_at": now()},
          out_dir / "predictions.json")
    result = {
        "label_source": label_source,
        "formal": label_source == "human_gold",
        "models": model_status,
        "metrics": metrics,
        "bootstrap_ndcg@5": bootstrap,
        "queries": {"groups": len(groups), "pairs": len(pair_ids)},
        "recompute_files": {
            "predictions": str((out_dir / "predictions.json").relative_to(ROOT)).replace("\\", "/"),
        },
    }
    jdump(result, out_dir / "metrics.json")
    return result


def run(demo: bool = False, models: list[str] | None = None) -> dict:
    ready = readiness_report()
    out = dict(ready)
    models = models or [BASELINE_NAME, "tfidf_cosine", "ridge", "gradient_boosting",
                        "mlp", "ranknet"]

    if ready["formal_metrics_allowed"]:
        from job_matching.independent_eval.dataset import load_frozen_eval_set
        es = load_frozen_eval_set(ready["frozen_evalset"])
        label_by_pair = {r["pair"]["pair_id"]: r["relevance"] for r in es.rows
                         if r["relevance"] is not None}
        out["formal_evaluation"] = _evaluate(es.pairs, label_by_pair, "human_gold",
                                             EVAL_OUT, models)
    else:
        out["formal_evaluation"] = {
            "status": "blocked",
            "note": "无真实人工 Gold：禁止输出正式性能数值（任务书第十节第 9 条）",
        }

    if demo:
        pairs = read_jsonl(PAIRS_DIR / "pairs_synthetic_v1.jsonl")
        if pairs:
            demo_labels = {p["pair_id"]: _demo_label(p) for p in pairs}
            out["synthetic_demo"] = _evaluate(pairs, demo_labels, "synthetic_demo",
                                              DEMO_OUT, [BASELINE_NAME, "tfidf_cosine"])
            out["synthetic_demo"]["warning"] = (
                "合成演示结果：label_source=synthetic_demo，仅验证评估流水线可运行，"
                "不是模型性能结论，禁止写入任何正式报告")
        else:
            out["synthetic_demo"] = {"status": "unavailable", "note": "无合成测试池"}

    write_report("evaluation-readiness.json", out)
    return out


def _demo_label(pair: dict) -> str:
    """合成演示标签（确定性，来源明确标记 synthetic_demo，绝非人工真值）。"""
    try:
        r = set(json.loads(pair.get("resume_skills") or "[]"))
        j = set(json.loads(pair.get("required_skills") or "[]"))
    except Exception:
        r, j = set(), set()
    if not r and not j:
        return "unjudgeable"
    jacc = len(r & j) / float(len(r | j))
    if jacc >= 0.4:
        return "2"
    if jacc >= 0.15:
        return "1"
    return "0"


def verify_recompute(metrics_file: Path) -> dict:
    """从保存的预测与标签复算指标（G2 要求）。"""
    from job_matching.core import jload
    m = jload(metrics_file)
    pred_path = ROOT / m["recompute_files"]["predictions"]
    pred = jload(pred_path)
    pairs_by_id = {}
    for name in ("pairs_v1.jsonl", "pairs_synthetic_v1.jsonl"):
        p = PAIRS_DIR / name
        if p.exists():
            for r in read_jsonl(p):
                pairs_by_id[r["pair_id"]] = r
    label_source = m["label_source"]
    ok = True
    checks = []
    scores = {}
    for row in pred["predictions"]:
        scores.setdefault(row["model"], {})[row["pair_id"]] = row["score"]
    # 重新构造标签（demo 或人工）
    if label_source == "human_gold":
        import pandas as pd
        labels_df = pd.read_csv(ANNOT_DIR / "final_labels.csv", dtype=str).fillna("")
        label_by_pair = dict(zip(labels_df["pair_id"], labels_df["final_relevance"]))
    else:
        label_by_pair = {pid: _demo_label(p) for pid, p in pairs_by_id.items()}
    order = pred["pair_order"]
    group_ids = [pairs_by_id[pid]["resume_id"] for pid in order]
    labels = [label_by_pair.get(pid, "") for pid in order]
    for name, smap in scores.items():
        pred_scores = [smap[pid] for pid in order]
        recomputed = evaluate_ranking_human(group_ids, pred_scores, labels)
        stored = m["metrics"].get(name, {})
        same = all(recomputed.get(f"ndcg@{k}") == stored.get(f"ndcg@{k}") for k in (5, 10))
        ok = ok and same
        checks.append({"model": name, "match": same})
    return {"ok": ok, "checks": checks, "label_source": label_source}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo-synthetic", action="store_true")
    ap.add_argument("--verify", type=str, default=None)
    args = ap.parse_args()
    if args.verify:
        res = verify_recompute(Path(args.verify))
    else:
        res = run(demo=args.demo_synthetic)
    print(json.dumps({k: res[k] for k in res
                      if k in ("blind_evaluation_status", "formal_metrics_allowed",
                               "blocking_reasons", "ok")},
                     ensure_ascii=False, indent=2))
