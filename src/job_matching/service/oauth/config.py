# -*- coding: utf-8 -*-
"""OAuth 类型化配置（Phase8-A / M8）。

配置只在**配置构建边界**读取环境变量（`OAuthSettings.from_env`），业务方法内禁止
改写 `os.environ`；测试通过显式构造 `OAuthSettings` / `OAuthProviderConfig` 注入。

环境变量命名（与 .env.example 一一对应，见 docs/oauth/environment-configuration.md）：

  JM_OAUTH_ENABLED=false              全局开关（false 时任何 Provider 不发起真实授权）
  JM_OAUTH_PUBLIC_BASE_URL=           后端对外公开 HTTPS 地址（回调域名基址）
  JM_OAUTH_FRONTEND_ORIGIN=           前端允许的 Origin（逗号分隔可多个，首个为主）
  JM_OAUTH_STATE_TTL_SECONDS=300      授权事务 TTL
  JM_OAUTH_TICKET_TTL_SECONDS=60      一次性登录票据 TTL
  JM_OAUTH_<PROVIDER>_ENABLED=false   单平台开关（PROVIDER ∈ WECHAT / QQ / WEIBO）
  JM_OAUTH_<PROVIDER>_CLIENT_ID=      AppID / App Key / client_id
  JM_OAUTH_<PROVIDER>_CLIENT_SECRET=  AppSecret / App Key Secret（只在服务端）
  JM_OAUTH_<PROVIDER>_REDIRECT_URI=   回调地址（可留空 -> 由 PUBLIC_BASE_URL 派生）
  JM_OAUTH_<PROVIDER>_VERIFIED=false  **真实平台联调通过后**人工置 true（才显示 available）

状态语义（三态，绝不把"有配置"当"已验收"）：
  disabled                          未启用 / 未配置（reason_code 说明原因）
  configured_pending_verification   配置齐全但**未真实联调**（默认落点）
  available                         显式 VERIFIED=true（真实扫码登录成功后人工登记）
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# 回调路径由受控代码决定，禁止请求体传入任意回调地址（SSRF / 开放重定向防线）
OAUTH_CALLBACK_PATH = "/api/v1/auth/oauth/{provider}/callback"
PROVIDER_WHITELIST: tuple[str, ...] = ("wechat", "qq", "weibo")
DEFAULT_RETURN_PATH = "/dashboard"

# Provider 展示名（前端也有一份文案，此处为 API 权威值）
PROVIDER_LABELS = {"wechat": "微信", "qq": "QQ", "weibo": "微博"}

_STATE_TTL_DEFAULT = 300
_TICKET_TTL_DEFAULT = 60
_STATE_TTL_MAX = 900
_TICKET_TTL_MAX = 300


def _env_bool(env: dict, key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_int(env: dict, key: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        val = int(str(raw).strip())
    except ValueError as e:
        raise ValueError(f"配置 {key} 必须是整数，实际为 {raw!r}") from e
    return max(lo, min(hi, val))


def _env_str(env: dict, key: str, default: str = "") -> str:
    raw = env.get(key)
    return default if raw is None else str(raw).strip()


@dataclass(frozen=True)
class OAuthProviderConfig:
    """单个第三方平台配置（Secret 只活在服务端内存/配置，绝不进响应与日志）。"""

    provider_id: str
    label: str
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    verified: bool = False          # 真实平台联调通过后人工置位（M11 纪律）
    extra: dict = field(default_factory=dict)

    @property
    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def resolve_redirect_uri(self, public_base_url: str) -> str:
        """回调地址解析：显式配置优先，否则由公开基址派生固定路径。

        **不接受**请求侧传入的回调地址；派生/校验都基于受控配置。
        """
        if self.redirect_uri:
            return self.redirect_uri
        base = (public_base_url or "").rstrip("/")
        if not base:
            return ""
        return base + OAUTH_CALLBACK_PATH.format(provider=self.provider_id)

    def status(self, *, global_enabled: bool) -> tuple[str, str]:
        """返回 (status, reason_code)。reason_code 仅在非 available 时有意义。"""
        if not global_enabled or not self.enabled:
            return "disabled", "OAUTH_PROVIDER_DISABLED"
        if not self.has_credentials or not self.client_id.strip():
            return "disabled", "OAUTH_PROVIDER_NOT_CONFIGURED"
        return ("available" if self.verified else "configured_pending_verification"), ""


@dataclass(frozen=True)
class OAuthSettings:
    """OAuth 全局配置（只读；可整体替换 -> 测试可注入）。"""

    enabled: bool = False
    public_base_url: str = ""
    frontend_origins: tuple[str, ...] = ()
    state_ttl_seconds: int = _STATE_TTL_DEFAULT
    ticket_ttl_seconds: int = _TICKET_TTL_DEFAULT
    api_env: str = "dev"
    cookie_secure: bool = False
    providers: dict = field(default_factory=dict)   # provider_id -> OAuthProviderConfig

    # ---------------------------------------------------------- 构建
    @classmethod
    def from_env(cls, env: dict | None = None) -> "OAuthSettings":
        e = dict(os.environ if env is None else env)
        origins_raw = _env_str(e, "JM_OAUTH_FRONTEND_ORIGIN")
        origins = tuple(o.strip().rstrip("/") for o in origins_raw.split(",") if o.strip())
        providers: dict = {}
        for pid in PROVIDER_WHITELIST:
            key = pid.upper()
            providers[pid] = OAuthProviderConfig(
                provider_id=pid,
                label=PROVIDER_LABELS[pid],
                enabled=_env_bool(e, f"JM_OAUTH_{key}_ENABLED", False),
                client_id=_env_str(e, f"JM_OAUTH_{key}_CLIENT_ID"),
                client_secret=_env_str(e, f"JM_OAUTH_{key}_CLIENT_SECRET"),
                redirect_uri=_env_str(e, f"JM_OAUTH_{key}_REDIRECT_URI"),
                verified=_env_bool(e, f"JM_OAUTH_{key}_VERIFIED", False),
            )
        base = _env_str(e, "JM_OAUTH_PUBLIC_BASE_URL").rstrip("/")
        return cls(
            enabled=_env_bool(e, "JM_OAUTH_ENABLED", False),
            public_base_url=base,
            frontend_origins=origins,
            state_ttl_seconds=_env_int(e, "JM_OAUTH_STATE_TTL_SECONDS",
                                       _STATE_TTL_DEFAULT, 60, _STATE_TTL_MAX),
            ticket_ttl_seconds=_env_int(e, "JM_OAUTH_TICKET_TTL_SECONDS",
                                        _TICKET_TTL_DEFAULT, 30, _TICKET_TTL_MAX),
            api_env=_env_str(e, "JM_API_ENV", "dev"),
            # HTTPS 部署时 Cookie 必须 Secure；HTTP 本地开发置 False（跨源 localhost 代理）
            cookie_secure=base.lower().startswith("https://"),
            providers=providers,
        )

    @classmethod
    def for_test(cls, *, enabled: bool = True,
                 public_base_url: str = "http://127.0.0.1:8000",
                 frontend_origins: tuple[str, ...] = ("http://127.0.0.1:5173",),
                 state_ttl_seconds: int = _STATE_TTL_DEFAULT,
                 ticket_ttl_seconds: int = _TICKET_TTL_DEFAULT,
                 providers: dict | None = None) -> "OAuthSettings":
        """测试注入入口（不读环境）。默认三家都按"配置齐全但未验收"注入假凭据。"""
        provs = dict(providers) if providers is not None else {
            pid: OAuthProviderConfig(
                provider_id=pid, label=PROVIDER_LABELS[pid], enabled=True,
                client_id=f"test-{pid}-appid", client_secret="test-secret-not-real",
                redirect_uri=public_base_url.rstrip("/") +
                OAUTH_CALLBACK_PATH.format(provider=pid))
            for pid in PROVIDER_WHITELIST
        }
        return cls(enabled=enabled, public_base_url=public_base_url.rstrip("/"),
                   frontend_origins=frontend_origins,
                   state_ttl_seconds=state_ttl_seconds,
                   ticket_ttl_seconds=ticket_ttl_seconds,
                   api_env="test", cookie_secure=False, providers=provs)

    # ---------------------------------------------------------- 查询
    def provider(self, provider_id: str) -> OAuthProviderConfig:
        return self.providers.get(provider_id)

    def provider_status(self, provider_id: str) -> tuple[str, str]:
        cfg = self.providers.get(provider_id)
        if cfg is None:
            return "disabled", "OAUTH_PROVIDER_NOT_CONFIGURED"
        return cfg.status(global_enabled=self.enabled)

    def callback_url(self, provider_id: str) -> str:
        cfg = self.providers.get(provider_id)
        if cfg is None:
            return ""
        return cfg.resolve_redirect_uri(self.public_base_url)

    def is_production_like(self) -> bool:
        return str(self.api_env or "").strip().lower() in ("prod", "production", "staging")

    # ---------------------------------------------------------- 安全门禁
    def check_safety(self) -> list[str]:
        """部署安全检查（未通过项必须阻断启用，不得口头宣称生产就绪）。"""
        problems: list[str] = []
        if not self.enabled:
            return problems
        if not self.public_base_url:
            problems.append("缺少 JM_OAUTH_PUBLIC_BASE_URL（回调域名基址）")
        elif self.is_production_like() and not self.public_base_url.lower().startswith("https://"):
            problems.append("生产/预发环境 OAuth 公开基址必须是 HTTPS")
        if not self.frontend_origins:
            problems.append("缺少 JM_OAUTH_FRONTEND_ORIGIN（前端可信 Origin 白名单）")
        for pid in PROVIDER_WHITELIST:
            cfg = self.providers.get(pid)
            if cfg is None or not cfg.enabled:
                continue
            if not cfg.has_credentials:
                problems.append(f"{pid} 已启用但缺少 client_id/client_secret")
                continue
            cb = cfg.resolve_redirect_uri(self.public_base_url)
            if not cb:
                problems.append(f"{pid} 无法解析回调地址（缺 public_base_url 且未配置 redirect_uri）")
            elif not self._redirect_allowed(cb):
                problems.append(f"{pid} 回调地址不在可信基址内: {self._safe_url(cb)}")
            elif self.is_production_like() and not cb.lower().startswith("https://"):
                problems.append(f"{pid} 生产环境回调地址必须是 HTTPS: {self._safe_url(cb)}")
        return problems

    def _redirect_allowed(self, redirect_uri: str) -> bool:
        """回调地址必须落在公开基址内且路径为固定回调路径（标准 URL 解析，非 startswith）。"""
        try:
            cb = urlsplit(redirect_uri)
            base = urlsplit(self.public_base_url)
        except ValueError:
            return False
        if not cb.scheme or not cb.netloc or not base.scheme or not base.netloc:
            return False
        if (cb.scheme.lower(), cb.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
            return False
        expected = {OAUTH_CALLBACK_PATH.format(provider=p) for p in PROVIDER_WHITELIST}
        return cb.path in expected and not cb.query and not cb.fragment

    @staticmethod
    def _safe_url(url: str) -> str:
        """只回显 scheme://host/path，避免把查询里的敏感内容带进错误/日志。"""
        try:
            p = urlsplit(url)
            return f"{p.scheme}://{p.netloc}{p.path}"
        except ValueError:  # pragma: no cover
            return "<unparseable-url>"
