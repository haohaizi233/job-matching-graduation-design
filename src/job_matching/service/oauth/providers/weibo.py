# -*- coding: utf-8 -*-
"""微博开放平台 · 网站 OAuth 2.0 授权登录适配器。

流程：
  api.weibo.com/oauth2/authorize → code → oauth2/access_token（表单 POST）
  → uid（经服务端核验）→ users/show.json（资料可选）→ OAuthIdentity

要点：
  * subject = uid（授权返回、服务端核验的稳定标识），不是昵称、不是头像；
  * 资料读取失败（权限不足/接口下线/令牌权限差异）**不得**导致错误的账号关联：
    uid 已确认即可登录（identity_without_profile_allowed=True），
    昵称/头像缺失只是展示缺失；
  * 是否允许仅以 uid 登录由该 Provider 明确契约控制（本类常量即契约）；
  * 平台错误（error + error_code）逐类映射：code/token 无效、用户取消、权限不足。

官方端点（受控常量）：
  https://api.weibo.com/oauth2/authorize
  https://api.weibo.com/oauth2/access_token
  https://api.weibo.com/2/users/show.json

PROVIDER_VERIFICATION_PENDING：
  * users/show.json 所需权限随应用资质变化（部分接口需额外申请）；
  * PKCE 参数支持情况未获官方明确文档确认（supports_pkce=False）。
"""
from __future__ import annotations

from urllib.parse import urlencode

from .base import BaseOAuthProvider
from ..exceptions import (IdentityIntegrityError, InvalidIdentity,
                          ProviderProtocolError, ProviderUnavailable,
                          TokenExchangeFailed)
from ..schemas import OAuthIdentity, OAuthTokenResponse

AUTH_URL = "https://api.weibo.com/oauth2/authorize"
TOKEN_URL = "https://api.weibo.com/oauth2/access_token"
USER_SHOW_URL = "https://api.weibo.com/2/users/show.json"

# error_code 映射（官方公开错误码的保守登记）
_WEIBO_TOKEN_INVALID = {21314, 21315, 21316, 21317, 21318, 21319, 21327,
                        21332, 21336, 21337}
_WEIBO_ACCESS_DENIED = {21330, 21331, 21332, 21333}
_WEIBO_BUSY = {10006, 10023}


class WeiboProvider(BaseOAuthProvider):
    provider_id = "weibo"
    label = "微博"
    supports_pkce = False       # PROVIDER_VERIFICATION_PENDING
    identity_without_profile_allowed = True
    scope = ""

    # ---------------------------------------------------------- 授权 URL
    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        if not state:
            raise ValueError("state 不得为空")
        params = {"client_id": self.client_id, "redirect_uri": redirect_uri,
                  "response_type": "code", "state": state}
        if self.scope:
            params["scope"] = self.scope
        return f"{AUTH_URL}?{urlencode(params)}"

    # ---------------------------------------------------------- code 换 token
    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        if not code:
            raise TokenExchangeFailed("微博回调缺少 code")
        payload = self._http.post_form_json(TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self._client_secret,
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": redirect_uri})
        self._raise_weibo_error(payload, where="exchange")

        access_token = self._require(payload.get("access_token"), "access_token", TOKEN_URL)
        uid = payload.get("uid")
        if uid is None or str(uid).strip() == "":
            raise ProviderProtocolError("微博 token 响应缺少 uid")
        return OAuthTokenResponse(
            provider=self.provider_id,
            client_id=self.client_id,
            access_token=str(access_token),
            token_type=str(payload.get("token_type") or "bearer"),
            expires_in=_as_int(payload.get("expires_in")),
            refresh_token=(str(payload["refresh_token"])
                           if payload.get("refresh_token") else None),
            scope=(str(payload["scope"]) if payload.get("scope") else None),
            raw_subject=str(uid),
            raw={"uid": str(uid)},
        )

    # ---------------------------------------------------------- 身份
    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        uid = token.raw_subject or token.raw.get("uid")
        if not uid:
            raise InvalidIdentity("微博未返回 uid")
        display_name = None
        avatar_url = None
        profile_fetched = False
        try:
            info = self._http.get_json(USER_SHOW_URL, params={
                "access_token": token.access_token, "uid": uid})
            self._raise_weibo_error(info, where="userinfo")
            got_id = info.get("id") or info.get("idstr")
            if got_id is not None and str(got_id) != str(uid):
                raise IdentityIntegrityError(
                    "微博 users/show 返回的 uid 与授权不一致")
            display_name = _clip(info.get("screen_name"))
            avatar_url = _clip(info.get("avatar_large") or info.get("profile_image_url"), 512)
            profile_fetched = True
        except IdentityIntegrityError:
            raise        # 身份串号必须阻断
        except Exception:  # noqa: BLE001 - 资料失败不影响 uid 已核验（契约允许）
            profile_fetched = False

        return OAuthIdentity(
            provider=self.provider_id,
            client_id=self.client_id,
            subject=str(uid),
            union_id=None,               # 微博 uid 不与微信/QQ 互通
            display_name=display_name,
            avatar_url=avatar_url,
            email=None,                  # 微博资料邮箱未经验证，绝不作为已验证邮箱
            email_verified=False,
            profile_fetched=profile_fetched,
        )

    # ---------------------------------------------------------- 错误映射
    def _raise_weibo_error(self, payload: dict, *, where: str) -> None:
        if "error_code" not in payload and "error" not in payload:
            return
        code_raw = payload.get("error_code")
        try:
            code = int(code_raw)
        except (TypeError, ValueError):
            code = -1
        desc = str(payload.get("error") or payload.get("error_description") or "")[:120]
        if code in _WEIBO_BUSY:
            raise ProviderUnavailable(f"微博接口繁忙/受限（error_code={code}）@ {where}")
        if code in _WEIBO_ACCESS_DENIED:
            raise TokenExchangeFailed(
                f"微博用户取消或拒绝授权（error_code={code}）@ {where}")
        if code in _WEIBO_TOKEN_INVALID or code > 0:
            raise TokenExchangeFailed(
                f"微博授权失败（error_code={code}, {desc}）@ {where}")


def _as_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clip(value, limit: int = 255) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s[:limit] if s else None
