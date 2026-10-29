# -*- coding: utf-8 -*-
"""业务服务类型化配置（Phase5-1A 集中配置管理）。

目标：把散落在 api.py / text_extract.py / model_registry.py 的运行参数集中到
**单一类型化配置**，支持环境变量覆盖，禁止写死本机绝对路径。

约定：
  * `ServiceSettings.from_env()` 读取 `JM_*` 环境变量，缺省即开发环境默认值；
  * `to_config_dict()` 输出与历史 `Services.config` 兼容的键（不删除、不改名），
    新增键只做加法，保证既有 API 消费者与测试不受影响；
  * 部署边界：`deployment_scope=local_dev_only` 表示**无认证、仅本地开发/演示**。
    任何外网部署必须先接入认证与网关级防护，并把 `JM_REQUIRE_AUTH=1` 打开，
    否则视为配置错误（见 docs/architecture/phase5-1a-dependency-rules.md）。

环境三分（见 docs/architecture/phase5-1a-target-state.md）：
  * Training Environment          —— 历史训练与实验复现（environment.yml，冻结不动）；
  * Serving Environment           —— FastAPI 业务推理（environment-service.yml）；
  * Legacy Model Compatibility    —— 旧 checkpoint 兼容验证（独立环境，仅必要时启用）。
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core import ROOT

# 与 api.py 历史默认值保持一致（不得悄悄改变既有行为）
DEFAULT_MATCHING_RUN_DIR = ("models/matching/ridge/double_cold/"
                            "ridge-double_cold-final-20261028-203750")
DEFAULT_DEPLOYMENT_NOTE = ("local_dev_only（无认证；外网部署必须先加认证与请求限制）")


def _env_bool(env: dict, key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_int(env: dict, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError as e:
        raise ValueError(f"配置 {key} 必须是整数，实际为 {raw!r}") from e


def _env_str(env: dict, key: str, default: str) -> str:
    raw = env.get(key)
    return default if raw is None or str(raw).strip() == "" else str(raw).strip()


@dataclass(frozen=True)
class ServiceSettings:
    """服务运行参数（只读配置对象，可整体替换 -> 测试可注入）。"""

    # --- 环境与部署边界 ---
    api_env: str = "dev"                     # dev | staging | prod
    deployment_scope: str = DEFAULT_DEPLOYMENT_NOTE
    require_auth: bool = False               # 无认证实现；外网部署必须 True（并在网关侧鉴权）
    log_level: str = "INFO"

    # --- 请求边界 ---
    max_request_bytes: int = 8 * 1024 * 1024     # JSON 请求体上限（解析前检查）
    max_base64_chars: int = 5_600_000            # Base64 字符串上限（≈4MB 解码后）
    max_upload_bytes: int = 4 * 1024 * 1024      # 解码后文件上限
    max_text_chars: int = 200_000                # 解析后文本上限
    max_jobs: int = 200                          # 批量岗位上限
    rate_limit_per_minute: int = 300             # 单客户端每分钟上限（仅单进程有效）
    inference_timeout_ms: int = 30_000           # 推理时间预算

    # --- 模型 ---
    model_dir: str = "models"
    matching_run_dir: str | None = DEFAULT_MATCHING_RUN_DIR
    education_run_dir: str | None = None
    allow_research_models: bool = True           # 是否允许 research_only 模型做诊断
    allow_baseline_fallback: bool = True         # 是否允许降级到启发式 Baseline

    # --- 其它 ---
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "ServiceSettings":
        e = dict(os.environ if env is None else env)
        return cls(
            api_env=_env_str(e, "JM_API_ENV", "dev"),
            deployment_scope=_env_str(e, "JM_DEPLOYMENT_SCOPE", DEFAULT_DEPLOYMENT_NOTE),
            require_auth=_env_bool(e, "JM_REQUIRE_AUTH", False),
            log_level=_env_str(e, "JM_LOG_LEVEL", "INFO"),
            max_request_bytes=_env_int(e, "JM_MAX_REQUEST_BYTES", 8 * 1024 * 1024),
            max_base64_chars=_env_int(e, "JM_MAX_BASE64_CHARS", 5_600_000),
            max_upload_bytes=_env_int(e, "JM_MAX_UPLOAD_BYTES", 4 * 1024 * 1024),
            max_text_chars=_env_int(e, "JM_MAX_TEXT_CHARS", 200_000),
            max_jobs=_env_int(e, "JM_MAX_JOBS", 200),
            rate_limit_per_minute=_env_int(e, "JM_RATE_LIMIT_PER_MINUTE", 300),
            inference_timeout_ms=_env_int(e, "JM_INFERENCE_TIMEOUT_MS", 30_000),
            model_dir=_env_str(e, "JM_MODEL_DIR", "models"),
            matching_run_dir=_env_str(e, "JM_MATCHING_RUN_DIR", DEFAULT_MATCHING_RUN_DIR) or None,
            education_run_dir=_env_str(e, "JM_EDUCATION_RUN_DIR", "") or None,
            allow_research_models=_env_bool(e, "JM_ALLOW_RESEARCH_MODELS", True),
            allow_baseline_fallback=_env_bool(e, "JM_ALLOW_BASELINE_FALLBACK", True),
        )

    # ---------------------------------------------------------- 兼容输出
    def to_config_dict(self) -> dict:
        """输出历史 Services.config 键 + 新增键（只加不减）。"""
        d = asdict(self)
        d.pop("extra", None)
        out = dict(d)
        out.update({
            "api_version": "v1",
            # 历史键名保留（api.py / 测试依赖）
            "max_jobs": self.max_jobs,
            "max_request_bytes": self.max_request_bytes,
            "max_base64_chars": self.max_base64_chars,
            "max_upload_bytes": self.max_upload_bytes,
            "max_text_chars": self.max_text_chars,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "deployment": self.deployment_scope,
        })
        return out

    def resolve_model_dir(self) -> Path:
        """模型目录解析为绝对路径（相对路径相对项目根，禁止写死本机绝对路径）。"""
        p = Path(self.model_dir)
        return p if p.is_absolute() else (ROOT / p)

    def check_deployment_safety(self) -> list[str]:
        """外网部署前的安全检查（未通过项必须阻断发布，不得口头宣称生产就绪）。"""
        problems: list[str] = []
        if self.api_env in ("prod", "production", "staging") and not self.require_auth:
            problems.append("外网/正式环境必须启用认证（JM_REQUIRE_AUTH=1 且网关侧鉴权）")
        if self.api_env in ("prod", "production", "staging") and self.allow_research_models:
            problems.append("正式环境不得启用 research_only 模型（JM_ALLOW_RESEARCH_MODELS=0）")
        if self.api_env in ("prod", "production", "staging") and "local_dev_only" in self.deployment_scope:
            problems.append("deployment_scope 仍为 local_dev_only，未声明正式部署边界")
        return problems

    def assert_deployment_safe(self) -> None:
        """P1-09：production / staging 启动前的强制门禁（未通过即拒绝启动）。

        在没有完整认证安全边界前，不得以生产模式启动未受保护的旧业务端点。
        """
        env = str(self.api_env or "").strip().lower()
        if env not in ("prod", "production", "staging"):
            return
        problems = self.check_deployment_safety()
        if problems:
            raise ValueError("部署安全门禁未通过，拒绝以 production/staging 启动：" +
                             "；".join(problems))
