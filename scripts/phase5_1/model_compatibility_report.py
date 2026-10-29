# -*- coding: utf-8 -*-
"""Phase5-1 归档模型兼容性探测（只读，不写 models/、不重新训练）。

对 models/ 下每个含 manifest.json 的运行目录做一次最小加载 + 单条推理探测：
  * 匹配模型（ridge / gradient_boosting / mlp / ranknet）走 MatchPredictor；
  * 学历模型（tfidf_char_ovr_logreg / char_cnn）走 EducationNormalizer.from_model_dir；
  * 只读取权重与清单，绝不覆盖 checkpoint、不修改历史实验指标。

产出 reports/phase5-1/model-compatibility.json：
  * 每个 run 的 load_status：ok / incompatible / error；
  * 环境版本与 environment.yml 声明版本的偏差（pickle 兼容性根因线索）；
  * 对 Phase5-1 三种运行模式的可用性结论。

用法： python scripts/phase5_1/model_compatibility_report.py
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MATCHING_MODELS = ("ridge", "gradient_boosting", "mlp", "ranknet")

# 合成探测输入（与 tests/phase5_1 夹具同源口径，无敏感信息）
PROBE_RESUME = {"target_position_norm": "软件工程师",
                "skills_canonical_json": '["java", "spring", "mysql"]',
                "inferred_category": "INFORMATION-TECHNOLOGY",
                "years_experience": 3}
PROBE_JOB = {"job_id": 1, "job_title_norm": "java 开发工程师",
             "category": "INFORMATION-TECHNOLOGY",
             "skills_canonical_json": '["java", "spring"]'}
PROBE_EDU_TEXTS = ["本科及以上学历", "硕士研究生", "学历不限", "大专"]


def _env_info() -> dict:
    import numpy
    import sklearn
    info = {"python": sys.version.split()[0], "platform": sys.platform,
            "numpy": numpy.__version__, "scikit_learn": sklearn.__version__}
    try:
        import torch
        info["torch"] = torch.__version__
    except Exception as e:   # pragma: no cover
        info["torch"] = f"unavailable ({type(e).__name__})"
    info["environment_yml_pins"] = {"python": "3.11", "numpy": "1.26.4",
                                    "scikit-learn": "1.5.2", "torch": "2.1.2+cu121"}
    info["note"] = ("当前解释器与 environment.yml 声明版本存在偏差时，"
                    "旧 checkpoint 的 pickle/joblib 兼容性可能受损（只读探测如实登记）")
    return info


def probe_matching(run_dir: Path) -> dict:
    from job_matching.inference.predictor import MatchPredictor
    pred = MatchPredictor(run_dir, device="cpu")
    score = pred.predict_score(PROBE_RESUME, PROBE_JOB)
    ranked = pred.rank_jobs(PROBE_RESUME, [PROBE_JOB, dict(PROBE_JOB, job_id=2)])
    return {"probe_score": float(score), "probe_rank_job_ids": [r["job_id"] for r in ranked],
            "predictor_info": pred.info()}


def probe_education(run_dir: Path) -> dict:
    from job_matching.education.predictor import EducationNormalizer
    norm = EducationNormalizer.from_model_dir(run_dir)
    rows = [norm.normalize(t) for t in PROBE_EDU_TEXTS]
    return {"probe_labels": {r["input"]: r["labels"] for r in rows},
            "expression_seen_in_train": {r["input"]: r["expression_seen_in_train"] for r in rows},
            "normalizer": norm.describe()}


def probe_run(run_dir: Path, root: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rel = str(run_dir.relative_to(root)).replace("\\", "/")
    family = "education" if "education" in rel else "matching"
    rec = {
        "run_dir": rel,
        "family": family,
        "model_name": manifest.get("model_name"),
        "model_type": manifest.get("model_type"),
        "run_id": manifest.get("run_id"),
        "weights_present": {w: (run_dir / w).exists()
                            for w in ("model.pkl", "model.pt", "feature_map.json",
                                      "tokenizer.json")},
    }
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            if family == "matching":
                rec["probe"] = probe_matching(run_dir)
            else:
                rec["probe"] = probe_education(run_dir)
        rec["load_status"] = "ok"
        rec["error"] = None
        rec["load_warnings"] = sorted({f"{w.category.__name__}: {str(w.message)[:200]}"
                                       for w in caught})
    except Exception as e:
        rec["load_status"] = "incompatible" if isinstance(e, AttributeError) else "error"
        rec["error"] = {"type": type(e).__name__, "message": str(e)[:500]}
        rec["traceback_tail"] = traceback.format_exc()[-800:]
    return rec


def main() -> int:
    models_root = ROOT / "models"
    run_dirs = sorted(p.parent for p in models_root.rglob("manifest.json"))
    runs = [probe_run(d, ROOT) for d in run_dirs]

    n_ok = sum(1 for r in runs if r["load_status"] == "ok")
    n_bad = len(runs) - n_ok
    by_family: dict[str, dict] = {}
    for fam in ("matching", "education"):
        rows = [r for r in runs if r["family"] == fam]
        by_family[fam] = {
            "total": len(rows),
            "loadable": sum(1 for r in rows if r["load_status"] == "ok"),
            "incompatible": sum(1 for r in rows if r["load_status"] == "incompatible"),
            "error": sum(1 for r in rows if r["load_status"] == "error"),
        }

    out = {
        "generated_by": "scripts/phase5_1/model_compatibility_report.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "read_only": True,
        "disclaimer": ("探测只读加载归档模型，不重新训练、不覆盖 checkpoint、"
                       "不修改历史实验指标；探测结论只说明工程可加载性，"
                       "不代表模型效果验收。"),
        "environment": _env_info(),
        "totals": {"runs": len(runs), "loadable": n_ok, "problematic": n_bad},
        "by_family": by_family,
        "phase5_1_mode_conclusions": {
            "baseline": "不依赖归档模型，中文合成输入上可运行（heuristic_score）",
            "experimental_model": ("可加载的 run 直接用于研究/诊断；"
                                   "不可加载的 run 一律 MODEL_MISSING/降级 baseline，禁止伪造输出"),
            "future_verified": "无已验证中文模型，返回 FUTURE_MODEL_UNAVAILABLE（不伪称存在）"},
        "runs": runs,
    }
    out_dir = ROOT / "reports" / "phase5-1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "model-compatibility.json"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print(f"runs={len(runs)} loadable={n_ok} problematic={n_bad}")
    for r in runs:
        flag = {"ok": "OK ", "incompatible": "INC", "error": "ERR"}[r["load_status"]]
        err = (r.get("error") or {}).get("type", "")
        print(f"[{flag}] {r['run_dir']} {err}")
    print(f"报告: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
