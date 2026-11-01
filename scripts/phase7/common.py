# -*- coding: utf-8 -*-
"""Phase7 脚本公共工具：路径、报告写出、隔离工作区安全检查。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT, ensure_dir, jdump, rel, sha256_file  # noqa: E402

#: 隔离演练工作区环境变量（与 scripts/phase4_3a_2/common.py 同名口径）
WORKSPACE_ENV = "PHASE7_WORKSPACE"
WORKSPACE = Path(os.environ.get(WORKSPACE_ENV) or ROOT).resolve()
IS_FIXTURE_WORKSPACE = WORKSPACE != ROOT.resolve()

#: 演练/测试产物绝不允许写入的真实数据目录
FORBIDDEN_REAL_DIRS = (
    ROOT / "data" / "private",
    ROOT / "data" / "independent_eval" / "frozen",
    ROOT / "data" / "independent_eval" / "annotation" / "imports",
    ROOT / "data" / "independent_eval" / "pairs",
)


def ensure_workspace_safe() -> None:
    """工作区不得落在真实数据目录内（防止污染真实 Gold / 授权记录 / 标注原文）。

    规则（单向包含判定）：
      * WORKSPACE 等于或位于 `data/private`、`data/independent_eval/{frozen,annotation/imports,pairs}` 之内
        → 一律拒绝（无论是否夹具模式）；
      * 夹具模式下 WORKSPACE 不得是项目根本身（项目根是生产工作区，不属于夹具）。
    反向包含（真实目录位于 WORKSPACE 之内）是正常生产形态，不拒绝。
    """
    for f in FORBIDDEN_REAL_DIRS:
        f = f.resolve()
        if WORKSPACE == f or f in WORKSPACE.parents:
            raise RuntimeError(
                f"[phase7] 工作区 {WORKSPACE} 落在真实数据目录 {f} 内，拒绝执行")
    if IS_FIXTURE_WORKSPACE and WORKSPACE == ROOT.resolve():
        raise RuntimeError(
            f"[phase7] 夹具工作区不得指向项目根 {ROOT}（会污染真实成果）")


def report_path(*parts: str) -> Path:
    """报告落盘路径（相对 WORKSPACE）。"""
    p = WORKSPACE.joinpath(*parts)
    ensure_dir(p.parent)
    return p


def write_json(path: Path, payload: dict) -> Path:
    jdump(payload, str(path))
    return path


def read_json(path: Path | str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "ROOT", "WORKSPACE", "WORKSPACE_ENV", "IS_FIXTURE_WORKSPACE",
    "ensure_dir", "ensure_workspace_safe", "jdump", "read_json", "rel",
    "report_path", "sha256_file", "write_json",
]
