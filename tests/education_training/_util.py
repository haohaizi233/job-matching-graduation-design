# -*- coding: utf-8 -*-
"""第四阶段 4.2 学历模型训练/推理测试公共工具（stdlib unittest）。"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "education_training")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MODELS_ROOT = ROOT / "models" / "education"
SPLITS_DIR = ROOT / "data" / "splits" / "education"
REPORT_DIR = ROOT / "reports" / "education-training"
MATCHING_MODELS = ROOT / "models" / "matching"

# 合成小样本：仅用于结构/训练链路测试，不代表任何真实数据
SYNTH_TEXTS = ["本科", "本科及以上", "硕士", "硕士及以上", "大专", "博士", "不限", "专科及以上",
               "硕士研究生", "学历不限", "", "大学本科"]
SYNTH_LABELS = [
    ["本科"], ["本科", "硕士", "博士"], ["硕士"], ["硕士", "博士"], ["大专"], ["博士"],
    ["学历不限"], ["大专", "本科", "硕士", "博士"], ["硕士"], ["学历不限"], ["学历不明"],
    ["本科"],
]


def jload(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def all_run_dirs(include_smoke: bool = True) -> list[Path]:
    out = []
    for mdir in sorted(MODELS_ROOT.glob("*/*")):
        if (mdir / "manifest.json").exists() and (include_smoke or "smoke" not in mdir.name):
            out.append(mdir)
    return out


def latest_run_dir() -> Path | None:
    runs = all_run_dirs(include_smoke=False) or all_run_dirs(include_smoke=True)
    return runs[-1] if runs else None


def synth_multi_hot() -> np.ndarray:
    from job_matching.education.labels import LABEL_ORDER, tokens_to_multi_hot
    return tokens_to_multi_hot(SYNTH_LABELS).astype(np.int8)


FORBIDDEN_LABEL_TOKENS = ["label_tokens_json", "label_multi_hot", "label_status", "label_raw",
                          "assistant", "人工正确结果", "label_provenance", "is_gold"]


def strip_comments_and_docstrings(src: str) -> str:
    """去掉 # 注释与字符串字面量，只留真实代码用于关键词扫描。"""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "#":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith('"""', i) or src.startswith("'''", i):
            q = src[i:i + 3]
            j = src.find(q, i + 3)
            i = n if j < 0 else j + 3
            continue
        if c in "\"'":
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q:
                    break
                j += 1
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def label_access_hits(path: Path) -> list[str]:
    code = strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
    return [t for t in FORBIDDEN_LABEL_TOKENS if t in code]
