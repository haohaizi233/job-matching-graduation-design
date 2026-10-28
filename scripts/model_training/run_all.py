# -*- coding: utf-8 -*-
"""第四阶段 4.1 端到端执行入口：训练 -> 评估 -> 对比 -> 验证 -> 测试。

用法：
    python scripts/model_training/run_all.py                # 全量
    python scripts/model_training/run_all.py --skip-train   # 跳过训练，仅对比/验证/测试
    python scripts/model_training/run_all.py --only smoke   # 只跑冒烟

纪律：
  * 每个实验独立 run_id 与独立输出目录，互不覆盖；
  * 任何一步失败立即停止并保留失败记录（reports/model-training/run-failure.json）；
  * 全程不修改 data/raw、不重新切分数据、不覆盖第三阶段产物。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402
from job_matching.core import ROOT, ensure_dir, jdump  # noqa: E402

PY = sys.executable
MODELS = ["ridge", "gradient_boosting", "mlp", "ranknet"]
PROTOCOLS = ["candidate_cold", "job_cold", "double_cold"]
ABLATION_MODELS = ["ridge", "ranknet"]
ABLATION_GROUPS = ["skill", "position", "category"]
LOG_DIR = ROOT / "reports" / "model-training" / "logs"
OUT_DIR = ROOT / "reports" / "model-training"


def run_step(name: str, cmd: list[str], steps: list[dict]) -> None:
    ensure_dir(LOG_DIR)
    log_path = LOG_DIR / f"step-{len(steps) + 1:02d}-{name}.log"
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                              cwd=str(ROOT), text=True, encoding="utf-8", errors="replace")
    dt = round(time.time() - t0, 2)
    steps.append({"step": name, "cmd": " ".join(cmd), "returncode": proc.returncode,
                  "seconds": dt, "log": str(log_path.relative_to(ROOT)).replace("\\", "/")})
    print(f"[{'OK' if proc.returncode == 0 else 'FAIL'}] {name} ({dt}s)", flush=True)
    if proc.returncode != 0:
        jdump({"ok": False, "failed_step": name, "returncode": proc.returncode,
               "log": steps[-1]["log"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
              OUT_DIR / "run-failure.json")
        raise SystemExit(f"步骤失败: {name}（日志 {steps[-1]['log']}）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-train", action="store_true")
    ap.add_argument("--only", choices=["smoke", "train", "evaluate", "ablation",
                                       "compare", "verify", "tests"], default="")
    args = ap.parse_args()

    ensure_dir(OUT_DIR)
    ts = time.strftime("%Y%m%d-%H%M%S")
    steps: list[dict] = []
    t_start = time.time()

    def want(name: str) -> bool:
        return (not args.only) or args.only == name

    # ---- 0. 环境与原始数据完整性
    if want("verify") or not args.only:
        run_step("pip_check", [PY, "-m", "pip", "check"], steps)
        run_step("raw_data_integrity",
                 [PY, "scripts/verify_data_integrity.py", "--quiet"], steps)

    # ---- 1. 冒烟测试（小批量，确认维度/loss/梯度/显存）
    if want("smoke") and not args.skip_train:
        for m in MODELS:
            run_step(f"smoke_{m}",
                     [PY, "scripts/model_training/train.py", "--model", m,
                      "--protocol", "candidate_cold", "--smoke",
                      "--run-id", f"{m}-candidate_cold-smoke-{ts}"], steps)

    # ---- 2. 完整训练（4 模型 x 3 协议）
    run_ids: dict[tuple[str, str], str] = {}
    if want("train") and not args.skip_train:
        for p in PROTOCOLS:
            for m in MODELS:
                rid = f"{m}-{p}-final-{ts}"
                run_ids[(m, p)] = rid
                run_step(f"train_{m}_{p}",
                         [PY, "scripts/model_training/train.py", "--model", m,
                          "--protocol", p, "--run-id", rid], steps)

    # ---- 3. 确认评估（validation + test）
    if want("evaluate") and not args.skip_train:
        for (m, p), rid in run_ids.items():
            run_step(f"eval_{m}_{p}",
                     [PY, "scripts/model_training/evaluate.py",
                      "--run-dir", f"models/matching/{m}/{p}/{rid}"], steps)

    # ---- 4. 特征组消融（candidate_cold，线性 + 成对两类代表模型）
    if want("ablation") and not args.skip_train:
        for m in ABLATION_MODELS:
            for g in ABLATION_GROUPS:
                rid = f"{m}-candidate_cold-ablation-{g}-{ts}"
                run_step(f"ablation_{m}_drop_{g}",
                         [PY, "scripts/model_training/train.py", "--model", m,
                          "--protocol", "candidate_cold", "--drop-group", g,
                          "--tag", f"ablation-{g}", "--run-id", rid], steps)
                run_step(f"eval_ablation_{m}_drop_{g}",
                         [PY, "scripts/model_training/evaluate.py",
                          "--run-dir", f"models/matching/{m}/candidate_cold/{rid}"], steps)

    # ---- 5. 模型对比 / Bootstrap / 错误分析 / 报告
    if want("compare"):
        run_step("compare_models", [PY, "scripts/model_training/compare_models.py"], steps)

    # ---- 6. 模型产物验证
    if want("verify"):
        run_step("verify_models", [PY, "scripts/model_training/verify_models.py"], steps)

    # ---- 7. 自动化测试
    if want("tests"):
        run_step("tests_model_training",
                 [PY, "tests/model_training/run_all.py"], steps)
        run_step("pip_check_after", [PY, "-m", "pip", "check"], steps)

    fail = OUT_DIR / "run-failure.json"
    if fail.exists():
        fail.replace(LOG_DIR / f"run-failure-archive-{ts}.json")
    jdump({"generated_by": "scripts/model_training/run_all.py",
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "ok": True, "seconds": round(time.time() - t_start, 2), "steps": steps},
          OUT_DIR / "pipeline-run.json")
    print(f"=== 全部完成（{round(time.time() - t_start, 1)}s）===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
