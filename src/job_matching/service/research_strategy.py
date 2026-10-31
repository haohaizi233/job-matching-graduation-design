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
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from ..domain.job_rules import classify_job_category
from ..models.fusion import FeatureFusion, FusionConfig
from ..models.retrieval import BM25Recall, EmbeddingRecall, RecallFusion, TfidfRecall
from ..models.runtime_guard import ModelResult
from .contracts import JobProfile, StudentProfile
from .errors import ServiceError
from .logging_utils import get_service_logger

__all__ = [
    "StrategySpec", "RESEARCH_STRATEGY_SPECS", "ResearchRetrievalScorer",
    "build_scorer", "INDEX_CACHE", "RecallIndexCache", "INDEX_SCHEMA_VERSION",
]

LOG = get_service_logger("job_matching.service.research_strategy")

# ------------------------------------------------------------------ 版本口径
MODEL_VERSION = "zh_research_v1-20261031"
FEATURE_VERSION = "zh_research_feature_v1"
SCORING_CONFIG_VERSION = "research_scoring_config_v1"
# 精排（Cross-Encoder）融合口径升级：原 `weight * (logit / max_logit)` 在全负/零/
# 混合 logits 下会静默跳过或越界，改为批内 min-max 归一化到 [0,1] 的严格单调变换。
# 只有使用精排的策略升级到 v2；无精排策略保持 v1，历史结果版本解释不变。
SCORING_CONFIG_VERSION_RERANK = "research_scoring_config_v2"
RESEARCH_SCORE_TYPE = "research_fusion_score"
SERVICE_SCORE_TYPE = "model_raw_score"     # 服务层 SCORE_TYPES 允许值
RECALL_FUSION_ID = "rrf_k60_bm25_tfidf"
#: 精排实际作用的最大候选数（Top-50 边界）
RERANK_TOP_N = 50


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
        scoring_config_version=SCORING_CONFIG_VERSION_RERANK,
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
        scoring_config_version=SCORING_CONFIG_VERSION_RERANK,
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


#: 索引 schema 版本：索引结构/语义变化时升级（缓存键组成部分，旧索引自动失效）
INDEX_SCHEMA_VERSION = 1


# ------------------------------------------------------------------ 索引缓存
class RecallIndexCache:
    """召回索引生命周期管理：内容哈希 + 煍略/配置版本 + 容量上限 + 并发安全失效。

    * 索引构建与查询分离：`build` 只在缓存未命中时发生；
    * 键 = (策略标识, 检索配置哈希, 索引 schema 版本, 岗位文本内容哈希)。
      岗位新增/修改、rrf_k 等检索配置、编码器版本、策略版本变化均产生新键 = 安全失效；
    * 并发安全：`get_or_build` 持锁 check-then-act，同一键并发只构建一次
      （builder 在锁外执行会引入重复构建，锁内执行对索引构建是可接受的串行点）；
    * 容量上限（默认 8 个索引）控制内存，超出按 LRU 淘汰。
    """

    def __init__(self, max_entries: int = 8):
        self.max_entries = int(max_entries)
        self._entries: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.build_count = 0
        self.hit_count = 0
        self.evict_count = 0

    @staticmethod
    def content_key(strategy_id: str, docs: list[str],
                    config: dict | None = None) -> str:
        """缓存键：覆盖全部影响索引内容/检索语义的输入。

        config 建议包含：retrieval（检索配置如 rrf_k）、encoder_tag（编码器/
        Embedding 版本）、strategy_version（策略实现版本）、scoring_config_version、
        schema（索引 schema 版本）。缺省 config 时与历史键口径兼容（仅策略+文档）。
        """
        blob = json.dumps({"s": strategy_id, "d": list(docs),
                           "c": dict(config or {})},
                          ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def get_or_build(self, key: str, builder):
        with self._lock:
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
        with self._lock:
            before = len(self._entries)
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)
            return before - len(self._entries)

    def stats(self) -> dict:
        with self._lock:
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


# ------------------------------------------------------------------ 精排输出契约
def _rerank_contract_error(model_id: str, msg: str, **extra) -> ServiceError:
    """精排返回值**契约违规**（数据类型/长度/非有限值），明确区别于权重损坏。

    与 MODEL_CORRUPT（真实推理/加载异常）严格区分：契约违规是软件口径问题，
    不得伪装成模型权重损坏，也不静默吞掉。
    """
    detail = {"model_id": model_id, "component": "reranker",
              "failure_kind": "rerank_output_contract_violation"}
    detail.update(extra)
    return ServiceError("INTERNAL_ERROR", msg, detail)


