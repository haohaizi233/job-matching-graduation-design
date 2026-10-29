# -*- coding: utf-8 -*-
"""Phase4-3A-2 脚本公共工具：路径、报告写出、清单记录（不硬编码绝对路径）。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT, ensure_dir, jdump, rel, sha256_file  # noqa: E402

# 工作区根：默认项目根；测试/演练可用 PHASE4_3A_2_WORKSPACE 指向隔离目录。
# 隔离工作区下所有数据、私有标注、报告路径全部改写到该目录，
# 保证自动化测试**不触碰**真实 Gold 目录与 data/private 真实信息。
WORKSPACE_ENV = "PHASE4_3A_2_WORKSPACE"
WORKSPACE = Path(os.environ.get(WORKSPACE_ENV) or ROOT).resolve()
IS_FIXTURE_WORKSPACE = WORKSPACE != ROOT.resolve()


def ensure_workspace_safe() -> None:
    """工程夹具工作区不得指向真实数据/模型/项目根（防止污染历史成果）。"""
    if not IS_FIXTURE_WORKSPACE:
        return
    forbidden = [(ROOT / "data").resolve(), (ROOT / "models").resolve(),
                 ROOT.resolve()]
    for f in forbidden:
        if WORKSPACE == f or f in WORKSPACE.parents:
            raise RuntimeError(
                f"[workspace_guard] {WORKSPACE_ENV}={WORKSPACE} 指向受保护目录 {f}；"
                f"工程夹具必须使用独立临时目录，禁止触碰真实数据/模型/项目根")


REPORT_DIR = WORKSPACE / "reports" / "phase4-3a-2"
EVAL_DATA_DIR = WORKSPACE / "data" / "independent_eval"
POOL_DIR = EVAL_DATA_DIR / "pool"
PAIRS_DIR = EVAL_DATA_DIR / "pairs"
ANNOT_DIR = EVAL_DATA_DIR / "annotation"
TEMPLATE_DIR = ANNOT_DIR / "templates"
PACKET_DIR = ANNOT_DIR / "packets"
IMPORT_DIR = ANNOT_DIR / "imports"
FROZEN_DIR = EVAL_DATA_DIR / "frozen"
DOCS_DIR = WORKSPACE / "docs"

# 真实简历 / 授权 / 原始人工标注：仅限本地非公开目录（.gitignore 忽略）
PRIVATE_DIR = WORKSPACE / "data" / "private"
PRIVATE_RESUME_DIR = PRIVATE_DIR / "resumes"
PRIVATE_CONSENT_DIR = PRIVATE_DIR / "consent"
PRIVATE_ANNOT_DIR = PRIVATE_DIR / "annotations_raw"
PRIVATE_ACCEPTED_DIR = PRIVATE_DIR / "accepted"

JOB_POOL_V1 = POOL_DIR / "job_pool_v1.jsonl"
JOB_POOL_V2 = POOL_DIR / "job_pool_v2.jsonl"
PAIRS_REAL_V2 = PAIRS_DIR / "pairs_real_v2.jsonl"

ANNOTATOR_A = "annotator_A"
ANNOTATOR_B = "annotator_B"
ARBITRATOR = "arbitrator_1"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def write_report(name: str, obj: dict) -> Path:
    ensure_dir(REPORT_DIR)
    return jdump(obj, REPORT_DIR / name)


def write_jsonl(rows: list[dict], path: Path) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_jsonl(path: Path) -> list[dict]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def file_record(path: Path) -> dict:
    p = Path(path)
    return {"path": rel(p),
            "bytes": p.stat().st_size, "sha256": sha256_file(p)}


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def find_resume_files(resume_dir: Path) -> list[Path]:
    """收集简历文件（txt/docx/pdf/csv/jsonl），确定性排序。"""
    resume_dir = Path(resume_dir)
    if not resume_dir.exists():
        return []
    out = []
    for ext in ("*.txt", "*.docx", "*.pdf", "*.csv", "*.jsonl"):
        out.extend(resume_dir.glob(ext))
    return sorted(out)
