# -*- coding: utf-8 -*-
"""Phase4-3B 研究工具的仓库根路径解析（可移植、防串仓）。

历史缺陷（本轮修复）：
    多个脚本曾写死 `ROOT = Path(os.environ.get("JM_ROOT", r"D:\\desktop\\job-matching-model-research"))`。
    一旦在别的检出（例如主工作区）里运行，脚本会**静默扫描另一个仓库的 models/ 与 data/**，
    导致模型登记表串仓、冻结复验失败，且错误极难定位。

修复原则（任务书 2.2 / 环境可复现要求）：
  1. 默认根路径由本文件位置推导，绝不写死本机绝对路径；
  2. `JM_ROOT` 仅作为显式覆盖入口，覆盖后必须通过 `assert_repo_root` 自检；
  3. 自检不通过直接抛 `RootResolutionError`，**不静默退化**到任何别的目录。
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "RootResolutionError",
    "assert_repo_root",
    "repo_root",
    "ROOT",
    "MODELS_ROOT",
    "DATA_ROOT",
    "REPORTS_ROOT",
    "PHASE4_3B_DIR",
    "MODEL_RESEARCH_DIR",
    "SRC_ROOT",
    "ensure_src_on_path",
]


class RootResolutionError(RuntimeError):
    """仓库根路径解析失败或指向了别的工程。"""


#: 判定「这是本仓库」的最小标记
_REQUIRED_MARKERS = (
    ("src", "job_matching"),
    ("tests", "phase4_3b"),
    ("scripts", "phase4_3b"),
)


def assert_repo_root(root: Path) -> Path:
    """确认 `root` 确实是本仓库根目录，否则抛错（不静默继续）。"""
    root = Path(root).resolve()
    if not root.is_dir():
        raise RootResolutionError(f"仓库根目录不存在: {root}")
    missing = [str(Path(*m)) for m in _REQUIRED_MARKERS if not (root.joinpath(*m)).exists()]
    if missing:
        raise RootResolutionError(
            f"路径不像本项目仓库根目录: {root}（缺少 {missing}）。"
            "若确实要指向别处，请设置 JM_ROOT 指向一个完整的本项目检出。"
        )
    return root


def repo_root() -> Path:
    """解析仓库根目录：`JM_ROOT` 显式覆盖 > 由本文件位置推导。"""
    here = Path(__file__).resolve()
    # scripts/phase4_3b/_paths.py -> 仓库根是 parents[2]
    derived = here.parents[2]
    override = os.environ.get("JM_ROOT", "").strip()
    root = assert_repo_root(Path(override)) if override else assert_repo_root(derived)
    return root


ROOT: Path = repo_root()
MODELS_ROOT: Path = ROOT / "models"
DATA_ROOT: Path = ROOT / "data"
REPORTS_ROOT: Path = ROOT / "reports"
PHASE4_3B_DIR: Path = REPORTS_ROOT / "phase4-3b"
MODEL_RESEARCH_DIR: Path = REPORTS_ROOT / "model-research"
SRC_ROOT: Path = ROOT / "src"


def ensure_src_on_path() -> Path:
    """把 `src/` 加入 sys.path（幂等），返回仓库根。"""
    import sys

    s = str(SRC_ROOT)
    if s not in sys.path:
        sys.path.insert(0, s)
    return ROOT
