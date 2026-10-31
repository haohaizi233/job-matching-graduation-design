# -*- coding: utf-8 -*-
"""研究推荐策略（Phase4-3B 检索/融合成果 -> 生产业务推荐链路的正式接入）。

定位
----
把 Phase4-3B 已验证的中文检索/融合模块真正接到 `MatchingService` 的
`experimental_model` 模式上，让用户能在现有系统里**实际调用**研究推荐策略，
而不是只停留在研究报告里的代码片段。

推荐链路（任务书 4.2 默认安全方案）
--------------------------------
    简历画像
        -> 岗位候选集（业务过滤后的 JobProfile 列表）
        -> BM25 + TF-IDF（+ 可选 BGE 向量召回）
        -> RRF 融合（RecallFusion）
        -> FeatureFusion（结构化特征 + 语义分，产出可解释明细）
        -> 业务约束（硬性学历约束等，filtered=true 时 score=0 并记录原因）
        -> Top-K（稳定排序：filtered 升序 -> 分数降序 -> 输入顺序）
        -> 解释与历史持久化（由 reco_store 落库）

四个可选策略（同一链路，不同召回/精排配置）
------------------------------------------
| model_id                     | 召回                        | 精排            |
|------------------------------|-----------------------------|-----------------|
| zh_research_retrieval_v1     | BM25 + TF-IDF + RRF         | 无              |
| zh_research_bge_recall_v1    | BM25 + TF-IDF + BGE + RRF   | 无              |
| zh_research_rerank_v1        | BM25 + TF-IDF + RRF         | CrossEncoder    |
| zh_research_bge_rerank_v1    | BM25 + TF-IDF + BGE + RRF   | CrossEncoder    |

纪律（与任务书 4.2 / 4.3 一致）
-----------------------------
  * 全部登记为 `research_only_zh`，**不得**登记为 `verified`，
    `formal_use_allowed=False`，正式模式（`formal=True`）一律拒绝；
  * 精排**默认关闭**：Phase4-3B 已观察到 Reranker 在合成代理标签上有负贡献，
    只有显式配置策略时才启用；
  * 模型不可用 / 权重缺失 / 输入非法 -> 显式 `ServiceError`（可降级码），
    绝不静默返回随机分或 0 分冒充结果；
  * 推理超时 -> `INFERENCE_TIMEOUT`（永不降级）；
  * 分数是**排序参考分**，禁止表述为录用概率/成功率/适配概率；
  * 解释输出不得携带简历原文与 PII（`ModelResult._PRIVATE` 护栏复用）。

版本口径（每策略独立且稳定）
--------------------------
    model_id                策略标识
    model_version           策略实现版本
    feature_version         特征/融合口径版本
    scoring_config_version  评分配置版本（权重/参数）
    evaluation_status       research_only_zh
    score_type              model_raw_score（服务层契约允许值）
    research_score_type     research_fusion_score（研究层信封内的融合分类型）
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from ..domain.job_rules import classify_job_category
from ..models.fusion import FeatureFusion, FusionConfig
from ..models.retrieval import BM25Recall, EmbeddingRecall, RecallFusion, TfidfRecall
from ..models.runtime_guard import ModelResult
from .contracts import JobProfile, StudentProfile
from .errors import ServiceError
from .logging_utils import get_service_logger

__all__ = [
    "StrategySpec", "RESEARCH_STRATEGY_SPECS", "ResearchRetrievalScorer",
    "build_scorer", "INDEX_CACHE", "RecallIndexCache",
]

LOG = get_service_logger("job_matching.service.research_strategy")

# ------------------------------------------------------------------ 版本口径
MODEL_VERSION = "zh_research_v1-20261031"
FEATURE_VERSION = "zh_research_feature_v1"
SCORING_CONFIG_VERSION = "research_scoring_config_v1"
RESEARCH_SCORE_TYPE = "research_fusion_score"
SERVICE_SCORE_TYPE = "model_raw_score"     # 服务层 SCORE_TYPES 允许值
RECALL_FUSION_ID = "rrf_k60_bm25_tfidf"


@dataclass(frozen=True)
class StrategySpec:
    """一个研究推荐策略的稳定身份与配置。"""

    model_id: str
    model_version: str
    feature_version: str
    scoring_config_version: str
    score_type: str
    research_score_type: str
    evaluation_status: str
    use_embedding: bool = False
    use_reranker: bool = False
    description: str = ""
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "scoring_config_version": self.scoring_config_version,
            "score_type": self.score_type,
            "research_score_type": self.research_score_type,
            "evaluation_status": self.evaluation_status,
            "use_embedding": self.use_embedding,
            "use_reranker": self.use_reranker,
            "description": self.description,
            "limitations": list(self.limitations),
        }


_COMMON_LIMITS = (
    "在真实人工 Gold（H2）到位前，全部策略为研究/实验性推荐，不得表述为已验证匹配效果",
    "融合权重 DEFAULT_WEIGHTS 由分析者人工设定，不是训练得到的权重",
    "语义分为 RRF 融合分在当次候选池内的归一化值，跨请求不可比",
    "score 为排序参考分，不是录用概率/成功率",
)

RESEARCH_STRATEGY_SPECS: dict[str, StrategySpec] = {
    "zh_research_retrieval_v1": StrategySpec(
        model_id="zh_research_retrieval_v1",
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_config_version=SCORING_CONFIG_VERSION,
        score_type=SERVICE_SCORE_TYPE,
        research_score_type=RESEARCH_SCORE_TYPE,
        evaluation_status="research_only_zh",
        use_embedding=False, use_reranker=False,
        description="BM25 + TF-IDF 双路召回 -> RRF 融合 -> FeatureFusion -> 业务约束 -> Top-K",
        limitations=_COMMON_LIMITS + ("语义分只来自词法召回，无语义向量增强",),
    ),
    "zh_research_bge_recall_v1": StrategySpec(
        model_id="zh_research_bge_recall_v1",
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_config_version=SCORING_CONFIG_VERSION,
        score_type=SERVICE_SCORE_TYPE,
        research_score_type=RESEARCH_SCORE_TYPE,
        evaluation_status="research_only_zh",
        use_embedding=True, use_reranker=False,
        description="BM25 + TF-IDF + BGE 向量三路召回 -> RRF 融合 -> FeatureFusion -> 业务约束 -> Top-K",
        limitations=_COMMON_LIMITS + ("依赖 BGE 权重；权重缺失时显式报 MODEL_MISSING，不回退随机分",),
    ),
    "zh_research_rerank_v1": StrategySpec(
        model_id="zh_research_rerank_v1",
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_config_version=SCORING_CONFIG_VERSION,
        score_type=SERVICE_SCORE_TYPE,
        research_score_type=RESEARCH_SCORE_TYPE,
        evaluation_status="research_only_zh",
        use_embedding=False, use_reranker=True,
        description="BM25 + TF-IDF + RRF 召回 -> Cross-Encoder 精排 -> FeatureFusion -> 业务约束 -> Top-K",
        limitations=_COMMON_LIMITS + (
            "实验性精排：Phase4-3B 观察到 Reranker 在合成代理标签上有负贡献，默认不启用",
        ),
    ),
    "zh_research_bge_rerank_v1": StrategySpec(
        model_id="zh_research_bge_rerank_v1",
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_config_version=SCORING_CONFIG_VERSION,
        score_type=SERVICE_SCORE_TYPE,
        research_score_type=RESEARCH_SCORE_TYPE,
        evaluation_status="research_only_zh",
        use_embedding=True, use_reranker=True,
        description="BGE 三路召回 -> RRF -> Cross-Encoder 精排 -> FeatureFusion -> 业务约束 -> Top-K",
        limitations=_COMMON_LIMITS + (
            "实验性精排：Phase4-3B 观察到 Reranker 在合成代理标签上有负贡献，默认不启用",
        ),
    ),
}


# ------------------------------------------------------------------ 索引缓存
class RecallIndexCache:
    """召回索引生命周期管理：内容哈希 + 索引版本 + 容量上限 + 安全失效。

    * 索引构建与查询分离：`build` 只在缓存未命中时发生；
    * 键 = (策略标识, 岗位文本内容哈希)，岗位新增/修改即产生新键 = 安全失效；
    * 容量上限（默认 8 个索引）控制内存，超出按 LRU 淘汰。
    """

    def __init__(self, max_entries: int = 8):
        self.max_entries = int(max_entries)
        self._entries: dict[str, dict] = {}
        self.build_count = 0
        self.hit_count = 0
        self.evict_count = 0

    @staticmethod
    def content_key(strategy_id: str, docs: list[str]) -> str:
        blob = json.dumps({"s": strategy_id, "d": list(docs)}, ensure_ascii=False,
                          sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def get_or_build(self, key: str, builder):
        if key in self._entries:
            self.hit_count += 1
            ent = self._entries.pop(key)          # LRU 触碰
            self._entries[key] = ent
            return ent
        t0 = time.perf_counter()
        index = builder()
        self._entries[key] = {
            "index": index,
            "index_version": key[:16],
            "built_ms": round((time.perf_counter() - t0) * 1000, 3),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.build_count += 1
        while len(self._entries) > self.max_entries:
            self._entries.pop(next(iter(self._entries)))
            self.evict_count += 1
        return self._entries[key]

    def invalidate(self, key: str | None = None) -> int:
        before = len(self._entries)
        if key is None:
            self._entries.clear()
        else:
            self._entries.pop(key, None)
        return before - len(self._entries)

    def stats(self) -> dict:
        return {"entries": len(self._entries), "max_entries": self.max_entries,
                "builds": self.build_count, "hits": self.hit_count,
                "evictions": self.evict_count}


#: 进程级索引缓存（同一岗位集多次推荐复用同一索引）
INDEX_CACHE = RecallIndexCache(max_entries=8)


# ------------------------------------------------------------------ 输入适配
def _min_acceptable_edu_tokens(tokens) -> list[str]:
    """可接受学历集合 -> [最低可接受层级]（供 FeatureFusion 作为最低要求）。

    与 annotation/pool.min_required_degree 语义一致：tokens 里的元素是“该岗位
    可接受的学历集合”，最低要求 = 其中层级最低者；学历不限/不明/无法解析不构成
    要求（返回空列表，由 FeatureFusion 按“无要求”中性处理）。
    """
    from ..models.fusion import education_rank
    ranked = [(education_rank(t), str(t).strip()) for t in tokens or []]
    ranked = [(r, t) for r, t in ranked if r > 0]
    if not ranked:
        return []
    return [min(ranked, key=lambda rt: rt[0])[1]]


def build_fusion_inputs(student: StudentProfile,
                        job: JobProfile) -> tuple[dict, dict]:
    """StudentProfile / JobProfile -> FeatureFusion 输入（不携带任何目标值/派生评分）。"""
    intention = str(student.employment_intention.value or "").strip()
    title = str(job.job_title.value or "").strip()
    stu_cat = classify_job_category(intention, "")[0] if intention else "UNKNOWN"
    job_cat = str(job.job_category.value or "").strip()
    if not job_cat:
        job_cat = classify_job_category(title, "")[0] if title else "UNKNOWN"

    cities = student.preferred_cities.value or []
    if isinstance(cities, str):
        cities = [cities]
    resume_city = str(cities[0]).strip() if cities else ""

    resume = {
        "education_level": str(student.education_level.value or ""),
        "skills": {s.canonical_name for s in student.skills},
        # 业务画像不采集工作年限 -> 显式缺失（None），由 FeatureFusion 按中性处理，
        # 禁止编造年限或用目标值填充。
        "years_experience": None,
        "inferred_category": stu_cat,
        "city": resume_city,
        "target_position": intention,
    }
    job_in = {
        # 岗位学历 tokens 是「可接受学历集合」（与 annotation/pool.min_required_degree
        # 同一口径，如“本科及以上” -> [博士, 硕士, 本科]）。FeatureFusion 的
        # education_tokens 语义是「最低学历要求」，因此先按可接受集合归一出最低
        # 可接受层级（min rank），避免把“本科及以上”误判成要求博士。
        "education_tokens": _min_acceptable_edu_tokens(job.education_requirement.tokens or []),
        "skills": {s.canonical_name for s in (job.required_skills + job.preferred_skills)},
        "years_min": job.experience_requirement.years_min,
        "category": job_cat,
        "city": str(job.city.value or ""),
        "job_title": title,
    }
    return resume, job_in


def _resume_query_text(student: StudentProfile) -> str:
    parts = [str(student.employment_intention.value or ""),
             str(student.major.value or ""), str(student.education_level.value or "")]
    parts += [s.canonical_name for s in student.skills]
    for e in (student.project_experiences + student.internship_experiences
              + student.certificates):
        parts.append(str(getattr(e, "excerpt", "") or ""))
    return " ".join(p for p in parts if p).strip()


def _job_doc_text(job: JobProfile) -> str:
    parts = [str(job.job_title.value or ""), str(job.job_category.value or "")]
    resp = job.responsibilities.value
    if resp:
        parts.extend(str(x) for x in (resp if isinstance(resp, (list, tuple)) else [resp]))
    parts += [s.canonical_name for s in job.required_skills + job.preferred_skills]
    return " ".join(p for p in parts if p).strip()


# ------------------------------------------------------------------ 策略执行体
class ResearchRetrievalScorer:
    """研究推荐策略执行体：召回 -> RRF -> FeatureFusion -> 业务约束 -> Top-K。"""

    def __init__(self, spec: StrategySpec, *, fusion_config: FusionConfig | None = None,
                 encoder_factory=None, reranker_factory=None,
                 cache: RecallIndexCache | None = None,
                 rrf_k: int = 60, candidate_pool: int | None = None):
        self.spec = spec
        self.fusion = FeatureFusion(fusion_config)
        self.rrf_k = int(rrf_k)
        self.candidate_pool = candidate_pool
        self._encoder_factory = encoder_factory
        self._reranker_factory = reranker_factory
        self._encoder = None
        self._reranker = None
        self._encoder_error: ServiceError | None = None
        self._reranker_error: ServiceError | None = None
        self.cache = cache or INDEX_CACHE

    # ---------------------------------------------------------- 资源惰性加载
    def _get_encoder(self):
        if self._encoder is not None:
            return self._encoder
        if not self.spec.use_embedding:
            return None
        if self._encoder_error is not None:
            raise self._encoder_error   # 失败被记忆并**重复显式报错**，绝不静默返回 None
        try:
            if self._encoder_factory is not None:
                self._encoder = self._encoder_factory()
            else:
                from ..models.text_encoder import build_encoder
                self._encoder = build_encoder("bge_small_zh_v15", local_files_only=True)
        except Exception as e:  # noqa: BLE001
            self._encoder_error = ServiceError(
                "MODEL_MISSING",
                f"策略 {self.spec.model_id} 需要 BGE 编码器但不可用: {type(e).__name__}: {e}",
                {"model_id": self.spec.model_id, "failure_kind": "artifact_missing",
                 "component": "bge_encoder"})
            raise self._encoder_error from e
        return self._encoder

    def _get_reranker(self):
        if self._reranker is not None:
            return self._reranker
        if not self.spec.use_reranker:
            return None
        if self._reranker_error is not None:
            raise self._reranker_error  # 同上：失败记忆 + 显式重抛，不静默降级成无精排
        try:
            if self._reranker_factory is not None:
                self._reranker = self._reranker_factory()
            else:
                from ..models.reranker import build_reranker
                self._reranker = build_reranker("bge_reranker_base", local_files_only=True)
        except Exception as e:  # noqa: BLE001
            self._reranker_error = ServiceError(
                "MODEL_MISSING",
                f"策略 {self.spec.model_id} 需要精排模型但不可用: {type(e).__name__}: {e}",
                {"model_id": self.spec.model_id, "failure_kind": "artifact_missing",
                 "component": "reranker"})
            raise self._reranker_error from e
        return self._reranker

    # ---------------------------------------------------------- 描述
    def describe(self) -> dict:
        d = self.spec.to_dict()
        d.update({
            "score_semantics": "排序参考分（研究层融合分），不是录用概率",
            "recall_fusion": {"fusion_id": "rrf", "rrf_k": self.rrf_k,
                              "members": ["bm25_okapi", "tfidf_char"]
                                         + (["embedding_cosine"] if self.spec.use_embedding else [])},
            "rerank": ("cross_encoder" if self.spec.use_reranker else "disabled"),
            "fusion_weights": dict(self.fusion.config.weights),
            "fusion_weight_provenance": self.fusion.config.weight_provenance.to_dict(),
            "candidate_pool": self.candidate_pool,
            "index_cache": self.cache.stats(),
        })
        return d

    # ---------------------------------------------------------- 索引构建
    def _build_index(self, docs: list[str]) -> RecallFusion:
        indexes = [BM25Recall(), TfidfRecall()]
        if self.spec.use_embedding:
            indexes.append(EmbeddingRecall(self._get_encoder()))
        fusion = RecallFusion(indexes=indexes, rrf_k=self.rrf_k, fusion_id="rrf")
        fusion.build(docs)
        return fusion

    # ---------------------------------------------------------- 主入口
    def rank(self, student: StudentProfile, jobs: list[JobProfile], *,
             top_k: int | None = None,
             deadline_check=None,
             candidate_pool: int | None = ...) -> list[dict]:
        """返回按业务排序的候选明细（未截断 Top-K 之前是全量有序）。

        每项：{"pos", "score", "breakdown", "envelope", "filtered", "filter_reason"}
        """
        if not jobs:
            raise ServiceError("INVALID_REQUEST", "岗位列表为空", {"field": "jobs"})
        pool_limit = self.candidate_pool if candidate_pool is ... else candidate_pool

        query = _resume_query_text(student)
        if not query:
            raise ServiceError(
                "MODEL_INAPPLICABLE",
                "简历画像缺少可用于检索的文本（求职意向/专业/学历/技能/经历均为空），"
                "研究推荐策略拒绝用随机分或中性分冒充结果",
                {"model_id": self.spec.model_id,
                 "missing_fields": ["employment_intention|major|education_level|skills|experiences"]})

        docs = [_job_doc_text(j) for j in jobs]
        content_key = self.cache.content_key(self.spec.model_id, docs)
        entry = self.cache.get_or_build(content_key, lambda: self._build_index(docs))
        index = entry["index"]

        # ---- 阶段 1/2：召回 + RRF -> 归一化语义分
        pool = len(jobs) if not pool_limit else min(len(jobs), max(int(pool_limit), 1))
        hits = index.search([query], top_k=pool, pool=pool)[0]
        recall_scores: dict[int, float] = {int(d): float(s) for d, s in hits}
        max_rrf = max(recall_scores.values()) if recall_scores else 0.0

        rows: list[dict] = []
        scored_positions: set[int] = set()

        def _eval(pos: int, semantic_score: float | None) -> dict:
            if deadline_check is not None:
                deadline_check()
            resume_in, job_in = build_fusion_inputs(student, jobs[pos])
            breakdown = self.fusion.score(resume_in, job_in, semantic_score=semantic_score)
            return {"pos": pos, "breakdown": breakdown}

        # 召回命中的候选：语义分 = RRF 归一化
        for pos, rrf in sorted(recall_scores.items(), key=lambda kv: (-kv[1], kv[0])):
            sem = (rrf / max_rrf) if max_rrf > 0 else None
            rows.append(_eval(pos, sem))
            scored_positions.add(pos)

        # 未命中候选：不静默丢弃 —— 全量池下按中性语义分补齐；
        # 显式截断池下跳过并在结果里登记 truncation。
        truncated = 0
        for pos in range(len(jobs)):
            if pos in scored_positions:
                continue
            if pool_limit and pool < len(jobs):
                truncated += 1
                continue
            rows.append(_eval(pos, None))

        # ---- 可选阶段：精排（默认关闭）
        rerank_applied = False
        reranker = self._get_reranker()
        if reranker is not None and rows:
            order = [r["pos"] for r in rows[: max(1, min(len(rows), 50))]]
            queries = [query] * len(order)
            documents = [_job_doc_text(jobs[p]) for p in order]
            try:
                rr = reranker.score(queries, documents)
                rr_scores = list(getattr(rr, "scores", []) or [])
            except Exception as e:  # noqa: BLE001
                raise ServiceError(
                    "MODEL_CORRUPT",
                    f"精排模型推理失败: {type(e).__name__}: {e}",
                    {"model_id": self.spec.model_id,
                     "failure_kind": "artifact_corrupt_or_load_failed",
                     "component": "reranker"}) from e
            if len(rr_scores) != len(order):
                raise ServiceError(
                    "MODEL_CORRUPT",
                    f"精排返回条数不一致: expected={len(order)} actual={len(rr_scores)}",
                    {"model_id": self.spec.model_id, "component": "reranker"})
            m = max(rr_scores) if rr_scores else 0.0
            for row, s in zip(rows, rr_scores):
                if m > 0:
                    row["breakdown"].contributions["semantic"] = (
                        row["breakdown"].weights["semantic"] * (float(s) / m))
                    row["breakdown"].total = float(sum(
                        row["breakdown"].contributions.values()))
                    if row["breakdown"].filtered:
                        row["breakdown"].total = 0.0
                    row["rerank_score"] = float(s)
            rerank_applied = True

        # ---- 阶段 3：业务约束 + 稳定排序
        out = []
        for row in rows:
            b = row["breakdown"]
            score = float(b.total)
            if not _finite(score):
                raise ServiceError(
                    "INTERNAL_ERROR",
                    f"融合分数非法（NaN/Inf），拒绝出层: pos={row['pos']}",
                    {"model_id": self.spec.model_id, "pos": row["pos"]})
            out.append({
                "pos": row["pos"],
                "score": score,
                "breakdown": b.to_dict(),
                "filtered": bool(b.filtered),
                "filter_reason": b.filter_reason,
                "rerank_score": row.get("rerank_score"),
            })

        out.sort(key=lambda r: (1 if r["filtered"] else 0, -r["score"], r["pos"]))
        if top_k is not None:
            out = out[: max(0, int(top_k))]

        # ---- 统一模型输出信封（研究层契约）
        for rank_i, item in enumerate(out, start=1):
            item["envelope"] = ModelResult(
                model_id=self.spec.model_id,
                model_version=self.spec.model_version,
                score=item["score"],
                score_type="relevance_score",
                explanation={
                    "contributions": item["breakdown"]["contributions"],
                    "constraints": item["breakdown"]["constraints"],
                    "filtered": item["filtered"],
                    "filter_reason": item["filter_reason"],
                    "rank": rank_i,
                    "recall_rrf": item["pos"] in recall_scores,
                },
                feature_version=self.spec.feature_version,
                degradation=None,
                extra={"scoring_config_version": self.spec.scoring_config_version,
                       "research_score_type": self.spec.research_score_type,
                       "evaluation_status": self.spec.evaluation_status,
                       "rerank_applied": rerank_applied},
            ).to_dict()

        LOG.info("research_strategy rank model_id=%s candidates=%d scored=%d "
                 "truncated=%d rerank=%s index=%s",
                 self.spec.model_id, len(jobs), len(scored_positions),
                 truncated, rerank_applied, entry["index_version"])
        for item in out:
            item["retrieval_truncated"] = truncated
            item["index_version"] = entry["index_version"]
            item["candidate_scored"] = len(scored_positions)
        return out


def _finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


# ------------------------------------------------------------------ 工厂
_SCORERS: dict[str, ResearchRetrievalScorer] = {}


def build_scorer(model_id: str, **kw) -> ResearchRetrievalScorer:
    """按 model_id 构建（或复用）研究推荐策略执行体。"""
    spec = RESEARCH_STRATEGY_SPECS.get(model_id)
    if spec is None:
        raise ServiceError("MODEL_MISSING", f"未登记的研究推荐策略: {model_id}",
                           {"model_id": model_id,
                            "failure_kind": "model_not_registered"})
    if not kw:
        cached = _SCORERS.get(model_id)
        if cached is not None:
            return cached
    scorer = ResearchRetrievalScorer(spec, **kw)
    if not kw:
        _SCORERS[model_id] = scorer
    return scorer


def list_strategies() -> list[dict]:
    return [RESEARCH_STRATEGY_SPECS[k].to_dict() for k in sorted(RESEARCH_STRATEGY_SPECS)]
