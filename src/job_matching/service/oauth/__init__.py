# -*- coding: utf-8 -*-
"""Phase8-A 统一 OAuth 2.0 认证基础设施（微信 / QQ / 微博）。

分层（每层单一职责，禁止堆成单文件 oauth.py）：
  config.py              类型化配置（JM_OAUTH_*，只在配置构建边界读环境）
  schemas.py             统一身份/令牌对象（OAuthIdentity / OAuthTokenResponse）
  exceptions.py          OAuth 错误类型（全部挂在已登记的 ServiceError 错误码上）
  security.py            state/摘要/浏览器绑定 Cookie/重定向与 return_path 白名单/PKCE
  http_client.py         受约束的 httpx 客户端（超时/体积上限/错误分类/可注入 Transport）
  registry.py            Provider 注册表（白名单 wechat/qq/weibo，拒绝任意 Provider）
  providers/             微信 / QQ / 微博协议适配器（平台差异只活在这一层）
  transaction_store.py   授权事务（state 摘要、TTL、一次性消费、浏览器绑定）
  ticket_store.py        一次性登录票据（摘要落库、原子消费、重放拒绝）
  identity_repository.py oauth_identities 持久化（唯一约束防重复绑定）
  identity_service.py    账号解析/创建/绑定/解绑（禁止昵称/邮箱自动合并）
  service.py             OAuthService 业务编排（登录 / 绑定 / 票据交换）
  router.py              FastAPI 路由（/api/v1/auth/oauth/*，复用既有信封与错误体）

安全边界（M5）：
  * state / ticket 只存 SHA-256 摘要，明文仅在内存与 HttpOnly Cookie 中流转；
  * Provider Access Token 不进浏览器、不进 URL、不进日志、不做无谓持久化；
  * 本模块不签发 JWT，不改动既有 Bearer 会话体系；
  * Fake Provider 只允许测试代码注入（tests/phase8a），生产无任何请求级开关。
"""
from __future__ import annotations

from .config import (OAUTH_CALLBACK_PATH, OAuthProviderConfig, OAuthSettings)
from .schemas import OAuthIdentity, OAuthTokenResponse

__all__ = [
    "OAUTH_CALLBACK_PATH",
    "OAuthIdentity",
    "OAuthProviderConfig",
    "OAuthSettings",
    "OAuthTokenResponse",
]
