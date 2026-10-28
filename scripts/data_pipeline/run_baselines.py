# -*- coding: utf-8 -*-
"""单独执行：零训练 Baseline（人岗匹配 + 学历）。

用法：python scripts/data_pipeline/run_baselines.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401
from job_matching.core import setup_logging  # noqa: E402
from job_matching import pipeline as P  # noqa: E402


def main() -> int:
    log = setup_logging(log_file="run_baselines.log")
    try:
        P.step_run_baselines()
        log.info("Baseline 运行完成")
        return 0
    except Exception as exc:
        log.error("Baseline 运行失败：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
