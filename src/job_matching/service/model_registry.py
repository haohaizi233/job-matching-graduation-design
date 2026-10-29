# -*- coding: utf-8 -*-
"""模型注册表（模块 C / future_verified 预留）。

每个模型登记：
  model_id / model_version / task_type / training_data_version /
  input_schema_version / evaluation_status / supported_languages /
  artifacts / checksum / limitations

纪律：
  * 本轮**不伪称存在已验证的中文人岗匹配模型**：chinese_match_* 槽位
    evaluation_status="pending_phase4_3b"，加载一律拒绝；
  * 旧英文代理标签模型登记为 research_only_proxy_labels，formal_use_allowed=False，
    只允许 experimental_model 模式做研究/诊断；
  * 模型加载只在初始化或缓存失效后进行（load_events 可审计），
    同一 (model_id, model_version, checksum) 只加载一次；
  * 权重缺失 -> MODEL_MISSING，绝不伪造输出。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..core import sha256_file
from .errors import ServiceError

INPUT_SCHEMA_VERSION = "phase5-1-input-v1"

EVALUATION_STATUSES = (
    "not_a_trained_model",          # 启发式/规则，非训练模型
    "research_only_proxy_labels",   # Phase4-1 英文代理标签模型
    "research_only_zh",             # Phase4-2 中文学历模型（未做正式效果验收）
    "verified",                     # 只有 Phase4-3B 验证完成后才允许
    "pending_phase4_3b",            # 预留槽位
)

FORMAL_OK_EVAL = ("not_a_trained_model", "verified")


# ---- 加载失败分类（Phase5-1A：环境不兼容 ≠ 权重缺失 ≠ 文件损坏）----
# 公开错误码与 failure_kind 的兼容映射见 docs/architecture/phase5-1a-dependency-rules.md。
def classify_load_failure(exc: BaseException) -> tuple[str, str]:
    """返回 (failure_kind, 说明)。

    * env_incompatible              —— 历史 checkpoint 与当前依赖栈不兼容
      （旧 scikit-learn 反序列化、C 扩展符号缺失、pickle 协议过高等）；
      **不是**权重文件缺失，也**不是**权重文件损坏。
    * artifact_corrupt_or_load_failed —— 文件确实损坏或加载逻辑失败。
    """
    msg = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return "env_incompatible", f"依赖缺失/结构变化: {msg}"
    if isinstance(exc, AttributeError) and ("Can't get attribute" in str(exc)
                                            or "__pyx_unpickle" in str(exc)):
        return "env_incompatible", f"历史反序列化入口缺失（依赖版本变化）: {msg}"
    if isinstance(exc, ValueError) and "unsupported pickle protocol" in str(exc):
        return "env_incompatible", f"pickle 协议高于当前解释器: {msg}"
    return "artifact_corrupt_or_load_failed", f"文件损坏或加载失败: {msg}"


@dataclass
class ModelRegistration:
    model_id: str
    model_version: str
    task_type: str
    training_data_version: str
    input_schema_version: str = INPUT_SCHEMA_VERSION
    evaluation_status: str = "research_only_proxy_labels"
    supported_languages: list[str] = field(default_factory=lambda: ["zh"])
    artifacts: list[dict] = field(default_factory=list)
    checksum: str = ""
    limitations: list[str] = field(default_factory=list)
    loader: str = "none"            # none | legacy_match | education | future
    loader_kwargs: dict = field(default_factory=dict)

    @property
    def formal_use_allowed(self) -> bool:
        return (self.evaluation_status in FORMAL_OK_EVAL
                and "zh" in self.supported_languages)

    def to_info(self) -> dict:
        d = asdict(self)
        d["formal_use_allowed"] = self.formal_use_allowed
        return d


class ModelRegistry:
    """模型注册 + 惰性加载缓存。load 只在初始化或 cache_clear 后真正执行。"""

    def __init__(self, loader_impl: Callable[[ModelRegistration], Any] | None = None):
        self._regs: dict[str, ModelRegistration] = {}
        self._cache: dict[str, Any] = {}
        self._loader_impl = loader_impl or self._default_loader
        self.load_events: list[dict] = []
        self.cache_hits = 0

    # ---------------------------------------------------------- 注册
    def register(self, reg: ModelRegistration) -> ModelRegistration:
        if reg.evaluation_status not in EVALUATION_STATUSES:
            raise ValueError(f"未登记的 evaluation_status: {reg.evaluation_status}")
        self._regs[reg.model_id] = reg
        self._cache.pop(reg.model_id, None)   # 注册信息变更 -> 缓存失效
        return reg

    def get(self, model_id: str) -> ModelRegistration:
        if model_id not in self._regs:
            raise ServiceError("MODEL_MISSING", f"模型未注册: {model_id}",
                               {"model_id": model_id,
                                "failure_kind": "model_not_registered"})
        return self._regs[model_id]

    def get_optional(self, model_id: str) -> ModelRegistration | None:
        return self._regs.get(model_id)

    def list_ids(self) -> list[str]:
        return sorted(self._regs)

    def describe_all(self) -> list[dict]:
        out = []
        for mid in self.list_ids():
            reg = self._regs[mid]
            info = reg.to_info()
            info["load_state"] = "loaded" if mid in self._cache else "not_loaded"
            out.append(info)
        return out

    # ---------------------------------------------------------- 加载（惰性缓存）
    def load(self, model_id: str) -> Any:
        reg = self.get(model_id)
        if model_id in self._cache:
            self.cache_hits += 1
            return self._cache[model_id]
        if reg.loader == "future":
            raise ServiceError(
                "FUTURE_MODEL_UNAVAILABLE",
                f"模型 {model_id} 仅为 future_verified 预留槽位，"
                f"当前 evaluation_status={reg.evaluation_status}，无可加载权重",
                {"model_id": model_id, "evaluation_status": reg.evaluation_status})
        try:
            obj = self._loader_impl(reg)
        except ServiceError:
            raise
        except FileNotFoundError as e:
            raise ServiceError("MODEL_MISSING", f"模型权重缺失: {model_id} ({e})",
                               {"model_id": model_id,
                                "failure_kind": "artifact_missing"}) from e
        except Exception as e:
            # 加载失败必须分类：环境不兼容 / 文件损坏 与「文件缺失」是不同失败类型（链路 C）
            kind, why = classify_load_failure(e)
            code = "MODEL_ENV_INCOMPATIBLE" if kind == "env_incompatible" else "MODEL_CORRUPT"
            raise ServiceError(code,
                               f"模型加载失败({kind}): {model_id} ({type(e).__name__}: {e})",
                               {"model_id": model_id,
                                "failure_kind": kind,
                                "cause": why,
                                "hint": ("历史 checkpoint 需要匹配的训练环境"
                                         "（见 models/*/manifest.json 的 environment 字段），"
                                         "不得重训或改写历史权重"
                                         if kind == "env_incompatible" else
                                         "请核对权重文件与 manifest 校验和")}) from e
        self._cache[model_id] = obj
        self.load_events.append({"model_id": model_id,
                                 "model_version": reg.model_version,
                                 "checksum": reg.checksum})
        return obj

    def is_loaded(self, model_id: str) -> bool:
        return model_id in self._cache

    @property
    def load_count(self) -> int:
        """真正触发加载的次数（不含缓存命中）。"""
        return len(self.load_events)

    def cache_clear(self, model_id: str | None = None) -> None:
        if model_id is None:
            self._cache.clear()
        else:
            self._cache.pop(model_id, None)

    # ---------------------------------------------------------- 校验
    def verify_checksum(self, model_id: str) -> dict:
        reg = self.get(model_id)
        if not reg.artifacts:
            return {"model_id": model_id, "checksum_ok": None, "note": "无 artifact 登记"}
        for art in reg.artifacts:
            p = Path(art["path"])
            if not p.exists():
                return {"model_id": model_id, "checksum_ok": False,
                        "missing": art.get("path", "")}
            if art.get("sha256"):
                if sha256_file(p) != art["sha256"]:
                    return {"model_id": model_id, "checksum_ok": False,
                            "mismatch": art.get("path", "")}
        return {"model_id": model_id, "checksum_ok": True}

    def status(self, model_id: str) -> dict:
        reg = self.get(model_id)
        info = reg.to_info()
        info["load_state"] = "loaded" if self.is_loaded(model_id) else "not_loaded"
        info["load_count_total"] = self.load_count
        info["checksum_check"] = self.verify_checksum(model_id)
        return info

    # ---------------------------------------------------------- 默认加载器
    def _default_loader(self, reg: ModelRegistration) -> Any:
        if reg.loader == "none":
            return None
        if reg.loader == "legacy_match":
            from ..inference.predictor import MatchPredictor
            run_dir = Path(reg.loader_kwargs["run_dir"])
            return MatchPredictor(run_dir, device="cpu")
        if reg.loader == "education":
            from ..education.predictor import EducationNormalizer
            return EducationNormalizer.from_model_dir(Path(reg.loader_kwargs["run_dir"]))
        raise ServiceError("MODEL_MISSING", f"未知加载器类型: {reg.loader}",
                           {"model_id": reg.model_id})


# ------------------------------------------------------------------ 默认注册
def _artifact_entry(path: Path) -> dict:
    entry = {"path": str(path)}
    if path.exists() and path.is_file():
        entry["sha256"] = sha256_file(path)
        entry["bytes"] = path.stat().st_size
    return entry


def register_builtin_models(registry: ModelRegistry, *,
                            matching_run_dir: Path | str | None = None,
                            education_run_dir: Path | str | None = None) -> ModelRegistry:
    """登记本轮业务可用/受限模型 + future_verified 预留槽位。"""
    registry.register(ModelRegistration(
        model_id="baseline_skill_text_v1",
        model_version="baseline_skill_text_v1-20261029",
        task_type="heuristic_ranking",
        training_data_version="none_zero_training",
        evaluation_status="not_a_trained_model",
        supported_languages=["zh", "en"],
        artifacts=[],
        checksum="none",
        limitations=[
            "启发式规则（技能覆盖率/类别/文本相关性），未在任何 Gold 数据上验证精度",
            "score_type 恒为 heuristic_score，不得表述为录用概率或校准分数",
            "技能识别受词表覆盖率限制，未命中技能一律按证据不足处理",
        ],
        loader="none",
    ))

    if matching_run_dir is not None and Path(matching_run_dir).exists():
        run_dir = Path(matching_run_dir)
        manifest_path = run_dir / "manifest.json"
        weights = [p for p in (run_dir / "model.pkl", run_dir / "model.pt")
                   if p.exists()]
        registry.register(ModelRegistration(
            model_id="legacy_match_proxy_v1",
            model_version=run_dir.name,
            task_type="match_ranking",
            training_data_version="dv-english-proxy-labels(phase4-1)",
            evaluation_status="research_only_proxy_labels",
            supported_languages=["en"],
            artifacts=[_artifact_entry(p) for p in [manifest_path, *weights] if p.exists()],
            checksum=(weights[0].name + ":" + sha256_file(weights[0]))[:71] if weights else "",
            limitations=[
                "训练标签 label_strength/final_score 由旧评分系统公式派生，是代理标签",
                "训练词表与类别分布来自英文简历/岗位，中文输入类别与职位全部落 OOV",
                "仅允许 experimental_model 模式做研究/诊断，禁止正式模式与录用概率表述",
            ],
            loader="legacy_match",
            loader_kwargs={"run_dir": str(run_dir)},
        ))

    if education_run_dir is not None and Path(education_run_dir).exists():
        run_dir = Path(education_run_dir)
        weights = [p for p in (run_dir / "model.pt", run_dir / "model.pkl") if p.exists()]
        registry.register(ModelRegistration(
            model_id="education_normalizer_v1",
            model_version=run_dir.name,
            task_type="education_multilabel",
            training_data_version="job-education(pseudo+human-gold-not-used-for-training)",
            evaluation_status="research_only_zh",
            supported_languages=["zh"],
            artifacts=[_artifact_entry(p) for p in [run_dir / "manifest.json", *weights] if p.exists()],
            checksum=(weights[0].name + ":" + sha256_file(weights[0]))[:71] if weights else "",
            limitations=[
                "confidence 未经校准，不是真实正确概率",
                "human Gold（人工正确结果）未参与训练，也未做正式效果验收",
                "规则回退路径不产生任何模型字段",
            ],
            loader="education",
            loader_kwargs={"run_dir": str(run_dir)},
        ))

    # future_verified 预留槽位：本轮不伪称存在已验证中文模型
    registry.register(ModelRegistration(
        model_id="chinese_match_future_v1",
        model_version="reserved",
        task_type="match_ranking",
        training_data_version="pending",
        evaluation_status="pending_phase4_3b",
        supported_languages=["zh"],
        artifacts=[],
        checksum="",
        limitations=[
            "仅为 Phase4-3B 验证完成后的中文模型预留注册与适配接口",
            "当前无可加载权重，任何加载请求返回 FUTURE_MODEL_UNAVAILABLE",
        ],
        loader="future",
    ))
    return registry
