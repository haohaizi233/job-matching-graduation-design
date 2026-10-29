# -*- coding: utf-8 -*-
"""匹配推理适配层（模块 C）：MatchingService.rank(student_profile, job_profiles, options)。

三种运行模式：
  1) baseline            —— 中文技能覆盖率 + 岗位类别 + 文本相关性的启发式排序
                            （复用 preprocess_skills / pool 词表与 pair_features.title_tokens）；
  2) experimental_model  —— 加载 Phase4-1 历史模型（MatchPredictor.predict_score/rank_jobs）
                            做研究/诊断；先校验 FeatureMap 全部字段能否从业务输入合法构建，
                            缺失一律 model_inapplicable，禁止读目标值/伪造旧评分/构造虚假 embedding；
  3) future_verified     —— Phase4-3B 验证完成后的中文模型预留槽位，本轮明确不可用。

通用纪律：
  * 同输入 + 同模型版本 => 确定性结果（稳定排序：分数降序，同分按输入顺序）；
  * 重复 job_id 只保留首条并告警；
  * 推理超时保护（协作式时间预算）与批量上限；
  * score_type ∈ {heuristic_score, model_raw_score, calibrated_score}，本轮禁用 calibrated；
  * 不产出"录用成功概率"。
"""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field

from ..annotation.pool import classify_job_category
from ..pair_features import title_tokens
from ..preprocess_skills import jaccard
from .contracts import JobProfile, StudentProfile
from .errors import ServiceError
from .explanations import build_match_result
from .logging_utils import get_service_logger
from .model_registry import ModelRegistry

RUN_MODES = ("baseline", "experimental_model", "future_verified")

# 旧模型禁用输入（目标值与派生评分链，见 configs/feature_policy.yaml）
LEAKAGE_FORBIDDEN_KEYS = (
    "final_score", "raw_score", "semantic_score", "skill_score", "position_score",
    "category_score", "experience_score", "education_score",
    "candidate_rank", "candidate_rank_pct", "label_strength", "label_ordinal",
)

_BASELINE_WEIGHTS = {
    "required_skill_coverage": 0.50,
    "preferred_skill_coverage": 0.10,
    "category_match": 0.15,
    "title_overlap": 0.15,
    "text_relevance": 0.10,
}

MAX_JOBS_DEFAULT = 200


@dataclass
class RankOptions:
    mode: str = "baseline"
    top_k: int | None = None
    model_id: str | None = None
    allow_fallback: bool = True
    timeout_ms: int | None = 30000
    formal: bool = False
    max_jobs: int = MAX_JOBS_DEFAULT

    @classmethod
    def from_dict(cls, d: dict | None) -> "RankOptions":
        d = dict(d or {})
        opts = cls()
        for k in ("mode", "model_id"):
            if d.get(k) is not None:
                setattr(opts, k, d[k])
        for k in ("top_k", "timeout_ms", "max_jobs"):
            if d.get(k) is not None:
                setattr(opts, k, int(d[k]))
        for k in ("allow_fallback", "formal"):
            if k in d:
                setattr(opts, k, bool(d[k]))
        if opts.mode not in RUN_MODES:
            raise ServiceError("INVALID_REQUEST",
                               f"非法 mode: {opts.mode!r}，合法值 {RUN_MODES}",
                               {"field": "options.mode"})
        return opts

    def echo(self) -> dict:
        return {"mode": self.mode, "top_k": self.top_k, "model_id": self.model_id,
                "allow_fallback": self.allow_fallback, "timeout_ms": self.timeout_ms,
                "formal": self.formal, "max_jobs": self.max_jobs}


# ------------------------------------------------------------------ 文本相关度
def _bigram_counts(s: str) -> Counter:
    t = "".join(str(s).split())
    return Counter(t[i:i + 2] for i in range(max(0, len(t) - 1)))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def student_text_repr(student: StudentProfile) -> str:
    parts = [student.employment_intention.value or "", student.major.value or "",
             student.education_level.value or ""]
    parts += [s.canonical_name for s in student.skills]
    for e in (student.project_experiences + student.internship_experiences
              + student.certificates):
        parts.append(e.excerpt)
    return " ".join(str(p) for p in parts if p)


def job_text_repr(job: JobProfile) -> str:
    parts = [job.job_title.value or "", job.job_category.value or ""]
    if job.responsibilities.value:
        parts.extend(str(x) for x in job.responsibilities.value)
    parts += [s.canonical_name for s in job.required_skills + job.preferred_skills]
    return " ".join(str(p) for p in parts if p)


