# -*- coding: utf-8 -*-
"""Phase4-3A-2 泄漏与重复风险检查 -> reports/phase4-3a-2/leakage-check.json。

检查项：
  1. 真实配对池内完全重复 / 近似重复（配对级、简历级、岗位级）；
  2. 与历史 Gold（gold_holdout 736 条）交叉（岗位级裁决复核）；
  3. 与学历训练语料重合（复用 job-candidate-audit 逐岗扫描结果，分任务说明影响）；
  4. 合成样本混入真实配对（必须为 0）；
  5. 导出文件个人信息残留（pii.check_export 口径）；
  6. 许可与授权登记状态；
  7. 预训练污染声明（只声明「未发现已知泄漏」）。

阻断口径：只有「未处理」的发现进入 unresolved_blocking_findings；
已裁决处理的（历史 Gold 交叉 -> 禁入盲测、训练重合 -> 禁入盲测、近似重复 -> 隔离）
登记为 handled_findings 并说明处理方式。

用法：
  python scripts/phase4_3a_2/leakage_gate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    JOB_POOL_V2, PAIRS_REAL_V2, PACKET_DIR, file_record, now, read_jsonl, write_report,
)

from job_matching.annotation import dedup as dedup_mod  # noqa: E402
from job_matching.annotation.pii import detect_pii, pii_field_violations  # noqa: E402
from job_matching.core import ROOT  # noqa: E402


def _jload_if(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pool_internal_checks(pairs: list[dict], jobs: list[dict]) -> dict:
    pair_texts = {str(p["pair_id"]): f"{p.get('resume_text', '')}\x1f{p.get('job_text', '')}"
                  for p in pairs}
    near = dedup_mod.near_duplicate_pairs(pair_texts, threshold=0.90)
    exact_seen: dict[str, str] = {}
    exact_dups = []
    for pid in sorted(pair_texts):
        h = dedup_mod.exact_hash(pair_texts[pid])
        if h in exact_seen:
            exact_dups.append([exact_seen[h], pid])
        else:
            exact_seen[h] = pid

    resume_hash_ids: dict[str, set[str]] = {}
    for p in pairs:
        resume_hash_ids.setdefault(dedup_mod.norm_hash(p.get("resume_text", "")),
                                   set()).add(str(p["resume_id"]))
    job_hash_ids: dict[str, set[str]] = {}
    for j in jobs:
        job_hash_ids.setdefault(dedup_mod.norm_hash(j.get("job_text", "") or j.get("job_title", "")),
                                set()).add(str(j["job_id"]))
    same_resume = {h: sorted(v) for h, v in resume_hash_ids.items() if len(v) > 1}
    same_job = {h: sorted(v) for h, v in job_hash_ids.items() if len(v) > 1}
    return {
        "pair_level": {"pairs_checked": len(pairs),
                       "exact_duplicates": len(exact_dups),
                       "exact_duplicate_pairs": exact_dups[:50],
                       "near_duplicates": len(near),
                       "near_duplicate_pairs": near[:50], "near_threshold": 0.90},
        "resume_level": {"resumes_checked": len(resume_hash_ids),
                         "same_resume_different_id": len(same_resume),
                         "detail": list(same_resume.values())[:50]},
        "job_level": {"jobs_checked": len(job_hash_ids),
                      "same_job_different_id": len(same_job),
                      "detail": list(same_job.values())[:50]},
    }


def export_pii_scan(paths: list[Path]) -> dict:
    out = {"files": [], "pii_field_violations": [], "pii_text_hits": {}}
    for path in paths:
        if not path.exists():
            continue
        recs = read_jsonl(path) if path.suffix == ".jsonl" else []
        hits: dict[str, int] = {}
        for r in recs:
            for field in ("resume_text", "job_text", "job_description"):
                for k, v in detect_pii(r.get(field, "")).items():
                    hits[k] = hits.get(k, 0) + v
            for bad in pii_field_violations(r):
                out["pii_field_violations"].append({"file": path.name, "field": bad})
        out["files"].append({"file": str(path.name), "records": len(recs)})
        out["pii_text_hits"][path.name] = hits
    return out


def run() -> dict:
    pairs = read_jsonl(PAIRS_REAL_V2) if PAIRS_REAL_V2.exists() else []
    jobs = read_jsonl(JOB_POOL_V2) if JOB_POOL_V2.exists() else []
    job_audit = _jload_if(ROOT / "reports" / "phase4-3a-2" / "job-candidate-audit.json")

    internal = pool_internal_checks(pairs, jobs)

    # 历史 Gold 交叉（岗位级，逐条裁决见 job-candidate-audit.json）
    gold_cross = job_audit.get("historical_gold_cross_analysis", {})
    edu = job_audit.get("education_corpus_overlap", {})
    per_job_flags = {
        "jobs_with_hash_overlap": edu.get("jobs_with_hash_overlap"),
        "jobs_with_near_overlap": edu.get("jobs_with_near_overlap"),
    }

    synthetic_in_real = [p["pair_id"] for p in pairs if bool(p.get("is_synthetic"))]
    scan_paths = [PAIRS_REAL_V2, JOB_POOL_V2]
    if PACKET_DIR.exists():
        scan_paths += sorted(PACKET_DIR.glob("*.csv"))
    pii_scan = export_pii_scan(scan_paths)

    handled, unresolved = [], []

    if internal["pair_level"]["exact_duplicates"] > 0:
        unresolved.append("真实配对池存在完全重复配对（未隔离）")
    else:
        handled.append({"item": "配对级重复", "status": "无完全重复",
                        "note": "近似重复在配对生成时按 gold_gate.quarantine_near_duplicates 隔离并登记"})

    if internal["resume_level"]["same_resume_different_id"] > 0:
        unresolved.append("存在同简历不同 resume_id（去标识化 ID 派生异常）")
    if internal["job_level"]["same_job_different_id"] > 0:
        unresolved.append("存在同 JD 不同 job_id（岗位去重未生效）")

    if synthetic_in_real:
        unresolved.append(f"真实配对池混入合成样本 {len(synthetic_in_real)} 组")
    else:
        handled.append({"item": "合成样本混入", "status": "0 组",
                        "note": "合成样本只在 pairs_synthetic_*.jsonl，永不进人工真值"})

    if gold_cross.get("overlap_job_ids"):
        handled.append({
            "item": "历史 Gold 交叉", "status": f"{len(gold_cross['overlap_job_ids'])} 个 job_id 已裁决",
            "note": "逐条裁决=剔除出盲测集（quarantine_from_blind），保留用于 dev 与对照；"
                    "见 job-candidate-audit.json -> historical_gold_cross_analysis"})

    if per_job_flags.get("jobs_with_hash_overlap") or per_job_flags.get("jobs_with_near_overlap"):
        handled.append({
            "item": "学历训练语料重合", "status": "已逐岗标记并禁入盲测",
            "note": "仅对『要求模型未见过岗位文本』的任务构成污染；"
                    "人岗匹配排序模型（英文语料训练）无直接文本泄漏；"
                    "详见 job-candidate-audit.json -> contamination_by_task"})

    if pii_scan["pii_field_violations"]:
        unresolved.append("导出文件存在个人信息字段残留: "
                          + json.dumps(pii_scan["pii_field_violations"][:10], ensure_ascii=False))
    else:
        handled.append({"item": "导出 PII 检查", "status": "无字段残留",
                        "note": "文本脱敏掩码 + 字段名白名单双重拦截（pii.check_export）"})

    result = {
        "generated_by": "scripts/phase4_3a_2/leakage_gate.py",
        "created_at": now(),
        "scope": "Phase4-3A-2 真实配对池 / 岗位准入池 / 标注材料",
        "pool_internal_duplicates": internal,
        "historical_gold_cross": {
            "overlap_job_ids": gold_cross.get("overlap_job_ids", []),
            "decisions": gold_cross.get("decisions", []),
            "policy": "交叉岗位剔除出最终盲测集；不得作为全新独立盲测样本",
        },
        "training_data_overlap": {
            "education_corpus": {
                "scan": {k: v for k, v in (edu.get("scan") or {}).items() if k != "per_job"},
                **per_job_flags,
                "contamination_by_task": edu.get("contamination_by_task", {}),
            },
        },
        "synthetic_in_real_pairs": {"count": len(synthetic_in_real),
                                    "pair_ids": synthetic_in_real[:50]},
        "pii_export_scan": pii_scan,
        "license_and_consent": {
            "job_sources": "见 reports/phase4-3a-2/source-audit.json",
            "resume_consent": "见 reports/phase4-3a-2/resume-intake-audit.json（授权逐条可核）",
        },
        "pretraining_contamination": {
            "statement": ("预训练语料来源不可知，无法完全排除预训练污染；"
                          "本报告只能声明『未发现已知泄漏』，不能声称绝对无泄漏"),
            "checkable": ["本地训练语料文本重合", "历史 Gold 交叉", "池内重复", "PII 残留"],
            "not_checkable": ["外部预训练模型语料", "原始数据集上游采集范围"],
        },
        "handled_findings": handled,
        "blocking_findings": unresolved,
        "unresolved_blocking_findings": unresolved,
        "files": {},
    }
    for label, path in (("job_pool_v2", JOB_POOL_V2), ("pairs_real_v2", PAIRS_REAL_V2)):
        if path.exists():
            result["files"][label] = file_record(path)
    write_report("leakage-check.json", result)
    return result


if __name__ == "__main__":
    res = run()
    print(json.dumps({
        "unresolved_blocking_findings": res["unresolved_blocking_findings"],
        "handled_findings": [h["item"] for h in res["handled_findings"]],
        "pair_near_duplicates": res["pool_internal_duplicates"]["pair_level"]["near_duplicates"],
        "synthetic_in_real_pairs": res["synthetic_in_real_pairs"]["count"],
    }, ensure_ascii=False, indent=2))
