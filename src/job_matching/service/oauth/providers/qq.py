# -*- coding: utf-8 -*-
"""QQ 互联 · 网站应用授权登录适配器。

流程：
  graph.qq.com/oauth2.0/authorize → code → oauth2.0/token（表单串/JSON）
  → oauth2.0/me（OpenID，历史 JSONP）→ user/get_user_info（资料可选）→ OAuthIdentity

QQ 特有难点（全部在本适配器内消化，业务层无感）：
  * 不同接口响应格式不同：token 是 `a=b&c=d` 表单串（`fmt=json` 可用时优先 JSON），
    `/me` 历史上是 JSONP（`callback( {...} );`），资料接口是 JSON 且用 `ret` 表达结果；
  * **JSONP 安全解析**：只做「括号剥离 + json.loads」，禁止 eval()、禁止动态脚本执行；
  * access_token 与 openid 必须经 `/me` 关联校验（oauth_consumer_key = client_id），
    防止拿 A 应用的 openid 当 B 应用身份；
  * 仅凭资料接口返回的昵称不能确认唯一身份（subject 一律取 /me 的 openid）。

官方端点（受控常量）：
  https://graph.qq.com/oauth2.0/authorize
  https://graph.qq.com/oauth2.0/token
  https://graph.qq.com/oauth2.0/me
  https://graph.qq.com/user/get_user_info

PROVIDER_VERIFICATION_PENDING：
  * `fmt=json` 在 token 与 /me 端点的实际可用性随应用资质/版本变化，代码两条路都支持；
  * PKCE 参数支持情况未获官方明确文档确认（supports_pkce=False）。
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlencode

from .base import BaseOAuthProvider
from ..exceptions import (IdentityIntegrityError, InvalidIdentity,
                          ProviderProtocolError, ProviderUnavailable,
                          TokenExchangeFailed)
from ..schemas import OAuthIdentity, OAuthTokenResponse

AUTH_URL = "https://graph.qq.com/oauth2.0/authorize"
TOKEN_URL = "https://graph.qq.com/oauth2.0/token"
ME_URL = "https://graph.qq.com/oauth2.0/me"
USER_INFO_URL = "https://graph.qq.com/user/get_user_info"

# JSONP：`callback( {...} );` / `callback({...})` —— 只识别"标识符 + 括号包裹 JSON"形态
_JSONP_RE = re.compile(r"^\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\((.*)\)\s*;?\s*$", re.DOTALL)

_QQ_BUSY_ERRORS = {100030, 100031, 100032}   # 频率/系统繁忙类（保守登记）
_QQ_TOKEN_ERRORS = {100014, 100015, 100016, 100017, 100018, 100019,
                    100020, 100021, 100022, 100023, 100024, 100025}


class QQProvider(BaseOAuthProvider):
    provider_id = "qq"
    label = "QQ"
    supports_pkce = False       # PROVIDER_VERIFICATION_PENDING
    scope = ""

    # ---------------------------------------------------------- 授权 URL
    def build_authorization_url(self, *, state: str, redirect_uri: str,
                                code_challenge: str | None = None) -> str:
        if not state:
            raise ValueError("state 不得为空")
        params = {"response_type": "code", "client_id": self.client_id,
                  "redirect_uri": redirect_uri, "state": state}
        if self.scope:
            params["scope"] = self.scope
        return f"{AUTH_URL}?{urlencode(params)}"

    # ---------------------------------------------------------- code 换 token
    def exchange_code(self, *, code: str, redirect_uri: str,
                      code_verifier: str | None = None) -> OAuthTokenResponse:
        if not code:
            raise TokenExchangeFailed("QQ 回调缺少 code")
        params = {"grant_type": "authorization_code", "client_id": self.client_id,
                  "client_secret": self._client_secret, "code": code,
                  "redirect_uri": redirect_uri}
        # fmt=json 可用时优先 JSON；失败回退历史表单串格式（两条路都在本适配器内）
        text = self._http.get_text(TOKEN_URL, params={**params, "fmt": "json"})
        data = parse_qq_payload(text, url=TOKEN_URL)
        if "access_token" not in data:
            # 该端点不支持 fmt=json 时会忽略参数照常返回表单串；此处已兼容
            raise _map_qq_error(data, TOKEN_URL, where="exchange")
        access_token = str(self._require(data.get("access_token"), "access_token", TOKEN_URL))

        # /me：OpenID 必须与本应用 client_id 关联（应用级 OpenID 命名空间）
        me_text = self._http.get_text(ME_URL, params={
            "access_token": access_token, "oauth_consumer_key": self.client_id,
            "fmt": "json"})
        me = parse_qq_payload(me_text, url=ME_URL)
        if "openid" not in me:
            raise _map_qq_error(me, ME_URL, where="me")
        openid = str(self._require(me.get("openid"), "openid", ME_URL))
        consumer = str(me.get("client_id") or me.get("oauth_consumer_key") or "")
        if consumer and consumer != str(self.client_id):
            raise IdentityIntegrityError(
                "QQ /me 返回的 client_id 与本应用不一致")

        return OAuthTokenResponse(
            provider=self.provider_id,
            client_id=self.client_id,
            access_token=access_token,
            token_type="bearer",
            expires_in=_as_int(data.get("expires_in")),
            refresh_token=(str(data["refresh_token"])
                           if data.get("refresh_token") else None),
            scope=(str(data["scope"]) if data.get("scope") else None),
            raw_subject=openid,
            raw={"openid": openid},
        )

    # ---------------------------------------------------------- 身份
    def get_identity(self, token: OAuthTokenResponse) -> OAuthIdentity:
        openid = token.raw_subject or token.raw.get("openid")
        if not openid:
            raise InvalidIdentity("QQ 未返回 openid")
        display_name = None
        avatar_url = None
        profile_fetched = False
        try:
            info = self._http.get_json(USER_INFO_URL, params={
                "access_token": token.access_token,
                "oauth_consumer_key": self.client_id, "openid": openid,
                "fmt": "json"})
            ret = int(info.get("ret", -1))
            if ret == 0:
                display_name = _clip(info.get("nickname"))
                avatar_url = _clip(info.get("figureurl_qq_2") or info.get("figureurl_qq_1"), 512)
                profile_fetched = True
            # ret != 0：仅资料缺失/权限不足 —— 身份已由 /me 核验，不构成账号关联错误
        except IdentityIntegrityError:
            raise        # 身份串号必须阻断
        except Exception:  # noqa: BLE001 - 资料读取失败不影响已核验身份
            profile_fetched = False

        return OAuthIdentity(
            provider=self.provider_id,
            client_id=self.client_id,
            subject=str(openid),
            union_id=None,               # QQ 无 UnionID 概念，不与微信/微博互通
            display_name=display_name,
            avatar_url=avatar_url,
            email=None,                  # 资料接口邮箱不可信且不验证
            email_verified=False,
            profile_fetched=profile_fetched,
        )


# ---------------------------------------------------------------- 安全解析
def parse_qq_payload(text: str, *, url: str) -> dict:
    """QQ 响应解析：JSON / 表单串 / 历史 JSONP 三种形态统一转 dict。

    **禁止 eval() / 动态脚本执行**：JSONP 只做「括号剥离 + json.loads」，
    形态不符直接判协议异常（不猜、不执行）。
    """
    raw = (text or "").strip()
    if not raw:
        raise ProviderProtocolError(f"QQ 响应为空 @ {url}")
    # 1) 纯 JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:  # noqa: BLE001
        pass
    # 2) JSONP：callback( {...} );
    m = _JSONP_RE.match(raw)
    if m:
        inner = m.group(1).strip()
        if inner.endswith(";"):
            inner = inner[:-1]
        try:
            obj = json.loads(inner)
        except Exception as e:  # noqa: BLE001
            raise ProviderProtocolError(
                f"QQ JSONP 内层不是合法 JSON @ {url}") from e
        if not isinstance(obj, dict):
            raise ProviderProtocolError(f"QQ JSONP 载荷不是对象 @ {url}")
        return obj
    # 3) 表单串：a=b&c=d
    if "=" in raw and "&" in raw or raw.count("=") == 1:
        pairs = parse_qs(raw, keep_blank_values=True)
        flat = {k: (v[0] if v else "") for k, v in pairs.items()}
        if flat:
            return flat
    raise ProviderProtocolError(f"QQ 响应格式无法安全解析 @ {url}")


def _map_qq_error(data: dict, url: str, *, where: str) -> Exception:
    err = data.get("error") or data.get("ret")
    desc = str(data.get("error_description") or data.get("msg") or "")[:120]
    try:
        code = int(err)
    except (TypeError, ValueError):
        code = -1
    if code in _QQ_BUSY_ERRORS:
        return ProviderUnavailable(f"QQ 接口繁忙/受限（error={code}）@ {where}")
    if code in _QQ_TOKEN_ERRORS or code > 0:
        return TokenExchangeFailed(
            f"QQ 授权失败（error={code}, {desc}）@ {where}")
    return TokenExchangeFailed(f"QQ 响应缺少必要字段 @ {where}")


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
