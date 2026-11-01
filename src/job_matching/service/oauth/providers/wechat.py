# -*- coding: utf-8 -*-
"""微信开放平台 · PC 网站应用扫码登录适配器（qrconnect + snsapi_login）。

流程（唯一合法形态：**开放平台网站应用**扫码授权）：
  二维码授权 → code → sns/oauth2/access_token → openid（+ 可用时 unionid）
  → sns/userinfo（资料可选）→ OAuthIdentity

纪律：
  * **不得**混入公众号网页授权（sns/oauth2/authorize + snsapi_userinfo）
    或小程序 wx.login()；后续如需支持，另建独立 Provider 类型/配置扩展；
  * subject = openid（经 code 换 token 服务端核验）；昵称/头像永不参与身份识别；
  * unionid 仅在响应真实携带时采用（与开放平台账号绑定关系有关），
    缺失 unionid 不影响登录；
  * errcode/errmsg 逐类映射：code 无效/已消费、access_token 失败、
    权限不足、频率限制、系统繁忙；用户拒绝授权由回调 error=access_denied 表达。

官方端点（受控常量，禁止请求侧传入）：
  https://open.weixin.qq.com/connect/qrconnect
  https://api.weixin.qq.com/sns/oauth2/access_token
  https://api.weixin.qq.com/sns/userinfo

PROVIDER_VERIFICATION_PENDING（官方文档未在本轮可核实范围内确认，不虚构）：
  * PKCE（code_challenge/code_challenge_method）参数在网站扫码流程是否被接受；
  * unionid 返回的前置绑定条件需在真实开放平台账号侧核对。
"""
from __future__ import annotations

from urllib.parse import urlencode

from .base import BaseOAuthProvider
from ..exceptions import (IdentityIntegrityError, InvalidIdentity,
                          ProviderProtocolError, ProviderUnavailable,
                          TokenExchangeFailed)
from ..schemas import OAuthIdentity, OAuthTokenResponse

AUTH_URL = "https://open.weixin.qq.com/connect/qrconnect"
TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"
DEFAULT_SCOPE = "snsapi_login"

# errcode 映射（只登记官方公开错误码的语义，不虚构）
_CODE_REPLAY_OR_INVALID = {40029, 40163, 40013, 40125, 40001, 42001}
_PROVIDER_BUSY = {-1, 45002, 45011, 45009}


class WeChatProvider(BaseOAuthProvider):
    provider_id = "wechat"
    label = "微信"
    supports_pkce = False       # PROVIDER_VERIFICATION_PENDING
    scope = DEFAULT_SCOPE

    # ---------------------------------------------------------- 授权 URL
    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        if not state:
            raise ValueError("state 不得为空")
        params = {
            "appid": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
        }
        # 微信约定授权入口尾部携带 #wechat_redirect
        return f"{AUTH_URL}?{urlencode(params)}#wechat_redirect"

    # ---------------------------------------------------------- code 换 token
    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        if not code:
            raise TokenExchangeFailed("微信回调缺少 code")
        payload = self._http.get_json(
            TOKEN_URL,
            params={"appid": self.client_id, "secret": self._client_secret,
                    "code": code, "grant_type": "authorization_code"})
        self._raise_wechat_error(payload, TOKEN_URL, where="exchange")

        access_token = self._require(payload.get("access_token"), "access_token", TOKEN_URL)
        openid = self._require(payload.get("openid"), "openid", TOKEN_URL)
        return OAuthTokenResponse(
            provider=self.provider_id,
            client_id=self.client_id,
            access_token=str(access_token),
            token_type=str(payload.get("token_type") or "bearer"),
            expires_in=_as_int(payload.get("expires_in")),
            refresh_token=payload.get("refresh_token"),
            scope=payload.get("scope"),
            raw_subject=str(openid),
            raw={"openid": str(openid),
                 "unionid": (str(payload["unionid"])
                             if payload.get("unionid") else None)},
        )

    # ---------------------------------------------------------- 身份
    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        openid = token.raw_subject or token.raw.get("openid")
        if not openid:
            raise InvalidIdentity("微信未返回 openid")
        unionid = token.raw.get("unionid")
        display_name = None
        avatar_url = None
        profile_fetched = False
        try:
            info = self._http.get_json(
                USERINFO_URL,
                params={"access_token": token.access_token, "openid": openid,
                        "lang": "zh_CN"})
            self._raise_wechat_error(info, USERINFO_URL, where="userinfo")
            # openid 必须与换 token 时一致，否则视为协议异常（防身份串号）
            got_openid = str(info.get("openid") or "")
            if got_openid and got_openid != str(openid):
                raise IdentityIntegrityError(
                    "微信 userinfo 返回的 openid 与授权不一致")
            display_name = _clip(info.get("nickname"))
            avatar_url = _clip(info.get("headimgurl"), 512)
            unionid = unionid or (str(info["unionid"]) if info.get("unionid") else None)
            profile_fetched = True
        except IdentityIntegrityError:
            raise        # 身份串号必须阻断
        except Exception:  # noqa: BLE001 - 资料读取失败不影响已核验身份（契约允许）
            profile_fetched = False

        return OAuthIdentity(
            provider=self.provider_id,
            client_id=self.client_id,
            subject=str(openid),
            union_id=unionid,
            display_name=display_name,
            avatar_url=avatar_url,
            email=None,                 # 微信网站扫码流程不提供可信邮箱
            email_verified=False,
            profile_fetched=profile_fetched,
        )

    # ---------------------------------------------------------- 错误映射
    def _raise_wechat_error(self, payload: dict, url: str, *, where: str) -> None:
        errcode = payload.get("errcode")
        if errcode in (None, 0):
            return
        errmsg = str(payload.get("errmsg") or "")[:120]
        code = int(errcode)
        if code in _PROVIDER_BUSY:
            raise ProviderUnavailable(
                f"微信接口繁忙/受限（errcode={code}）@ {where}", )
        if code in _CODE_REPLAY_OR_INVALID:
            raise TokenExchangeFailed(
                f"微信授权码或凭据无效（errcode={code}）@ {where}")
        raise TokenExchangeFailed(
            f"微信接口返回错误（errcode={code}, errmsg={errmsg}）@ {where}")


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
