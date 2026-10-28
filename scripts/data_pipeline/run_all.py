# -*- coding: utf-8 -*-
"""完整执行入口：串联第三阶段全部步骤。

用法：
    python scripts/data_pipeline/run_all.py                 # 全量执行
    python scripts/data_pipeline/run_all.py --from 5        # 从第 5 步开始
    python scripts/data_pipeline/run_all.py --only 6        # 只执行第 6 步

特性：日志输出 / 失败即停（非零退出码）/ 可重复执行 / 明确输入输出 /
      不覆盖已存在且未验证的产物（产物带哈希清单，重跑即重新校验）。
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401
from job_matching.core import ROOT, RunContext, get_logger, jdump, setup_logging  # noqa: E402
from job_matching import pipeline as P  # noqa: E402

STEPS = [
    ("check_raw_integrity", "原始数据完整性（G1 前置）", P.step_check_raw_integrity),
    ("validate_schema", "Schema 校验", P.step_validate_schema),
    ("normalize_data", "数据规范化", P.step_normalize_data),
    ("build_embeddings", "Embedding 缓存", P.step_build_embeddings),
    ("build_features", "特征构造与泄漏审计", P.step_build_features),
    ("build_splits", "可信数据切分", P.step_build_splits),
    ("run_baselines", "零训练 Baseline", P.step_run_baselines),
    ("run_gates", "数据质量门禁 G1-G7", P.step_run_gates),
    ("write_reports", "报告生成", P.step_write_reports),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="第三阶段数据流水线")
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--only", dest="only", type=int, default=0)
    args = ap.parse_args()

    log = setup_logging(log_file="pipeline.log")
    log.info("=== 第三阶段流水线启动 ===")
    t0 = time.time()
    results = {}
    for i, (name, title, fn) in enumerate(STEPS, start=1):
        if args.only and i != args.only:
            continue
        if not args.only and i < args.start:
            continue
        ctx = RunContext(f"step_{name}", {"step_index": i, "step": name})
        try:
            with ctx.step(f"{i}. {title}"):
                results[name] = fn()
            # 每步结果落盘，供报告与验收逐条取证
            jdump(results[name], ROOT / "reports" / "phase3-steps" / f"{i}-{name}.json")
        except Exception as exc:  # 关键失败立即停止，不允许继续宣布成功
            log.error("步骤 %d（%s）失败：%s", i, name, exc)
            log.debug("%s", traceback.format_exc())
            jdump({"ok": False, "failed_step": name, "error": str(exc),
                   "traceback": traceback.format_exc()},
                  Path("reports") / "phase3-run-failure.json")
            log.error("=== 流水线失败退出（耗时 %.1fs）===", time.time() - t0)
            return 2
    log.info("=== 流水线全部完成（耗时 %.1fs）===", time.time() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
