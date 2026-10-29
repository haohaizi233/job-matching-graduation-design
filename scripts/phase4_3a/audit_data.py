# -*- coding: utf-8 -*-
"""数据可用性审计（任务书 5.1）-> reports/phase4-3a/dataset-audit.{json,md}。

统计口径：
  * 中文/英文简历、中文/英文岗位数量（语言按 CJK 字符占比判定）；
  * 简历-岗位合法关联数量；
  * 含完整 JD 文本的样本数；只有标签/字段没有文本证据的记录数；
  * 缺少数据来源或使用许可的记录数。
不做任何数据修改，只读 data/raw。
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from common import REPORT_DIR, now, write_report  # noqa: E402
from job_matching.core import ROOT  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")
DESC_RX = re.compile(r"<岗位描述>(.*?)</岗位描述>", re.S)


def _zh_ratio(s: str) -> float:
    s = str(s or "")
    cjk = len(CJK.findall(s))
    latin = len(re.findall(r"[A-Za-z]", s))
    total = cjk + latin
    return (cjk / total) if total else 0.0


def profile_job_education(path: Path) -> dict:
    cols = pd.read_csv(path, nrows=0, encoding="utf-8").columns.tolist()
    usecols = [c for c in ("job_id", "user", "assistant", "人工正确结果") if c in cols]
    rows = 0
    job_ids: set[str] = set()
    with_desc = 0
    desc_len: list[int] = []
    zh_rows = 0
    gold_rows = 0
    for chunk in pd.read_csv(path, usecols=usecols, dtype=str, encoding="utf-8",
                             low_memory=False, chunksize=20000):
        chunk = chunk.fillna("")
        rows += len(chunk)
        job_ids.update(chunk["job_id"].astype(str).str.strip())
        desc = chunk["user"].astype(str).str.extract(DESC_RX, expand=False).fillna("")
        non_empty = desc.str.strip() != ""
        with_desc += int(non_empty.sum())
        desc_len.extend(desc[non_empty].str.len().tolist())
        zh_rows += int(sum(1 for v in chunk["user"] if _zh_ratio(v) >= 0.5))
        if "人工正确结果" in chunk.columns:
            gold_rows += int((chunk["人工正确结果"].astype(str).str.strip() != "").sum())
    desc_len.sort()
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "rows": rows,
        "unique_job_id": len(job_ids),
        "rows_with_jd_text": with_desc,
        "rows_without_jd_text": rows - with_desc,
        "jd_text_len_median": (desc_len[len(desc_len) // 2] if desc_len else 0),
        "jd_text_len_max": (desc_len[-1] if desc_len else 0),
        "rows_language_zh": zh_rows,
        "rows_human_gold_labels": gold_rows,
        "license": "apache-2.0",
        "license_evidence": "data/raw/job-education/README.md front-matter",
    }


def profile_matching() -> dict:
    base = ROOT / "data" / "raw" / "job-resume-matching"
    cv = pd.read_csv(base / "cv.csv", usecols=["candidate_id", "resume_text"],
                     dtype=str, encoding="utf-8", low_memory=False).fillna("")
    job = pd.read_csv(base / "job.csv", usecols=["job_id", "job_description", "job_text"],
                      dtype=str, encoding="utf-8", low_memory=False).fillna("")
    matches = pd.read_csv(base / "matches.csv", usecols=["candidate_id", "job_id", "label_strength"],
                          dtype=str, encoding="utf-8", low_memory=False).fillna("")
    zh_cv = int(sum(1 for v in cv["resume_text"] if _zh_ratio(v) >= 0.5))
    zh_job = int(sum(1 for v in job["job_description"] if _zh_ratio(v) >= 0.5))
    with_email = int(cv["resume_text"].str.contains(r"[\w.+-]+@[\w-]+\.[\w.]+", regex=True).sum())
    with_phone = int(cv["resume_text"].str.contains(r"(?<!\d)1[3-9]\d{9}(?!\d)", regex=True).sum())
    return {
        "path": "data/raw/job-resume-matching",
        "resumes_rows": len(cv),
        "resumes_unique_id": int(cv["candidate_id"].nunique()),
        "resumes_language_zh": zh_cv,
        "resumes_language_en": len(cv) - zh_cv,
        "resumes_with_full_text": int((cv["resume_text"].str.len() > 0).sum()),
        "jobs_rows": len(job),
        "jobs_unique_id": int(job["job_id"].nunique()),
        "jobs_language_zh": zh_job,
        "jobs_language_en": len(job) - zh_job,
        "jobs_with_jd_text": int((job["job_description"].str.len() > 0).sum()),
        "matches_rows": len(matches),
        "matches_unique_candidates": int(matches["candidate_id"].nunique()),
        "matches_unique_jobs": int(matches["job_id"].nunique()),
        "matches_label_distribution": matches["label_strength"].value_counts().to_dict(),
        "matches_text_evidence": ("跨表可回链 cv.csv/job.csv 文本，但记录本身只有评分字段"),
        "pii_email_hits_in_resume_text": with_email,
        "pii_mobile_hits_in_resume_text": with_phone,
        "license": "unverified",
        "license_evidence": ("卡片 front-matter license: mit 与正文 License 节"
                             "『Please update the dataset license』不一致"),
        "usable_for_chinese_eval": False,
    }


def profile_all_df() -> dict:
    path = ROOT / "data" / "raw" / "other" / "all_df.csv" / "all_df.csv"
    df = pd.read_csv(path, dtype=str, encoding="utf-8", low_memory=False).fillna("")
    return {
        "path": "data/raw/other/all_df.csv/all_df.csv",
        "rows": len(df),
        "columns": df.columns.tolist(),
        "rows_with_jd_text": 0,
        "rows_structured_only": len(df),
        "unique_job_name": int(df["job_name"].nunique()),
        "license": "UNKNOWN",
        "license_evidence": "本地无 README / 许可证证据（docs/datasets/README.md 已登记）",
        "note": "来源与许可 UNKNOWN，且无 JD 正文；补齐授权前不得进入正式评估集",
    }


def capability_audit() -> dict:
    """能力复用审计（任务书第三节）：可复用 vs 必须新建。"""
    return {
        "reusable": [
            {"item": "文本规范化与哈希", "where": "src/job_matching/core.py (norm_text/sha256_file/short_hash)",
             "use": "pair content_hash、去重、冻结清单"},
            {"item": "排序指标 NDCG/MRR/Recall + 稳定 tie-breaking",
             "where": "src/job_matching/metrics_ranking.py (evaluate_ranking)",
             "use": "独立评估指标主体（Precision@K 为本阶段补充）"},
            {"item": "查询级配对 Bootstrap", "where": "src/job_matching/evaluation/statistical_tests.py (bootstrap_diff)",
             "use": "模型差值 95% CI，共享重采样组"},
            {"item": "模型加载与前向推理", "where": "src/job_matching/inference/predictor.py (MatchPredictor)",
             "use": "Ridge/GBDT/MLP/RankNet 在真实 pair 上打分"},
            {"item": "零训练基线打分口径", "where": "src/job_matching/baseline_ranking.py / evaluation/statistical_tests.local_baseline_scores",
             "use": "对照第三阶段基线口径"},
            {"item": "学历要求规范化", "where": "src/job_matching/preprocess_education.py (normalize_label/parse_user_segments)",
             "use": "岗位学历要求字段解析"},
            {"item": "隐私约束与日志规范", "where": "src/job_matching/core.py / policy.py",
             "use": "导出脱敏检查、特征黑名单"},
            {"item": "测试与报告机制", "where": "tests/*/run_all.py (stdlib unittest + JSON 报告)",
             "use": "tests/phase4_3a 沿用同一风格"},
        ],
        "newly_built": [
            {"item": "人工标注数据模式与校验", "where": "src/job_matching/annotation/schema.py, importer.py"},
            {"item": "PII 检测/脱敏/导出检查", "where": "src/job_matching/annotation/pii.py"},
            {"item": "三级重复检测（完全/规范化/近似）", "where": "src/job_matching/annotation/dedup.py"},
            {"item": "候选池构建与分层采样", "where": "src/job_matching/annotation/pool.py"},
            {"item": "双人标注一致性（Kappa/Weighted Kappa）", "where": "src/job_matching/annotation/agreement.py"},
            {"item": "仲裁与最终标签留痕", "where": "src/job_matching/annotation/arbitration.py"},
            {"item": "数据集冻结与 SHA-256 复验", "where": "src/job_matching/annotation/freeze.py"},
            {"item": "人工 Gold 评估口径与护栏", "where": "src/job_matching/independent_eval/"},
            {"item": "评估集泄漏检查", "where": "scripts/phase4_3a/leakage_check.py"},
        ],
        "not_reused_reason": {
            "metrics_ranking.precision": "原实现不含 Precision@K，本阶段在 independent_eval/metrics.py 补充并复用其余指标",
            "existing_annotation_code": "仓库内不存在人工标注/独立评估相关代码（已全仓库检索确认）",
        },
    }


def run() -> dict:
    edu_files = [
        ROOT / "data/raw/job-education/default/train/19w_0701.csv",
        ROOT / "data/raw/job-education/default/validation/4w_0708.csv",
        ROOT / "data/raw/job-education/default/test/2w_0716.csv",
        ROOT / "data/raw/job-education/annotated/2w_0716_eval.csv",
    ]
    edu = [profile_job_education(p) for p in edu_files if p.exists()]
    matching = profile_matching()
    all_df = profile_all_df()

    zh_resume = 0
    en_resume = matching["resumes_language_en"]
    all_job_ids: set[str] = set()
    for e, p in zip(edu, [p for p in edu_files if p.exists()]):
        ids = pd.read_csv(p, usecols=["job_id"], dtype=str, encoding="utf-8",
                          low_memory=False)["job_id"].astype(str).str.strip()
        all_job_ids.update(ids.tolist())
    zh_job = len(all_job_ids)
    zh_job_rows_with_text = sum(e["rows_with_jd_text"] for e in edu)
    en_job = matching["jobs_language_en"]
    license_missing_rows = (all_df["rows"] + matching["resumes_rows"] +
                            matching["jobs_rows"] + matching["matches_rows"])

    out = {
        "generated_by": "scripts/phase4_3a/audit_data.py",
        "created_at": now(),
        "availability": {
            "chinese_resumes": {"count": zh_resume, "status": "GAP",
                                "note": "本地无真实中文简历；英文简历不得充当中国大学生就业画像数据"},
            "english_resumes": {"count": en_resume, "status": "available",
                                "note": "仅用于流程验证，禁止进入中文人工真值"},
            "chinese_jobs": {"count_unique_ids": zh_job, "rows_with_jd_text": zh_job_rows_with_text,
                             "status": "available"},
            "english_jobs": {"count_unique_ids": en_job, "status": "available",
                             "note": "来自 Indeed，语言 en"},
            "resume_job_links": {
                "english_links": matching["matches_rows"],
                "chinese_links": 0,
                "note": "matches.csv 全部为正样本代理标签；中文简历-岗位配对需简历导入后生成",
            },
            "records_with_full_jd_text": zh_job_rows_with_text + matching["jobs_with_jd_text"],
            "records_label_only_no_text_evidence": {
                "matches_csv": matching["matches_rows"],
                "all_df_structured_only": all_df["rows_structured_only"],
            },
            "records_missing_source_or_license": {
                "count": license_missing_rows,
                "detail": {
                    "other/all_df (license UNKNOWN)": all_df["rows"],
                    "job-resume-matching (license unverified)":
                        matching["resumes_rows"] + matching["jobs_rows"] + matching["matches_rows"],
                },
            },
        },
        "job_education_profiles": edu,
        "matching_profile": matching,
        "all_df_profile": all_df,
        "capability_audit": capability_audit(),
        "data_gaps": [
            {"item": "经授权脱敏的真实中文简历（目标 30–50 份）", "current": 0,
             "impact": "G2 阻断：无法建立真实中文简历-岗位人工评估配对"},
            {"item": "真实中文简历-岗位人工标注（目标 300–600 对）", "current": 0,
             "impact": "G2 阻断：blind_evaluation_status=blocked"},
            {"item": "other/all_df 来源与授权说明", "current": "UNKNOWN",
             "impact": "补齐前不得进入正式评估集"},
        ],
    }
    write_report("dataset-audit.json", out)
    return out


if __name__ == "__main__":
    result = run()
    print(f"dataset-audit.json 已生成：{REPORT_DIR / 'dataset-audit.json'}")
    print("chinese_resumes =", result["availability"]["chinese_resumes"])