# ------------------------------------------------------------------ 泄漏护栏
def assert_no_forbidden_keys(*dicts: dict) -> None:
    """输入若携带目标值/派生评分字段 -> LEAKAGE_GUARD 错误（禁止任何形式的目标泄漏）。"""
    for d in dicts:
        if not isinstance(d, dict):
            continue
        bad = [k for k in d if k in LEAKAGE_FORBIDDEN_KEYS]
        if bad:
            raise ServiceError("LEAKAGE_GUARD",
                               f"输入携带禁用字段（目标值/派生评分）: {sorted(bad)}",
                               {"forbidden_fields": sorted(bad)})


# ------------------------------------------------------------------ 旧模型适配
class LegacyMatchAdapter:
    """StudentProfile/JobProfile -> Phase4-1 MatchPredictor 输入的合法性适配。

    合法性规则（缺一即 model_inapplicable，禁止任何伪造填充）：
      * resume.target_position_norm  <- student.employment_intention（必须非空）；
      * job.job_title_norm           <- job.job_title（必须非空）；
      * skills_canonical_json        <- 双方技能规范名（可为空列表，触发 both_skills_empty）；
      * inferred_category / category <- pool.classify_job_category 规则映射；
      * years_experience             <- 业务画像不采集工作年限 => 显式缺失(NaN)，
                                        由 FeatureMap 按 train 均值填充（既有合法行为），
                                        绝不编造年限。
    """

    @staticmethod
    def build_inputs(student: StudentProfile, job: JobProfile) -> tuple[dict, dict]:
        missing: list[str] = []
        intention = str(student.employment_intention.value or "").strip()
        if not intention:
            missing.append("student.employment_intention")
        title = str(job.job_title.value or "").strip()
        if not title:
            missing.append("job.job_title")
        if missing:
            raise ServiceError(
                "MODEL_INAPPLICABLE",
                "当前业务输入无法合法构建旧模型所需特征，禁止用目标值/旧评分/虚假 embedding 填充",
                {"missing_fields": missing,
                 "required_fields": ["student.employment_intention", "job.job_title",
                                     "skills(可空)", "category(规则映射)",
                                     "years_experience(显式缺失)"]})

        stu_cat, _ = classify_job_category(intention, "")
        job_cat = str(job.job_category.value or "") or classify_job_category(title, "")[0]
        resume = {
            "target_position_norm": intention,
            "skills_canonical_json": json.dumps(
                [s.canonical_name for s in student.skills], ensure_ascii=False),
            "inferred_category": stu_cat,
            "years_experience": None,
        }
        job_in = {
            "job_title_norm": title,
            "category": job_cat,
            "skills_canonical_json": json.dumps(
                [s.canonical_name for s in job.required_skills + job.preferred_skills],
                ensure_ascii=False),
        }
        assert_no_forbidden_keys(resume, job_in)
        return resume, job_in

    @staticmethod
    def check_feature_policy(raw_columns: list[str]) -> None:
        """复用 feature_policy 白名单强制（task=match_ranking）。"""
        from .. import policy
        policy.check_feature_columns("match_ranking", raw_columns, raise_on_violation=True)