def _extract_rerank_scores(result, *, expected: int, model_id: str,
                           positions: list[int]) -> list[float]:
    """严格按 RerankResult 契约取出 scores -> 一维有限数值序列。

    * 显式判断 `scores is None`（不能用 `or []`：NumPy 数组布尔歧义）；
    * 转为一维数值序列；
    * 校验长度与候选数一致（保证与 job_id/positions 一一对应）；
    * 校验非 NaN/Inf；
    * 以上违规 -> 契约错误（非 MODEL_CORRUPT）。
    """
    scores = getattr(result, "scores", None)
    if scores is None:
        raise _rerank_contract_error(model_id, "精排返回 scores=None（契约要求一维数值数组）",
                                     expected=expected, positions=positions[:8])
    try:
        arr = np.asarray(scores, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError) as e:
        raise _rerank_contract_error(
            model_id, f"精排 scores 无法转为一维数值序列: {type(e).__name__}: {e}",
            expected=expected) from e
    if arr.size != expected:
        raise _rerank_contract_error(
            model_id, f"精排返回条数与候选数不一致: expected={expected} actual={int(arr.size)}",
            expected=expected, actual=int(arr.size), positions=positions[:8])
    if not bool(np.all(np.isfinite(arr))):
        bad = int(np.sum(~np.isfinite(arr)))
        raise _rerank_contract_error(
            model_id, f"精排分数含 NaN/Inf（{bad} 个非有限值），拒绝出层",
            expected=expected, nonfinite=bad)
    return [float(x) for x in arr]


