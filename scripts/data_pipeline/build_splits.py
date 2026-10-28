# -*- coding: utf-8 -*-
"""单独执行：人岗匹配三协议切分 + 学历数据重新划分 + 切分验证。

用法：python scripts/data_pipeline/build_splits.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401
from job_matching.core import setup_logging  # noqa: E402
from job_matching import pipeline as P  # noqa: E402


def main() -> int:
    log = setup_logging(log_file="build_splits.log")
    try:
        P.step_check_raw_integrity()
        P.step_build_splits()
        log.info("切分完成")
        return 0
    except Exception as exc:
        log.error("切分失败：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