# ------------------------------------------------------------------ 服务
class MatchingService:
    """业务匹配推理服务（模块 C + 模块 D）。"""

    def __init__(self, registry: ModelRegistry, *,
                 default_model_id: str = "legacy_match_proxy_v1"):
        self.registry = registry
        self.default_model_id = default_model_id
        self.log = get_service_logger("job_matching.service.matching")

    # ---------------------------------------------------------- baseline 打分
    def _baseline_score(self, student: StudentProfile, job: JobProfile) -> tuple[float, dict]:
        comps: dict[str, float] = {}
        req = [s.canonical_name for s in job.required_skills]
        own = {s.canonical_name for s in student.skills}
        if req:
            comps["required_skill_coverage"] = len(own & set(req)) / len(req)
        pref = [s.canonical_name for s in job.preferred_skills]
        if pref:
            comps["preferred_skill_coverage"] = len(own & set(pref)) / len(pref)
        s_cat = classify_job_category(str(student.employment_intention.value or ""), "")[0]
        j_cat = str(job.job_category.value or "")
        if student.employment_intention.value and j_cat and j_cat not in ("UNKNOWN", ""):
            comps["category_match"] = 1.0 if s_cat == j_cat else 0.0
        if student.employment_intention.value and job.job_title.value:
            comps["title_overlap"] = jaccard(
                title_tokens(str(student.employment_intention.value)),
                title_tokens(str(job.job_title.value)))
        s_txt = student_text_repr(student)
        j_txt = job_text_repr(job)
        if s_txt and j_txt:
            comps["text_relevance"] = _cosine(_bigram_counts(s_txt), _bigram_counts(j_txt))
        if not comps:
            raise ServiceError("INVALID_REQUEST",
                               "学生画像与岗位画像均无可比较特征，无法计算启发式分数",
                               {"job_id": job.job_id})
        num = 0.0
        den = 0.0
        for k, v in comps.items():
            w = _BASELINE_WEIGHTS[k]
            num += w * float(v)
            den += w
        return num / den, comps

    # ---------------------------------------------------------- 主入口
    def rank(self, student_profile: StudentProfile | dict,
             job_profiles: list[JobProfile | dict],
             options: RankOptions | dict | None = None) -> dict:
        t0 = time.monotonic()
        opts = options if isinstance(options, RankOptions) else RankOptions.from_dict(options)
        student = (student_profile if isinstance(student_profile, StudentProfile)
                   else StudentProfile.from_dict(student_profile))
        if not isinstance(job_profiles, (list, tuple)):
            raise ServiceError("INVALID_REQUEST", "job_profiles 必须是列表",
                               {"field": "jobs"})
        jobs_raw = [j if isinstance(j, JobProfile) else JobProfile.from_dict(j)
                    for j in job_profiles]
        if len(jobs_raw) == 0:
            raise ServiceError("INVALID_REQUEST", "岗位列表为空", {"field": "jobs"})
        if len(jobs_raw) > opts.max_jobs:
            raise ServiceError("BATCH_LIMIT_EXCEEDED",
                               f"岗位数量 {len(jobs_raw)} 超过上限 {opts.max_jobs}",
                               {"max_jobs": opts.max_jobs})

        # 重复岗位：job_id 去重（保留首条）+ 内容哈希告警
        jobs: list[JobProfile] = []
        seen_ids: dict[str, int] = {}
        dropped: list[str] = []
        warnings: list[str] = []
        for j in jobs_raw:
            if j.job_id in seen_ids:
                dropped.append(j.job_id)
                continue
            seen_ids[j.job_id] = len(jobs)
            jobs.append(j)
        if dropped:
            warnings.append("duplicate_job_ids_dropped:" + ",".join(sorted(set(dropped))))

        deadline = (t0 + opts.timeout_ms / 1000.0) if opts.timeout_ms is not None else None

        if opts.mode == "baseline":
            scored = self._rank_baseline(student, jobs, opts, deadline)
            result = self._assemble(student, jobs, scored, opts, "heuristic_score",
                                    "baseline_skill_text_v1",
                                    "baseline_skill_text_v1-20261029", warnings)
        elif opts.mode == "experimental_model":
            result = self._rank_experimental(student, jobs, opts, deadline, warnings)
        else:
            result = self._rank_future(student, jobs, opts)

        result["latency_ms"] = round((time.monotonic() - t0) * 1000, 3)
        return result

    # ---------------------------------------------------------- baseline
    def _rank_baseline(self, student: StudentProfile, jobs: list[JobProfile],
                       opts: RankOptions, deadline: float | None) -> list[tuple]:
        scored = []
        for pos, job in enumerate(jobs):
            self._check_deadline(deadline)
            score, comps = self._baseline_score(student, job)
            scored.append((pos, job, score, comps))
        return scored

    def _assemble(self, student, jobs, scored, opts, score_type, scoring_method,
                  model_version, warnings, extra_warnings=None) -> dict:
        rows = sorted(scored, key=lambda t: (-t[2], t[0]))
        if opts.top_k is not None:
            rows = rows[: max(0, int(opts.top_k))]
        results = []
        for rank, (_pos, job, score, comps) in enumerate(rows, start=1):
            item_warns = []
            if isinstance(comps, dict):
                item_warns.append("score_components:" + ",".join(sorted(comps)))
            results.append(build_match_result(
                student, job, rank=rank, score=score, score_type=score_type,
                scoring_method=scoring_method, model_version=model_version,
                warnings=item_warns))
        all_warns = list(warnings) + list(extra_warnings or [])
        if opts.mode == "baseline":
            all_warns.append("heuristic_baseline_unvalidated:启发式基线未经 Gold 验证")
        all_warns.append("score_semantics:排序参考分，不是录用概率")
        return {
            "mode": opts.mode,
            "scoring_method": scoring_method,
            "score_type": score_type,
            "model_version": model_version,
            "evaluation_status": ("not_a_trained_model" if opts.mode == "baseline"
                                  else "research_only_proxy_labels"),
            "formal_evaluation": False,
            "demo": True,
            "label_source": "synthetic_or_unlabeled",
            "options": opts.echo(),
            "warnings": all_warns,
            "results": results,
        }

    # ---------------------------------------------------------- experimental
    # 可降级错误（策略显式）：模型文件缺失 / 模型损坏 / 输入不适用。
    # 永不降级：正式模式门禁、future 槽位、推理超时、目标泄漏护栏、请求非法。
    DEGRADABLE_CODES = ("MODEL_MISSING", "MODEL_CORRUPT", "MODEL_INAPPLICABLE")

    def _degrade_to_baseline(self, student, jobs, opts, deadline, warnings, *,
                             code: str, model_id: str, detail: dict | None = None) -> dict:
        """显式降级到 Baseline：返回中必须写明降级来源，绝不伪装模型输出。"""
        warnings.append(f"degraded_to_baseline:{code}:{model_id}")
        scored = self._rank_baseline(student, jobs, opts, deadline)
        result = self._assemble(student, jobs, scored, opts, "heuristic_score",
                                "baseline_skill_text_v1",
                                "baseline_skill_text_v1-20261029", warnings)
        result["degradation"] = {
            "degraded": True,
            "reason_code": code,
            "failure_kind": (detail or {}).get("failure_kind", ""),
            "requested_model_id": model_id,
            "actual_scoring_method": "baseline_skill_text_v1",
            "policy": "allow_fallback=True（调用方可设 allow_fallback=False 改为拒绝）",
        }
        return result

    def _rank_experimental(self, student, jobs, opts, deadline, warnings) -> dict:
        model_id = opts.model_id or self.default_model_id
        reg = self.registry.get(model_id)
        if opts.formal and not reg.formal_use_allowed:
            raise ServiceError(
                "MODEL_FORMAL_USE_FORBIDDEN",
                f"模型 {model_id} 不允许正式模式：evaluation_status={reg.evaluation_status}，"
                f"supported_languages={reg.supported_languages}（未通过中文正式用途验证）",
                {"model_id": model_id, "evaluation_status": reg.evaluation_status,
                 "supported_languages": reg.supported_languages})
        try:
            predictor = self.registry.load(model_id)
            resume_in, _ = LegacyMatchAdapter.build_inputs(student, jobs[0])
            LegacyMatchAdapter.check_feature_policy(
                ["skill_jaccard", "skill_overlap_ratio_cv", "skill_overlap_ratio_job",
                 "both_skills_empty", "position_token_overlap", "category_match",
                 "years_experience", "target_position_norm", "inferred_category",
                 "job_category"])
            job_inputs = []
            idx_by_input: dict[int, int] = {}
            for pos, job in enumerate(jobs):
                self._check_deadline(deadline)
                _, job_in = LegacyMatchAdapter.build_inputs(student, job)
                idx_by_input[id(job_in)] = pos
                job_inputs.append(job_in)
            ranked = predictor.rank_jobs(resume_in, job_inputs)
        except ServiceError as e:
            if e.code in self.DEGRADABLE_CODES and opts.allow_fallback:
                # 错误被识别并按策略降级，但降级来源必须显式返回（不静默吞错）
                return self._degrade_to_baseline(student, jobs, opts, deadline, warnings,
                                                 code=e.code, model_id=model_id,
                                                 detail=e.detail)
            raise

        scored = []
        for row in ranked:
            pos = idx_by_input.get(id(row.get("job")))
            if pos is None:
                continue
            scored.append((pos, jobs[pos], float(row["score"]), None))
        return self._assemble(
            student, jobs, scored, opts, "model_raw_score",
            f"match_predictor.{getattr(predictor, 'model_name', reg.task_type)}",
            getattr(predictor, "info", lambda: {})().get("run_id", reg.model_version),
            warnings,
            extra_warnings=[
                "experimental_model:旧英文代理标签模型，仅供研究/诊断",
                "not_a_chinese_validated_model:禁止表述为中文人岗适配度或录用概率",
            ])

    # ---------------------------------------------------------- future
    def _rank_future(self, student, jobs, opts) -> dict:
        model_id = opts.model_id or "chinese_match_future_v1"
        reg = self.registry.get_optional(model_id)
        if reg is None or reg.evaluation_status != "verified":
            raise ServiceError(
                "FUTURE_MODEL_UNAVAILABLE",
                "future_verified 模式暂无已验证中文人岗匹配模型（Phase4-3B 尚未解锁），"
                "本轮不伪称存在已验证模型",
                {"model_id": model_id,
                 "evaluation_status": reg.evaluation_status if reg else "not_registered"})
        # 预留：Phase4-3B 验证完成并登记为 verified 后，此处加载并走同一解释链路
        predictor = self.registry.load(model_id)   # pragma: no cover - 本轮不可达
        raise ServiceError("INTERNAL_ERROR", "future 模型加载后适配尚未实现",
                           {"model_id": model_id})

    # ---------------------------------------------------------- 其它
    @staticmethod
    def _check_deadline(deadline: float | None) -> None:
        if deadline is not None and time.monotonic() > deadline:
            raise ServiceError("INFERENCE_TIMEOUT", "推理超过时间预算",
                               {"timeout_exceeded": True})
