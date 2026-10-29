# -*- coding: utf-8 -*-
"""真实中文简历安全导入（Phase4-3A-2 模块 A / 测试场景 1、2、3、13、18）。

支持格式：PDF（PyMuPDF/fitz，缺失时显式报错）、DOCX（stdlib zipfile+XML 最小适配器）、
UTF-8 TXT、结构化 CSV / JSONL。

纪律：
  * 来源三类隔离（consent.SOURCE_CLASSES）：A 本人同意 / B 许可公开 / C 合成测试；
  * 无授权记录的真实简历**拒绝进入**（ResumeIntakeError）；授权未通过的一律隔离；
  * 英文简历不得充当中文 Gold（usable_for_chinese_gold=false + 隔离）；
  * 合成简历 is_synthetic=true、eligible_for_gold=false，永不冒充真实数据；
  * 导入即脱敏（PII 掩码），原始命中只记数量不记原文；
  * resume_id 随机化（内容哈希 + 种子派生），不用真实姓名；同文本重复自动隔离。
"""
from __future__ import annotations

import csv
import json
import re
import zipfile
from pathlib import Path

from ..core import norm_text
from ..infra.documents import (  # noqa: F401  文本抽取适配器已下沉 infra
    SUPPORTED_FORMATS,
    ResumeIntakeError,
    extract_text,
)
from . import dedup as dedup_mod
from .consent import ConsentError, SOURCE_CLASSES, consent_index, gold_eligibility
from .pii import scrub_record
from .pool import detect_language


INTAKE_FIELDS = (
    "resume_id", "resume_source", "source_class", "consent_id", "consent_status",
    "resume_text", "target_position", "skills", "education_level", "graduation_cohort",
    "employment_type", "years_experience", "city", "salary_expectation",
    "language", "is_synthetic", "usable_for_chinese_gold", "eligible_for_gold",
    "quarantine_reason", "resume_license", "content_hash", "dataset_version",
)

_STRUCTURED_REQUIRED = ("resume_text",)
_STRUCTURED_OPTIONAL = (
    "resume_id", "target_position", "skills", "education_level", "graduation_cohort",
    "employment_type", "years_experience", "city", "salary_expectation", "license",
)


# ResumeIntakeError / SUPPORTED_FORMATS / extract_text 由 ..infra.documents 提供（上方 re-export）。


