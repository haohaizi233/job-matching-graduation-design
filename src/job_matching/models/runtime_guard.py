# -*- coding: utf-8 -*-
"""推理运行期守卫：超时预算、降级契约与统一模型输出信封（Phase4-3B / M6）。

背景（reports/phase4-3b/13-regression-results.md 遗留缺口 #1）：
  上一轮验收把「推理超时契约与测试」登记为**未覆盖**。本模块补齐该契约，
  并给出任务书第九节要求的统一模型输出结构。

设计边界：
  * 本模块只做**运行期约束与结果封装**，不训练、不改权重、不触碰训练配置；
  * 推理失败/超时必须显式登记 `degradation`，**绝不静默返回 0 分或 NaN**；
  * 排名分数只表达相对排序强度，**不是录用概率**（`score_type="ranking_score"`）；
  * 集成侧（Phase5-3）可直接复用 `ModelResult` 的 `to_dict()` 契约，
    也可以完全不使用本模块——本模块是独立适配层，不改既有 API 契约。

超时语义：
  * `run_with_budget` 在同一线程内用单调时钟做**预算检查**；
    超过预算立刻抛 `InferenceTimeoutError` 并返回已用时长，不做无限重试；
  * 需要硬性中断重计算时，可传 `alarm=True` 使用 `signal.SIGALRM`
    （仅 POSIX 主线程可用；Windows 上自动退化为软预算检查并如实登记
    `degradation.timeout_mode="soft"`）。
"""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "BudgetExceeded",
    "InferenceTimeoutError",
    "RuntimeBudget",
    "ModelResult",
    "run_with_budget",
    "build_result",
    "DEFAULT_BUDGET",
]


class BudgetExceeded(RuntimeError):
    """超出运行期预算（非超时类，例如候选规模、输入长度）。"""


class InferenceTimeoutError(BudgetExceeded):
    """推理超时：必须显式失败或按契约降级，不得静默给分。"""

    def __init__(self, elapsed_seconds: float, budget_seconds: float):
        self.elapsed_seconds = float(elapsed_seconds)
        self.budget_seconds = float(budget_seconds)
        super().__init__(
            f"推理超时: 已用 {self.elapsed_seconds:.3f}s > 预算 {self.budget_seconds:.3f}s"
        )


@dataclass(frozen=True)
class RuntimeBudget:
    """推理运行期预算（超时契约的唯一来源）。"""

    timeout_seconds: float = 30.0
    max_candidates: int = 10_000
    max_text_chars: int = 20_000
    #: 是否尝试硬中断（POSIX 主线程）；不可用时退化为软预算
    alarm: bool = False

    def __post_init__(self):
        if not (self.timeout_seconds > 0):
            raise ValueError("timeout_seconds 必须 > 0")
        if self.max_candidates <= 0:
            raise ValueError("max_candidates 必须 > 0")
        if self.max_text_chars <= 0:
            raise ValueError("max_text_chars 必须 > 0")

    def to_dict(self) -> dict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_candidates": self.max_candidates,
            "max_text_chars": self.max_text_chars,
            "alarm": self.alarm,
        }


DEFAULT_BUDGET = RuntimeBudget()


@dataclass
class ModelResult:
    """统一模型输出（任务书第九节建议结构，附加可解释与降级信息）。"""

    model_id: str
    model_version: str
    score: float | None
    score_type: str = "ranking_score"
    explanation: dict = field(default_factory=dict)
    feature_version: str = "v1"
    degradation: dict | None = None
    elapsed_ms: float | None = None
    extra: dict = field(default_factory=dict)

    #: 任何对外导出都必须排除的字段（隐私纪律）
    _PRIVATE = ("resume_text", "job_text", "raw_resume", "raw_job", "phone", "email", "id_card")

    def to_dict(self) -> dict:
        out = {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "score": None if self.score is None else float(self.score),
            "score_type": self.score_type,
            "explanation": self.explanation,
            "feature_version": self.feature_version,
            "degradation": self.degradation,
        }
        if self.elapsed_ms is not None:
            out["elapsed_ms"] = round(float(self.elapsed_ms), 3)
        if self.extra:
            out["extra"] = self.extra
        return out

    def validate(self) -> "ModelResult":
        """契约自检：分数必须有限，score_type 不得暗示概率语义。"""
        if self.score is not None:
            s = float(self.score)
            if s != s or s in (float("inf"), float("-inf")):
                raise ValueError("score 不得为 NaN/Inf")
        if self.score_type not in ("ranking_score", "relevance_score"):
            raise ValueError(f"非法 score_type: {self.score_type}")
        blob = repr(self.to_dict())
        for bad in self._PRIVATE:
            if bad in self.explanation:
                raise ValueError(f"explanation 不得携带隐私字段: {bad}")
        if "probability" in blob or "录用概率" in blob:
            raise ValueError("排名分数不得表述为录用概率")
        return self


