# -*- coding: utf-8 -*-
"""汇总第四阶段 4.2 全部实验结果 -> reports/education-training/results.json。

只聚合已落盘的机器可读产物（runs/*.json、experiment-comparison.json、
model-verification.json、education-tests.json、learnability.json、label-noise.json），
不重新计算指标，不手工覆盖任何历史数字。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT, jdump, rel  # noqa: E402

REPORT_DIR = ROOT / "reports" / "education-training"
RUNS_DIR = REPORT_DIR / "runs"
MODELS_DIR = ROOT / "models" / "education"


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _model_sizes() -> dict:
    out = {}
    for run_dir in sorted(MODELS_DIR.glob("*/*")):
        if not (run_dir / "manifest.json").exists():
            continue
        meta = _load(run_dir / "manifest.json")
        files = {p.name: p.stat().st_size for p in run_dir.iterdir() if p.is_file()}
        out[meta["run_id"]] = {
            "model_type": meta["model_type"], "experiment": meta["experiment"],
            "input_mode": meta["input_mode"],
            "sample_weight_strategy": meta["sample_weight_strategy"],
            "n_parameters": meta.get("n_parameters") or
            meta.get("model_description", {}).get("n_parameters"),
            "train_seconds": meta.get("train_seconds") or meta.get("train_info", {}).get("seconds"),
            "peak_memory_mb": meta.get("train_info", {}).get("peak_memory_mb"),
            "device": meta.get("train_info", {}).get("device"),
            "epochs_run": meta.get("train_info", {}).get("epochs_run"),
            "best_epoch": meta.get("train_info", {}).get("best_epoch"),
            "model_bytes": files.get("model.pkl") or files.get("model.pt"),
            "threshold_selected_on": meta.get("threshold_selected_on"),
            "thresholds": meta.get("thresholds"),
            "created_at": meta.get("created_at"),
        }
    return out


def main() -> int:
    runs = [_load(p) for p in sorted(RUNS_DIR.glob("*.json"))] if RUNS_DIR.exists() else []
    result = {
        "generated_by": "scripts/education_training/build_results.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phase": "4.2 中文岗位学历要求规范化与多标签分类",
        "task_scope": ("<学历描述> 短槽位表达的规范化/多标签归一；"
                       "不是从完整 JD 端到端抽取学历信息"),
        "label_order": ["博士", "硕士", "本科", "大专", "学历不限", "学历不明"],
        "data": {
            "split_manifest": "data/splits/education/manifest.json",
            "train_rows": 180903, "validation_rows": 45226, "gold_rows": 736,
            "dataset_version": "dv-0ce28fa6b560（见 reports/phase3-preprocessing-summary.json）",
        },
        "runs": [r for r in runs if r],
        "models": _model_sizes(),
        "comparison": _load(REPORT_DIR / "experiment-comparison.json"),
        "verification": _load(REPORT_DIR / "model-verification.json"),
        "tests": _load(REPORT_DIR / "education-tests.json"),
        "learnability": _load(REPORT_DIR / "learnability.json"),
        "label_noise": _load(REPORT_DIR / "label-noise.json"),
        "run_all": _load(REPORT_DIR / "run-all.json"),
        "limitations": [
            "开发集标签全部是伪标签（旧线上系统输出，人工复核一致率 45.92%），"
            "所有开发集指标度量的是对伪标签的拟合能力，不是真实标注准确率。",
            "人工金标准 736 条在第三阶段已用于规则基线比较，本阶段只做一次性最终评估，"
            "不参与训练、阈值选择与模型选择；不能视为全新盲测集。",
            "实验 A 的 train/validation 按整条输入文本切分，槽位表达高度重叠，"
            "度量的是已知表达分布下的归一化性能；未见表达泛化只能看实验 B。",
            "同一槽位表达存在大量标签冲突（见 learnability.json），槽位单独可辨识的上限有限。",
        ],
    }
    jdump(result, REPORT_DIR / "results.json")
    print(f"-> {rel(REPORT_DIR / 'results.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
