# -*- coding: utf-8 -*-
"""Provider 适配器集合与构造工厂。

工厂只认识白名单内、由受控代码登记的 Provider 类型；
**禁止**按请求传入的字符串/URL 动态 import 或动态构造（SSRF / 任意 Provider 防线）。
"""
from __future__ import annotations

from .base import BaseOAuthProvider, OAuthProvider
from .qq import QQProvider
from .wechat import WeChatProvider
from .weibo import WeiboProvider

# 受控 Provider 表：新增平台必须在此显式登记并走安全评审
PROVIDER_CLASSES: dict[str, type[BaseOAuthProvider]] = {
    "wechat": WeChatProvider,
    "qq": QQProvider,
    "weibo": WeiboProvider,
}

__all__ = ["BaseOAuthProvider", "OAuthProvider", "WeChatProvider", "QQProvider",
           "WeiboProvider", "PROVIDER_CLASSES", "build_provider"]


def build_provider(provider_id: str, cfg, http) -> BaseOAuthProvider:
    """按配置构造适配器实例（未登记的 provider_id 一律拒绝）。"""
    cls = PROVIDER_CLASSES.get(provider_id)
    if cls is None:
        raise ValueError(f"未登记的 Provider: {provider_id}")
    return cls.from_config(cfg, http=http)
