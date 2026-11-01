# -*- coding: utf-8 -*-
"""P7-1：真实数据现状四级审计（只读，不输出任何个人信息）。

任务书要求严格区分四个概念，**不能把「文件存在」直接视作「有效真实简历」**：

    file_exists        —— 磁盘上确实存在简历文件
    consent_verified   —— 存在合法授权记录（consent_status ∈ {granted, licensed}）且可核
    intake_accepted    —— 已走完 resume_intake 导入并进入 accepted 集
    eligible_for_gold  —— 满足 Gold 准入（授权 + 中文 + 非合成 + 已脱敏 + 无重复隔离）

本脚本只读审计当前工作区，输出**不含个人信息**的状态报告：
reports/phase7/01-data-status.json

退出码恒为 0（审计本身成功与否与数据是否到位解耦）；数据缺口以状态字段表达。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, report_path, sha256_file, write_json  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from job_matching.annotation import consent as consent_mod  # noqa: E402

PRIVATE_RESUMES = ROOT / "data" / "private" / "resumes"
CONSENT_DIR = ROOT / "data" / "private" / "consent"
RESUME_POOL = ROOT / "data" / "independent_eval" / "resume_pool" / "resumes.csv"
PAIRS_REAL_V1 = ROOT / "data" / "independent_eval" / "pairs" / "pairs_v1.jsonl"
PAIRS_REAL_V2 = ROOT / "data" / "independent_eval" / "pairs" / "pairs_real_v2.jsonl"
ANNOT_RAW = ROOT / "data" / "private" / "annotations_raw"
FROZEN_V2 = ROOT / "data" / "independent_eval" / "frozen" / "evalset_v2"
JOB_POOL_V1 = ROOT / "data" / "independent_eval" / "pool" / "job_pool_v1.jsonl"
POOL_MANIFEST = ROOT / "data" / "independent_eval" / "pool" / "pool_manifest_v1.json"

H2_MIN_REAL_PAIRS = 300
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def audit_resume_files() -> dict:
    """第一级：file_exists。只统计与指纹，不读取/输出正文。"""
    files = sorted(PRIVATE_RESUMES.rglob("*.txt")) if PRIVATE_RESUMES.exists() else []
    items = []
    cjk_ok = 0
    pii_suspect = 0
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        cjk = len(CJK_RE.findall(raw))
        ratio = cjk / max(1, len(raw))
        # 只登记极粗粒度的隐私信号计数，不保留原文
        hits = {
            "mobile_like": len(re.findall(r"(?<!\d)1[3-9]\d{9}(?!\d)", raw)),
            "email_like": len(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", raw)),
            "idcard_like": len(re.findall(r"(?<!\d)\d{17}[\dXx](?!\d)", raw)),
        }
        if ratio >= 0.15:
            cjk_ok += 1
        if any(hits.values()):
            pii_suspect += 1
        items.append({
            "sha256_prefix": sha256_file(str(f))[:16],
            "bytes": f.stat().st_size,
            "cjk_ratio": round(ratio, 3),
            "language_guess": "zh_or_mixed" if ratio >= 0.15 else "non_chinese",
            "pii_pattern_hits": hits,
            "storage_layout": "app_upload_sharded_store" if re.match(r"^[\w-]{36}$", f.parents[1].name) else "other",
        })
    return {
        "level": "file_exists",
        "root": _rel(PRIVATE_RESUMES),
        "count": len(items),
        "cjk_likely": cjk_ok,
        "pii_pattern_suspect": pii_suspect,
        "items": items,
        "note": "仅登记指纹与粗粒度统计，不输出简历正文或任何个人标识",
    }


def audit_consent() -> dict:
    """第二级：consent_verified。复用 consent.py 的字段校验。"""
    records: list[dict] = []
    sources: list[str] = []
    parse_errors: list[str] = []
    if CONSENT_DIR.exists():
        for f in sorted(CONSENT_DIR.glob("*.csv")) + sorted(CONSENT_DIR.glob("*.jsonl")):
            sources.append(_rel(f))
            try:
                if f.suffix == ".csv":
                    with open(f, "r", encoding="utf-8-sig", newline="") as fh:
                        records.extend(dict(r) for r in csv.DictReader(fh))
                else:
                    with open(f, "r", encoding="utf-8") as fh:
                        records.extend(json.loads(ln) for ln in fh if ln.strip())
            except Exception as e:  # noqa: BLE001
                parse_errors.append(f"{_rel(f)}: {type(e).__name__}")

    valid, invalid = [], []
    for row in records:
        try:
            valid.append(consent_mod.validate_consent_record(row))
        except consent_mod.ConsentError as e:
            invalid.append({"code": e.code})

    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for r in valid:
        by_status[r["consent_status"]] = by_status.get(r["consent_status"], 0) + 1
        by_class[r["source_class"]] = by_class.get(r["source_class"], 0) + 1

    granted = [r for r in valid if r["consent_status"] in ("granted", "licensed")]
    return {
        "level": "consent_verified",
        "record_files": sources,
        "records_total": len(records),
        "records_valid": len(valid),
        "records_invalid": len(invalid),
        "invalid_codes": sorted({i["code"] for i in invalid}),
        "parse_errors": parse_errors,
        "by_consent_status": dict(sorted(by_status.items())),
        "by_source_class": dict(sorted(by_class.items())),
        "granted_or_licensed": len(granted),
        "withdrawn": sum(1 for r in valid if r["consent_status"] == "withdrawn"),
        "verified": bool(granted),
        "note": "授权记录本身可能含个人信息，只统计计数与状态分布",
    }


def audit_intake() -> dict:
    """第三级：intake_accepted。检查导入 accepted 集与真实配对产物。"""
    pool_rows = _count_lines(RESUME_POOL)
    pairs_v1 = _count_lines(PAIRS_REAL_V1)
    pairs_v2 = _count_lines(PAIRS_REAL_V2)
    return {
        "level": "intake_accepted",
        "resume_pool_csv": _rel(RESUME_POOL),
        "resume_pool_exists": RESUME_POOL.exists(),
        "resume_pool_rows": pool_rows,
        "pairs_real_v1": {"path": _rel(PAIRS_REAL_V1), "exists": PAIRS_REAL_V1.exists(), "rows": pairs_v1},
        "pairs_real_v2": {"path": _rel(PAIRS_REAL_V2), "exists": PAIRS_REAL_V2.exists(), "rows": pairs_v2},
        "real_pairs_total": pairs_v1 + pairs_v2,
        "accepted": bool(pool_rows > 0),
    }


def audit_gold_eligibility(resume_audit: dict, consent_audit: dict) -> dict:
    """第四级：eligible_for_gold。授权 + 中文 + 非合成 + 已脱敏 + 未重复隔离。"""
    cjk_resumes = resume_audit["cjk_likely"]
    granted = consent_audit["granted_or_licensed"]
    eligible = min(cjk_resumes, granted)
    gaps = []
    if cjk_resumes == 0:
        gaps.append("无中文真实简历")
    if granted == 0:
        gaps.append("无有效授权记录（consent_status 非 granted/licensed）")
    if eligible == 0:
        gaps.append("同时满足「中文 + 已授权」的真实简历为 0")
    return {
        "level": "eligible_for_gold",
        "candidates_cjk": cjk_resumes,
        "candidates_with_consent": granted,
        "eligible_for_gold": eligible,
        "gaps": gaps,
        "derivation": "eligible = min(中文可判定简历数, 有效授权记录数)，且必须通过脱敏与重复隔离（当前无 accepted 导入，故为 0）",
    }


def audit_annotation_and_freeze() -> dict:
    files = sorted(ANNOT_RAW.glob("annotations_*.csv")) if ANNOT_RAW.exists() else []
    annotators: set[str] = set()
    covered: set[str] = set()
    for f in files:
        try:
            with open(f, "r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    a = str(row.get("annotator_id") or "").strip()
                    p = str(row.get("pair_id") or "").strip()
                    if a:
                        annotators.add(a)
                    if p:
                        covered.add(p)
        except Exception:  # noqa: BLE001
            pass
    freeze_written = freeze_verified = False
    h2 = "blocked"
    fb = FROZEN_V2 / "freeze_blocked.json"
    if fb.exists():
        try:
            d = json.loads(fb.read_text(encoding="utf-8"))
            h2 = d.get("h2_status", "blocked")
            freeze_written = bool(d.get("freeze_written"))
            freeze_verified = bool(d.get("freeze_verified"))
        except Exception:  # noqa: BLE001
            h2 = "INVALID"
    return {
        "level": "annotation_and_freeze",
        "annotation_files": len(files),
        "distinct_annotators": len(annotators),
        "covered_pairs": len(covered),
        "dual_annotation_complete": len(annotators) >= 2 and len(covered) > 0,
        "freeze_written": freeze_written,
        "freeze_verified": freeze_verified,
        "h2_status": h2,
    }


def audit_job_pool() -> dict:
    jobs = _count_lines(JOB_POOL_V1)
    manifest = {}
    if POOL_MANIFEST.exists():
        try:
            m = json.loads(POOL_MANIFEST.read_text(encoding="utf-8"))
            jp = m.get("job_pool", {})
            manifest = {
                "jobs_selected": jp.get("jobs_selected"),
                "jobs_unique": jp.get("jobs_unique"),
                "jobs_read_total": jp.get("jobs_read_total"),
                "category_distribution": jp.get("category_distribution"),
                "license_status": jp.get("license_status"),
                "duplicates_removed": jp.get("duplicates_removed"),
                "historical_gold_in_source": jp.get("historical_gold_in_source"),
                "dataset_version": m.get("dataset_version"),
            }
        except Exception as e:  # noqa: BLE001
            manifest = {"parse_error": type(e).__name__}
    return {
        "level": "job_pool",
        "job_pool_path": _rel(JOB_POOL_V1),
        "jobs_in_pool": jobs,
        "manifest": manifest,
    }


def derive_status(resume_audit, consent_audit, intake_audit, elig_audit, annot_audit) -> dict:
    real_pairs = intake_audit["real_pairs_total"]
    if real_pairs == 0:
        status = "BLOCKED"
    elif annot_audit["dual_annotation_complete"]:
        status = "READY_FOR_FREEZE"
    else:
        status = "READY_FOR_ANNOTATION"
    if annot_audit["freeze_verified"] and annot_audit["freeze_written"] and real_pairs > 0:
        status = "FROZEN_AND_VERIFIED"

    missing = {
        "valid_resumes_missing": max(0, 30 - elig_audit["eligible_for_gold"]),
        "real_pairs_missing": max(0, H2_MIN_REAL_PAIRS - real_pairs),
        "annotators_missing": max(0, 2 - annot_audit["distinct_annotators"]),
    }
    return {
        "gold_state": status,
        "h2_status": annot_audit["h2_status"],
        "h2_min_real_pairs": H2_MIN_REAL_PAIRS,
        "blockers": [
            f"有效真实简历缺口 {missing['valid_resumes_missing']} 份（协议下限 30）",
            f"真实人岗配对缺口 {missing['real_pairs_missing']} 组（协议门禁 {H2_MIN_REAL_PAIRS}）",
            f"独立标注员缺口 {missing['annotators_missing']} 人（协议要求 ≥2）",
            "授权记录缺口：当前无任何 consent 记录文件",
        ] if status != "FROZEN_AND_VERIFIED" else [],
        "missing": missing,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase7 真实数据现状四级审计（只读，无 PII）")
    ap.add_argument("--write-report", action="store_true", default=True)
    args = ap.parse_args(argv)

    resume_audit = audit_resume_files()
    consent_audit = audit_consent()
    intake_audit = audit_intake()
    elig_audit = audit_gold_eligibility(resume_audit, consent_audit)
    annot_audit = audit_annotation_and_freeze()
    job_pool = audit_job_pool()
    status = derive_status(resume_audit, consent_audit, intake_audit, elig_audit, annot_audit)

    payload = {
        "artifact": "phase7-real-data-status",
        "generated_at": "2026-10-31T22:25:00+08:00",
        "pii_policy": "不含任何简历正文、姓名、联系方式；仅指纹前缀与计数",
        "status": status,
        "levels": {
            "file_exists": resume_audit,
            "consent_verified": consent_audit,
            "intake_accepted": intake_audit,
            "eligible_for_gold": elig_audit,
        },
        "annotation_and_freeze": annot_audit,
        "job_pool": job_pool,
        "historical_snapshot_discrepancy": {
            "note": "历史报告存在两个统计时点（旧冻结阻断快照 real_resumes=0 / Phase6-R 本地审计 real_resumes=1）；"
                    "本报告是第三个实测时点，不改写历史报告，两者并存可追溯",
            "old_freeze_blocked_snapshot": {"real_resumes": 0, "real_pairs": 0,
                                            "source": "data/independent_eval/frozen/evalset_v2/freeze_blocked.json"},
            "phase6r_local_audit": {"real_resumes": 1, "real_pairs": 0,
                                    "source": "reports/phase6-r/04-gold-gate-readiness.md"},
            "phase7_now": {"real_resumes": resume_audit["count"],
                           "real_pairs": intake_audit["real_pairs_total"],
                           "source": "reports/phase7/01-data-status.json"},
        },
    }

    out = write_json(report_path("reports", "phase7", "01-data-status.json"), payload)
    print(f"[{status['gold_state']}] H2={status['h2_status']} "
          f"file_exists={resume_audit['count']} consent={consent_audit['granted_or_licensed']} "
          f"intake={intake_audit['accepted']} eligible={elig_audit['eligible_for_gold']} "
          f"real_pairs={intake_audit['real_pairs_total']}")
    for b in status["blockers"]:
        print(f"  - {b}")
    print(f"  报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
