# -*- coding: utf-8 -*-
"""第四阶段 4.1：模型产物验证（保存/加载一致性、独立推理、无标签依赖）。

用法：
    python scripts/model_training/verify_models.py

产出：reports/model-training/model-verification.json
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
from job_matching.core import ROOT, ensure_dir, jdump  # noqa: E402
from job_matching.inference.predictor import MatchPredictor  # noqa: E402
from job_matching.models.base import get_model_module  # noqa: E402
from job_matching.policy import forbidden_for_task  # noqa: E402
from job_matching.training.dataset import load_pairs  # noqa: E402
from job_matching.training.feature_map import (  # noqa: E402
    FeatureMap, compute_pair_raw_features,
)

OUT = ROOT / "reports" / "model-training"
FORBIDDEN = sorted(forbidden_for_task("match_ranking"))


def load_model(run_dir: Path, model_name: str):
    mod = get_model_module(model_name)
    cls = {"ridge": "RidgeModel", "gradient_boosting": "GradientBoostingModel",
           "mlp": "MLPModel", "ranknet": "RankNetModel"}[model_name]
    return getattr(mod, cls).load(run_dir)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dirs", nargs="*", default=[])
    args = ap.parse_args()
    log = setup_train_logging("verify_models")

    run_dirs = [Path(d if Path(d).is_absolute() else ROOT / d) for d in args.run_dirs]
    if not run_dirs:
        run_dirs = sorted((ROOT / "models" / "matching").glob("*/*/*/manifest.json"))
        run_dirs = [p.parent for p in run_dirs]
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        log.info("[%s] %s | %s", "PASS" if ok else "FAIL", name, detail)

    # ---- 1. 单 pair 特征构建与第三阶段 features_pairs.csv 一致
    pairs = load_pairs(with_skill_json=True)
    fr = pairs.frame
    sample = fr.iloc[list(range(0, len(fr), max(len(fr) // 50, 1)))]
    max_err, n_checked = 0.0, 0
    for _, row in sample.iterrows():
        resume = {"candidate_id": str(row["candidate_id"]),
                  "target_position_norm": row["target_position_norm"],
                  "skills_canonical_json": row["cv_skills_canonical_json"],
                  "inferred_category": row["inferred_category"],
                  "years_experience": row["years_experience"]}
        job = {"job_id": int(row["job_id"]), "job_title_norm": row["job_title_norm"],
               "category": row["job_category"],
               "skills_canonical_json": row["job_skills_canonical_json"]}
        raw = compute_pair_raw_features(resume, job)
        for col in ("skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
                    "position_token_overlap", "category_match", "years_experience",
                    "both_skills_empty"):
            ref = float(row[col])
            got = float(raw[col])
            max_err = max(max_err, abs(ref - got))
        n_checked += 1
    record("single_pair_features_match_pipeline", max_err < 1e-9,
           f"抽样 {n_checked} 个 pair，数值最大绝对误差 {max_err:.2e}")

    # ---- 2. 单 pair 特征只含白名单列（无标签依赖）
    raw_keys = set(compute_pair_raw_features(
        {"target_position_norm": "x", "skills_canonical_json": "[]",
         "inferred_category": "A", "years_experience": 1},
        {"job_title_norm": "y", "category": "B", "skills_canonical_json": "[]"}))
    hit = sorted(raw_keys & set(FORBIDDEN))
    record("independent_inference_no_label_fields", not hit,
           f"单 pair 特征键 {sorted(raw_keys)}；命中禁止字段 {hit}")

    for run_dir in run_dirs:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        m_name, rid = manifest["model_name"], manifest["run_id"]
        fm = FeatureMap.load(run_dir / "feature_map.json")
        model = load_model(run_dir, m_name)

        # ---- 3. 特征列白名单合规
        hit = sorted(set(fm.raw_columns_) & set(FORBIDDEN))
        record(f"{rid}:feature_columns_policy", not hit,
               f"raw_columns={fm.raw_columns_}；命中禁止字段 {hit}")

        # ---- 4. 保存/加载预测一致
        sub = fr.sample(n=min(512, len(fr)), random_state=0).sort_values("pair_index")
        npz = run_dir / "predictions_test.npz"
        ok, detail = True, "无 predictions_test.npz，跳过与训练期预测比对"
        if npz.exists():
            data = np.load(npz)
            pair_scores = dict(zip(data["pair_index"].tolist(), data["pred_scores"].tolist()))
            # 仅与训练期真正评估过的 pair 逐一对齐比对（两侧行集合不同会误报）
            sub = sub[sub["pair_index"].isin(pair_scores)]
            if len(sub):
                X = fm.transform(sub)
                pred = predict_scores(model, X)
                ref = np.array([pair_scores[int(p)] for p in sub["pair_index"]],
                               dtype=np.float64)
                diff = float(np.max(np.abs(ref - pred)))
                ok = diff < 1e-5
                detail = f"重载预测与训练期预测最大绝对差 {diff:.2e}（n={len(sub)}）"
        record(f"{rid}:reload_consistency", ok, detail)

        # ---- 5. 无标签字段的独立推理 + CPU
        resume = {"candidate_id": "cand_verify", "target_position_norm": "软件工程师",
                  "skills_canonical_json": '["java", "spring"]',
                  "inferred_category": "INFORMATION-TECHNOLOGY", "years_experience": 3}
        jobs = [{"job_id": 1, "job_title_norm": "java 开发工程师", "category": "INFORMATION-TECHNOLOGY",
                 "skills_canonical_json": '["java"]'},
                {"job_id": 2, "job_title_norm": "财务分析师", "category": "FINANCE",
                 "skills_canonical_json": '["finance"]'}]
        predictor = MatchPredictor(run_dir, device="cpu")
        s1 = predictor.predict_score(resume, jobs[0])
        s2 = predictor.predict_score(resume, jobs[1])
        ranked1 = predictor.rank_jobs(resume, jobs)
        ranked2 = predictor.rank_jobs(resume, jobs)
        stable = [r["job_id"] for r in ranked1] == [r["job_id"] for r in ranked2]
        ordered_ok = ranked1[0]["score"] >= ranked1[-1]["score"]
        # 交换输入顺序，分数应不变（稳定排序只影响同分顺序）
        ranked3 = predictor.rank_jobs(resume, list(reversed(jobs)))
        same_scores = sorted(r["score"] for r in ranked1) == sorted(r["score"] for r in ranked3)
        record(f"{rid}:cpu_inference_and_ranking",
               all([np.isfinite(s1), np.isfinite(s2), stable, ordered_ok, same_scores]),
               f"scores=({s1:.6f},{s2:.6f}) stable={stable} order_ok={ordered_ok} "
               f"order_invariant={same_scores}")

    ok_all = all(c["ok"] for c in checks)
    jdump({"generated_by": "scripts/model_training/verify_models.py",
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "ok": ok_all, "checks": checks}, OUT / "model-verification.json")
    log.info("[done] 验证项 %d，全部通过=%s", len(checks), ok_all)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
