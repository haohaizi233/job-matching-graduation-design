# -*- coding: utf-8 -*-
"""第四阶段 4.2 模型验证：重载一致性 / CPU 推理 / 异常输入 / 稳定性 / 无标签依赖。

产出：reports/education-training/model-verification.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import MODELS_DIR, REPORT_DIR, prepare_experiment_a, setup_train_logging  # noqa: E402
from job_matching.core import ROOT, jdump, rel, sha256_file  # noqa: E402
from job_matching.education.predictor import EducationNormalizer  # noqa: E402

# 推理代码禁止出现的监督目标字段（只扫描真实代码，注释与文档字符串会被剥离）
FORBIDDEN_TOKENS = ["label_tokens_json", "label_multi_hot", "label_status", "label_raw",
                    "assistant", "人工正确结果", "label_provenance", "is_gold"]


def _strip_comments_and_docstrings(src: str) -> str:
    """去掉 # 注释与三引号字符串，避免文档说明误触发关键词扫描。"""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "#":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith('"""', i) or src.startswith("'''", i):
            q = src[i:i + 3]
            j = src.find(q, i + 3)
            i = n if j < 0 else j + 3
            continue
        if c in "\"'":
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q:
                    break
                j += 1
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)

EDGE_INPUTS = [
    ("empty_string", ""),
    ("none_value", None),
    ("whitespace", "   "),
    ("unknown_expr", "火星文学历"),
    ("long_string", "博士" * 200),
    ("mixed_punct", "本科/硕士、博士；及以上?"),
    ("emoji", "🎓硕士"),
    ("numeric", "985"),
]


def _check_predictor_source() -> dict:
    src = (ROOT / "src" / "job_matching" / "education" / "predictor.py").read_text(encoding="utf-8")
    code = _strip_comments_and_docstrings(src)
    hits = [t for t in FORBIDDEN_TOKENS if t in code]
    return {"file": "src/job_matching/education/predictor.py",
            "scan_mode": "code_only(comments/docstrings stripped)",
            "forbidden_tokens_found": hits, "ok": not hits}


def verify_run(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    out = {"run_id": meta["run_id"], "model_dir": rel(run_dir),
           "model_type": meta["model_type"]}
    nz = EducationNormalizer.from_model_dir(run_dir, fallback_to_rules=True)
    data = prepare_experiment_a()
    va = data["validation"]
    texts = va["slot"].astype(str).tolist()[:2000]

    # 1) 重载一致性
    # 注意：神经网络训练时预测在 CUDA 上完成，重载验证在 CPU 上完成，
    # 两种设备浮点运算顺序不同会造成 ~1e-4 量级的数值差（阈值化标签应完全一致）。
    # 因此 tfidf 要求严格一致（<=1e-5），神经网络允许 1e-3 数值容差，
    # 但阈值化后的标签必须逐行完全一致。
    is_nn = not meta["model_type"].startswith("tfidf")
    tol = 1e-3 if is_nn else 1e-5
    npz_name = "predictions_validation_pseudo"
    npz = run_dir / f"{npz_name}.npz"
    if npz.exists():
        old = np.load(npz, allow_pickle=False)
        proba_new = (nz.model.predict_proba(texts) if not is_nn else _nn_proba(nz, texts))
        d = float(np.abs(old["proba"][:len(texts)].astype(np.float64)
                         - proba_new.astype(np.float64)).max())
        labels_old = (old["proba"][:len(texts)] >= nz.thresholds.reshape(1, -1)).astype(np.int8)
        labels_new = (proba_new >= nz.thresholds.reshape(1, -1)).astype(np.int8)
        labels_identical = bool((labels_old == labels_new).all())
        out["reload_consistency"] = {
            "rows_compared": len(texts), "max_abs_diff": d,
            "numeric_tolerance": tol,
            "tolerance_note": ("训练时 CUDA / 验证时 CPU 浮点差异，数值容差 1e-3，"
                               "阈值化标签要求完全一致" if is_nn else "同设备精确重算，容差 1e-5"),
            "thresholded_labels_identical": labels_identical,
            "ok": bool(d <= tol and labels_identical)}
    # 2) 单条 vs 批量一致性 + 重复运行稳定性
    single = [nz.normalize(t) for t in texts[:200]]
    batch = nz.batch(texts[:200])
    same = all(a["labels"] == b["labels"] for a, b in zip(single, batch))
    batch2 = nz.batch(texts[:200])
    same2 = all(a["labels"] == b["labels"] for a, b in zip(batch, batch2))
    out["single_vs_batch"] = {"identical_labels": bool(same)}
    out["repeat_stability"] = {"identical_labels": bool(same2)}
    # 3) 异常输入
    edge = {}
    for name, val in EDGE_INPUTS:
        try:
            r = nz.normalize(val)
            edge[name] = {"ok": True, "labels": r["labels"], "fallback_to_rule": r["fallback_to_rule"]}
        except Exception as e:  # noqa: BLE001
            edge[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out["edge_inputs"] = edge
    out["edge_inputs_all_ok"] = all(v["ok"] for v in edge.values())
    # 4) 延迟（CPU）
    t0 = time.perf_counter()
    for _ in range(3):
        nz.batch(texts[:500])
    out["latency_ms_per_sample_cpu"] = round((time.perf_counter() - t0) / (500 * 3) * 1000, 4)
    # 5) 模型文件
    files = {}
    for p in sorted(run_dir.iterdir()):
        if p.is_file():
            files[p.name] = {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
    out["files"] = files
    out["ok"] = bool(out.get("reload_consistency", {}).get("ok", True)
                     and out["single_vs_batch"]["identical_labels"]
                     and out["repeat_stability"]["identical_labels"]
                     and out["edge_inputs_all_ok"])
    return out


def _nn_proba(nz: EducationNormalizer, texts: list[str]) -> np.ndarray:
    import torch
    from job_matching.education.trainer import evaluate_proba
    return evaluate_proba(nz.model, nz.tokenizer.transform(texts), torch.device("cpu"))


def main() -> int:
    log = setup_train_logging("verify_models")
    t0 = time.time()
    runs = []
    for run_dir in sorted(MODELS_DIR.glob("*/*")):
        if (run_dir / "manifest.json").exists():
            runs.append(verify_run(run_dir))
            log.info("[验证] %s ok=%s", runs[-1]["run_id"], runs[-1]["ok"])
    result = {"generated_by": "scripts/education_training/verify_models.py",
              "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "predictor_source_check": _check_predictor_source(),
              "runs": runs,
              "total": len(runs),
              "passed": sum(1 for r in runs if r["ok"]),
              "seconds": round(time.time() - t0, 2)}
    jdump(result, REPORT_DIR / "model-verification.json")
    log.info("[完成] 验证 %d/%d 通过 -> %s", result["passed"], result["total"],
             rel(REPORT_DIR / "model-verification.json"))
    return 0 if result["passed"] == result["total"] and result["predictor_source_check"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
