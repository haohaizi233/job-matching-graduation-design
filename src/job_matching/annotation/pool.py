# -*- coding: utf-8 -*-
"""候选评估样本池构建（协议第三节）。

能力：
  * 从合法本地数据源读取中文岗位 JD（job-education）与岗位资格字段（other/all_df）；
  * 经授权脱敏中文简历的导入接口（当前真实中文简历数 = 0，属数据缺口）；
  * 合成简历测试池（is_synthetic=true，eligible_for_gold=false，绝不冒充真实数据）；
  * 简历-岗位配对生成：固定种子、按岗位类别分层、简历级/岗位级/配对级去重、
    五类难度层覆盖；
  * 候选池清单（来源、内容哈希、抽样策略、覆盖度）。

所有技能/类别/年限抽取都是**启发式辅助字段**，只用于抽样分层与标注辅助，
不是人工真值（每条记录都带 `*_source` 标识）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import ROOT, norm_text, sha256_text, write_csv
from ..preprocess_education import normalize_label, parse_user_segments
from ..pair_features import title_tokens
from . import dedup as dedup_mod
from .pii import detect_pii, scrub_record
from .schema import DIFFICULTY_TIERS, PAIR_FIELDS, PROTOCOL_VERSION

# ------------------------------------------------------------------ 来源登记
JOB_SOURCES = {
    "job-education/annotated": {
        "path": "data/raw/job-education/annotated/2w_0716_eval.csv",
        "language": "zh",
        "has_jd_text": True,
        "license": "apache-2.0",
        "license_evidence": "data/raw/job-education/README.md front-matter license: apache-2.0",
        "provenance": "HuggingFace 数据集 job-educational-parser（@wangzihaogithub）",
        "note": "含 736 条历史人工 Gold（人工正确结果），曾参与 Phase4-2 规则研究，必须登记交叉",
    },
    "job-education/default-test": {
        "path": "data/raw/job-education/default/test/2w_0716.csv",
        "language": "zh",
        "has_jd_text": True,
        "license": "apache-2.0",
        "license_evidence": "data/raw/job-education/README.md front-matter license: apache-2.0",
        "provenance": "同上；default/* 的 assistant 为线上旧系统伪标注",
        "note": "原 default/test ⊂ default/validation（历史实测），使用时按文本去重",
    },
    "other/all_df": {
        "path": "data/raw/other/all_df.csv/all_df.csv",
        "language": "zh",
        "has_jd_text": False,
        "license": "UNKNOWN",
        "license_evidence": "本地无 README / 许可证证据（docs/datasets/README.md 已登记）",
        "provenance": "UNKNOWN（本地无证据）",
        "note": "仅结构化岗位字段，无 JD 正文；来源与授权补齐前不得进入正式评估集",
    },
}

RESUME_SOURCES = {
    "job-resume-matching/cv": {
        "path": "data/raw/job-resume-matching/cv.csv",
        "language": "en",
        "license": "unverified",
        "license_evidence": "卡片 front-matter license: mit 与正文 License 节不一致（见 docs/datasets/README.md）",
        "usable_for_chinese_eval": False,
        "note": "英文简历，禁止充当中国大学生就业画像数据",
    },
}

# 启发式技能词表（中英混合，仅用于抽样分层与标注辅助；非真值）
SKILL_LEXICON = (
    "python", "java", "c++", "c#", "go", "golang", "rust", "javascript", "typescript",
    "sql", "mysql", "postgresql", "oracle", "redis", "mongodb", "hive", "spark",
    "hadoop", "flink", "kafka", "etl", "tableau", "powerbi", "excel", "vba",
    "pytorch", "tensorflow", "机器学习", "深度学习", "自然语言处理", "计算机视觉",
    "数据分析", "数据挖掘", "数据治理", "数据仓库", "爬虫", "算法", "推荐系统",
    "大模型", "llm", "prompt", "transformer", "bert",
    "linux", "docker", "kubernetes", "k8s", "微服务", "spring", "django", "flask",
    "前端", "后端", "全栈", "vue", "react", "android", "ios", "小程序",
    "测试", "自动化测试", "运维", "网络安全", "信息安全",
    "财务分析", "会计", "审计", "税务", "成本核算", "财务报表", "预算管理", "资金管理",
    "投融资", "风控", "合规", "证券", "基金", "银行",
    "人力资源规划", "招聘", "绩效管理", "薪酬管理", "培训", "劳动关系", "社保公积金",
    "销售", "客户开发", "渠道管理", "商务谈判", "大客户", "招投标", "合同管理",
    "市场推广", "品牌策划", "活动策划", "新媒体运营", "内容运营", "用户运营", "社群运营",
    "电商运营", "文案策划", "平面设计", "ui设计", "ps", "pr", "ae", "剪辑",
    "产品经理", "需求分析", "项目管理", "敏捷开发", "英语", "日语",
)

# 岗位类别启发式关键词（顺序即优先级）
CATEGORY_KEYWORDS = (
    ("INFORMATION-TECHNOLOGY",
     ("工程师", "开发", "程序员", "算法", "数据", "运维", "测试", "前端", "后端",
      "java", "python", "c++", "嵌入式", "信息安全", "网络安全", "架构师", "人工智能",
      "机器学习", "产品经理", "技术支持")),
    ("FINANCE",
     ("财务", "会计", "金融", "审计", "税务", "出纳", "银行", "投资", "基金", "证券", "风控")),
    ("HR",
     ("人力", "招聘", "人事", "薪酬", "绩效", "培训专员", "劳动关系")),
    ("SALES",
     ("销售", "商务", "渠道", "客户经理", "业务员", "市场拓展", "招投标")),
    ("MARKETING-OPS",
     ("运营", "市场", "品牌", "策划", "文案", "新媒体", "内容", "编辑")),
)
CATEGORY_OTHER = "OTHER"

_EXPERIENCE_PATTERNS = (
    re.compile(r"(\d+)\s*[-~—至到]\s*(\d+)\s*年"),
    re.compile(r"(\d+)\s*年以上"),
    re.compile(r"至少\s*(\d+)\s*年"),
    re.compile(r"(\d+)\s*年及以上"),
)
_NO_EXPERIENCE_PATTERNS = ("经验不限", "经验不限", "应届", "应届毕业生", "无需经验", "不限")

_PREFERRED_MARKERS = ("优先", "加分", "更佳", "尤佳", "者优先")
_SECTION_MARKERS = ("任职要求", "岗位要求", "任职资格", "岗位职责", "工作职责", "职位描述")


# ------------------------------------------------------------------ 基础抽取
def detect_language(text) -> str:
    s = "" if text is None else str(text)
    if not s.strip():
        return "unknown"
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    latin = len(re.findall(r"[A-Za-z]", s))
    total = max(1, cjk + latin)
    zh_ratio = cjk / total
    if zh_ratio >= 0.5:
        return "zh"
    if zh_ratio <= 0.1:
        return "en"
    return "mixed"


_SKILL_RES = {s: re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(s.lower())}(?![A-Za-z0-9+#])"
                            if re.match(r"^[A-Za-z0-9+#]", s) else re.escape(s))
              for s in SKILL_LEXICON}


def extract_skills(text) -> list[str]:
    """启发式技能词表命中（确定性、按词表顺序）。"""
    s = "" if text is None else str(text).lower()
    out = []
    for term in SKILL_LEXICON:
        if _SKILL_RES[term].search(s):
            out.append(term)
    return out


def preferred_segment(text: str) -> str:
    s = "" if text is None else str(text)
    for marker in _PREFERRED_MARKERS:
        i = s.find(marker)
        if i >= 0:
            return s[i:]
    return ""


def classify_job_category(title, description="") -> tuple[str, str]:
    s = f"{title or ''} {description or ''}".lower()
    for cat, kws in CATEGORY_KEYWORDS:
        for kw in kws:
            if kw.lower() in s:
                return cat, "heuristic_keyword_v1"
    return CATEGORY_OTHER, "heuristic_keyword_v1"


def parse_experience_requirement(text) -> dict:
    s = "" if text is None else str(text)
    for marker in _NO_EXPERIENCE_PATTERNS:
        if marker in s:
            return {"raw": marker, "years_min": 0.0, "source": "heuristic_keyword_v1"}
    for rx in _EXPERIENCE_PATTERNS:
        m = rx.search(s)
        if m:
            raw = m.group(0)
            years_min = float(m.group(1))
            return {"raw": raw, "years_min": years_min, "source": "heuristic_pattern_v1"}
    return {"raw": "", "years_min": None, "source": "absent"}


def education_requirement_fields(raw) -> dict:
    norm = normalize_label(raw)
    return {
        "raw": norm_text(raw),
        "tokens": norm["tokens"],
        "status": norm["status"],
        "source": "configs/education_labels.yaml",
    }


_DEGREE_RANK = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def min_required_degree(tokens: list[str]) -> int | None:
    """可接受学历集合 -> 最低要求层级（1-4）。学历不限/不明返回 None。"""
    ranks = [_DEGREE_RANK[t] for t in tokens if t in _DEGREE_RANK]
    return min(ranks) if ranks else None


# ------------------------------------------------------------------ 简历侧
RESUME_IMPORT_FIELDS = (
    "resume_id", "resume_source", "resume_text", "target_position", "skills",
    "education_level", "graduation_cohort", "employment_type", "years_experience",
    "city", "salary_expectation", "consent_status", "license",
)


class ResumeImportError(ValueError):
    pass


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
            lst = json.loads(s)
            return [str(v).strip() for v in lst if str(v).strip()]
        except Exception:
            pass
    return [p.strip() for p in re.split(r"[;,;、|/]", s) if p.strip()]


def load_resume_file(path: Path | str, source_name: str,
                     require_consent: bool = True) -> tuple[list[dict], dict]:
    """经授权脱敏中文简历导入接口。

    必须提供 consent_status（granted/authorized）与 license；
    导入时自动做 PII 脱敏（邮箱/手机/身份证/微信等），并统计命中。
    """
    path = Path(path)
    if not path.exists():
        raise ResumeImportError(f"简历文件不存在: {path}")
    df = pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")
    missing = [c for c in ("resume_id", "resume_text") if c not in df.columns]
    if missing:
        raise ResumeImportError(f"简历文件缺少必要列: {missing}")
    if require_consent and "consent_status" not in df.columns:
        raise ResumeImportError("缺少 consent_status 列：必须提供授权状态才能导入真实简历")

    out: list[dict] = []
    pii_hits: dict[str, int] = {}
    seen_ids: set[str] = set()
    for _, row in df.iterrows():
        rid = str(row["resume_id"]).strip()
        if not rid:
            raise ResumeImportError("存在空 resume_id")
        if rid in seen_ids:
            raise ResumeImportError(f"resume_id 重复: {rid}")
        seen_ids.add(rid)
        consent = str(row.get("consent_status", "")).strip().lower()
        if require_consent and consent not in ("granted", "authorized"):
            raise ResumeImportError(f"简历 {rid} 未取得授权（consent_status={consent!r}），禁止导入")
        text, hits = scrub_record({"resume_text": str(row["resume_text"])}, ["resume_text"])
        for k, v in hits.items():
            pii_hits[k] = pii_hits.get(k, 0) + v
        skills = _split_skills(row.get("skills", ""))
        rec = {
            "resume_id": rid,
            "resume_source": f"import:{source_name}",
            "resume_text": text["resume_text"],
            "target_position": norm_text(row.get("target_position", "")),
            "skills": skills,
            "education_level": norm_text(row.get("education_level", "")),
            "graduation_cohort": norm_text(row.get("graduation_cohort", "")),
            "employment_type": norm_text(row.get("employment_type", "")),
            "years_experience": _to_float(row.get("years_experience")),
            "city": norm_text(row.get("city", "")),
            "salary_expectation": norm_text(row.get("salary_expectation", "")),
            "language": detect_language(text["resume_text"]),
            "is_synthetic": False,
            "resume_license": norm_text(row.get("license", "")),
        }
        rec["content_hash"] = dedup_mod.exact_hash(rec["resume_text"])
        out.append(rec)
    info = {"source": source_name, "rows": len(out), "pii_hits": pii_hits,
            "path": str(path)}
    return out, info


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def make_synthetic_resumes(n: int = 6, seed: int = 20261210) -> list[dict]:
    """合成简历测试池（流程验证用）。合成样本永不进入人工真值。"""
    rng = np.random.default_rng(int(seed))
    titles = ["Python 开发工程师", "数据分析师", "Java 后端工程师", "财务专员",
              "HR 实习生", "新媒体运营", "算法工程师", "销售管培生"]
    skill_bank = [
        ["python", "sql", "数据分析"], ["java", "spring", "mysql"], ["机器学习", "python", "pytorch"],
        ["会计", "财务报表", "excel"], ["招聘", "培训", "劳动关系"], ["新媒体运营", "文案策划", "ps"],
        ["算法", "深度学习", "c++"], ["销售", "商务谈判", "客户开发"],
    ]
    levels = ["大专", "本科", "硕士"]
    out = []
    for i in range(int(n)):
        k = int(rng.integers(0, len(titles)))
        text = (f"求职意向：{titles[k]} 教育背景：{levels[int(rng.integers(0, len(levels)))]} "
                f"项目经历：参与相关项目，负责核心模块设计与交付。技能："
                f"{'、'.join(skill_bank[k])}。")
        rec = {
            "resume_id": f"syn_resume_{i:03d}",
            "resume_source": "synthetic_fixture",
            "resume_text": text,
            "target_position": titles[k],
            "skills": list(skill_bank[k]),
            "education_level": levels[int(rng.integers(0, len(levels)))],
            "graduation_cohort": "2027",
            "employment_type": "校招",
            "years_experience": float(rng.integers(0, 3)),
            "city": "上海",
            "salary_expectation": "面议",
            "language": detect_language(text),
            "is_synthetic": True,
            "resume_license": "synthetic-generated-local",
            "content_hash": "",
        }
        rec["content_hash"] = dedup_mod.exact_hash(rec["resume_text"])
        out.append(rec)
    return out


# ------------------------------------------------------------------ 岗位侧
def load_jobs_from_job_education(source_key: str) -> tuple[list[dict], dict]:
    src = JOB_SOURCES[source_key]
    path = ROOT / src["path"]
    df = pd.read_csv(path, dtype=str, encoding="utf-8", low_memory=False).fillna("")
    out: list[dict] = []
    skipped_empty_desc = 0
    pii_hits: dict[str, int] = {}
    for _, row in df.iterrows():
        seg = parse_user_segments(row.get("user", ""))
        title = seg.get("job_title_norm", "")
        desc = seg.get("job_description_norm", "")
        if not desc.strip():
            skipped_empty_desc += 1
            continue
        job_text = norm_text(f"{title}\n{desc}")
        job_text, hits = scrub_record({"job_text": job_text}, ["job_text"])
        for k, v in hits.items():
            pii_hits[k] = pii_hits.get(k, 0) + v
        cat, cat_src = classify_job_category(title, desc)
        skills = extract_skills(job_text)
        pref = extract_skills(preferred_segment(desc))
        edu = education_requirement_fields(seg.get("slot_education_norm", ""))
        exp = parse_experience_requirement(desc)
        rec = {
            "job_id": str(row.get("job_id", "")).strip(),
            "job_source": source_key,
            "job_title": title,
            "job_description": desc,
            "job_text": job_text["job_text"],
            "job_category": cat,
            "job_category_source": cat_src,
            "language": detect_language(job_text["job_text"]),
            "required_skills": skills,
            "preferred_skills": pref,
            "education_requirement": edu,
            "experience_requirement": exp,
            "historical_gold": "人工正确结果" in df.columns and
                               str(row.get("人工正确结果", "")).strip() not in ("", "nan"),
        }
        rec["content_hash"] = dedup_mod.exact_hash(rec["job_text"])
        out.append(rec)
    info = {"source": source_key, "path": src["path"], "rows_read": len(df),
            "rows_kept": len(out), "rows_skipped_empty_description": skipped_empty_desc,
            "pii_hits": pii_hits}
    return out, info


def load_jobs_from_all_df(limit: int | None = None) -> tuple[list[dict], dict]:
    """other/all_df：仅结构化字段、无 JD 正文；标记 text_missing。"""
    src = JOB_SOURCES["other/all_df"]
    path = ROOT / src["path"]
    df = pd.read_csv(path, dtype=str, encoding="utf-8", low_memory=False).fillna("")
    if limit:
        df = df.head(int(limit))
    out: list[dict] = []
    for i, row in df.iterrows():
        title = norm_text(row.get("job_name", ""))
        cat, cat_src = classify_job_category(title, "")
        edu = education_requirement_fields(row.get("educational_requirements", ""))
        exp = {"raw": norm_text(row.get("work_experience", "")), "years_min": None,
               "source": "all_df.work_experience"}
        rec = {
            "job_id": f"allf_{i}",
            "job_source": "other/all_df",
            "job_title": title,
            "job_description": "",
            "job_text": "",
            "job_text_missing": True,
            "job_category": cat,
            "job_category_source": cat_src,
            "language": "zh",
            "required_skills": [],
            "preferred_skills": [],
            "education_requirement": edu,
            "experience_requirement": exp,
            "city": norm_text(row.get("company_address", "")),
            "historical_gold": False,
            "content_hash": "",
        }
        rec["content_hash"] = dedup_mod.exact_hash(title or f"allf_{i}")
        out.append(rec)
    info = {"source": "other/all_df", "path": src["path"], "rows_read": len(df),
            "rows_kept": len(out), "text_missing_rows": len(out)}
    return out, info


# ------------------------------------------------------------------ 配对
def pair_content_hash(resume_text: str, job_text: str) -> str:
    return sha256_text(norm_text(resume_text) + "\x1f" + norm_text(job_text))


def make_pair_id(content_hash: str) -> str:
    return f"pair-{content_hash[:12]}"


def difficulty_tier(resume: dict, job: dict) -> tuple[str, dict]:
    """难度层判定（互斥、确定性、优先级固定）。返回 (tier, 因子)。"""
    r_skills = {s.lower() for s in resume.get("skills", [])}
    j_skills = {s.lower() for s in job.get("required_skills", [])}
    skill_j = dedup_mod.jaccard(r_skills, j_skills)
    title_j = dedup_mod.jaccard(title_tokens(resume.get("target_position", "")),
                               title_tokens(job.get("job_title", "")))
    req_rank = min_required_degree(job.get("education_requirement", {}).get("tokens", []))
    resume_rank = _DEGREE_RANK.get(str(resume.get("education_level", "")).strip())
    edu_gap = bool(req_rank is not None and resume_rank is not None and resume_rank < req_rank)
    exp_req = job.get("experience_requirement", {}).get("years_min")
    exp_have = resume.get("years_experience")
    exp_gap = bool(exp_req is not None and exp_have is not None and exp_have < exp_req)
    cat_match = (str(resume.get("target_position", "")) != "" and
                 classify_job_category(resume.get("target_position", ""))[0] ==
                 job.get("job_category"))
    factors = {
        "skill_jaccard": round(float(skill_j), 4),
        "title_token_overlap": round(float(title_j), 4),
        "education_gap": bool(edu_gap),
        "experience_gap": bool(exp_gap),
        "category_match": bool(cat_match),
    }
    if not cat_match and title_j < 0.2 and skill_j < 0.1:
        return "cross_category_negative", factors
    if edu_gap or exp_gap:
        return "hard_requirement_gap", factors
    if skill_j >= 0.3:
        return "high_skill_overlap", factors
    if title_j >= 0.3 and skill_j < 0.15:
        return "same_direction_diff_duties", factors
    return "medium_skill_overlap", factors


def build_pairs(resumes: list[dict], jobs: list[dict], *, seed: int = 20261210,
                pairs_per_resume: int = 12,
                tier_quotas: dict[str, int] | None = None) -> tuple[list[dict], dict]:
    """生成简历-岗位配对：按难度层配额 + 类别分层 + 固定种子，结果确定。"""
    quotas = dict(tier_quotas or {
        "high_skill_overlap": 3, "medium_skill_overlap": 3,
        "same_direction_diff_duties": 2, "hard_requirement_gap": 2,
        "cross_category_negative": 2,
    })
    rng = np.random.default_rng(int(seed))
    pairs: list[dict] = []
    tier_counts = {t: 0 for t in DIFFICULTY_TIERS}
    used_pairs: set[str] = set()
    index = dedup_mod.DuplicateIndex()

    for resume in resumes:
        scored = []
        for job in jobs:
            tier, factors = difficulty_tier(resume, job)
            scored.append((tier, job, factors))
        picked_ids: set[str] = set()
        for tier in DIFFICULTY_TIERS:
            cands = [x for x in scored if x[0] == tier and x[1]["job_id"] not in picked_ids]
            if not cands:
                continue
            # 类别分层：打乱前按类别分组，轮转抽取，保证类别覆盖
            by_cat: dict[str, list] = {}
            for x in cands:
                by_cat.setdefault(x[1]["job_category"], []).append(x)
            order = sorted(by_cat)
            for cat in order:
                by_cat[cat].sort(key=lambda x: x[1]["job_id"])
            n_pick = min(quotas.get(tier, 0), len(cands))
            picked = []
            idx = 0
            while len(picked) < n_pick:
                cat = order[idx % len(order)]
                bucket = by_cat[cat]
                if bucket:
                    pos = int(rng.integers(0, len(bucket)))
                    picked.append(bucket.pop(pos))
                idx += 1
                if all(not b for b in by_cat.values()):
                    break
            for tier_name, job, factors in picked:
                picked_ids.add(job["job_id"])
                ch = pair_content_hash(resume["resume_text"], job["job_text"] or job["job_title"])
                pid = make_pair_id(ch)
                if pid in used_pairs:
                    continue
                used_pairs.add(pid)
                dup = index.check(pid, (resume["resume_text"] or "") + "\x1f" +
                                  (job["job_text"] or job["job_title"]))
                is_synthetic = bool(resume.get("is_synthetic"))
                rec = {
                    "pair_id": pid,
                    "resume_id": resume["resume_id"],
                    "job_id": job["job_id"],
                    "resume_source": resume["resume_source"],
                    "job_source": job["job_source"],
                    "resume_text": resume["resume_text"],
                    "job_text": job["job_text"] or job["job_title"],
                    "job_category": job["job_category"],
                    "job_category_source": job["job_category_source"],
                    "language": job.get("language", detect_language(job["job_text"])),
                    "graduation_cohort": resume.get("graduation_cohort", ""),
                    "employment_type": resume.get("employment_type", ""),
                    "required_skills": json.dumps(job.get("required_skills", []), ensure_ascii=False),
                    "preferred_skills": json.dumps(job.get("preferred_skills", []), ensure_ascii=False),
                    "education_requirement": json.dumps(job.get("education_requirement", {}),
                                                        ensure_ascii=False),
                    "experience_requirement": json.dumps(job.get("experience_requirement", {}),
                                                         ensure_ascii=False),
                    "city": resume.get("city", "") or job.get("city", ""),
                    "salary_expectation": resume.get("salary_expectation", ""),
                    "resume_target_position": resume.get("target_position", ""),
                    "resume_skills": json.dumps(resume.get("skills", []), ensure_ascii=False),
                    "resume_education_level": resume.get("education_level", ""),
                    "resume_years_experience": ("" if resume.get("years_experience") is None
                                                else str(resume.get("years_experience"))),
                    "job_title": job.get("job_title", ""),
                    "difficulty_tier": tier_name,
                    "difficulty_factors": json.dumps(factors, ensure_ascii=False),
                    "content_hash": ch,
                    "dataset_version": "",
                    "is_synthetic": is_synthetic,
                    "pair_provenance": ("synthetic_resume_x_real_job" if is_synthetic
                                        else f"{resume['resume_source']} x {job['job_source']}"),
                    "eligible_for_gold": (not is_synthetic and
                                          job.get("job_source") != "other/all_df"),
                    "split": "pool",
                    "_dup_status": dup["status"],
                }
                pairs.append(rec)
                tier_counts[tier_name] += 1
        if len([p for p in pairs if p["resume_id"] == resume["resume_id"]]) > int(pairs_per_resume):
            raise ValueError(f"简历 {resume['resume_id']} 配对数超过上限 {pairs_per_resume}")

    info = {
        "seed": int(seed),
        "tier_quotas": quotas,
        "pairs_built": len(pairs),
        "resumes_used": len(resumes),
        "jobs_used": len({p["job_id"] for p in pairs}),
        "tier_counts": tier_counts,
        "synthetic_pairs": sum(1 for p in pairs if p["is_synthetic"]),
        "real_pairs": sum(1 for p in pairs if not p["is_synthetic"]),
        "duplicate_pairs_skipped": sum(1 for p in pairs if p["_dup_status"] != "unique"),
    }
    return pairs, info


# ------------------------------------------------------------------ 池构建与清单
def build_job_pool(n_target: int = 150, seed: int = 20261210,
                   allow_all_df: bool = False) -> tuple[list[dict], dict]:
    """构建中文岗位候选池：去重 + 按类别分层采样 + 清单统计。

    源内去重：完全 + 规范化哈希（全量）；近似重复以选中池为目标做 target 驱动阻塞比对
    （见 leakage_check），避免对十万级候选做两两比对。
    """
    jobs: list[dict] = []
    load_stats = []
    for key in ("job-education/annotated", "job-education/default-test"):
        js, info = load_jobs_from_job_education(key)
        jobs.extend(js)
        load_stats.append(info)
    if allow_all_df:
        js, info = load_jobs_from_all_df(limit=2000)
        jobs.extend(js)
        load_stats.append(info)

    # 去重（完全 -> 规范化；近似重复在 leakage_check 中对选中池做 target 驱动检测）
    index = dedup_mod.DuplicateIndex(check_near=False)
    unique_jobs: list[dict] = []
    dup_counts = {"exact_dup": 0, "norm_dup": 0, "near_dup": 0}
    for job in sorted(jobs, key=lambda x: (x["job_source"], x["job_id"])):
        res = index.check(f"{job['job_source']}:{job['job_id']}",
                          job["job_text"] or job["job_title"])
        job["dup_status"] = res["status"]
        job["dup_of"] = res["dup_of"]
        if res["status"] == "unique":
            unique_jobs.append(job)
        else:
            dup_counts[res["status"]] = dup_counts.get(res["status"], 0) + 1

    # 按类别分层采样（确定性）
    rng = np.random.default_rng(int(seed))
    by_cat: dict[str, list[dict]] = {}
    for job in unique_jobs:
        by_cat.setdefault(job["job_category"], []).append(job)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: (x["job_source"], x["job_id"]))
    total = sum(len(v) for v in by_cat.values())
    cats = sorted(by_cat)
    if total <= n_target:
        picked = [j for c in cats for j in by_cat[c]]
    else:
        # 比例分配 + 每层至少 2 条 + 最大余数法（确定性）
        quota = {c: max(2, int(round(len(by_cat[c]) / total * n_target))) for c in cats}
        while sum(quota.values()) > n_target:
            c = max(cats, key=lambda x: (quota[x], x))
            if quota[c] <= 2:
                break
            quota[c] -= 1
        while sum(quota.values()) < n_target:
            c = max(cats, key=lambda x: (len(by_cat[x]) - quota[x], x))
            if quota[c] >= len(by_cat[c]):
                continue
            quota[c] += 1
        picked = []
        for c in cats:
            bucket = list(by_cat[c])
            take = min(quota[c], len(bucket))
            pos = rng.permutation(len(bucket))[:take]
            chosen = sorted((bucket[i] for i in pos), key=lambda x: (x["job_source"], x["job_id"]))
            picked.extend(chosen)
        picked.sort(key=lambda x: (x["job_source"], x["job_id"]))

    stats = {
        "sources": load_stats,
        "jobs_read_total": len(jobs),
        "jobs_unique": len(unique_jobs),
        "duplicates_removed": dup_counts,
        "n_target": int(n_target),
        "jobs_selected": len(picked),
        "category_distribution": {c: sum(1 for j in picked if j["job_category"] == c)
                                  for c in cats},
        "category_source": "heuristic_keyword_v1",
        "sampling": {
            "seed": int(seed),
            "strategy": "stratified_by_job_category(max_remainder, min_quota=2, rng_permutation)",
            "stratum_key": "job_category",
        },
        "historical_gold_in_source": sum(1 for j in jobs if j.get("historical_gold")),
        "license_status": {k: v["license"] for k, v in JOB_SOURCES.items()},
        "protocol_version": PROTOCOL_VERSION,
    }
    return picked, stats


def coverage_report(pairs: list[dict], job_stats: dict, pair_stats: dict) -> dict:
    """候选池覆盖度：类别 × 难度层 × 语言 × 来源。"""
    def _cross(a_key, b_key):
        out: dict[str, dict[str, int]] = {}
        for p in pairs:
            out.setdefault(str(p.get(a_key, "")), {})
            bk = str(p.get(b_key, ""))
            out[str(p.get(a_key, ""))][bk] = out[str(p.get(a_key, ""))].get(bk, 0) + 1
        return out

    return {
        "pairs_total": len(pairs),
        "pairs_by_tier": pair_stats.get("tier_counts", {}),
        "pairs_by_category": _cross("job_category", "difficulty_tier"),
        "pairs_by_language": _cross("language", "difficulty_tier"),
        "pairs_by_source": _cross("job_source", "difficulty_tier"),
        "jobs_in_pool": job_stats.get("jobs_selected"),
        "jobs_by_category": job_stats.get("category_distribution"),
        "resume_language_mix": _cross("resume_source", "language"),
        "gaps": [
            {"item": "真实中文简历", "count": 0,
             "note": "本地无真实中文简历；英文简历不可充当中国大学生就业画像数据"},
            {"item": "真实中文简历-岗位配对", "count": 0,
             "note": "依赖经授权脱敏中文简历导入后才能生成"},
        ],
    }


def write_pool(pairs: list[dict], path: Path) -> Path:
    """导出配对池 JSONL/CSV（导出前做 PII 检查，命中即脱敏）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    pii_report: dict[str, int] = {}
    for p in pairs:
        rec, hits = scrub_record({k: v for k, v in p.items() if not k.startswith("_")},
                                 ["resume_text", "job_text"])
        for k, v in hits.items():
            pii_report[k] = pii_report.get(k, 0) + v
        rows.append(rec)
    if path.suffix == ".jsonl":
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for rec in rows:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        write_csv(pd.DataFrame(rows), path)
    return path


def pool_manifest(pairs: list[dict], job_stats: dict, pair_stats: dict,
                  coverage: dict, files: dict[str, str], dataset_version: str) -> dict:
    return {
        "generated_by": "scripts/phase4_3a/build_pool.py",
        "protocol_version": PROTOCOL_VERSION,
        "dataset_version": dataset_version,
        "files": files,
        "job_pool": job_stats,
        "pair_pool": pair_stats,
        "coverage": coverage,
        "sampling_strategy_recorded": True,
        "pii_hit_counts": _pii_counts(pairs),
    }


def _pii_counts(pairs: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in pairs:
        for field in ("resume_text", "job_text"):
            for k, v in detect_pii(p.get(field, "")).items():
                out[k] = out.get(k, 0) + v
    return out
