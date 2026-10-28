# -*- coding: utf-8 -*-
"""单独执行：数据质量门禁 G1-G7 + 可复现性验证。

用法：python scripts/data_pipeline/validate_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401
from job_matching.core import setup_logging  # noqa: E402
from job_matching import pipeline as P  # noqa: E402


def main() -> int:
    log = setup_logging(log_file="validate_pipeline.log")
    try:
        P.step_check_raw_integrity()
        P.step_run_gates()
        log.info("数据质量门禁全部通过")
        return 0
    except Exception as exc:
        log.error("门禁失败：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