# ------------------------------------------------------------------ 结构化导入
def _split_skills(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            return [str(v).strip() for v in json.loads(s) if str(v).strip()]
        except Exception:
            pass
    return [t.strip() for t in re.split(r"[;,;、|/]", s) if t.strip()]


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_structured(path: Path | str) -> list[dict]:
    """CSV / JSONL 结构化简历行。必须含 resume_text 列。"""
    p = Path(path)
    if not p.exists():
        raise ResumeIntakeError(f"简历文件不存在: {p}")
    ext = p.suffix.lower()
    if ext == ".jsonl":
        rows = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    elif ext == ".csv":
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    else:
        raise ResumeIntakeError(f"结构化导入仅支持 .csv / .jsonl: {p}")
    if not rows:
        return []
    missing = [c for c in _STRUCTURED_REQUIRED if c not in rows[0]]
    if missing:
        raise ResumeIntakeError(f"结构化简历文件缺少必要列: {missing}")
    return rows


# ------------------------------------------------------------------ 稳定 ID
def assign_resume_id(content_hash: str, seed: int = 20261212) -> str:
    """随机化 resume_id：内容哈希 + 种子派生，确定性可复现，绝不使用真实姓名。"""
    return "resume_" + dedup_mod.sha256_text(f"{int(seed)}:{content_hash}")[:12]


# ------------------------------------------------------------------ 导入主流程
def intake_resumes(items: list[dict], *, source_class: str,
                   consent_records: list[dict] | None = None,
                   seed: int = 20261212, source_name: str = "import",
                   require_consent: bool = True) -> dict:
    """批量导入简历。

    items 元素：{"path": <txt/docx/pdf>} 或 {"row": <csv/jsonl 行>}（可带 "path" 溯源）。
    返回 {"accepted": [...], "quarantined": [...], "report": {...}}。
    accepted = 可进入 Gold 候选的真实中文简历；其余全部带原因隔离。
    """
    if source_class not in SOURCE_CLASSES:
        raise ResumeIntakeError(f"来源类别非法: {source_class!r}，合法值 {SOURCE_CLASSES}")
    is_synthetic_source = source_class == "C_synthetic"
    try:
        cidx = consent_index(consent_records or [])
    except ConsentError as e:
        raise ResumeIntakeError(f"授权记录非法: {e}") from e

    accepted: list[dict] = []
    quarantined: list[dict] = []
    pii_hits: dict[str, int] = {}
    seen_hash: dict[str, str] = {}
    fmt_counts: dict[str, int] = {}

    for item in items:
        if "row" in item:
            row = dict(item["row"])
            raw_text = str(row.get("resume_text", ""))
            fmt = "row"
        else:
            got = extract_text(item["path"])
            raw_text = got["text"]
            fmt = got["format"]
            row = {}
        fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1

        if not str(raw_text).strip():
            raise ResumeIntakeError(f"简历正文为空（source={source_name}, format={fmt}）")

        text, hits = scrub_record({"resume_text": raw_text}, ["resume_text"])
        for k, v in hits.items():
            pii_hits[k] = pii_hits.get(k, 0) + v

        content_hash = dedup_mod.exact_hash(text["resume_text"])
        rid = str(row.get("resume_id", "")).strip() or assign_resume_id(content_hash, seed)

        # 同文本重复：相同简历不同 ID -> 隔离（保留首条）
        if content_hash in seen_hash:
            quarantined.append({"resume_id": rid, "reason": "duplicate_resume_text",
                                "dup_of": seen_hash[content_hash], "content_hash": content_hash})
            continue
        seen_hash[content_hash] = rid

        consent = cidx.get(rid)
        if consent is None:
            if is_synthetic_source:
                consent = {"consent_id": "", "source_class": "C_synthetic",
                           "consent_status": "not_applicable", "license": "synthetic-generated-local"}
            elif require_consent:
                raise ResumeIntakeError(
                    f"简历 {rid} 无授权记录，拒绝导入（未经同意的数据禁止进入 Gold）")
            else:
                quarantined.append({"resume_id": rid, "reason": "consent_missing",
                                    "content_hash": content_hash})
                continue
        if consent["source_class"] != source_class:
            raise ResumeIntakeError(
                f"简历 {rid} 来源类别与授权记录不一致: {source_class} != {consent['source_class']}")
        consent_status = str(consent.get("consent_status", "")).lower()
        if not is_synthetic_source and require_consent and consent_status not in ("granted", "licensed"):
            quarantined.append({"resume_id": rid, "reason": f"consent_{consent_status}",
                                "content_hash": content_hash})
            continue

        language = detect_language(text["resume_text"])
        rec = {
            "resume_id": rid,
            "resume_source": f"import:{source_name}",
            "source_class": source_class,
            "consent_id": str(consent.get("consent_id", "")),
            "consent_status": consent_status,
            "resume_text": text["resume_text"],
            "target_position": norm_text(row.get("target_position", "")),
            "skills": _split_skills(row.get("skills", "")),
            "education_level": norm_text(row.get("education_level", "")),
            "graduation_cohort": norm_text(row.get("graduation_cohort", "")),
            "employment_type": norm_text(row.get("employment_type", "")),
            "years_experience": _to_float(row.get("years_experience")),
            "city": norm_text(row.get("city", "")),
            "salary_expectation": norm_text(row.get("salary_expectation", "")),
            "language": language,
            "is_synthetic": bool(is_synthetic_source),
            "resume_license": norm_text(consent.get("license", "")),
            "content_hash": content_hash,
            "dataset_version": "",
        }
        eligible, reason = gold_eligibility(rec)
        rec["usable_for_chinese_gold"] = bool(eligible and language in ("zh", "mixed"))
        rec["eligible_for_gold"] = bool(eligible)
        rec["quarantine_reason"] = reason
        if not rec["usable_for_chinese_gold"] and language not in ("zh", "mixed"):
            rec["quarantine_reason"] = "non_chinese_resume"
        if rec["eligible_for_gold"]:
            accepted.append(rec)
        else:
            quarantined.append({"resume_id": rid, "reason": rec["quarantine_reason"],
                                "content_hash": content_hash})

    report = {
        "source_class": source_class,
        "source_name": source_name,
        "items_read": len(items),
        "accepted": len(accepted),
        "quarantined": len(quarantined),
        "quarantine_reasons": _count_by([q["reason"] for q in quarantined]),
        "formats": fmt_counts,
        "pii_hits_masked": pii_hits,
        "synthetic_in_accepted": sum(1 for r in accepted if r["is_synthetic"]),
        "real_in_accepted": sum(1 for r in accepted if not r["is_synthetic"]),
        "require_consent": bool(require_consent),
    }
    return {"accepted": accepted, "quarantined": quarantined, "report": report}


def _count_by(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items()))
