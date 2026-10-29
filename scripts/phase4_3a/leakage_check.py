# -*- coding: utf-8 -*-
"""评估集泄漏与重复检查（任务书 5.3）-> reports/phase4-3a/leakage-check.json。

检查项：
  1. 候选池内完全重复 / 规范化文本重复 / 近似重复（配对级、简历级、岗位级）；
  2. 同一简历不同 ID、同一岗位不同 ID；
  3. 与原历史 Gold（data/splits/education/gold_holdout.csv，736 条）交叉；
  4. 与训练数据的文本重合（学历训练语料 default/train+validation、
     人岗匹配英文语料 cv/job/matches）；
  5. 数据来源不明（license UNKNOWN / unverified）；
  6. 导出文件的个人信息残留；
  7. 预训练污染声明（只能声明"无法完全排除"）。

近似重复跨语料检查使用确定性等距抽样阻塞（默认 8 万行），限制如实登记。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

import pandas as pd  # noqa: E402

from common import (  # noqa: E402
    ANNOT_DIR, PAIRS_DIR, POOL_DIR, file_record, now, read_jsonl, write_report,
)
from job_matching.annotation import dedup as dedup_mod  # noqa: E402
from job_matching.annotation.pii import detect_pii, pii_field_violations  # noqa: E402
from job_matching.annotation.pool import JOB_SOURCES, RESUME_SOURCES  # noqa: E402
from job_matching.core import ROOT  # noqa: E402
from job_matching.preprocess_education import parse_user_segments  # noqa: E402

DESC_RX_SAMPLE_ROWS = 200000


def load_pool() -> tuple[list[dict], list[dict], list[dict]]:
    jobs = read_jsonl(POOL_DIR / "job_pool_v1.jsonl") if (POOL_DIR / "job_pool_v1.jsonl").exists() else []
    real = read_jsonl(PAIRS_DIR / "pairs_v1.jsonl") if (PAIRS_DIR / "pairs_v1.jsonl").exists() else []
    syn = read_jsonl(PAIRS_DIR / "pairs_synthetic_v1.jsonl") if (PAIRS_DIR / "pairs_synthetic_v1.jsonl").exists() else []
    return jobs, real, syn


def check_pool_internal(jobs: list[dict], pairs: list[dict]) -> dict:
    """候选池内重复：配对级 + 简历级 + 岗位级。"""
    pair_texts = {p["pair_id"]: f"{p.get('resume_text','')}\x1f{p.get('job_text','')}" for p in pairs}
    near_pairs = dedup_mod.near_duplicate_pairs(pair_texts, threshold=0.90)

    resume_by_id: dict[str, set[str]] = {}
    job_by_id: dict[str, set[str]] = {}
    for p in pairs:
        resume_by_id.setdefault(p["resume_id"], set()).add(dedup_mod.norm_hash(p.get("resume_text", "")))
        job_by_id.setdefault(p["job_id"], set()).add(dedup_mod.norm_hash(p.get("job_text", "")))
    for j in jobs:
        job_by_id.setdefault(j["job_id"], set()).add(dedup_mod.norm_hash(j.get("job_text", "") or j.get("job_title", "")))

    # 同文本不同 ID
    resume_hash_to_ids: dict[str, set[str]] = {}
    for p in pairs:
        resume_hash_to_ids.setdefault(dedup_mod.norm_hash(p.get("resume_text", "")), set()).add(p["resume_id"])
    job_hash_to_ids: dict[str, set[str]] = {}
    for j in jobs:
        job_hash_to_ids.setdefault(dedup_mod.norm_hash(j.get("job_text", "") or j.get("job_title", "")), set()).add(j["job_id"])

    same_resume_diff_id = {h: sorted(ids) for h, ids in resume_hash_to_ids.items() if len(ids) > 1}
    same_job_diff_id = {h: sorted(ids) for h, ids in job_hash_to_ids.items() if len(ids) > 1}

    pair_hash_seen: dict[str, str] = {}
    exact_dups = []
    for pid in sorted(pair_texts):
        h = dedup_mod.exact_hash(pair_texts[pid])
        if h in pair_hash_seen:
            exact_dups.append([pair_hash_seen[h], pid])
        else:
            pair_hash_seen[h] = pid

    return {
        "pair_level": {
            "pairs_checked": len(pairs),
            "exact_duplicates": len(exact_dups),
            "exact_duplicate_pairs": exact_dups[:50],
            "near_duplicates": len(near_pairs),
            "near_duplicate_pairs": near_pairs[:50],
            "near_threshold": 0.90,
        },
        "resume_level": {
            "resumes_checked": len(resume_by_id),
            "same_resume_different_id": len(same_resume_diff_id),
            "detail": list(same_resume_diff_id.values())[:50],
        },
        "job_level": {
            "jobs_checked": len(job_by_id),
            "same_job_different_id": len(same_job_diff_id),
            "detail": list(same_job_diff_id.values())[:50],
        },
    }


def check_historical_gold(jobs: list[dict]) -> dict:
    """与原历史 Gold（736 条，参与过规则研究）交叉。"""
    path = ROOT / "data" / "splits" / "education" / "gold_holdout.csv"
    if not path.exists():
        return {"status": "not_available", "note": "gold_holdout.csv 不存在"}
    gold = pd.read_csv(path, dtype=str).fillna("")
    gold_job_ids = set(gold["job_id"].astype(str).str.strip())
    pool_job_ids = {str(j["job_id"]).strip() for j in jobs}
    inter = sorted(gold_job_ids & pool_job_ids)
    return {
        "status": "checked",
        "gold_records": len(gold),
        "gold_unique_job_ids": len(gold_job_ids),
        "pool_jobs": len(pool_job_ids),
        "overlap_job_ids": len(inter),
        "overlap_job_id_sample": inter[:50],
        "policy": ("历史 Gold 曾参与 Phase4-2 规则研究与基线分析，"
                   "与之交叉的样本必须登记；不得作为全新独立盲测样本"),
    }


def _stream_desc(path: Path, limit: int | None = None):
    """流式产出 (row_key, 岗位描述)；limit>0 时做确定性等距抽样。"""
    total = 0
    kept = 0
    stride = 1
    if limit:
        n_rows = sum(1 for _ in open(path, "r", encoding="utf-8", errors="ignore")) - 1
        stride = max(1, int(n_rows // max(1, limit)))
    for chunk in pd.read_csv(path, usecols=["user"], dtype=str, encoding="utf-8",
                             low_memory=False, chunksize=20000):
        for i, v in enumerate(chunk["user"].fillna("")):
            total += 1
            if limit and (total % stride):
                continue
            desc = parse_user_segments(str(v)).get("job_description_norm", "")
            if not desc:
                continue
            kept += 1
            yield (f"{path.name}:{total}", desc)
    return


def check_training_overlap(jobs: list[dict], near_limit: int = 80000) -> dict:
    """与训练数据的文本重合（学历训练语料 / 英文人岗语料）。"""
    pool_desc = {str(j["job_id"]): str(j.get("job_description") or j.get("job_title") or "")
                 for j in jobs}
    pool_desc = {k: v for k, v in pool_desc.items() if v.strip()}
    pool_hashes = {dedup_mod.norm_hash(v) for v in pool_desc.values()}

    edu_files = [
        ROOT / "data/raw/job-education/default/train/19w_0701.csv",
        ROOT / "data/raw/job-education/default/validation/4w_0708.csv",
    ]
    edu = {"files": [], "rows_scanned": 0, "exact_or_norm_hash_overlap": 0,
           "near_duplicate_overlap": 0, "near_duplicate_sample": []}
    for f in edu_files:
        if not f.exists():
            continue
        overlap_hashes = 0
        rows = 0
        for _key, desc in _stream_desc(f):
            rows += 1
            if dedup_mod.norm_hash(desc) in pool_hashes:
                overlap_hashes += 1
        edu["files"].append(str(f.relative_to(ROOT)).replace("\\", "/"))
        edu["rows_scanned"] += rows
        edu["exact_or_norm_hash_overlap"] += overlap_hashes

    # 近似重复（target 驱动阻塞，确定性等距抽样）
    near = []
    for f in edu_files:
        if not f.exists():
            continue
        ref = _stream_desc(f, limit=near_limit)
        near.extend(dedup_mod.cross_near_duplicate_pairs(pool_desc, ref, threshold=0.90))
    edu["near_duplicate_overlap"] = len(near)
    edu["near_duplicate_sample"] = near[:50]
    edu["near_check_reference_limit"] = near_limit
    edu["near_check_limitation"] = (
        "近似重复跨语料检查在确定性等距抽样子集上执行（默认 8 万行），"
        "可能漏检抽样外的近似重复；完全/规范化哈希检查覆盖全量语料")

    # 英文人岗语料（语言不同，预期零重合）
    en = {"files": [], "rows_scanned": 0, "exact_or_norm_hash_overlap": 0}
    base = ROOT / "data" / "raw" / "job-resume-matching"
    for name, col in (("cv.csv", "resume_text"), ("job.csv", "job_description")):
        p = base / name
        if not p.exists():
            continue
        df = pd.read_csv(p, usecols=[col], dtype=str, encoding="utf-8", low_memory=False).fillna("")
        en["files"].append(f"data/raw/job-resume-matching/{name}")
        en["rows_scanned"] += len(df)
        en["exact_or_norm_hash_overlap"] += sum(
            1 for v in df[col] if dedup_mod.norm_hash(v) in pool_hashes)
    en["note"] = ("英文语料与中文评估池语言不同，按规范化哈希比对；"
                  "英文简历/岗位禁止充当中国大学生就业画像数据")

    splits_note = {
        "data/splits/matching/*": ("切分索引只含 pair_index/candidate_id/job_id，"
                                   "指向英文 matches.csv；与中文评估池无文本重合可能"),
        "data/splits/education/*": "学历切分清单按 record_key/user_hash 组织，交叉检查见 historical_gold 与 edu 语料检查",
    }
    return {"education_training_corpus": edu, "english_matching_corpus": en,
            "split_indices": splits_note}


def check_license_and_provenance(jobs: list[dict]) -> dict:
    by_source: dict[str, int] = {}
    for j in jobs:
        by_source[str(j.get("job_source", ""))] = by_source.get(str(j.get("job_source", "")), 0) + 1
    unknown = sum(n for s, n in by_source.items() if JOB_SOURCES.get(s, {}).get("license") in (None, "UNKNOWN", "unverified"))
    return {
        "pool_jobs_by_source": by_source,
        "jobs_with_unknown_license": unknown,
        "resume_sources": {k: {"license": v["license"], "usable_for_chinese_eval":
                               v["usable_for_chinese_eval"]} for k, v in RESUME_SOURCES.items()},
        "all_df_license": "UNKNOWN（本地无证据，补齐前不得进入正式评估集）",
        "job_resume_matching_license": "unverified（front-matter mit 与正文 License 节不一致）",
        "job_education_license": "apache-2.0（README front-matter 可核）",
    }


def check_pii_exports() -> dict:
    out = {"files": [], "pii_field_violations": [], "pii_text_hits": {}}
    for path in sorted(PAIRS_DIR.glob("*.jsonl")) + sorted(POOL_DIR.glob("*.jsonl")):
        recs = read_jsonl(path)
        hits: dict[str, int] = {}
        for r in recs:
            for field in ("resume_text", "job_text", "job_description", "resume_source"):
                for k, v in detect_pii(r.get(field, "")).items():
                    hits[k] = hits.get(k, 0) + v
            for bad in pii_field_violations(r):
                out["pii_field_violations"].append({"file": str(path.name), "field": bad})
        out["files"].append({"file": str(path.relative_to(ROOT)).replace("\\", "/"),
                             "records": len(recs), "pii_text_hits": hits})
        out["pii_text_hits"][str(path.name)] = hits
    return out


def run(near_limit: int = 80000) -> dict:
    jobs, real, syn = load_pool()
    pairs = real + syn
    result = {
        "generated_by": "scripts/phase4_3a/leakage_check.py",
        "created_at": now(),
        "pool_internal_duplicates": check_pool_internal(jobs, pairs),
        "historical_gold_cross": check_historical_gold(jobs),
        "training_data_overlap": check_training_overlap(jobs, near_limit=near_limit),
        "license_and_provenance": check_license_and_provenance(jobs),
        "pii_export_scan": check_pii_exports(),
        "pretraining_contamination": {
            "statement": ("预训练语料来源不可知，无法完全排除预训练污染；"
                          "本报告只能声明『未发现已知泄漏』，不能声称绝对无泄漏"),
            "checkable": ["本地训练语料文本重合", "历史 Gold 交叉", "池内重复"],
            "not_checkable": ["外部预训练模型语料", "原始数据集上游采集范围"],
        },
        "blocking_findings": [],
        "files": {},
    }
    blocking = []
    if result["pool_internal_duplicates"]["pair_level"]["exact_duplicates"] > 0:
        blocking.append("候选池存在完全重复配对")
    if result["historical_gold_cross"].get("overlap_job_ids", 0) > 0:
        blocking.append("候选池与原历史 Gold 存在 job_id 交叉（需在评估时登记并降级解释）")
    if result["pii_export_scan"]["pii_field_violations"]:
        blocking.append("导出文件存在个人信息字段残留")
    result["blocking_findings"] = blocking

    for label, path in (("job_pool", POOL_DIR / "job_pool_v1.jsonl"),
                        ("pairs_real", PAIRS_DIR / "pairs_v1.jsonl"),
                        ("pairs_synthetic", PAIRS_DIR / "pairs_synthetic_v1.jsonl")):
        if path.exists():
            result["files"][label] = file_record(path)
    write_report("leakage-check.json", result)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--near-limit", type=int, default=80000)
    args = ap.parse_args()
    res = run(near_limit=args.near_limit)
    print(json.dumps({"blocking_findings": res["blocking_findings"],
                      "gold_overlap": res["historical_gold_cross"].get("overlap_job_ids"),
                      "edu_hash_overlap":
                          res["training_data_overlap"]["education_training_corpus"]["exact_or_norm_hash_overlap"],
                      "edu_near_overlap":
                          res["training_data_overlap"]["education_training_corpus"]["near_duplicate_overlap"]},
                     ensure_ascii=False, indent=2))
