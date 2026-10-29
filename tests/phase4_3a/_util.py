# -*- coding: utf-8 -*-
"""Phase4-3A 人工标注 / 独立评估测试公共工具（stdlib unittest）。

约束：
  * 只用小规模合成夹具，不读 data/raw 全量语料、不跑任何 GPU 训练；
  * 不硬编码绝对路径，ROOT 由 __file__ 推导；
  * 夹具只用于验证工程链路，不代表任何真实人工标注。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase4_3a")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 字段定义统一从 schema 取，避免测试与实现两套口径
from job_matching.annotation.schema import (  # noqa: E402
    ANNOTATION_FIELDS,
    ARBITRATION_FIELDS,
    FINAL_LABEL_FIELDS,
)

ANNOT_DIR = ROOT / "data" / "independent_eval" / "annotation"
REPORT_DIR = ROOT / "reports" / "phase4-3a"

ANNOTATOR_A = "annotator_A"
ANNOTATOR_B = "annotator_B"
ARBITRATOR = "arbitrator_1"
PV = "phase4-3a-annotation-v1"
TS = "2026-10-29T10:00:00"


# ------------------------------------------------------------------ IO
def jload(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(p: Path) -> list[dict]:
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(rows: list[dict], p: Path) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def write_csv(rows: list[dict], columns: tuple[str, ...] | list[str], p: Path) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    return p


# ------------------------------------------------------------------ 夹具
def make_resume(i: int = 0, *, rid: str | None = None, text: str | None = None,
                target_position: str = "数据分析师", skills: list[str] | None = None,
                education_level: str = "本科", years_experience: float | None = 1.0,
                is_synthetic: bool = False, source: str = "unit_fixture",
                city: str = "上海") -> dict:
    """合成简历夹具（字段形状与 annotation/pool.load_resume_file 一致）。"""
    skills = list(skills if skills is not None else ["python", "sql", "数据分析"])
    rid = rid or f"resume_{i:03d}"
    text = text if text is not None else (
        f"求职意向：{target_position}。项目经历：参与数据平台建设，负责核心模块。"
        f"技能：{'、'.join(skills)}。")
    return {
        "resume_id": rid,
        "resume_source": source,
        "resume_text": text,
        "target_position": target_position,
        "skills": skills,
        "education_level": education_level,
        "graduation_cohort": "2027",
        "employment_type": "校招",
        "years_experience": years_experience,
        "city": city,
        "salary_expectation": "面议",
        "language": "zh",
        "is_synthetic": is_synthetic,
        "resume_license": "unit-fixture",
        "content_hash": "",
    }


def make_job(i: int = 0, *, jid: str | None = None, text: str | None = None,
             title: str = "数据分析师", category: str = "INFORMATION-TECHNOLOGY",
             required: list[str] | None = None, preferred: list[str] | None = None,
             edu_tokens: list[str] | None = None, exp_years: float | None = None,
             source: str = "job-education/annotated") -> dict:
    """合成岗位夹具（字段形状与 annotation/pool.load_jobs_from_job_education 一致）。"""
    required = list(required if required is not None else ["python", "sql", "数据分析"])
    text = text if text is not None else (
        f"{title}\n岗位职责：负责相关业务系统建设。"
        f"任职要求：{'、'.join(required)}。")
    return {
        "job_id": jid or f"job_{i:03d}",
        "job_source": source,
        "job_title": title,
        "job_description": text,
        "job_text": text,
        "job_category": category,
        "job_category_source": "unit_fixture",
        "language": "zh",
        "required_skills": required,
        "preferred_skills": list(preferred or []),
        "education_requirement": {"raw": "", "tokens": list(edu_tokens or []),
                                  "status": "ok", "source": "unit_fixture"},
        "experience_requirement": {"raw": "", "years_min": exp_years,
                                   "source": "unit_fixture"},
        "historical_gold": False,
        "content_hash": "",
    }


def make_pair(i: int = 0, *, pid: str | None = None, rid: str | None = None,
              jid: str | None = None, resume_text: str = "", job_text: str = "",
              **extra) -> dict:
    pid = pid or f"pair-{i:04d}"
    rec = {
        "pair_id": pid,
        "resume_id": rid or f"resume_{i // 3:03d}",
        "job_id": jid or f"job_{i:03d}",
        "resume_source": "unit_fixture",
        "job_source": "job-education/annotated",
        "resume_text": resume_text,
        "job_text": job_text,
        "job_category": "INFORMATION-TECHNOLOGY",
        "job_category_source": "unit_fixture",
        "language": "zh",
        "difficulty_tier": "medium_skill_overlap",
        "content_hash": f"hash{i:04d}",
        "dataset_version": "dv-unit",
        "is_synthetic": False,
        "pair_provenance": "unit_fixture",
        "eligible_for_gold": True,
        "split": "dev_validation",
    }
    rec.update(extra)
    return rec


def annotation_row(pair_id: str, relevance: str, *, who: str = ANNOTATOR_A,
                   confidence: str = "high", reason: str = "1,2 必备技能满足",
                   evidence: str = "简历：技能 python；JD：任职要求 python",
                   timestamp: str = TS, protocol_version: str = PV) -> dict:
    return {
        "annotator_id": who,
        "pair_id": pair_id,
        "relevance": relevance,
        "confidence": confidence,
        "reason": reason,
        "evidence": evidence,
        "annotation_timestamp": timestamp,
        "protocol_version": protocol_version,
    }


def arbitration_row(pair_id: str, final_relevance: str, *, who: str = ARBITRATOR,
                    confidence: str = "high", reason: str = "仲裁复核原文后裁定",
                    evidence: str = "JD：任职要求 python；简历：项目经历含 python",
                    timestamp: str = TS, protocol_version: str = PV) -> dict:
    return {
        "arbitrator_id": who,
        "pair_id": pair_id,
        "final_relevance": final_relevance,
        "final_confidence": confidence,
        "reason": reason,
        "evidence": evidence,
        "annotation_timestamp": timestamp,
        "protocol_version": protocol_version,
    }


def paired(who_a: str, labels_a: list[str], who_b: str, labels_b: list[str],
           prefix: str = "pair") -> tuple[list[dict], list[dict]]:
    """构造两个标注员在同一组 pair 上的标注行（顺序一一对应）。"""
    a = [annotation_row(f"{prefix}-{i:03d}", v, who=who_a) for i, v in enumerate(labels_a)]
    b = [annotation_row(f"{prefix}-{i:03d}", v, who=who_b) for i, v in enumerate(labels_b)]
    return a, b


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
