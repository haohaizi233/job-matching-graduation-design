# -*- coding: utf-8 -*-
"""单独执行：Schema 校验 -> 数据规范化 -> Embedding 缓存 -> 特征构造与泄漏审计。

用法：python scripts/data_pipeline/build_features.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401
from job_matching.core import setup_logging, jdump  # noqa: E402
from job_matching import pipeline as P  # noqa: E402


def main() -> int:
    log = setup_logging(log_file="build_features.log")
    try:
        P.step_check_raw_integrity()
        P.step_validate_schema()
        s = P.step_normalize_data()
        P.step_build_embeddings()
        f = P.step_build_features()
        jdump({"ok": True, "preprocessing": {
                   k: v for k, v in s.items() if k != "education"},
               "features": {"outputs": f["outputs"],
                            "matrix_shape": f["matrix_shape"],
                            "policy_audit": f["policy_audit"]}},
              Path("reports") / "phase3-feature-build.json")
        log.info("特征构建完成")
        return 0
    except Exception as exc:
        log.error("特征构建失败：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
