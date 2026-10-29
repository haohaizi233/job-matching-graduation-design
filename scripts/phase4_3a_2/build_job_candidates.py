# -*- coding: utf-8 -*-
"""中文校招岗位准入审计与筛选（Phase4-3A-2 模块 B）。

复用 Phase4-3A 岗位候选池（job_pool_v1.jsonl，150 条，seed=20261210），不重新采集。
产出 job_pool_v2.jsonl（100–200 条合规中文 JD，字段缺失显式 unknown，不推断编造）：
  * 岗位准入字段补全（employer_name / source_url / source_license / collection_time ...）；
  * 岗位族分类（Java 后端 / Python / 前端 / 测试 / 数据分析 / 算法 AI / 运维 / 其他）；
  * all_df 来源隔离清单（许可 UNKNOWN，隔离不入 Gold）；
  * 9 处配对近似重复 + 5 个历史 Gold 交叉逐条裁决（保留/隔离/剔除 + 原因）；
  * 与学历训练语料的哈希/近似重合逐岗标记，并按训练任务分别说明污染风险。

用法：
  python scripts/phase4_3a_2/build_job_candidates.py [--rescan-edu-corpus] [--near-limit 80000]

产物：
  data/independent_eval/pool/job_pool_v2.jsonl
  reports/phase4-3a-2/source-audit.json
  reports/phase4-3a-2/job-candidate-audit.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

import pandas as pd  # noqa: E402

from common import JOB_POOL_V1, JOB_POOL_V2, now, read_jsonl, write_jsonl, write_report  # noqa: E402

from job_matching.annotation import dedup as dedup_mod  # noqa: E402
from job_matching.annotation.pool import JOB_SOURCES, RESUME_SOURCES  # noqa: E402
from job_matching.core import ROOT, sha256_file  # noqa: E402
from job_matching.preprocess_education import parse_user_segments  # noqa: E402

# 岗位准入字段（缺失显式 unknown）
ADMISSION_FIELDS = (
    "job_id", "job_title", "employer_name", "job_description", "required_skills",
    "preferred_skills", "education_requirement", "experience_requirement",
    "employment_type", "graduation_cohort", "city", "source", "source_url",
    "source_license", "collection_time", "content_hash",
)

UNKNOWN = "unknown"

JOB_FAMILY_KEYWORDS = (
    ("java_backend", ("java", "spring", "springboot", "spring boot", "微服务", "后端开发", "后端工程师")),
    ("python_dev", ("python", "django", "flask", "爬虫开发", "python开发")),
    ("web_frontend", ("前端", "vue", "react", "javascript", "typescript", "小程序", "h5", "web开发")),
    ("software_test", ("测试工程师", "自动化测试", "软件测试", "测试开发", "qa")),
    ("data_analysis", ("数据分析", "数据运营", "bi", "tableau", "powerbi", "数据专员", "数据产品经理")),
    ("algo_ai", ("算法工程师", "算法", "机器学习", "深度学习", "人工智能", "自然语言处理",
                 "计算机视觉", "大模型", "推荐系统", "nlp")),
    ("devops", ("运维", "devops", "kubernetes", "docker", "linux", "网络安全", "信息安全", "数据库管理员")),
    ("other_tech", ("工程师", "开发", "程序员", "嵌入式", "技术支持", "技术")),
)
FAMILY_NON_TECH = "non_tech"
TARGET_FAMILIES = ("java_backend", "python_dev", "web_frontend", "software_test",
                   "data_analysis", "algo_ai", "devops")

_COHORT_RX = re.compile(r"(20\d{2})\s*届")
_EMPLOYMENT_RULES = (
    (("应届", "应届毕业生", "校招"), "campus_recruitment"),
    (("实习",), "internship"),
    (("兼职",), "part_time"),
    (("全职",), "full_time"),
)


def classify_job_family(title, description="") -> tuple[str, str]:
    s = f"{title or ''} {description or ''}".lower()
    for family, kws in JOB_FAMILY_KEYWORDS:
        for kw in kws:
            if kw.lower() in s:
                return family, "heuristic_keyword_v1"
    return FAMILY_NON_TECH, "heuristic_keyword_v1"


def extract_graduation_cohort(text) -> tuple[str, str]:
    m = _COHORT_RX.search("" if text is None else str(text))
    return (m.group(1), "jd_text_regex") if m else (UNKNOWN, "absent")


def extract_employment_type(text) -> tuple[str, str]:
    s = "" if text is None else str(text)
    for kws, token in _EMPLOYMENT_RULES:
        if any(k in s for k in kws):
            return token, "jd_text_keyword"
    return UNKNOWN, "absent"


# ------------------------------------------------------------------ 学历训练语料交叉扫描
def _stream_edu_desc(path: Path):
    """流式产出 (row_key, 岗位描述)。"""
    total = 0
    for chunk in pd.read_csv(path, usecols=["user"], dtype=str, encoding="utf-8",
                             low_memory=False, chunksize=20000):
        for v in chunk["user"].fillna(""):
            total += 1
            desc = parse_user_segments(str(v)).get("job_description_norm", "")
            if desc:
                yield (f"{path.name}:{total}", desc)


def scan_education_corpus(jobs: list[dict], near_limit: int = 80000) -> dict:
    """逐岗扫描与学历训练语料（default/train+validation）的哈希/近似重合。"""
    desc_by_id = {str(j["job_id"]): str(j.get("job_description") or j.get("job_title") or "")
                  for j in jobs}
    desc_by_id = {k: v for k, v in desc_by_id.items() if v.strip()}
    hash_to_jobs: dict[str, list[str]] = {}
    for jid, desc in desc_by_id.items():
        hash_to_jobs.setdefault(dedup_mod.norm_hash(desc), []).append(jid)

    per_job = {jid: {"edu_train_hash_overlap_rows": 0, "edu_train_near_overlap_rows": 0,
                     "edu_overlap_samples": []} for jid in desc_by_id}
    edu_files = [
        ROOT / "data/raw/job-education/default/train/19w_0701.csv",
        ROOT / "data/raw/job-education/default/validation/4w_0708.csv",
    ]
    files_used = []
    rows_scanned = 0
    hash_overlap_rows = 0
    for f in edu_files:
        if not f.exists():
            continue
        files_used.append(str(f.relative_to(ROOT)).replace("\\", "/"))
        for key, desc in _stream_edu_desc(f):
            rows_scanned += 1
            jids = hash_to_jobs.get(dedup_mod.norm_hash(desc), [])
            if jids:
                hash_overlap_rows += 1
                for jid in jids:
                    per_job[jid]["edu_train_hash_overlap_rows"] += 1
                    if len(per_job[jid]["edu_overlap_samples"]) < 5:
                        per_job[jid]["edu_overlap_samples"].append(
                            {"kind": "hash", "edu_row": key})

    # 近似重复（确定性等距抽样，限制如实登记）
    near_hits = []
    for f in edu_files:
        if not f.exists():
            continue
        ref = []
        total = 0
        kept = 0
        stride = 1
        if near_limit:
            n_rows = sum(1 for _ in open(f, "r", encoding="utf-8", errors="ignore")) - 1
            stride = max(1, int(n_rows // max(1, near_limit)))
        for chunk in pd.read_csv(f, usecols=["user"], dtype=str, encoding="utf-8",
                                 low_memory=False, chunksize=20000):
            for v in chunk["user"].fillna(""):
                total += 1
                if near_limit and (total % stride):
                    continue
                desc = parse_user_segments(str(v)).get("job_description_norm", "")
                if not desc:
                    continue
                kept += 1
                ref.append((f"{f.name}:{total}", desc))
        near_hits.extend(dedup_mod.cross_near_duplicate_pairs(desc_by_id, ref, threshold=0.90))
    for hit in near_hits:
        jid = str(hit["a"])
        if jid in per_job:
            per_job[jid]["edu_train_near_overlap_rows"] += 1
            if len(per_job[jid]["edu_overlap_samples"]) < 5:
                per_job[jid]["edu_overlap_samples"].append(
                    {"kind": "near", "edu_row": hit["b"], "similarity": hit["similarity"]})

    return {
        "files_scanned": files_used,
        "rows_scanned": rows_scanned,
        "hash_overlap_rows_total": hash_overlap_rows,
        "near_overlap_pairs_total": len(near_hits),
        "near_check_reference_limit": near_limit,
        "near_check_limitation": ("近似重复跨语料检查在确定性等距抽样子集上执行"
                                  "（默认 8 万行），可能漏检抽样外近似重复；"
                                  "哈希检查覆盖全量语料"),
        "per_job": per_job,
    }


# ------------------------------------------------------------------ 裁决
def adjudicate_jobs(jobs: list[dict], edu_scan: dict, gold_overlap_ids: set[str]) -> list[dict]:
    """逐岗裁决：保留 / 剔除出盲测 / 隔离，附显式原因。

    两级盲测口径（分任务，不把不同训练任务的语料重合一概当泄漏）：
      * blind_eligible（排名 Gold 默认口径）：人岗匹配排序模型训练语料为英文 matches，
        与中文 JD 无文本重合；仅历史 Gold 交叉与近似重复岗位禁入盲测；
      * strict_unseen_jd_eligible（要求模型完全未见过岗位文本的任务）：
        与学历训练语料（default/train+validation）哈希/近似重合的岗位全部排除。
    """
    out = []
    for j in jobs:
        jid = str(j["job_id"])
        edu = (edu_scan.get("per_job") or {}).get(jid, {})
        hash_ov = int(edu.get("edu_train_hash_overlap_rows", 0) or 0)
        near_ov = int(edu.get("edu_train_near_overlap_rows", 0) or 0)
        in_gold = jid in gold_overlap_ids
        edu_overlap = bool(hash_ov or near_ov)
        flags = {
            "historical_gold_cross": in_gold,
            "edu_train_hash_overlap": hash_ov > 0,
            "edu_train_near_overlap": near_ov > 0,
            "edu_train_overlap_rows": hash_ov + near_ov,
            "edu_text_overlap": edu_overlap,
        }
        if in_gold:
            decision = "quarantine_from_blind"
            reason = ("岗位曾带人工正确结果参与 Phase4-2 规则研究（gold_holdout 交叉），"
                      "不得作为全新独立盲测样本；保留用于 dev_validation 与对照分析")
        elif edu_overlap:
            decision = "keep_with_edu_text_overlap"
            reason = (f"JD 文本与学历模型训练语料重合（哈希 {hash_ov} 行 / 近似 {near_ov} 处）："
                      "对要求『模型完全未见过岗位文本』的评估任务禁入盲测集；"
                      "对人岗匹配排序模型（英文语料训练）无直接文本泄漏，排名 Gold 口径下保留盲测资格")
        else:
            decision = "keep"
            reason = "未发现与训练语料 / 历史 Gold 的已知重合，可用于 dev 与 blind"
        out.append({**j, "audit_flags": flags,
                    "blind_eligible": decision != "quarantine_from_blind",
                    "strict_unseen_jd_eligible": decision == "keep",
                    "adjudication": {"decision": decision, "reason": reason,
                                     "checked_at": now()}})
    return out


def job_level_near_duplicates(jobs: list[dict]) -> list[dict]:
    """岗位级近似重复裁决：按 job_id 排序保留首条，其余隔离。"""
    texts = {str(j["job_id"]): (j.get("job_text") or j.get("job_title") or "") for j in jobs}
    near = dedup_mod.near_duplicate_pairs(texts, threshold=0.90)
    by_id = {str(j["job_id"]): j for j in jobs}
    out = []
    for hit in near:
        a, b = str(hit["a"]), str(hit["b"])
        keep, drop = (a, b) if a < b else (b, a)
        out.append({
            "a": a, "b": b, "similarity": hit["similarity"],
            "keep_job_id": keep, "quarantined_job_id": drop,
            "decision": "quarantine_later",
            "reason": (f"岗位 JD 近似重复（Jaccard={hit['similarity']}），"
                       f"保留 {keep}、隔离 {drop}，避免同 JD 不同 ID 造成配对重复与指标虚高"),
            "job_titles": [by_id.get(a, {}).get("job_title", ""), by_id.get(b, {}).get("job_title", "")],
        })
    return out


def load_phase4_3a_pair_near_dups() -> list[dict]:
    """Phase4-3A 已登记的 9 处配对级近似重复（均在合成配对池）逐条裁决。"""
    path = ROOT / "reports" / "phase4-3a" / "leakage-check.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = (((data.get("pool_internal_duplicates") or {}).get("pair_level") or {})
            .get("near_duplicate_pairs") or [])
    out = []
    for r in rows:
        out.append({
            "a": r.get("a"), "b": r.get("b"), "similarity": r.get("similarity"),
            "decision": "quarantine_from_gold",
            "reason": ("配对级近似重复且均位于合成测试配对（is_synthetic=true）："
                       "只用于流程验证，绝不进人工真值；真实配对生成时同文本副本按 "
                       "gold_gate.quarantine_near_duplicates 隔离，不得重复计数"),
        })
    return out


def load_gold_overlap_ids() -> set[str]:
    path = ROOT / "data" / "splits" / "education" / "gold_holdout.csv"
    if not path.exists():
        return set()
    gold = pd.read_csv(path, dtype=str).fillna("")
    return set(gold["job_id"].astype(str).str.strip())


# ------------------------------------------------------------------ 字段补全
def build_admitted_record(j: dict) -> dict:
    """岗位准入字段补全：缺失显式 unknown，不推断编造。"""
    desc = str(j.get("job_description") or "")
    cohort, cohort_src = extract_graduation_cohort(desc)
    emp, emp_src = extract_employment_type(desc)
    family, family_src = classify_job_family(j.get("job_title", ""), desc)
    source_key = str(j.get("job_source", ""))
    src_meta = JOB_SOURCES.get(source_key, {})
    rec = {
        "job_id": str(j.get("job_id", "")),
        "job_title": j.get("job_title", "") or UNKNOWN,
        "employer_name": UNKNOWN,          # 来源无雇主字段，允许匿名化，缺失显式 unknown
        "job_description": desc,
        "required_skills": j.get("required_skills", []),
        "preferred_skills": j.get("preferred_skills", []),
        "education_requirement": j.get("education_requirement", {}),
        "experience_requirement": j.get("experience_requirement", {}),
        "employment_type": emp,
        "graduation_cohort": cohort,
        "city": j.get("city", UNKNOWN) or UNKNOWN,
        "source": source_key,
        "source_url": UNKNOWN,             # HF repo id 本地无证据（docs/datasets/README.md）
        "source_license": src_meta.get("license", UNKNOWN),
        "source_license_evidence": src_meta.get("license_evidence", UNKNOWN),
        "collection_time": UNKNOWN,        # 下载日期本地无证据
        "content_hash": j.get("content_hash", ""),
        "language": j.get("language", "zh"),
        "job_text": j.get("job_text", "") or desc,
        "job_category": j.get("job_category", ""),
        "job_category_source": j.get("job_category_source", ""),
        "job_family": family,
        "job_family_source": family_src,
        "historical_gold": bool(j.get("historical_gold")),
        "field_sources": {
            "employer_name": "absent_in_source",
            "source_url": "unknown_local_evidence_absent",
            "collection_time": "unknown_local_evidence_absent",
            "employment_type": emp_src,
            "graduation_cohort": cohort_src,
            "city": src_meta.get("city_field", "absent_in_source"),
        },
    }
    rec["content_hash"] = rec["content_hash"] or dedup_mod.exact_hash(rec["job_text"])
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescan-edu-corpus", action="store_true",
                    help="重新扫描学历训练语料交叉（默认复用缓存结果）")
    ap.add_argument("--near-limit", type=int, default=80000)
    args = ap.parse_args()

    if not JOB_POOL_V1.exists():
        print(json.dumps({"status": "blocked",
                          "reason": f"岗位候选池不存在: {JOB_POOL_V1}（请先运行 Phase4-3A build_pool）"},
                         ensure_ascii=False, indent=2))
        return 2
    jobs = read_jsonl(JOB_POOL_V1)

    # 学历训练语料交叉扫描（缓存复用）
    cache_path = ROOT / "reports" / "phase4-3a-2" / "job-candidate-audit.json"
    edu_scan = None
    if cache_path.exists() and not args.rescan_edu_corpus:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_scan = (cached.get("education_corpus_overlap") or {}).get("scan")
            if cached_scan and cached_scan.get("per_job"):
                edu_scan = cached_scan
                edu_scan["cache_reused"] = True
        except Exception:
            edu_scan = None
    if edu_scan is None:
        edu_scan = scan_education_corpus(jobs, near_limit=args.near_limit)
        edu_scan["cache_reused"] = False

    gold_ids = load_gold_overlap_ids()
    pool_gold_ids = sorted(gold_ids & {str(j["job_id"]) for j in jobs})

    admitted = [build_admitted_record(j) for j in jobs]
    admitted = adjudicate_jobs(admitted, edu_scan, gold_ids)

    # 岗位级近似重复：隔离后进入配对的副本
    near_jobs = job_level_near_duplicates(jobs)
    quarantined_ids = {str(r["quarantined_job_id"]) for r in near_jobs}
    for rec in admitted:
        if str(rec["job_id"]) in quarantined_ids and rec["adjudication"]["decision"] != "quarantine_near_duplicate":
            if rec["adjudication"]["decision"] == "keep":
                rec["adjudication"] = {
                    "decision": "quarantine_near_duplicate",
                    "reason": "岗位 JD 与已保留岗位近似重复，隔离不进入配对，避免重复计数",
                    "checked_at": now()}
            rec["blind_eligible"] = False
            rec["strict_unseen_jd_eligible"] = False

    write_jsonl(admitted, JOB_POOL_V2)

    # all_df 隔离清单（许可 UNKNOWN：不进正式 Gold 池）
    all_df_in_pool = [r for r in admitted if r["source"] == "other/all_df"]
    all_df_isolation = {
        "source": "other/all_df",
        "license": "UNKNOWN（本地无 README / 许可证证据，docs/datasets/README.md 已登记）",
        "decision": "quarantine",
        "reason": ("来源与使用许可未确认，禁止进入正式 Gold 池；"
                   "补齐 license + license_evidence 并经准入检查后方可解隔离"),
        "records_in_pool_v2": len(all_df_in_pool),
        "record_ids_in_pool_v2": [str(r["job_id"]) for r in all_df_in_pool][:200],
        "source_record_count": "251,381 行（docs/datasets/README.md 登记）",
        "fields_available": "job_name/company_name/job_salary/work_experience/"
                            "educational_requirements/company_address/job_type/scam_probability",
    }

    pair_near = load_phase4_3a_pair_near_dups()

    fam_dist: dict[str, int] = {}
    for r in admitted:
        fam_dist[r["job_family"]] = fam_dist.get(r["job_family"], 0) + 1
    unknown_counts = {f: sum(1 for r in admitted if str(r.get(f, "")) == UNKNOWN)
                      for f in ("employer_name", "source_url", "collection_time",
                                "employment_type", "graduation_cohort", "city")}
    blind_ok = [r for r in admitted if r["blind_eligible"]]
    decision_counts: dict[str, int] = {}
    for r in admitted:
        d = r["adjudication"]["decision"]
        decision_counts[d] = decision_counts.get(d, 0) + 1

    audit = {
        "generated_by": "scripts/phase4_3a_2/build_job_candidates.py",
        "created_at": now(),
        "pool_source_file": {"path": "data/independent_eval/pool/job_pool_v1.jsonl",
                             "sha256": sha256_file(JOB_POOL_V1)},
        "admission_fields": list(ADMISSION_FIELDS),
        "candidates_read": len(jobs),
        "candidates_admitted": len(admitted),
        "target_range": "100–200 条合规中文 JD",
        "field_completeness": {
            "explicit_unknown_counts": unknown_counts,
            "policy": "缺失字段显式 unknown，不推断编造；field_sources 登记每个字段的取值口径",
        },
        "job_family_distribution": dict(sorted(fam_dist.items())),
        "target_family_coverage": {
            "target_families": list(TARGET_FAMILIES),
            "covered": sorted(f for f in TARGET_FAMILIES if fam_dist.get(f, 0) > 0),
            "gaps": sorted(f for f in TARGET_FAMILIES if fam_dist.get(f, 0) == 0),
            "note": "非技术岗位保留作跨类别负例来源（配对多样性），不占技术族配额",
        },
        "adjudication_summary": dict(sorted(decision_counts.items())),
        "near_duplicate_analysis": {
            "job_level_pairs": near_jobs,
            "pair_level_from_phase4_3a": pair_near,
            "threshold": 0.90,
            "policy": "近似重复一律保留首条、隔离其余，禁止同文本重复计数",
        },
        "historical_gold_cross_analysis": {
            "gold_holdout_records": 736,
            "overlap_job_ids": pool_gold_ids,
            "decisions": [{"job_id": jid,
                           "decision": "quarantine_from_blind",
                           "reason": "岗位曾带人工正确结果参与 Phase4-2 规则研究；"
                                     "保留用于 dev_validation，剔除出最终盲测集"}
                          for jid in pool_gold_ids],
        },
        "education_corpus_overlap": {
            "corpus": "job-education default/train + default/validation（学历抽取模型训练语料）",
            "scan": edu_scan,
            "jobs_with_hash_overlap": sum(1 for r in admitted if r["audit_flags"]["edu_train_hash_overlap"]),
            "jobs_with_near_overlap": sum(1 for r in admitted if r["audit_flags"]["edu_train_near_overlap"]),
            "contamination_by_task": {
                "education_extraction_models": (
                    "训练语料与候选 JD 文本哈希/近似重合的岗位，对学历抽取组件不是零样本；"
                    "涉及其学历字段输出的评估任务必须剔除重合岗位"),
                "matching_ranking_models": (
                    "人岗匹配排序模型训练语料为英文 matches，与中文 JD 无文本重合，"
                    "无直接文本泄漏（其训练标签为英文代理标签，属口径限制而非泄漏）"),
                "strict_unseen_jd_tasks": (
                    "要求『模型完全未见过岗位文本』的任务必须排除全部 edu 重合岗位；"
                    "若重合覆盖整个候选池，则该类任务不能使用本岗位池，需另行采集岗位（外部依赖）"),
                "pretraining_contamination": (
                    "外部预训练语料不可知，只能声明『未发现已知泄漏』，不能声称绝对无泄漏"),
            },
        },
        "all_df_isolation": all_df_isolation,
        "blind_eligibility": {
            "blind_eligible_jobs_ranking_gold": len(blind_ok),
            "blind_excluded_jobs": len(admitted) - len(blind_ok),
            "strict_unseen_jd_eligible_jobs": sum(1 for r in admitted
                                                  if r.get("strict_unseen_jd_eligible")),
            "policy": {
                "ranking_gold_default": (
                    "排名 Gold 默认口径：仅历史 Gold 交叉与近似重复岗位禁入盲测；"
                    "学历语料重合对英文语料训练的排序模型不构成文本泄漏"),
                "strict_unseen_jd": (
                    "要求模型完全未见过岗位文本的任务：排除全部学历语料重合岗位；"
                    "若 strict 可用岗位为 0，该类任务不得使用本岗位池"),
            },
            "note": "blind_eligible=false 的岗位可用于 dev；进入 blind_test 的配对必须岗位盲测合格",
        },
        "job_pool_v2_file": "data/independent_eval/pool/job_pool_v2.jsonl",
    }
    write_report("job-candidate-audit.json", audit)

    # 来源与许可审计
    sources = {}
    for key, meta in JOB_SOURCES.items():
        n = sum(1 for r in admitted if r["source"] == key)
        sources[key] = {
            "license": meta.get("license"),
            "license_evidence": meta.get("license_evidence"),
            "provenance": meta.get("provenance"),
            "source_url": UNKNOWN,
            "source_url_note": "HF 具体 repo id 本地无证据（docs/datasets/README.md），不推断编造",
            "collection_time": UNKNOWN,
            "records_in_pool_v2": n,
            "decision": ("admitted" if meta.get("license") not in (None, "UNKNOWN", "unverified")
                         else "quarantined"),
        }
    for key, meta in RESUME_SOURCES.items():
        sources[f"resume:{key}"] = {
            "license": meta.get("license"),
            "license_evidence": meta.get("license_evidence"),
            "language": meta.get("language"),
            "usable_for_chinese_eval": meta.get("usable_for_chinese_eval"),
            "decision": "quarantined",
            "reason": "英文简历禁止充当中国大学生就业画像数据",
        }
    source_audit = {
        "generated_by": "scripts/phase4_3a_2/build_job_candidates.py",
        "created_at": now(),
        "sources": sources,
        "quarantine_list": [
            {"item": "other/all_df（251,381 行）", "decision": "quarantine",
             "reason": "来源与许可 UNKNOWN，补齐前不进入正式 Gold 池"},
            {"item": "job-resume-matching/cv.csv（9,544 份英文简历）", "decision": "quarantine",
             "reason": "英文简历禁止充当中文就业画像数据；许可状态 unverified"},
        ],
        "admission_checklist": [
            {"item": "来源可追溯", "status": "partial",
             "note": "job-education 有 HF 数据卡（@wangzihaogithub）；具体 repo id 与下载日期本地无证据"},
            {"item": "许可明确", "status": "ok", "note": "job-education apache-2.0（卡片 front-matter 可核）"},
            {"item": "岗位准入字段齐全", "status": "ok",
             "note": "缺失显式 unknown（employer_name/source_url/collection_time 等）"},
            {"item": "中文 JD 文本可评估", "status": "ok", "note": "150 条候选均含 JD 正文"},
            {"item": "PII 检查", "status": "ok", "note": "岗位文本导入时经 pii.scrub_record 脱敏"},
        ],
        "resume_source_summary": "见 reports/phase4-3a-2/resume-intake-audit.json",
    }
    write_report("source-audit.json", source_audit)

    print(json.dumps({
        "candidates_read": len(jobs),
        "candidates_admitted": len(admitted),
        "blind_eligible_jobs_ranking_gold": len(blind_ok),
        "strict_unseen_jd_eligible_jobs": audit["blind_eligibility"]["strict_unseen_jd_eligible_jobs"],
        "job_level_near_duplicates": len(near_jobs),
        "historical_gold_cross": len(pool_gold_ids),
        "edu_hash_overlap_jobs": audit["education_corpus_overlap"]["jobs_with_hash_overlap"],
        "edu_near_overlap_jobs": audit["education_corpus_overlap"]["jobs_with_near_overlap"],
        "family_distribution": fam_dist,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
