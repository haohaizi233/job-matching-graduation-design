# -*- coding: utf-8 -*-
"""E2E 用「远程模拟 Provider 适配器」（仅测试注入，生产代码不 import）。

与 tests/phase8a/fake_provider.py 的区别：
  * phase8a 的 FakeOAuthProvider 在**进程内**脚本化模拟（单测/集成测试用）；
  * 本模块走**真实 HTTP** 访问 tests/e2e/fake_oauth_server.py 起的模拟授权服务器，
    因此浏览器可以真实跳转授权页、真实点击「同意/拒绝」，整条链路只替换
    「外部平台」这一个外部依赖。

它实现与 wechat/qq/weibo 完全一致的 `OAuthProvider` 协议（含错误分类、
资料缺失容忍、身份完整性校验），业务层无从分辨。
"""
from __future__ import annotations

from urllib.parse import urlencode

from job_matching.service.oauth.exceptions import (InvalidIdentity,
                                                   TokenExchangeFailed)
from job_matching.service.oauth.schemas import OAuthIdentity, OAuthTokenResponse


class RemoteFakeProvider:
    """HTTP 版模拟 Provider（provider_id 由注入决定：wechat / qq / weibo）。"""

    supports_pkce = False               # 与真实三家一致（契约未确认前不启用）
    identity_without_profile_allowed = True
    scope = "fake_profile"

    def __init__(self, *, provider_id: str, label: str, client_id: str,
                 client_secret: str, fake_base: str, http):
        self.provider_id = provider_id
        self.label = label
        self.client_id = client_id
        self._client_secret = client_secret
        self._base = fake_base.rstrip("/")
        self._http = http

    # ---------------------------------------------------------- 协议
    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": self.scope,
            "provider": self.provider_id,
        }
        return f"{self._base}/authorize?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self._client_secret,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        payload = self._http.post_form_json(f"{self._base}/oauth/token", data=data)
        if payload.get("error") or not payload.get("access_token"):
            # 真实平台同样以错误字段表达 code 无效/已消费/redirect_uri 不匹配
            raise TokenExchangeFailed(
                f"模拟平台拒绝换取 access_token：{payload.get('error')}",
                {"provider": self.provider_id})
        return OAuthTokenResponse(
            provider=self.provider_id,
            client_id=self.client_id,
            access_token=str(payload["access_token"]),
            token_type=str(payload.get("token_type") or "bearer"),
            expires_in=int(payload["expires_in"]) if payload.get("expires_in") else None,
            raw_subject=(str(payload["subject"]) if payload.get("subject") else None),
            raw={},
        )

    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        # subject 以 code 换 token 时服务端核验的值为准（微信 openid / 微博 uid 语义）；
        # 资料接口只是展示信息：失败不影响已核验身份（profile_fetched=False）。
        subject = str(token.raw_subject or "").strip()
        display_name = None
        avatar_url = None
        union_id = None
        profile_fetched = False
        try:
            info = self._http.get_json(
                f"{self._base}/oauth/userinfo",
                params={"access_token": token.access_token})
            api_subject = str(info.get("subject") or "").strip()
            if api_subject and subject and api_subject != subject:
                # 身份串号必须阻断（与真实适配器同一纪律）
                raise InvalidIdentity("模拟平台身份标识前后不一致，拒绝关联",
                                      {"provider": self.provider_id})
            subject = subject or api_subject
            union_id = str(info["union_id"]) if info.get("union_id") else None
            display_name = (str(info["display_name"])[:64]
                            if info.get("display_name") else None)
            avatar_url = (str(info["avatar_url"])[:512]
                          if info.get("avatar_url") else None)
            profile_fetched = True
        except InvalidIdentity:
            raise
        except Exception:  # noqa: BLE001 - 资料读取失败不影响已核验身份（契约允许）
            profile_fetched = False
        if not subject:
            raise InvalidIdentity("模拟平台未返回稳定的 subject",
                                  {"provider": self.provider_id})
        return OAuthIdentity(
            provider=self.provider_id,
            client_id=self.client_id,
            subject=subject,
            union_id=union_id,
            display_name=display_name,
            avatar_url=avatar_url,
            email=None,                 # 与真实三家一致：不提供可信邮箱
            email_verified=False,
            profile_fetched=profile_fetched,
        )
