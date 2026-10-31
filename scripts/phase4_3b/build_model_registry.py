# -*- coding: utf-8 -*-
"""Phase4-3B 模型资产登记（B0）。

扫描 models/ 下全部运行目录，核对 checkpoint 是否真实存在、可否加载、
训练依赖版本、实测指标，并写出 reports/phase4-3b/model-registry.json。

纪律：
  * 只读扫描，绝不写入 models/ 下任何文件；
  * 文件缺失登记 NOT_PRESENT，不猜测、不补造；
  * 加载失败登记具体异常类型，不掩盖。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths  # noqa: E402

ROOT = _paths.ROOT
MODELS_ROOT = _paths.MODELS_ROOT
OUT_DIR = _paths.PHASE4_3B_DIR
OUT_JSON = OUT_DIR / "model-registry.json"

CHECKPOINT_NAMES = ("model.pkl", "model.pt", "checkpoint_best.pt")


def sha256_file(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    read = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            if limit is not None and read + len(chunk) > limit:
                chunk = chunk[: limit - read]
            h.update(chunk)
            read += len(chunk)
            if limit is not None and read >= limit:
                break
    return h.hexdigest()


def find_checkpoint(run_dir: Path) -> Path | None:
    for name in CHECKPOINT_NAMES:
        p = run_dir / name
        if p.exists():
            return p
    return None


def read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        return {"__error__": f"{type(e).__name__}: {e}"}


def probe_load(checkpoint: Path, model_name: str) -> dict:
    """只做加载探针，不做预测。返回结构化状态。"""
    t0 = time.perf_counter()
    try:
        if checkpoint.suffix == ".pkl":
            import joblib
            obj = joblib.load(checkpoint)
        else:
            import torch
            obj = torch.load(checkpoint, map_location="cpu")
    except Exception as e:  # noqa: BLE001
        return {
            "load_status": "ENV_INCOMPATIBLE" if "pyx_unpickle" in str(e) else "LOAD_FAILED",
            "load_seconds": round(time.perf_counter() - t0, 4),
            "loaded_type": None,
            "error": f"{type(e).__name__}: {e}",
        }
    return {
        "load_status": "LOADED",
        "load_seconds": round(time.perf_counter() - t0, 4),
        "loaded_type": type(obj).__name__,
        "error": None,
    }


def discover() -> list[Path]:
    """枚举运行目录：models/<family>/<model>/<protocol>/<run_id>/ 或 models/education/<model>/<run_id>/。"""
    runs: list[Path] = []
    if not MODELS_ROOT.exists():
        return runs
    for family in sorted(p for p in MODELS_ROOT.iterdir() if p.is_dir()):
        for model_dir in sorted(p for p in family.iterdir() if p.is_dir()):
            # 两种布局：
            #   education/<model>/<run_id>
            #   matching/<model>/<protocol>/<run_id>
            sub = [p for p in model_dir.iterdir() if p.is_dir()]
            for d in sorted(sub):
                if (d / "manifest.json").exists() or find_checkpoint(d):
                    runs.append(d)
                else:
                    for x in sorted(d.iterdir()):
                        if x.is_dir() and ((x / "manifest.json").exists() or find_checkpoint(x)):
                            runs.append(x)
    return sorted(set(runs))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = discover()
    records = []
    for run_dir in runs:
        rel = run_dir.relative_to(MODELS_ROOT).as_posix()
        manifest = read_json(run_dir / "manifest.json")
        config = read_json(run_dir / "config.json")
        metrics = read_json(run_dir / "metrics.json")
        feature_map = read_json(run_dir / "feature_map.json")
        ckpt = find_checkpoint(run_dir)
        parts = rel.split("/")
        family = parts[0]
        model_name = parts[1] if len(parts) > 1 else "unknown"
        protocol = parts[2] if family == "matching" and len(parts) > 3 else None
        run_id = parts[-1]

        entry = {
            "model_id": f"{family}.{model_name}",
            "model_version": run_id,
            "run_dir": rel,
            "task_type": manifest.get("task") or config.get("common", {}).get("task")
            or ("matching_ranking" if family == "matching" else "education_multilabel"),
            "split_protocol": protocol or manifest.get("protocol"),
            "training_dataset": {
                "dataset_version": manifest.get("dataset_version"),
                "split_manifest_file": manifest.get("split_manifest_file"),
                "split_manifest_sha256": manifest.get("split_manifest_sha256"),
                "rows": manifest.get("rows"),
            },
            "label_source": (
                "derived_proxy_label_final_score_chain"
                if family == "matching"
                else "pseudo_online_assistant_or_human_gold"
            ),
            "feature_schema": {
                "feature_schema_file": manifest.get("feature_schema_file"),
                "feature_schema_sha256": manifest.get("feature_schema_sha256"),
                "n_features": len(feature_map.get("feature_names") or [])
                or feature_map.get("n_features"),
                "task_declared": feature_map.get("task"),
                "groups_enabled": feature_map.get("groups_enabled"),
            },
            "checkpoint_path": rel + "/" + ckpt.name if ckpt else None,
            "checkpoint_present": bool(ckpt),
            "checkpoint_bytes": ckpt.stat().st_size if ckpt else None,
            "checkpoint_sha256": sha256_file(ckpt) if ckpt else None,
            "dependency_versions": manifest.get("environment"),
            "created_at": manifest.get("created_at"),
            "seed": manifest.get("seed"),
            "training_seconds": manifest.get("training_seconds"),
            "metrics": metrics,
            "artifacts": manifest.get("artifacts"),
        }
        if ckpt is None:
            entry["inference_status"] = "NOT_PRESENT"
            entry["load_probe"] = {"load_status": "NOT_PRESENT"}
        else:
            probe = probe_load(ckpt, model_name)
            entry["load_probe"] = probe
            entry["inference_status"] = probe["load_status"]
        entry["limitations"] = []
        if family == "matching":
            entry["limitations"].append(
                "标签为英文代理标签（final_score 评分链派生），非人工相关性；"
                "指标仅表示与原系统代理偏好的一致度")
        if family == "education":
            entry["limitations"].append(
                "默认训练标签为线上旧系统伪标签（人工一致率 45.92%），可信度低")
        records.append(entry)

    fam_count: dict[str, int] = {}
    status_count: dict[str, int] = {}
    for r in records:
        fam_count[r["model_id"]] = fam_count.get(r["model_id"], 0) + 1
        status_count[r["inference_status"]] = status_count.get(r["inference_status"], 0) + 1

    out = {
        "generated_by": "scripts/phase4_3b/build_model_registry.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scan_root": str(MODELS_ROOT),
        "probe_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "totals": {"runs": len(records), "by_model_id": fam_count, "by_inference_status": status_count},
        "read_only_notice": "本登记只读扫描 models/，未写入或改动任何历史 checkpoint",
        "records": records,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"runs={len(records)} status={status_count}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
