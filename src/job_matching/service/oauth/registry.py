# -*- coding: utf-8 -*-
"""OAuth Provider 注册表（Phase8-A / M1.4）。

安全约束：
  * 只允许白名单 Provider（wechat / qq / weibo），注册时强校验；
  * 拒绝任意 Provider 名、动态 URL、未经审计的自定义 Provider；
  * 未注册/未配置/已禁用三种状态返回不同 reason_code，绝不给"假可用"。
"""
from __future__ import annotations

from ..errors import ServiceError
from .config import PROVIDER_LABELS, PROVIDER_WHITELIST, OAuthSettings
from .exceptions import ProviderDisabled, ProviderNotConfigured
from .http_client import OAuthHttpClient
from .providers import build_provider

STATUS_DISABLED = "disabled"
STATUS_PENDING = "configured_pending_verification"
STATUS_AVAILABLE = "available"


class OAuthProviderRegistry:
    """Provider 实例注册表（白名单 + 状态查询）。"""

    def __init__(self, *, settings: OAuthSettings,
                 allowed_ids: tuple[str, ...] = PROVIDER_WHITELIST):
        self._settings = settings
        self._allowed = tuple(allowed_ids)
        self._providers: dict[str, object] = {}

    # ---------------------------------------------------------- 注册
    def register(self, provider) -> None:
        pid = getattr(provider, "provider_id", "")
        if pid not in self._allowed:
            raise ValueError(f"拒绝注册非白名单 Provider: {pid!r}")
        self._providers[pid] = provider

    # ---------------------------------------------------------- 查询
    def get(self, provider_id: str):
        """取适配器实例；未配置/已禁用抛对应 OAUTH_* 错误（绝不静默降级）。"""
        pid = str(provider_id or "").strip().lower()
        if pid not in self._allowed:
            raise ProviderNotConfigured(f"未知或未白名单的 Provider: {pid!r}",
                                        {"provider": pid})
        inst = self._providers.get(pid)
        if inst is not None:
            return inst
        status, reason = self.get_status(pid)
        if reason == "OAUTH_PROVIDER_DISABLED":
            raise ProviderDisabled(f"Provider {pid} 已禁用", {"provider": pid})
        raise ProviderNotConfigured(f"Provider {pid} 尚未配置", {"provider": pid})

    def list(self) -> list:
        return [self._providers[pid] for pid in self._allowed
                if pid in self._providers]

    def allowed_ids(self) -> tuple[str, ...]:
        return self._allowed

    def get_status(self, provider_id: str) -> tuple[str, str]:
        pid = str(provider_id or "").strip().lower()
        if pid not in self._allowed:
            return STATUS_DISABLED, "OAUTH_PROVIDER_NOT_CONFIGURED"
        return self._settings.provider_status(pid)

    def describe_all(self) -> list[dict]:
        """API 输出形态（绝不含 client_secret）。"""
        out = []
        for pid in self._allowed:
            status, reason = self.get_status(pid)
            out.append({
                "id": pid,
                "label": PROVIDER_LABELS.get(pid, pid),
                "enabled": status in (STATUS_PENDING, STATUS_AVAILABLE),
                "status": status,
                "reason_code": reason or None,
            })
        return out


def build_registry(settings: OAuthSettings, http: OAuthHttpClient | None = None,
                   *, allowed_ids: tuple[str, ...] = PROVIDER_WHITELIST,
                   provider_factory=None) -> OAuthProviderRegistry:
    """按配置构建注册表：只有"已启用 + 凭据齐全"的 Provider 才会真正注册实例。

    `provider_factory(provider_id, cfg, http)` 可注入（测试用 Fake Provider 替换）。
    """
    registry = OAuthProviderRegistry(settings=settings, allowed_ids=allowed_ids)
    factory = provider_factory or (lambda pid, cfg, h: build_provider(pid, cfg, h))
    for pid in allowed_ids:
        cfg = settings.provider(pid)
        if cfg is None:
            continue
        status, _reason = cfg.status(global_enabled=settings.enabled)
        if status == STATUS_DISABLED:
            continue
        if not settings.public_base_url:
            # 无公开基址时无法解析可信回调，视为未配置（安全优先）
            continue
        registry.register(factory(pid, cfg, http))
    return registry
