# -*- coding: utf-8 -*-
"""多特征融合评分与硬/软约束（Phase4-3B / M3-6.4）。

设计纪律（任务书 6.4）：
  * 硬约束（hard）：不可协商的准入条件，例如岗位明确的最低学历要求。
    命中硬约束 -> 直接过滤或强制降权，并记录被过滤原因。
  * 软约束（soft）：程度型条件，例如技能覆盖度、城市偏好、项目经历相关性。
    软约束只贡献分数，不直接淘汰。
  * 输出可解释明细 breakdown，逐项记录「得分 / 权重 / 判定 / 原因」。
  * 权重来源必须显式声明：本模块默认权重是**人工设定**（见 DEFAULT_WEIGHTS），
    不是任何训练结果；若未来用数据拟合权重，必须另行登记 run_id 与数据版本。
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["DEFAULT_WEIGHTS", "WeightProvenance", "ConstraintVerdict", "ScoreBreakdown",
           "FusionConfig", "FeatureFusion", "education_rank", "EDU_ORDER"]

# 学历等级从高到低（与 docs/evaluation-protocol.md 的 label_order 语义一致）
EDU_ORDER = ["博士", "硕士", "本科", "大专", "学历不限", "学历不明"]
_EDU_RANK = {"博士": 4, "硕士": 3, "本科": 2, "大专": 1}


def education_rank(token: str) -> int:
    return _EDU_RANK.get(str(token).strip(), 0)


# 权重来源：人工设定（analyst-set），未用任何训练数据拟合。
DEFAULT_WEIGHTS: dict[str, float] = {
    "semantic": 0.30,
    "skill": 0.25,
    "education": 0.15,
    "experience": 0.15,
    "category": 0.10,
    "intent": 0.05,
}

WEIGHT_PROVENANCE_NOTE = (
    "DEFAULT_WEIGHTS 由分析者人工设定，取值参考原系统 raw_score 的相对量级"
    "（semantic 0.25 / skill 0.35 / position 0.20 / category 0.10 / experience 0.05 / education 0.05）"
    "并上调语义与学历权重以反映中文场景；**不是**训练结果，不得在论文中表述为学习得到的权重。"
)


@dataclass
class WeightProvenance:
    source: str = "analyst_set_manual"
    basis: str = WEIGHT_PROVENANCE_NOTE
    fitted_on: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ConstraintVerdict:
    name: str
    kind: str            # "hard" | "soft"
    passed: bool
    score: float         # 0..1 的软约束得分（硬约束为 1/0）
    reason: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["detail"] = dict(self.detail)
        return d


@dataclass
class ScoreBreakdown:
    total: float
    contributions: dict[str, float]
    weights: dict[str, float]
    constraints: list[ConstraintVerdict]
    filtered: bool
    filter_reason: str | None
    score_type: str = "fusion_score"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "score_type": self.score_type,
            "contributions": dict(self.contributions),
            "weights": dict(self.weights),
            "constraints": [c.to_dict() for c in self.constraints],
            "filtered": self.filtered,
            "filter_reason": self.filter_reason,
            "note": self.note,
        }


@dataclass
class FusionConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    hard_education: bool = True           # 岗位最低学历作为硬约束
    hard_missing_profile: bool = False    # 画像缺失时是否硬过滤
    city_soft: bool = True                # 城市偏好作为软约束（不淘汰）
    weight_provenance: WeightProvenance = field(default_factory=WeightProvenance)


class FeatureFusion:
    """结构化特征 + 语义分数 -> 可解释融合评分。"""

    def __init__(self, config: FusionConfig | None = None):
        self.config = config or FusionConfig()

    # ---------------- 单项软约束
    @staticmethod
    def _skill_score(resume_skills: set[str], job_skills: set[str]) -> tuple[float, str]:
        if not job_skills and not resume_skills:
            return 0.0, "双方技能均为空，无法评估技能覆盖"
        if not job_skills:
            return 0.5, "岗位未列出技能要求，按中性处理"
        cover = len(resume_skills & job_skills) / len(job_skills)
        return float(cover), f"岗位技能覆盖 {len(resume_skills & job_skills)}/{len(job_skills)}"

    @staticmethod
    def _education_verdict(resume_edu: str, job_edu_tokens: list[str],
                           hard: bool) -> ConstraintVerdict:
        req = [t for t in job_edu_tokens if education_rank(t) > 0]
        if not req:
            return ConstraintVerdict(
                "education", "hard" if hard else "soft", True, 1.0,
                "岗位未给出可解析的最低学历要求",
                {"resume_edu": resume_edu, "required": job_edu_tokens})
        need = max(education_rank(t) for t in req)
        have = education_rank(resume_edu)
        if have == 0:
            return ConstraintVerdict(
                "education", "hard" if hard else "soft", True, 0.5,
                "求职者学历无法解析，按中性处理不淘汰",
                {"resume_edu": resume_edu, "required": req})
        if have >= need:
            return ConstraintVerdict(
                "education", "hard" if hard else "soft", True, 1.0,
                f"学历满足：{resume_edu} >= {req}",
                {"resume_edu": resume_edu, "required": req})
        return ConstraintVerdict(
            "education", "hard" if hard else "soft", not hard, 0.0,
            f"学历不满足：{resume_edu} < 要求 {req}" + ("" if hard else "（软约束，仅降权）"),
            {"resume_edu": resume_edu, "required": req})

    @staticmethod
    def _experience_verdict(resume_years: float, job_years_min: float | None
                            ) -> ConstraintVerdict:
        if job_years_min is None:
            return ConstraintVerdict("experience", "soft", True, 1.0,
                                     "岗位未给出经验年限下限")
        if resume_years != resume_years:  # NaN
            return ConstraintVerdict("experience", "soft", True, 0.5,
                                     "求职者经验年限缺失，按中性处理",
                                     {"resume_years": None, "required_min": job_years_min})
        gap = resume_years - float(job_years_min)
        if gap >= 0:
            return ConstraintVerdict("experience", "soft", True, 1.0,
                                     f"经验满足：{resume_years} >= {job_years_min}",
                                     {"gap": round(float(gap), 3)})
        # 缺口按线性衰减，最多少 2 年衰减到 0
        score = max(0.0, 1.0 + float(gap) / 2.0)
        return ConstraintVerdict("experience", "soft", True, score,
                                 f"经验不足 {abs(float(gap)):.1f} 年，软性降权",
                                 {"gap": round(float(gap), 3)})

    @staticmethod
    def _category_score(resume_category: str, job_category: str) -> ConstraintVerdict:
        if not job_category or job_category == "UNKNOWN":
            return ConstraintVerdict("category", "soft", True, 0.5, "岗位类别未知")
        same = str(resume_category).strip().upper() == str(job_category).strip().upper()
        return ConstraintVerdict("category", "soft", True, 1.0 if same else 0.0,
                                 f"岗位类别 {'一致' if same else '不一致'}"
                                 f"（{resume_category} vs {job_category}）")

    @staticmethod
    def _intent_score(resume_city: str, job_city: str, resume_position: str,
                      job_title: str) -> ConstraintVerdict:
        detail = {"resume_city": resume_city, "job_city": job_city}
        if not resume_city or not job_city:
            city = 0.5
            reason = "城市信息不全，按中性处理"
        elif str(resume_city).strip() == str(job_city).strip():
            city = 1.0
            reason = "城市意向一致"
        else:
            city = 0.0
            reason = "城市意向不一致（软约束，不淘汰）"
        return ConstraintVerdict("intent", "soft", True, city, reason, detail)

    # ---------------- 主入口
    def score(self, resume: dict, job: dict, semantic_score: float | None = None,
              extra: dict | None = None) -> ScoreBreakdown:
        w = dict(self.config.weights)
        unknown = set(w) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"存在未登记的融合分量: {sorted(unknown)}")
        total_w = sum(w.values())
        if abs(total_w - 1.0) > 1e-6:
            raise ValueError(f"权重之和必须为 1.0，当前 {total_w}")

        def _skills(field_name: str) -> set[str]:
            v = job.get(field_name) if field_name in job else resume.get(field_name)
            return v if isinstance(v, set) else set(v or [])

        resume_skills = resume.get("skills") or set()
        job_skills = job.get("skills") or set()
        if not isinstance(resume_skills, set):
            resume_skills = set(resume_skills or [])
        if not isinstance(job_skills, set):
            job_skills = set(job_skills or [])

        skill_s, skill_reason = self._skill_score(resume_skills, job_skills)
        edu = self._education_verdict(
            str(resume.get("education_level") or ""),
            list(job.get("education_tokens") or []),
            hard=self.config.hard_education)
        raw_years = resume.get("years_experience")
        if raw_years is None or str(raw_years).strip() == "":
            years_val = float("nan")
        else:
            try:
                years_val = float(raw_years)   # 注意 0.0 是合法值，不得被当成缺失
            except (TypeError, ValueError):
                years_val = float("nan")
        exp = self._experience_verdict(years_val, job.get("years_min"))
        cat = self._category_score(
            str(resume.get("inferred_category") or "UNKNOWN"),
            str(job.get("category") or "UNKNOWN"))
        intent = self._intent_score(
            str(resume.get("city") or ""), str(job.get("city") or ""),
            str(resume.get("target_position") or ""), str(job.get("job_title") or ""))

        soft = {
            "skill": (skill_s, skill_reason),
            "education": (edu.score, edu.reason),
            "experience": (exp.score, exp.reason),
            "category": (cat.score, cat.reason),
            "intent": (intent.score, intent.reason),
        }
        sem = 0.5 if semantic_score is None else float(semantic_score)
        sem_reason = ("语义相似度未提供，按中性 0.5 处理" if semantic_score is None
                      else f"语义相似度 {sem:.4f}")

        contributions = {"semantic": w["semantic"] * sem}
        for key, (val, _reason) in soft.items():
            contributions[key] = w[key] * float(val)

        constraints = [
            ConstraintVerdict("semantic", "soft", True, float(sem), sem_reason),
            ConstraintVerdict("skill", "soft", True, float(skill_s), skill_reason),
            edu, exp, cat, intent,
        ]

        # 硬约束判定
        filtered = False
        filter_reason = None
        for c in constraints:
            if c.kind == "hard" and not c.passed:
                filtered = True
                filter_reason = c.reason
                break
        if not filtered and self.config.hard_missing_profile:
            missing = [k for k in ("education_level", "skills") if not resume.get(k)]
            if missing:
                filtered = True
                filter_reason = f"画像关键字段缺失: {missing}"

        total = sum(contributions.values())
        if filtered:
            total = 0.0
        note = ("人工设定权重，未训练；硬约束不满足时直接过滤并记录原因"
                if filtered else "人工设定权重，未训练；软约束以线性加权贡献")
        return ScoreBreakdown(
            total=float(total),
            contributions={k: round(float(v), 6) for k, v in contributions.items()},
            weights=w,
            constraints=constraints,
            filtered=filtered,
            filter_reason=filter_reason,
            note=note,
        )
