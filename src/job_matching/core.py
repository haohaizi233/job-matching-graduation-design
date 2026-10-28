# -*- coding: utf-8 -*-
"""job_matching 核心工具：项目根解析、哈希、JSON 读写、日志、运行清单。

约束：
  * 只读 data/raw；
  * 所有产物带 data_version（由原始文件哈希推导）与 pipeline_version；
  * 日志与报告中绝不输出简历正文 / JD 原文 / 联系方式。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

# src/job_matching/core.py -> parents[0]=job_matching, [1]=src, [2]=项目根
ROOT = Path(__file__).resolve().parents[2]
PIPELINE_VERSION = "phase3-v1"
LOG_DIR = ROOT / "reports" / "phase3-logs"


# ------------------------------------------------------------------ 基础
def fix_stdio() -> None:
    """Windows 控制台下强制 UTF-8，避免中文路径/输出乱码。"""
    for stream in ("stdout", "stderr"):
        h = getattr(sys, stream, None)
        if h is not None and hasattr(h, "reconfigure"):
            try:
                h.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def rel(p: os.PathLike | str) -> str:
    """相对项目根的路径，统一 / 分隔。"""
    p = Path(p)
    try:
        return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def ensure_dir(p: os.PathLike | str) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------ 哈希
def sha256_file(p: os.PathLike | str, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_array(a: np.ndarray) -> str:
    """对数组内容做哈希（含 dtype 与 shape，避免歧义）。"""
    h = hashlib.sha256()
    h.update(str(a.dtype).encode("utf-8"))
    h.update(str(a.shape).encode("utf-8"))
    h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def short_hash(*parts: str, n: int = 12) -> str:
    return sha256_text("\x1f".join(parts))[:n]


def dataset_version(file_hashes: dict[str, str]) -> str:
    """由原始文件哈希集合推导数据版本号，内容变则版本号变。"""
    payload = json.dumps(file_hashes, sort_keys=True, ensure_ascii=False)
    return "dv-" + sha256_text(payload)[:12]


# ------------------------------------------------------------------ JSON
def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def jdump(obj, path: os.PathLike | str, indent: int = 2, sort_keys: bool = True) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, sort_keys=sort_keys,
                  default=_json_default)
        f.write("\n")
    return path


def jload(path: os.PathLike | str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 日志
_LOGGER_NAME = "job_matching"


def setup_logging(name: str = _LOGGER_NAME, log_file: str | None = "pipeline.log",
                 level: int = logging.INFO) -> logging.Logger:
    fix_stdio()
    logger = logging.getLogger(name)
    if getattr(logger, "_phase3_configured", False):
        return logger
    logger.setLevel(level)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if log_file:
        ensure_dir(LOG_DIR)
        fh = logging.FileHandler(LOG_DIR / log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger._phase3_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


# ------------------------------------------------------------------ 运行上下文
class RunContext:
    """记录每个步骤的耗时、输入输出、行数变化与文件哈希，用于 manifest 与报告。"""

    def __init__(self, name: str, params: dict | None = None):
        self.name = name
        self.params = params or {}
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.steps: list[dict] = []
        self.log = setup_logging()

    # -- 步骤计时
    def step(self, title: str):
        return _Step(self, title)

    def add(self, record: dict) -> None:
        self.steps.append(record)

    # -- 产物登记
    def register_output(self, path: os.PathLike | str, kind: str = "file", **extra) -> dict:
        p = Path(path)
        info = {"path": rel(p), "kind": kind}
        if p.is_file():
            info["bytes"] = p.stat().st_size
            info["sha256"] = sha256_file(p)
        info.update(extra)
        return info

    def manifest(self, inputs: list[dict], outputs: list[dict], rows: dict | None = None,
                 notes: list[str] | None = None) -> dict:
        return {
            "generated_by": self.name,
            "pipeline_version": PIPELINE_VERSION,
            "started_at": self.started_at,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project_root": str(ROOT),
            "params": self.params,
            "inputs": inputs,
            "outputs": outputs,
            "row_counts": rows or {},
            "steps": self.steps,
            "notes": notes or [],
        }


class _Step:
    def __init__(self, ctx: RunContext, title: str):
        self.ctx = ctx
        self.title = title
        self.t0 = 0.0

    def __enter__(self):
        self.t0 = time.time()
        self.ctx.log.info("[开始] %s", self.title)
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.time() - self.t0
        if exc_type is None:
            self.ctx.log.info("[完成] %s （耗时 %.1fs）", self.title, dt)
        else:
            self.ctx.log.error("[失败] %s （耗时 %.1fs）%s", self.title, dt, exc)
        self.ctx.add({"title": self.title, "seconds": round(dt, 3),
                      "ok": exc_type is None})
        return False


# ------------------------------------------------------------------ 文本规范化
_WS = __import__("re").compile(r"\s+")


def norm_text(s) -> str:
    """Unicode NFKC + 空白折叠 + 去首尾空白。不改写正文内容。"""
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = _WS.sub(" ", t).strip()
    return t


def write_csv(df, path: os.PathLike | str, float_format: str = "%.10g") -> Path:
    """确定性 CSV 写出（固定浮点格式、固定换行、UTF-8 无 BOM），保证可复现哈希。"""
    path = Path(path)
    ensure_dir(path.parent)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n",
              float_format=float_format)
    return path
