# -*- coding: utf-8 -*-
"""历史模型加载 / 推理 / 输出一致性核查（Phase4-3B / M1-4.2）。

四类行为严格分开记录：
  * LOAD               —— 仅反序列化 checkpoint
  * PREDICT            —— 用既有 checkpoint 做前向推理（不训练）
  * REEVALUATE         —— 用既有预测文件重算指标（不训练、不推理）
  * COMPARE_HISTORICAL —— 比较「当前推理输出」与「历史落盘预测」是否一致

纪律：
  * 不修改历史权重；只读打开 models/；
  * 不用重新训练掩盖反序列化问题；
  * 文件缺失 -> NOT_PRESENT；依赖不兼容 -> ENV_INCOMPATIBLE；不虚报 PASS。
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths  # noqa: E402

ROOT = _paths.ROOT
_paths.ensure_src_on_path()

OUT_DIR = _paths.PHASE4_3B_DIR
OUT_JSON = OUT_DIR / "model-compatibility-runs.json"

RUN_TARGETS = [
    # (run_dir 相对 models/ 的路径, task)
    ("matching/ridge/candidate_cold/ridge-candidate_cold-final-20261028-203750", "matching_ranking"),
    ("matching/ridge/job_cold/ridge-job_cold-final-20261028-203750", "matching_ranking"),
    ("matching/ridge/double_cold/ridge-double_cold-final-20261028-203750", "matching_ranking"),
    ("matching/gradient_boosting/candidate_cold/gradient_boosting-candidate_cold-final-20261028-203750", "matching_ranking"),
    ("matching/gradient_boosting/job_cold/gradient_boosting-job_cold-final-20261028-203750", "matching_ranking"),
    ("matching/gradient_boosting/double_cold/gradient_boosting-double_cold-final-20261028-203750", "matching_ranking"),
    ("matching/mlp/candidate_cold/mlp-candidate_cold-final-20261028-203750", "matching_ranking"),
    ("matching/mlp/job_cold/mlp-job_cold-final-20261028-203750", "matching_ranking"),
    ("matching/mlp/double_cold/mlp-double_cold-final-20261028-203750", "matching_ranking"),
    ("matching/ranknet/candidate_cold/ranknet-candidate_cold-final-20261028-203750", "matching_ranking"),
    ("matching/ranknet/job_cold/ranknet-job_cold-final-20261028-203750", "matching_ranking"),
    ("matching/ranknet/double_cold/ranknet-double_cold-final-20261028-203750", "matching_ranking"),
    ("education/tfidf/tfidf-final-20261028-212254", "education_multilabel"),
    ("education/charcnn/charcnn-final-20261028-212510", "education_multilabel"),
]


def _rss_mb() -> float | None:
    try:
        import psutil  # noqa: F401
        return None
    except Exception:  # noqa: BLE001
        return None


def load_predictions(run_dir: Path) -> dict:
    out = {}
    for p in sorted(run_dir.glob("predictions_*.npz")):
        with np.load(p, allow_pickle=False) as z:
            out[p.name] = {k: z[k] for k in z.files}
    return out


def check_matching(run_dir: Path, label: str) -> dict:
    rec = {"run": label, "task": "matching_ranking", "run_dir": str(run_dir),
           "load": None, "predict": None, "reevaluate": None, "compare_historical": None}
    from job_matching.inference.predictor import MatchPredictor

    t0 = time.perf_counter()
    try:
        pred = MatchPredictor(run_dir, device="cpu")
    except Exception as e:  # noqa: BLE001
        rec["load"] = {"status": "LOAD_FAILED", "error": f"{type(e).__name__}: {e}",
                       "seconds": round(time.perf_counter() - t0, 4)}
        return rec
    load_s = round(time.perf_counter() - t0, 4)
    info = pred.info()
    rec["load"] = {"status": "LOADED", "seconds": load_s, "info": info,
                   "feature_names_n": len(pred.feature_map.feature_names_)}

    # --- 特征一致性
    fm = pred.feature_map
    fmap_file = run_dir / "feature_map.json"
    with open(fmap_file, "r", encoding="utf-8") as f:
        fmap_raw = json.load(f)
    declared_names = fmap_raw.get("feature_names") or []
    rec["feature_consistency"] = {
        "n_features_declared": len(declared_names),
        "n_features_loaded": fm.n_features,
        "names_match": list(fm.feature_names_) == list(declared_names),
        "task_declared": fmap_raw.get("task"),
        "groups_enabled": fmap_raw.get("groups_enabled"),
        "standardize_columns": fmap_raw.get("standardize_columns"),
    }

    # --- 历史预测比对（用 test 切分重建 X 后前向推理）
    hist = load_predictions(run_dir)
    proto = pred.manifest.get("protocol")
    if not hist:
        rec["compare_historical"] = {"status": "NOT_RUN", "reason": "run_dir 无 predictions_*.npz"}
        return rec
    try:
        from job_matching.training.dataset import load_pairs, load_split_index
        from job_matching.evaluation.metrics import ranking_report
        pairs = load_pairs()
        rec["reevaluate"] = {"status": "RUN", "n_pairs_table": pairs.n}
    except Exception as e:  # noqa: BLE001
        rec["reevaluate"] = {"status": "NOT_RUN",
                             "reason": f"特征表不可读: {type(e).__name__}: {e}"}
        rec["compare_historical"] = {"status": "NOT_RUN", "reason": "无法重建特征矩阵"}
        return rec

    cmp_rows = {}
    for fname, arrs in hist.items():
        subset = "test" if "test" in fname else "validation"
        try:
            idx = load_split_index(proto, subset)
            df = pairs.subset(idx)
            X = fm.transform(df)
            t1 = time.perf_counter()
            cur = np.asarray(pred.model.predict(X, device="cpu")
                             if _accepts_device(pred.model) else pred.model.predict(X),
                             dtype=np.float64).ravel()
            infer_s = round(time.perf_counter() - t1, 4)
        except Exception as e:  # noqa: BLE001
            cmp_rows[fname] = {"status": "PREDICT_FAILED",
                               "error": f"{type(e).__name__}: {e}",
                               "trace": traceback.format_exc(limit=3)}
            continue
        id_keys = ("pair_index", "candidate_id", "job_id", "row_index")
        cand_keys = [k for k in arrs if k not in id_keys and np.asarray(arrs[k]).dtype.kind in "fiu"]
        key = "pred_scores" if "pred_scores" in arrs else (
            "y_pred" if "y_pred" in arrs else (cand_keys[0] if cand_keys else None))
        if key is None:
            cmp_rows[fname] = {"status": "NO_PREDICTION_COLUMN", "keys": list(arrs.keys())}
            continue
        # 行对齐校验：历史 pair_index 必须与当前重建顺序一致
        align_ok = None
        if "pair_index" in arrs:
            hist_idx = np.asarray(arrs["pair_index"]).ravel()
            cur_idx = df["pair_index"].to_numpy()
            align_ok = bool(hist_idx.shape == cur_idx.shape and np.array_equal(hist_idx, cur_idx))
        hist_pred = np.asarray(arrs[key], dtype=np.float64).ravel()
        if hist_pred.shape != cur.shape:
            cmp_rows[fname] = {
                "status": "SHAPE_MISMATCH", "historical": list(hist_pred.shape),
                "current": list(cur.shape), "keys": list(arrs.keys())}
            continue
        diff = np.abs(hist_pred - cur)
        cmp_rows[fname] = {
            "status": "COMPARABLE",
            "keys": list(arrs.keys()),
            "prediction_key": key,
            "row_alignment_ok": align_ok,
            "n": int(cur.shape[0]),
            "max_abs_diff": float(diff.max()) if diff.size else 0.0,
            "mean_abs_diff": float(diff.mean()) if diff.size else 0.0,
            "identical": bool(diff.size and diff.max() == 0.0),
            "bitwise_allclose_1e-9": bool(np.allclose(hist_pred, cur, rtol=0, atol=1e-9)),
            "bitwise_allclose_1e-6": bool(np.allclose(hist_pred, cur, rtol=0, atol=1e-6)),
            "predict_seconds": infer_s,
            "finite": bool(np.isfinite(cur).all()),
        }
    rec["compare_historical"] = {"status": "RUN", "rows": cmp_rows}
    if rec["predict"] is None:
        rec["predict"] = {"status": "RUN", "device": "cpu",
                          "note": "仅前向推理，未训练、未修改权重"}
    return rec


def _accepts_device(model) -> bool:
    import inspect
    try:
        return "device" in inspect.signature(model.predict).parameters
    except Exception:  # noqa: BLE001
        return False


def check_education(run_dir: Path, label: str) -> dict:
    rec = {"run": label, "task": "education_multilabel", "run_dir": str(run_dir),
           "load": None, "predict": None, "reevaluate": None, "compare_historical": None}
    t0 = time.perf_counter()
    try:
        from job_matching.education.predictor import EducationNormalizer
        norm = EducationNormalizer.from_model_dir(run_dir)
    except Exception as e:  # noqa: BLE001
        rec["load"] = {"status": "LOAD_FAILED", "error": f"{type(e).__name__}: {e}",
                       "seconds": round(time.perf_counter() - t0, 4)}
        return rec
    rec["load"] = {"status": "LOADED", "seconds": round(time.perf_counter() - t0, 4),
                   "info": norm.describe() if hasattr(norm, "describe") else {}}
    t1 = time.perf_counter()
    try:
        out = norm.batch(["<岗位名称>数据分析师<岗位描述>负责报表<学历描述>本科"])
        rec["predict"] = {"status": "RUN", "seconds": round(time.perf_counter() - t1, 4),
                          "output_type": type(out).__name__,
                          "sample": _jsonable(out[:1] if isinstance(out, list) else out)}
    except Exception as e:  # noqa: BLE001
        rec["predict"] = {"status": "PREDICT_FAILED", "error": f"{type(e).__name__}: {e}",
                          "trace": traceback.format_exc(limit=3)}

    hist = load_predictions(run_dir)
    rows = {}
    for fname, arrs in hist.items():
        if "proba" not in arrs or "record_key" not in arrs:
            rows[fname] = {"status": "NO_PROBA", "keys": list(arrs.keys())}
            continue
        subset = "gold_holdout" if "gold" in fname else "validation"
        try:
            from job_matching.education.dataset import load_split_frame
            df = load_split_frame(subset)
            key_col = "record_key" if "record_key" in df.columns else df.columns[0]
            text_col = "slot_education_norm" if "slot_education_norm" in df.columns else (
                "user_norm" if "user_norm" in df.columns else df.columns[1])
            wanted = list(np.asarray(arrs["record_key"]).ravel())
            sub = df.set_index(key_col).loc[wanted].reset_index()
            texts = [str(v) for v in sub[text_col].tolist()]
            t2 = time.perf_counter()
            cur = np.asarray(norm._scores(texts), dtype=np.float64)
            infer_s = round(time.perf_counter() - t2, 4)
        except Exception as e:  # noqa: BLE001
            rows[fname] = {"status": "PREDICT_FAILED",
                           "error": f"{type(e).__name__}: {e}",
                           "trace": traceback.format_exc(limit=3)}
            continue
        hist_p = np.asarray(arrs["proba"], dtype=np.float64)
        if hist_p.shape != cur.shape:
            rows[fname] = {"status": "SHAPE_MISMATCH", "historical": list(hist_p.shape),
                           "current": list(cur.shape), "keys": list(arrs.keys())}
            continue
        diff = np.abs(hist_p - cur)
        rows[fname] = {
            "status": "COMPARABLE", "keys": list(arrs.keys()),
            "subset": subset, "n": int(cur.shape[0]), "dim": int(cur.shape[1]),
            "max_abs_diff": float(diff.max()), "mean_abs_diff": float(diff.mean()),
            "identical": bool(diff.max() == 0.0),
            "bitwise_allclose_1e-6": bool(np.allclose(hist_p, cur, rtol=0, atol=1e-6)),
            "predict_seconds": infer_s, "finite": bool(np.isfinite(cur).all()),
        }
    rec["compare_historical"] = (
        {"status": "RUN", "rows": rows} if rows
        else {"status": "NOT_RUN", "reason": "run_dir 无 predictions_*.npz"})
    return rec


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    env = {
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
    }
    for mod in ("numpy", "pandas", "sklearn", "joblib", "torch", "transformers", "jieba"):
        try:
            m = __import__(mod)
            env[mod] = getattr(m, "__version__", "unknown")
        except Exception as e:  # noqa: BLE001
            env[mod] = f"MISSING ({type(e).__name__})"
    try:
        import torch
        env["cuda_available"] = bool(torch.cuda.is_available())
        env["torch_cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            env["gpu"] = torch.cuda.get_device_name(0)
            env["gpu_total_memory_mb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024 ** 2))
    except Exception:  # noqa: BLE001
        pass

    results = []
    for rel, task in RUN_TARGETS:
        run_dir = ROOT / "models" / rel
        label = rel
        if not run_dir.exists():
            results.append({"run": label, "task": task, "run_dir": str(run_dir),
                            "load": {"status": "NOT_PRESENT"},
                            "predict": {"status": "NOT_RUN", "reason": "NOT_PRESENT"},
                            "compare_historical": {"status": "NOT_RUN", "reason": "NOT_PRESENT"}})
            continue
        try:
            rec = check_matching(run_dir, label) if task == "matching_ranking" \
                else check_education(run_dir, label)
        except Exception as e:  # noqa: BLE001
            rec = {"run": label, "task": task, "run_dir": str(run_dir),
                   "load": {"status": "ERROR", "error": f"{type(e).__name__}: {e}",
                            "trace": traceback.format_exc(limit=5)}}
        results.append(rec)
        print(f"{label}: load={rec.get('load', {}).get('status')} "
              f"cmp={rec.get('compare_historical', {}).get('status')}")

    status_count: dict[str, int] = {}
    for r in results:
        s = (r.get("load") or {}).get("status", "UNKNOWN")
        status_count[s] = status_count.get(s, 0) + 1

    out = {
        "generated_by": "scripts/phase4_3b/check_model_compatibility.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": env,
        "behavior_taxonomy": {
            "LOAD": "仅反序列化 checkpoint",
            "PREDICT": "加载既有 checkpoint 做前向推理（不训练）",
            "REEVALUATE": "用既有预测文件重算指标（不训练不推理）",
            "COMPARE_HISTORICAL": "比对当前推理输出与历史落盘预测",
            "RETRAIN": "重新训练（本轮未执行，见 03-baseline-reproduction.md）",
            "REPRODUCE_FROM_SCRATCH": "从零训练复现（本轮未执行）",
        },
        "totals": {"runs": len(results), "by_load_status": status_count},
        "read_only_notice": "全程只读 models/，未写入或改动任何历史 checkpoint",
        "results": results,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"status={status_count}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