def _minmax_normalize(raw: list[float]) -> list[float]:
    """批内 min-max 归一化到 [0,1]，严格单调、数值稳定、可解释。

    口径：
      * 输入 = Cross-Encoder 原始 Logit（未校准为概率，禁止表述为录用概率）；
      * 输出 = 「本批精排候选内的相对排序信号」∈ [0,1]，跨请求不可比；
      * hi > lo 时 `(x-lo)/(hi-lo)` 严格递增；全等（含单元素）退化为中性 0.5，
        不除零、不产生 NaN/Inf。
    """
    if not raw:
        return []
    lo = min(raw)
    hi = max(raw)
    if hi > lo:
        return [(x - lo) / (hi - lo) for x in raw]
    return [0.5] * len(raw)


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

    # ---------------------------------------------------------- 资源标识
    def warmup(self) -> dict:
        """预加载重资源（编码器/精排器），把冷加载移出请求 deadline 预算。

        背景缺陷（R2 超时审计）：BGE 编码器/精排器冷加载（权重读取 + 框架初始化）
        发生在首个请求的 `rank()` 内，而请求 deadline（默认 30s）从进入服务开始计时；
        冷加载属不可中断的底层 PyTorch 阶段，协作式 deadline 无法切分它——首个请求
        可能在加载完成后的下一处检查点被误判 INFERENCE_TIMEOUT（实测本机冷加载
        30–50s）。兼容方案：部署/预热阶段显式调用 warmup()，把加载时间移出请求预算。
        不得声称软超时能强制中断不可中断的底层推理。
        """
        loaded = []
        if self.spec.use_embedding:
            self._get_encoder()
            loaded.append("bge_encoder")
        if self.spec.use_reranker:
            self._get_reranker()
            loaded.append("reranker")
        return {"model_id": self.spec.model_id, "preloaded": loaded,
                "index_cache": self.cache.stats()}

    def _encoder_tag(self) -> str:
        """编码器/Embedding 版本标识（缓存键组成部分）。

        仅在 use_embedding 时有意义：编码器 revision 变化 -> 旧向量索引失效。
        未加载编码器时返回策略声明的默认标识（加载后会以实际 revision 为准，
        首次构建必然未命中缓存，不存在用旧标识命中旧索引的问题）。
        """
        if not self.spec.use_embedding:
            return "lexical_only"
        enc = self._encoder
        if enc is None:
            return "bge_small_zh_v15@pending"
        info = None
        try:
            if callable(getattr(enc, "describe", None)):
                info = enc.describe()      # 契约：EncoderInfo（dataclass）
        except Exception:  # noqa: BLE001 —— describe 失败不阻断，降级为类名标识
            info = None
        if info is None:
            return f"{type(enc).__name__}@unknown"
        # 严格按 EncoderInfo 契约取字段（dataclass 或 dict 两种形态兼容）
        if isinstance(info, dict):
            model_id, revision = info.get("model_id"), info.get("revision")
        else:
            model_id = getattr(info, "model_id", None)
            revision = getattr(info, "revision", None)
        return f"{model_id or type(enc).__name__}@{revision or 'unknown'}"

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
        # 缓存键覆盖：策略标识 + 检索配置（rrf_k）+ 编码器标识 + 策略/评分版本
        # + 索引 schema 版本 + 岗位文本内容哈希（任务 4.1：任何一项变化都安全失效）
        cache_config = {
            "retrieval": {"rrf_k": self.rrf_k, "fusion_id": "rrf"},
            "encoder_tag": self._encoder_tag(),
            "strategy_version": self.spec.model_version,
            "scoring_config_version": self.spec.scoring_config_version,
            "schema": INDEX_SCHEMA_VERSION,
        }
        content_key = self.cache.content_key(self.spec.model_id, docs,
                                             config=cache_config)
        if deadline_check is not None:
            deadline_check()      # 建索引（编码/倒排构建）是耗时阶段，构建前先查超时
        entry = self.cache.get_or_build(content_key, lambda: self._build_index(docs))
        index = entry["index"]

        # ---- 阶段 1：召回 + RRF -> 每候选归一化召回语义分
        pool = len(jobs) if not pool_limit else min(len(jobs), max(int(pool_limit), 1))
        hits = index.search([query], top_k=pool, pool=pool)[0]
        recall_scores: dict[int, float] = {int(d): float(s) for d, s in hits}
        max_rrf = max(recall_scores.values()) if recall_scores else 0.0

        # 候选顺序：召回命中按 (-rrf, pos)，未命中按 pos（全量池补齐 / 截断池跳过）
        order: list[int] = []
        recall_sem: dict[int, float | None] = {}
        for pos, rrf in sorted(recall_scores.items(), key=lambda kv: (-kv[1], kv[0])):
            order.append(pos)
            recall_sem[pos] = (rrf / max_rrf) if max_rrf > 0 else None
        truncated = 0
        for pos in range(len(jobs)):
            if pos in recall_sem:
                continue
            if pool_limit and pool < len(jobs):
                truncated += 1
                continue
            order.append(pos)
            recall_sem[pos] = None

        # ---- 阶段 2（可选）：Cross-Encoder 精排（默认关闭，Top-50 边界）
        rerank_applied = False
        rerank_raw: dict[int, float] = {}
        rerank_norm: dict[int, float] = {}
        rerank_truncated = 0
        reranker = self._get_reranker()
        if reranker is not None and order:
            if deadline_check is not None:
                deadline_check()
            rerank_positions = order[: min(len(order), RERANK_TOP_N)]
            queries = [query] * len(rerank_positions)
            documents = [_job_doc_text(jobs[p]) for p in rerank_positions]
            try:
                rr = reranker.score(queries, documents)
            except Exception as e:  # noqa: BLE001 —— 真实推理/加载异常 -> MODEL_CORRUPT
                raise ServiceError(
                    "MODEL_CORRUPT",
                    f"精排模型推理失败: {type(e).__name__}: {e}",
                    {"model_id": self.spec.model_id,
                     "failure_kind": "artifact_corrupt_or_load_failed",
                     "component": "reranker"}) from e
            # 契约校验在 try 之外：返回值类型/长度/非有限值 -> 契约违规，不伪装权重损坏
            raw_scores = _extract_rerank_scores(
                rr, expected=len(rerank_positions),
                model_id=self.spec.model_id, positions=rerank_positions)
            rerank_truncated = int(getattr(rr, "truncated", 0) or 0)
            norms = _minmax_normalize(raw_scores)
            for p, raw, norm in zip(rerank_positions, raw_scores, norms):
                rerank_raw[p] = raw
                rerank_norm[p] = norm
            rerank_applied = True

        # ---- 阶段 3：FeatureFusion（语义输入 = 精排归一化信号优先，否则召回信号）
        rows: list[dict] = []
        for pos in order:
            if deadline_check is not None:
                deadline_check()
            sem = rerank_norm[pos] if pos in rerank_norm else recall_sem[pos]
            resume_in, job_in = build_fusion_inputs(student, jobs[pos])
            breakdown = self.fusion.score(resume_in, job_in, semantic_score=sem)
            rows.append({
                "pos": pos, "breakdown": breakdown,
                "rerank_score": rerank_raw.get(pos),
                "rerank_norm": rerank_norm.get(pos),
            })

        # ---- 阶段 4：业务约束 + 稳定排序
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
                "rerank_norm": row.get("rerank_norm"),
                "rerank_truncated": rerank_truncated,
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
                       "rerank_applied": rerank_applied,
                       "rerank_truncated": rerank_truncated,
                       "rerank_positions": len(rerank_norm)},
            ).to_dict()

        LOG.info("research_strategy rank model_id=%s candidates=%d scored=%d "
                 "truncated=%d rerank=%s index=%s",
                 self.spec.model_id, len(jobs), len(order),
                 truncated, rerank_applied, entry["index_version"])
        for item in out:
            item["retrieval_truncated"] = truncated
            item["index_version"] = entry["index_version"]
            item["candidate_scored"] = len(order)
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
