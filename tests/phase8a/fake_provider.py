# -*- coding: utf-8 -*-
"""FakeOAuthProvider（Phase8-A / M9）：**仅测试环境**可导入/注入的模拟身份提供方。

纪律：
  * 本文件只存在于 tests/ 下，生产代码（src/job_matching）**不 import** 本模块；
  * 生产代码没有任何请求级/环境级开关能打开 Fake Provider；
  * 它实现与真实 Provider 完全一致的 `OAuthProvider` 协议，只替换"外部平台"，
    本站业务链路（事务/票据/账号/会话）全部走真实实现。

可模拟行为（behavior）：
  ok               正常授权成功
  access_denied    用户取消（由回调 error 参数模拟，见测试）
  code_expired     code 换 token 失败（TokenExchangeFailed）
  token_unavailable access_token 不可用（TokenExchangeFailed）
  identity_missing 用户身份缺失（InvalidIdentity）
  timeout          API 超时（ProviderTimeout）
  http_429         API 429（ProviderHttpError）
  http_500         API 500（ProviderHttpError）
  malformed        响应异常（ProviderProtocolError）
  profile_fail     UID/OpenID 已核验但资料读取失败（身份仍有效，昵称/头像缺失）
"""
from __future__ import annotations

from urllib.parse import urlencode

from job_matching.service.oauth.exceptions import (InvalidIdentity,
                                                   ProviderHttpError,
                                                   ProviderProtocolError,
                                                   ProviderTimeout,
                                                   TokenExchangeFailed)
from job_matching.service.oauth.schemas import OAuthIdentity, OAuthTokenResponse

AUTH_URL = "https://fake.oauth.test/authorize"


class FakeOAuthProvider:
    """脚本化 OAuth Provider（协议兼容 wechat/qq/weibo 的抽象）。"""

    provider_id = "fake"
    label = "模拟平台（仅测试）"
    supports_pkce = True          # 覆盖 PKCE 代码路径（真实三家按契约为 False）
    identity_without_profile_allowed = True

    def __init__(self, *, client_id: str = "fake-appid",
                 client_secret: str = "FAKE_SECRET_FOR_TESTS", http=None,
                 behavior: str = "ok"):
        self.client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self.behavior = behavior
        self._codes: dict[str, dict] = {}
        self.used_codes: set[str] = set()
        self.exchange_calls: list[dict] = []

    # ---------------------------------------------------------- 测试脚本接口
    def register_code(self, code: str, identity: OAuthIdentity,
                      *, verifier: str | None = None,
                      behavior: str | None = None) -> None:
        self._codes[code] = {"identity": identity, "verifier": verifier,
                             "behavior": behavior}

    def set_behavior(self, behavior: str) -> None:
        self.behavior = behavior

    # ---------------------------------------------------------- 协议
    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        params = {"client_id": self.client_id, "redirect_uri": redirect_uri,
                  "response_type": "code", "state": state,
                  "scope": "fake_profile"}
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        self.exchange_calls.append({"code": code, "redirect_uri": redirect_uri,
                                    "code_verifier": code_verifier})
        rec = self._codes.get(code)
        behavior = (rec or {}).get("behavior") or self.behavior
        if behavior == "timeout":
            raise ProviderTimeout("模拟 Provider 超时")
        if behavior == "http_429":
            raise ProviderHttpError("模拟 Provider 429", status_code=429)
        if behavior == "http_500":
            raise ProviderHttpError("模拟 Provider 500", status_code=500)
        if behavior == "malformed":
            raise ProviderProtocolError("模拟响应格式非法")
        if behavior == "code_expired":
            raise TokenExchangeFailed("模拟 code 过期")
        if behavior == "token_unavailable":
            raise TokenExchangeFailed("模拟 access_token 不可用")
        if rec is None or code in self.used_codes:
            # 真实平台同样对已消费 code 报错（重放不可成功）
            raise TokenExchangeFailed("模拟 code 无效或已被消费")
        if rec.get("verifier") and rec["verifier"] != code_verifier:
            raise TokenExchangeFailed("模拟 PKCE 校验失败")
        self.used_codes.add(code)
        identity: OAuthIdentity = rec["identity"]
        return OAuthTokenResponse(
            provider=self.provider_id, client_id=self.client_id,
            access_token=f"fake-at-{code}", token_type="bearer", expires_in=7200,
            raw_subject=identity.subject,
            raw={"subject": identity.subject, "behavior": behavior})

    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        behavior = (token.raw or {}).get("behavior") or self.behavior
        if behavior == "identity_missing":
            raise InvalidIdentity("模拟身份缺失")
        code = (token.access_token or "").replace("fake-at-", "", 1)
        rec = self._codes.get(code)
        if rec is None:
            raise InvalidIdentity("模拟身份不存在")
        identity: OAuthIdentity = rec["identity"]
        if behavior == "profile_fail":
            return OAuthIdentity(
                provider=identity.provider, client_id=identity.client_id,
                subject=identity.subject, union_id=identity.union_id,
                display_name=None, avatar_url=None,
                email=None, email_verified=False, profile_fetched=False)
        return identity


def make_identity(subject: str = "fake-subject-1", *,
                  provider: str = "fake", client_id: str = "fake-appid",
                  display_name: str | None = "合成昵称",
                  avatar_url: str | None = "https://img.fake.test/a.png",
                  email: str | None = None,
                  email_verified: bool = False,
                  union_id: str | None = None) -> OAuthIdentity:
    return OAuthIdentity(provider=provider, client_id=client_id, subject=subject,
                         union_id=union_id, display_name=display_name,
                         avatar_url=avatar_url, email=email,
                         email_verified=email_verified, profile_fetched=True)
