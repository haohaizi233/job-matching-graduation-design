# -*- coding: utf-8 -*-
"""第四阶段 4.2 一键流水线：分析 -> 冒烟 -> 训练 -> 评估 -> 对照 -> 验证 -> 测试 -> 汇总。

用法：
    python scripts/education_training/run_all.py            # 全流程
    python scripts/education_training/run_all.py --skip-training
    python scripts/education_training/run_all.py --force    # 忽略残留锁

安全约束：
  * 单实例锁（reports/education-training/.run_all.lock），避免多个后台任务写同一输出；
  * 每个训练实验使用独立 run_id 目录，绝不覆盖历史产物；
  * 不修改 data/raw、data/processed、data/splits 与 4.1 的任何产物。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT, ensure_dir, jdump, fix_stdio  # noqa: E402

PY = sys.executable
SCRIPTS = ROOT / "scripts" / "education_training"
TESTS = ROOT / "tests" / "education_training"
REPORT_DIR = ROOT / "reports" / "education-training"
LOG_DIR = REPORT_DIR / "logs"
LOCK = REPORT_DIR / ".run_all.lock"

TRAIN_RUNS = [
    ("tfidf", ["--model", "tfidf", "--experiment", "A", "--input", "slot",
               "--weights", "none", "--tag", "final"]),
    ("tfidf", ["--model", "tfidf", "--experiment", "A", "--input", "slot",
               "--weights", "slot_balanced", "--tag", "final-balanced"]),
    ("tfidf", ["--model", "tfidf", "--experiment", "A", "--input", "slot_title",
               "--weights", "none", "--tag", "final-title"]),
    ("charcnn", ["--model", "charcnn", "--experiment", "A", "--input", "slot",
                 "--weights", "none", "--tag", "final"]),
    ("charcnn", ["--model", "charcnn", "--experiment", "A", "--input", "slot",
                 "--weights", "slot_balanced", "--tag", "final-balanced"]),
    ("tfidf", ["--model", "tfidf", "--experiment", "B", "--input", "slot",
               "--weights", "none", "--tag", "final-holdout"]),
    ("charcnn", ["--model", "charcnn", "--experiment", "B", "--input", "slot",
                 "--weights", "none", "--tag", "final-holdout"]),
]


def run_step(idx: int, title: str, argv: list[str]) -> dict:
    ensure_dir(LOG_DIR)
    log_path = LOG_DIR / f"step-{idx:02d}-{title}.log"
    print(f"[步骤 {idx:02d}] {title}", flush=True)
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run([PY] + argv, cwd=str(ROOT), stdout=fh,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              errors="replace")
    rec = {"index": idx, "title": title, "argv": argv, "returncode": proc.returncode,
           "seconds": round(time.time() - t0, 2), "log": str(log_path.relative_to(ROOT)).replace("\\", "/")}
    print(f"       rc={proc.returncode} {rec['seconds']}s -> {rec['log']}", flush=True)
    return rec


def main() -> int:
    fix_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-training", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    ensure_dir(REPORT_DIR)
    if LOCK.exists() and not args.force:
        age = time.time() - LOCK.stat().st_mtime
        print(f"[中止] 发现锁文件 {LOCK}（{age:.0f}s 前）。若有任务在跑请勿重复启动；"
              f"确认无任务后可加 --force。")
        return 2
    LOCK.write_text(f"pid={os.getpid()} started={time.strftime('%Y-%m-%dT%H:%M:%S')}\n",
                    encoding="utf-8")

    steps: list[dict] = []
    t0 = time.time()
    try:
        steps.append(run_step(1, "analyze_learnability",
                              [str(SCRIPTS / "analyze_learnability.py")]))
        if not args.skip_training:
            steps.append(run_step(2, "smoke_tfidf",
                                  [str(SCRIPTS / "train.py"), "--model", "tfidf",
                                   "--experiment", "A", "--input", "slot", "--weights", "none",
                                   "--smoke", "3000", "--tag", "smoke"]))
            steps.append(run_step(3, "smoke_charcnn",
                                  [str(SCRIPTS / "train.py"), "--model", "charcnn",
                                   "--experiment", "A", "--input", "slot", "--weights", "none",
                                   "--smoke", "3000", "--tag", "smoke"]))
            for i, (_model, argv) in enumerate(TRAIN_RUNS, start=4):
                steps.append(run_step(i, "train_" + "-".join(argv[argv.index("--model") + 1::2]),
                                      [str(SCRIPTS / "train.py")] + argv))
        # 评估所有非 smoke run
        model_root = ROOT / "models" / "education"
        eval_idx = 20
        for run_dir in sorted(model_root.glob("*/*")):
            if not (run_dir / "manifest.json").exists() or "smoke" in run_dir.name:
                continue
            steps.append(run_step(eval_idx, f"evaluate_{run_dir.name}",
                                  [str(SCRIPTS / "evaluate.py"), "--run-dir", str(run_dir)]))
            eval_idx += 1
        steps.append(run_step(30, "compare_models", [str(SCRIPTS / "compare_models.py")]))
        steps.append(run_step(31, "verify_models", [str(SCRIPTS / "verify_models.py")]))
        steps.append(run_step(32, "tests", [str(TESTS / "run_all.py")]))
    finally:
        LOCK.unlink(missing_ok=True)

    ok = all(s["returncode"] == 0 for s in steps)
    summary = {
        "generated_by": "scripts/education_training/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": round(time.time() - t0, 2),
        "ok": ok,
        "steps": steps,
    }
    jdump(summary, REPORT_DIR / "run-all.json")
    print(f"=== 流水线完成 ok={ok} 用时 {summary['seconds']}s ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