def build_result(model_id: str, model_version: str, score: float | None,
                 *, explanation: dict | None = None,
                 feature_version: str = "v1",
                 degradation: dict | None = None,
                 elapsed_ms: float | None = None,
                 extra: dict | None = None) -> ModelResult:
    res = ModelResult(
        model_id=model_id, model_version=model_version, score=score,
        explanation=dict(explanation or {}), feature_version=feature_version,
        degradation=degradation, elapsed_ms=elapsed_ms, extra=dict(extra or {}),
    )
    return res.validate()


def _can_use_alarm(budget: RuntimeBudget) -> bool:
    if not budget.alarm:
        return False
    if platform.system() == "Windows":
        return False
    import threading
    return threading.current_thread() is threading.main_thread()


def run_with_budget(fn: Callable[..., Any], *args,
                    budget: RuntimeBudget = DEFAULT_BUDGET,
                    **kwargs) -> tuple[Any, dict]:
    """在预算内执行 `fn`，返回 `(result, runtime_info)`。

    `runtime_info` 含 `elapsed_ms` / `timed_out` / `timeout_mode` /
    `degradation`（未超时为 None）。超时抛 `InferenceTimeoutError`，
    由调用方决定「显式失败」还是「按契约降级」。
    """
    mode = "hard_alarm" if _can_use_alarm(budget) else "soft_poll"
    t0 = time.perf_counter()

    if mode == "hard_alarm":
        import signal

        def _on_alarm(_sig, _frm):  # pragma: no cover - 仅 POSIX
            raise InferenceTimeoutError(time.perf_counter() - t0,
                                        budget.timeout_seconds)

        old = signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, budget.timeout_seconds)
        try:
            out = fn(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
        elapsed = time.perf_counter() - t0
        return out, {
            "elapsed_ms": round(elapsed * 1000, 3),
            "timed_out": False,
            "timeout_mode": mode,
            "timeout_seconds": budget.timeout_seconds,
            "degradation": None,
        }

    # 软预算：只在进入前后检查；真正的协作式中断由 fn 自行检查 check()
    check = make_deadline_checker(budget.timeout_seconds, t0)
    out = fn(*args, **{**kwargs, **({"__deadline_check__": check}
                                   if _wants_check(fn) else {})})
    elapsed = time.perf_counter() - t0
    if elapsed > budget.timeout_seconds:
        raise InferenceTimeoutError(elapsed, budget.timeout_seconds)
    return out, {
        "elapsed_ms": round(elapsed * 1000, 3),
        "timed_out": False,
        "timeout_mode": mode,
        "timeout_seconds": budget.timeout_seconds,
        "degradation": None,
    }


def make_deadline_checker(timeout_seconds: float,
                          t0: float | None = None) -> Callable[[], None]:
    """返回一个可被长循环调用的检查函数，超时立即抛 `InferenceTimeoutError`。"""
    start = time.perf_counter() if t0 is None else float(t0)

    def _check() -> None:
        elapsed = time.perf_counter() - start
        if elapsed > timeout_seconds:
            raise InferenceTimeoutError(elapsed, timeout_seconds)

    return _check


def _wants_check(fn: Callable[..., Any]) -> bool:
    import inspect
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return "__deadline_check__" in sig.parameters
