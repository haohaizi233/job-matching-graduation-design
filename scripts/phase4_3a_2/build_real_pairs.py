# -*- coding: utf-8 -*-
"""真实中文简历-岗位配对生成（Phase4-3A-2 模块 C）。

目标：300–600 个真实中文人岗配对（每份简历 10–12 条），供人工判断的相关性候选配对。
纪律：
  * 生成的是**待人工判断的候选配对**，绝不按抽样类别自动赋予真实相关性标签；
  * 固定随机种子、按岗位类别分层、按简历分组、不重复配对、稳定 pair_id（内容哈希派生）；
  * 数据来源追踪 + 内容哈希 + 与旧训练集交叉检查 + 中文文本与字段完整性检查；
  * 不通过重复相同简历/岗位机械凑数（近似重复配对隔离并登记原因）。

用法：
  python scripts/phase4_3a_2/build_real_pairs.py [--seed 20261212] [--per-resume 12]

产物：
  data/independent_eval/pairs/pairs_real_v2.jsonl
  reports/phase4-3a-2/real-pair-manifest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    JOB_POOL_V2, PAIRS_REAL_V2, PRIVATE_ACCEPTED_DIR, file_record, now,
    read_jsonl, write_jsonl, write_report,
)

from job_matching.annotation import gold_gate  # noqa: E402
from job_matching.annotation import pool as pool_mod  # noqa: E402
from job_matching.annotation.pool import detect_language  # noqa: E402
from job_matching.annotation.schema import PAIR_FIELDS  # noqa: E402

# 抽样多样性（任务书模块 C）与难度层映射
DIVERSITY_MAPPING = {
    "专业方向明显相关": ["high_skill_overlap", "medium_skill_overlap"],
    "技能高度相似": ["high_skill_overlap"],
    "技能部分相似": ["medium_skill_overlap"],
    "技术方向相近但岗位职责不同": ["same_direction_diff_duties"],
    "存在重要资格差异": ["hard_requirement_gap"],
    "明显不相关": ["cross_category_negative"],
}

TARGET_PAIR_RANGE = (300, 600)
TARGET_PER_RESUME = (10, 12)


def load_real_resumes() -> tuple[list[dict], dict]:
    """读取 intake 导出的脱敏真实简历（data/private/accepted/）。"""
    files = sorted(PRIVATE_ACCEPTED_DIR.glob("resumes_accepted_*.jsonl")) \
        if PRIVATE_ACCEPTED_DIR.exists() else []
    resumes: list[dict] = []
    for f in files:
        resumes.extend(read_jsonl(f))
    real = [r for r in resumes if not bool(r.get("is_synthetic"))]
    return real, {
        "files": [str(f.name) for f in files],
        "records_total": len(resumes),
        "records_real": len(real),
        "records_synthetic_excluded": len(resumes) - len(real),
    }


def adapt_job(j: dict) -> dict:
    """job_pool_v2 记录 -> pool.build_pairs 期望的岗位形状。"""
    return {
        "job_id": j["job_id"],
        "job_source": j.get("source", j.get("job_source", "")),
        "job_title": j.get("job_title", ""),
        "job_description": j.get("job_description", ""),
        "job_text": j.get("job_text") or j.get("job_description", ""),
        "job_category": j.get("job_category", ""),
        "job_category_source": j.get("job_category_source", ""),
        "language": j.get("language", "zh"),
        "required_skills": j.get("required_skills", []),
        "preferred_skills": j.get("preferred_skills", []),
        "education_requirement": j.get("education_requirement", {}),
        "experience_requirement": j.get("experience_requirement", {}),
        "city": j.get("city", ""),
        "historical_gold": j.get("historical_gold", False),
    }


def check_text_and_fields(pairs: list[dict]) -> dict:
    """中文文本与字段完整性检查。"""
    problems = []
    for p in pairs:
        pid = p.get("pair_id", "")
        for f in ("resume_text", "job_text"):
            if not str(p.get(f, "")).strip():
                problems.append({"pair_id": pid, "code": "empty_text", "field": f})
        lang = detect_language(p.get("resume_text", ""))
        if lang not in ("zh", "mixed"):
            problems.append({"pair_id": pid, "code": "non_chinese_resume_text", "language": lang})
        if detect_language(p.get("job_text", "")) != "zh":
            problems.append({"pair_id": pid, "code": "non_chinese_job_text",
                             "language": detect_language(p.get("job_text", ""))})
        missing = [f for f in PAIR_FIELDS if f not in p]
        if missing:
            problems.append({"pair_id": pid, "code": "missing_pair_fields", "fields": missing})
        if str(p.get("label_status", "unlabeled")) != "unlabeled":
            problems.append({"pair_id": pid, "code": "auto_label_suspected"})
    return {
        "pairs_checked": len(pairs),
        "problems": problems[:200],
        "problem_count": len(problems),
        "ok": not problems,
        "language_policy": "resume_text 允许 zh/mixed，job_text 必须 zh",
    }


def run(seed: int = 20261212, per_resume: int = 12) -> dict:
    real_resumes, resume_info = load_real_resumes()
    manifest: dict = {
        "generated_by": "scripts/phase4_3a_2/build_real_pairs.py",
        "created_at": now(),
        "resume_intake": resume_info,
        "seed": int(seed),
        "pairs_per_resume": int(per_resume),
        "target_pair_range": list(TARGET_PAIR_RANGE),
        "target_per_resume": list(TARGET_PER_RESUME),
        "label_policy": ("候选配对不带任何相关性标签（label_status=unlabeled）；"
                         "抽样难度层只是分层元数据，不是真值，且对标注员隐藏"),
        "diversity_mapping": DIVERSITY_MAPPING,
    }

    if not real_resumes:
        write_jsonl([], PAIRS_REAL_V2)
        manifest.update({
            "status": "blocked_no_real_resumes",
            "reason": "真实中文简历 0 份：无法生成真实人岗配对（不生成虚假数据）",
            "pairs_real": 0, "resumes_used": 0, "jobs_used": 0,
            "tier_counts": {}, "per_resume_counts": {},
            "text_field_checks": {"ok": True, "pairs_checked": 0, "problem_count": 0,
                                  "problems": []},
            "exclusions": {},
            "files": {"pairs_real_v2": file_record(PAIRS_REAL_V2)},
            "next_step": "按 docs/evaluation/consent-template.md 取得授权简历后运行 "
                         "intake_resumes.py，再运行本脚本",
        })
        write_report("real-pair-manifest.json", manifest)
        return manifest

    jobs_raw = read_jsonl(JOB_POOL_V2) if JOB_POOL_V2.exists() else []
    if not jobs_raw:
        write_jsonl([], PAIRS_REAL_V2)
        manifest.update({
            "status": "blocked_no_job_pool",
            "reason": f"岗位准入池不存在: {JOB_POOL_V2}（先运行 build_job_candidates.py）",
            "pairs_real": 0,
            "files": {"pairs_real_v2": file_record(PAIRS_REAL_V2)},
        })
        write_report("real-pair-manifest.json", manifest)
        return manifest

    excluded_jobs = [j for j in jobs_raw
                     if j.get("adjudication", {}).get("decision") == "quarantine_near_duplicate"]
    jobs = [adapt_job(j) for j in jobs_raw
            if j.get("adjudication", {}).get("decision") != "quarantine_near_duplicate"]

    pairs, pair_stats = pool_mod.build_pairs(real_resumes, jobs, seed=int(seed),
                                             pairs_per_resume=int(per_resume))
    # 复现性：同种子再跑一次，pair_id 必须完全一致
    pairs_again, _ = pool_mod.build_pairs(real_resumes, jobs, seed=int(seed),
                                          pairs_per_resume=int(per_resume))
    reproducible = [p["pair_id"] for p in pairs] == [p["pair_id"] for p in pairs_again]
    if not reproducible:
        raise RuntimeError("同种子两次配对结果不一致，可复现性检查失败")

    # 门禁：pair_id / (resume, job) 唯一
    gold_gate.ensure_unique_pair_ids(pairs)

    # 近似重复配对隔离（不通过重复简历/岗位凑数）
    kept, near_quarantined = gold_gate.quarantine_near_duplicates(pairs, threshold=0.90)

    # 训练数据交叉检查：非 blind_eligible 岗位 → 配对禁入盲测集
    blind_excluded_job_ids = {str(j["job_id"]) for j in jobs_raw if not j.get("blind_eligible")}
    kept = gold_gate.flag_training_overlap(
        kept, blind_excluded_job_ids,
        reason="岗位曾参与历史 Gold 规则研究（见 job-candidate-audit.json），禁入盲测集")
    job_flag_map = {str(j["job_id"]): j for j in jobs_raw}
    for p in kept:
        p["label_status"] = "unlabeled"
        p["split"] = "pool"
        src_job = job_flag_map.get(str(p["job_id"]), {})
        p["edu_text_overlap"] = bool((src_job.get("audit_flags") or {}).get("edu_text_overlap"))
        p["strict_unseen_jd_eligible"] = bool(p.get("blind_eligible", True)) and not p["edu_text_overlap"]

    text_checks = check_text_and_fields(kept)

    write_jsonl(kept, PAIRS_REAL_V2)

    per_resume: dict[str, int] = {}
    for p in kept:
        per_resume[p["resume_id"]] = per_resume.get(p["resume_id"], 0) + 1
    tier_counts: dict[str, int] = {}
    for p in kept:
        t = p.get("difficulty_tier", "")
        tier_counts[t] = tier_counts.get(t, 0) + 1

    manifest.update({
        "status": "real_pairs_built",
        "pairs_real": len(kept),
        "pairs_quarantined_near_duplicate": len(near_quarantined),
        "resumes_used": len({p["resume_id"] for p in kept}),
        "jobs_used": len({p["job_id"] for p in kept}),
        "tier_counts": dict(sorted(tier_counts.items())),
        "per_resume_counts": dict(sorted(per_resume.items())),
        "per_resume_min": min(per_resume.values()) if per_resume else 0,
        "per_resume_max": max(per_resume.values()) if per_resume else 0,
        "reproducibility_check": {"seed": int(seed), "passed": bool(reproducible),
                                  "method": "同种子两次构建，pair_id 序列逐一对比"},
        "text_field_checks": text_checks,
        "exclusions": {
            "near_duplicate_pairs": [{"pair_id": q.get("pair_id"), "reason": q.get("quarantine_reason"),
                                      "dup_of": q.get("dup_of"), "similarity": q.get("dup_similarity")}
                                     for q in near_quarantined],
            "jobs_excluded_near_duplicate": [str(j.get("job_id")) for j in excluded_jobs],
            "jobs_excluded_from_blind": sorted(blind_excluded_job_ids),
            "synthetic_resumes_used": 0,
        },
        "blind_eligible_pairs": sum(1 for p in kept if p.get("blind_eligible")),
        "blind_excluded_pairs": sum(1 for p in kept if not p.get("blind_eligible")),
        "strict_unseen_jd_eligible_pairs": sum(1 for p in kept if p.get("strict_unseen_jd_eligible")),
        "strict_unseen_jd_note": ("要求『模型完全未见过岗位文本』的评估任务只能使用 "
                                  "strict_unseen_jd_eligible=true 的配对；"
                                  "口径与影响见 job-candidate-audit.json -> contamination_by_task"),
        "files": {"pairs_real_v2": file_record(PAIRS_REAL_V2),
                  "job_pool_v2": file_record(JOB_POOL_V2)},
    })
    if len(kept) < TARGET_PAIR_RANGE[0]:
        manifest["scale_note"] = (f"真实配对 {len(kept)} 组 < 目标下限 {TARGET_PAIR_RANGE[0]}；"
                                  "规模不足时 H2 保持 BLOCKED，不虚构补数")
    write_report("real-pair-manifest.json", manifest)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261212)
    ap.add_argument("--per-resume", type=int, default=12)
    args = ap.parse_args()
    manifest = run(seed=args.seed, per_resume=args.per_resume)
    print(json.dumps({k: manifest.get(k) for k in
                      ("status", "pairs_real", "resumes_used", "jobs_used",
                       "tier_counts", "blind_eligible_pairs", "blind_excluded_pairs",
                       "reproducibility_check")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
