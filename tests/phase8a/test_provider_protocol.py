# -*- coding: utf-8 -*-
"""微信 / QQ / 微博 Provider 协议测试（Phase8-A / M2 + M9）。

纪律：
  * 外部平台用 httpx.MockTransport 替换真实网络（**不使用真实凭据**）；
  * 断言协议细节：端点常量、参数编码、响应解析、错误码映射、身份映射；
  * QQ JSONP 只做安全解析（禁止 eval / 动态脚本执行）——负向用例验证恶意载荷被拒；
  * 资料读取失败不得产生错误账号关联（subject 已核验即可登录，昵称/头像缺失只降级）。
"""
from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

import httpx

from _util import ROOT  # noqa: F401

from job_matching.service.oauth.exceptions import (InvalidIdentity,
                                                   ProviderHttpError,
                                                   ProviderProtocolError,
                                                   ProviderTimeout,
                                                   TokenExchangeFailed,
                                                   ProviderUnavailable)
from job_matching.service.oauth.http_client import (HttpLimits, OAuthHttpClient,
                                                    redact_url)
from job_matching.service.oauth.providers.qq import (ME_URL, TOKEN_URL as QQ_TOKEN_URL,
                                                     USER_INFO_URL, QQProvider,
                                                     parse_qq_payload)
from job_matching.service.oauth.providers.wechat import (AUTH_URL as WX_AUTH_URL,
                                                         TOKEN_URL as WX_TOKEN_URL,
                                                         USERINFO_URL,
                                                         WeChatProvider)
from job_matching.service.oauth.providers.weibo import (TOKEN_URL as WB_TOKEN_URL,
                                                        USER_SHOW_URL,
                                                        WeiboProvider)
from job_matching.service.oauth.schemas import OAuthIdentity, OAuthTokenResponse

SECRET = "TEST-APP-SECRET-DO-NOT-LOG"


def make_http(handler, *, max_bytes: int = 1_048_576) -> OAuthHttpClient:
    return OAuthHttpClient(transport=httpx.MockTransport(handler),
                           limits=HttpLimits(max_response_bytes=max_bytes))


def query_params(request: httpx.Request) -> dict:
    """解析请求查询参数（httpx 新版 URL.query 可能为 bytes，统一转 str）。"""
    raw = request.url.query
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return parse_qs(raw)


def json_resp(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def text_resp(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text)


# ================================================================ 微信
class TestWeChatProtocol(unittest.TestCase):
    def setUp(self):
        self.requests: list[httpx.Request] = []

    def _provider(self, handler) -> WeChatProvider:
        def wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)
        return WeChatProvider(client_id="wx-appid", client_secret=SECRET,
                              http=make_http(wrapped))

    def test_build_authorization_url_qrconnect(self):
        p = self._provider(lambda r: json_resp({}))
        url = p.build_authorization_url(state="st-1", redirect_uri="https://app.test/cb",
                                        code_challenge="IGNORED")
        self.assertTrue(url.startswith(WX_AUTH_URL))
        self.assertTrue(url.endswith("#wechat_redirect"))
        q = parse_qs(urlsplit(url.split("#")[0]).query)
        self.assertEqual(q["appid"], ["wx-appid"])
        self.assertEqual(q["scope"], ["snsapi_login"])
        self.assertEqual(q["state"], ["st-1"])
        self.assertEqual(q["redirect_uri"], ["https://app.test/cb"])
        self.assertEqual(q["response_type"], ["code"])
        # 微信网站扫码契约未确认 PKCE：不得把 code_challenge 发给平台
        self.assertNotIn("code_challenge", q)
        self.assertFalse(p.supports_pkce)

    def test_exchange_code_happy_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "api.weixin.qq.com")
            self.assertEqual(request.url.path, "/sns/oauth2/access_token")
            q = query_params(request)
            self.assertEqual(q["grant_type"], ["authorization_code"])
            self.assertEqual(q["code"], ["wx-code-1"])
            self.assertEqual(q["appid"], ["wx-appid"])
            self.assertEqual(q["secret"], [SECRET])
            return json_resp({"access_token": "AT-1", "openid": "OID-1",
                              "unionid": "UNI-1", "expires_in": 7200,
                              "refresh_token": "RT-1", "scope": "snsapi_login"})
        p = self._provider(handler)
        token = p.exchange_code(code="wx-code-1", redirect_uri="https://app.test/cb")
        self.assertEqual(token.access_token, "AT-1")
        self.assertEqual(token.raw_subject, "OID-1")
        self.assertEqual(token.raw.get("unionid"), "UNI-1")
        self.assertEqual(token.expires_in, 7200)
        # 安全投影绝不携带 access_token
        self.assertNotIn("AT-1", str(token.describe()))

    def test_exchange_code_without_unionid(self):
        p = self._provider(lambda r: json_resp(
            {"access_token": "AT-1", "openid": "OID-1", "expires_in": 7200}))
        token = p.exchange_code(code="c", redirect_uri="u")
        self.assertIsNone(token.raw.get("unionid"))

    def test_errcode_maps_to_token_exchange_failed(self):
        for errcode in (40029, 40163, 40013, 40125, 40001, 42001, 12345):
            p = self._provider(lambda r, c=errcode: json_resp(
                {"errcode": c, "errmsg": "bad"}))
            with self.assertRaises(TokenExchangeFailed, msg=f"errcode={errcode}"):
                p.exchange_code(code="c", redirect_uri="u")

    def test_provider_busy_maps_to_unavailable(self):
        for errcode in (-1, 45002, 45011, 45009):
            p = self._provider(lambda r, c=errcode: json_resp(
                {"errcode": c, "errmsg": "busy"}))
            with self.assertRaises(ProviderUnavailable, msg=f"errcode={errcode}"):
                p.exchange_code(code="c", redirect_uri="u")

    def test_missing_openid_rejected(self):
        p = self._provider(lambda r: json_resp({"access_token": "AT-1"}))
        with self.assertRaises(ProviderProtocolError):
            p.exchange_code(code="c", redirect_uri="u")

    def test_missing_code_raises_token_exchange_failed(self):
        p = self._provider(lambda r: json_resp({}))
        with self.assertRaises(TokenExchangeFailed):
            p.exchange_code(code="", redirect_uri="u")

    def test_get_identity_happy_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/sns/userinfo")
            return json_resp({"openid": "OID-1", "nickname": "合成昵称",
                              "headimgurl": "https://img.test/a.png",
                              "unionid": "UNI-1"})
        p = self._provider(handler)
        token = OAuthTokenResponse(provider="wechat", client_id="wx-appid",
                                   access_token="AT-1", raw_subject="OID-1",
                                   raw={"openid": "OID-1", "unionid": "UNI-1"})
        ident = p.get_identity(token)
        self.assertIsInstance(ident, OAuthIdentity)
        self.assertEqual(ident.subject, "OID-1")
        self.assertEqual(ident.client_id, "wx-appid")
        self.assertEqual(ident.union_id, "UNI-1")
        self.assertEqual(ident.display_name, "合成昵称")
        self.assertTrue(ident.profile_fetched)
        self.assertFalse(ident.email_verified)

    def test_get_identity_openid_mismatch_rejected(self):
        p = self._provider(lambda r: json_resp({"openid": "OTHER-OID",
                                                "nickname": "x"}))
        token = OAuthTokenResponse(provider="wechat", client_id="wx-appid",
                                   access_token="AT-1", raw_subject="OID-1",
                                   raw={"openid": "OID-1"})
        with self.assertRaises(ProviderProtocolError):
            p.get_identity(token)

    def test_get_identity_profile_http_failure_degrades(self):
        """已核验 openid + 资料接口 500：身份仍有效，昵称/头像缺失只降级。"""
        p = self._provider(lambda r: json_resp({"err": "x"}, status=500))
        token = OAuthTokenResponse(provider="wechat", client_id="wx-appid",
                                   access_token="AT-1", raw_subject="OID-1",
                                   raw={"openid": "OID-1", "unionid": "UNI-1"})
        ident = p.get_identity(token)
        self.assertEqual(ident.subject, "OID-1")
        self.assertEqual(ident.union_id, "UNI-1")
        self.assertFalse(ident.profile_fetched)
        self.assertIsNone(ident.display_name)

    def test_get_identity_profile_errcode_degrades(self):
        """资料接口 errcode（如权限不足）同样只降级，不得阻断已核验身份登录。"""
        p = self._provider(lambda r: json_resp({"errcode": 48001,
                                                "errmsg": "api unauthorized"}))
        token = OAuthTokenResponse(provider="wechat", client_id="wx-appid",
                                   access_token="AT-1", raw_subject="OID-1",
                                   raw={"openid": "OID-1"})
        ident = p.get_identity(token)
        self.assertEqual(ident.subject, "OID-1")
        self.assertFalse(ident.profile_fetched)

    def test_get_identity_missing_subject_rejected(self):
        p = self._provider(lambda r: json_resp({}))
        token = OAuthTokenResponse(provider="wechat", client_id="wx-appid",
                                   access_token="AT-1")
        with self.assertRaises(InvalidIdentity):
            p.get_identity(token)

    def test_exchange_timeout_raises_provider_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated")
        p = self._provider(handler)
        with self.assertRaises(ProviderTimeout):
            p.exchange_code(code="c", redirect_uri="u")

    def test_exception_messages_do_not_leak_secret(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return json_resp({"errcode": 40029, "errmsg": "bad"}, status=200)
        p = self._provider(handler)
        try:
            p.exchange_code(code="c", redirect_uri="u")
            self.fail("应抛出异常")
        except Exception as e:  # noqa: BLE001
            self.assertNotIn(SECRET, str(e))


# ================================================================ QQ
class TestQQProtocol(unittest.TestCase):
    def setUp(self):
        self.requests: list[httpx.Request] = []

    def _provider(self, handler) -> QQProvider:
        def wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)
        return QQProvider(client_id="qq-appid", client_secret=SECRET,
                          http=make_http(wrapped))

    def test_build_authorization_url(self):
        p = self._provider(lambda r: text_resp(""))
        url = p.build_authorization_url(state="st-1",
                                        redirect_uri="https://app.test/cb")
        self.assertTrue(url.startswith("https://graph.qq.com/oauth2.0/authorize"))
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["client_id"], ["qq-appid"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["state"], ["st-1"])
        self.assertEqual(q["redirect_uri"], ["https://app.test/cb"])
        self.assertFalse(p.supports_pkce)

    def _token_and_identity(self, p, code="qq-code-1"):
        token = p.exchange_code(code=code, redirect_uri="https://app.test/cb")
        return token, p.get_identity(token)

    def test_full_flow_form_token_jsonp_me_json_profile(self):
        """token=表单串 → /me=JSONP → 资料=JSON（历史三种格式混合）。"""
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/oauth2.0/token":
                self.assertEqual(request.url.host, "graph.qq.com")
                q = query_params(request)
                self.assertEqual(q["client_secret"], [SECRET])
                self.assertEqual(q["fmt"], ["json"])
                return text_resp("access_token=AT-1&expires_in=7777&refresh_token=RT-1")
            if path == "/oauth2.0/me":
                q = query_params(request)
                self.assertEqual(q["oauth_consumer_key"], ["qq-appid"])
                return text_resp(
                    'callback( {"client_id":"qq-appid","openid":"QOID-1"} );')
            if path == "/user/get_user_info":
                q = query_params(request)
                self.assertEqual(q["openid"], ["QOID-1"])
                return json_resp({"ret": 0, "nickname": "合成昵称",
                                  "figureurl_qq_2": "https://img.test/qq.png"})
            raise AssertionError(f"意外请求 {path}")
        p = self._provider(handler)
        token, ident = self._token_and_identity(p)
        self.assertEqual(token.access_token, "AT-1")
        self.assertEqual(token.expires_in, 7777)
        self.assertEqual(token.raw_subject, "QOID-1")
        self.assertEqual(ident.subject, "QOID-1")
        self.assertEqual(ident.provider, "qq")
        self.assertIsNone(ident.union_id)      # QQ 无 UnionID，不与微信/微博互通
        self.assertIsNone(ident.email)          # 资料邮箱不可信且不验证
        self.assertFalse(ident.email_verified)
        self.assertEqual(ident.display_name, "合成昵称")
        self.assertTrue(ident.profile_fetched)

    def test_token_json_response_supported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2.0/token":
                return json_resp({"access_token": "AT-2", "expires_in": 100})
            if request.url.path == "/oauth2.0/me":
                return json_resp({"openid": "QOID-2", "client_id": "qq-appid"})
            return json_resp({"ret": 0, "nickname": "n"})
        p = self._provider(handler)
        token, ident = self._token_and_identity(p)
        self.assertEqual(ident.subject, "QOID-2")

    def test_jsonp_malicious_payload_rejected_without_eval(self):
        """JSONP 安全解析：非 JSON 载荷一律协议异常，绝不执行脚本。"""
        evil_payloads = [
            'callback((function(){steal()})());',
            'alert(1);callback({"openid":"x"});',
            'callback({"openid":"x"}) && steal();',
            'callback(<img src=x onerror=steal()>);',
            'eval("steal()")',
        ]
        for raw in evil_payloads:
            with self.assertRaises(ProviderProtocolError, msg=f"应拒绝 {raw!r}"):
                parse_qq_payload(raw, url="https://graph.qq.com/x")

    def test_parse_qq_payload_formats(self):
        self.assertEqual(parse_qq_payload('{"a":1}', url="u"), {"a": 1})
        self.assertEqual(parse_qq_payload('cb({"a":"b"});', url="u"), {"a": "b"})
        self.assertEqual(parse_qq_payload("access_token=AT&expires_in=1", url="u"),
                         {"access_token": "AT", "expires_in": "1"})
        with self.assertRaises(ProviderProtocolError):
            parse_qq_payload("", url="u")
        with self.assertRaises(ProviderProtocolError):
            parse_qq_payload("not-a-payload", url="u")

    def test_token_error_mapping(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return text_resp("error=100014&error_description=code%20invalid")
        p = self._provider(handler)
        with self.assertRaises(TokenExchangeFailed):
            p.exchange_code(code="c", redirect_uri="u")

    def test_me_error_maps_to_token_exchange_failed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2.0/token":
                return text_resp("access_token=AT-1&expires_in=1")
            return text_resp('callback( {"ret":100016} );')
        p = self._provider(handler)
        with self.assertRaises(TokenExchangeFailed):
            p.exchange_code(code="c", redirect_uri="u")

    def test_me_consumer_key_mismatch_rejected(self):
        """/me 返回的 client_id 与本应用不一致：拒绝（应用级 OpenID 命名空间）。"""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2.0/token":
                return text_resp("access_token=AT-1&expires_in=1")
            return text_resp('callback( {"client_id":"OTHER-APP","openid":"X"} );')
        p = self._provider(handler)
        with self.assertRaises(ProviderProtocolError):
            p.exchange_code(code="c", redirect_uri="u")

    def test_profile_permission_error_degrades(self):
        """/me 已核验 OpenID，资料 ret!=0 只降级，不阻断登录。"""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2.0/token":
                return text_resp("access_token=AT-1&expires_in=1")
            if request.url.path == "/oauth2.0/me":
                return text_resp('callback( {"client_id":"qq-appid","openid":"QOID-1"} );')
            return json_resp({"ret": 1002, "msg": "scope not granted"})
        p = self._provider(handler)
        _token, ident = self._token_and_identity(p)
        self.assertEqual(ident.subject, "QOID-1")
        self.assertFalse(ident.profile_fetched)
        self.assertIsNone(ident.display_name)

    def test_profile_http_failure_degrades(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2.0/token":
                return text_resp("access_token=AT-1&expires_in=1")
            if request.url.path == "/oauth2.0/me":
                return text_resp('callback( {"client_id":"qq-appid","openid":"QOID-1"} );')
            return json_resp({"err": "x"}, status=500)
        p = self._provider(handler)
        _token, ident = self._token_and_identity(p)
        self.assertEqual(ident.subject, "QOID-1")
        self.assertFalse(ident.profile_fetched)

    def test_nickname_alone_never_identity(self):
        """昵称只做展示：identity 的 subject 一律是 /me 的 openid。"""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2.0/token":
                return text_resp("access_token=AT-1&expires_in=1")
            if request.url.path == "/oauth2.0/me":
                return text_resp('callback( {"client_id":"qq-appid","openid":"QOID-9"} );')
            return json_resp({"ret": 0, "nickname": "张三", "figureurl_qq_2": "u"})
        p = self._provider(handler)
        _token, ident = self._token_and_identity(p)
        self.assertEqual(ident.subject, "QOID-9")
        self.assertNotEqual(ident.subject, "张三")


# ================================================================ 微博
class TestWeiboProtocol(unittest.TestCase):
    def _provider(self, handler) -> WeiboProvider:
        return WeiboProvider(client_id="wb-appkey", client_secret=SECRET,
                             http=make_http(handler))

    def test_build_authorization_url(self):
        p = self._provider(lambda r: json_resp({}))
        url = p.build_authorization_url(state="st-1",
                                        redirect_uri="https://app.test/cb")
        self.assertTrue(url.startswith("https://api.weibo.com/oauth2/authorize"))
        q = parse_qs(urlsplit(url).query)
        self.assertEqual(q["client_id"], ["wb-appkey"])
        self.assertEqual(q["state"], ["st-1"])
        self.assertEqual(q["redirect_uri"], ["https://app.test/cb"])
        self.assertFalse(p.supports_pkce)

    def test_exchange_code_happy_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/oauth2/access_token")
            body = parse_qs(request.content.decode("utf-8"))
            self.assertEqual(body["grant_type"], ["authorization_code"])
            self.assertEqual(body["client_secret"], [SECRET])
            self.assertEqual(body["redirect_uri"], ["https://app.test/cb"])
            return json_resp({"access_token": "WB-AT", "uid": 12345,
                              "expires_in": 3600, "token_type": "bearer"})
        p = self._provider(handler)
        token = p.exchange_code(code="wb-code", redirect_uri="https://app.test/cb")
        self.assertEqual(token.access_token, "WB-AT")
        self.assertEqual(token.raw_subject, "12345")
        self.assertNotIn("WB-AT", str(token.describe()))

    def test_missing_uid_rejected(self):
        p = self._provider(lambda r: json_resp({"access_token": "WB-AT"}))
        with self.assertRaises(ProviderProtocolError):
            p.exchange_code(code="c", redirect_uri="u")

    def test_missing_access_token_rejected(self):
        p = self._provider(lambda r: json_resp({"uid": 1}))
        with self.assertRaises(ProviderProtocolError):
            p.exchange_code(code="c", redirect_uri="u")

    def test_error_code_mapping(self):
        cases = [(21327, TokenExchangeFailed), (21314, TokenExchangeFailed),
                 (21330, TokenExchangeFailed), (10006, ProviderUnavailable),
                 (10023, ProviderUnavailable)]
        for code, expected in cases:
            p = self._provider(lambda r, c=code: json_resp(
                {"error": "bad", "error_code": c}))
            with self.assertRaises(expected, msg=f"error_code={code}"):
                p.exchange_code(code="c", redirect_uri="u")

    def test_get_identity_happy_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/2/users/show.json")
            q = query_params(request)
            self.assertEqual(q["uid"], ["12345"])
            return json_resp({"id": 12345, "screen_name": "合成昵称",
                              "avatar_large": "https://img.test/wb.png"})
        p = self._provider(handler)
        token = OAuthTokenResponse(provider="weibo", client_id="wb-appkey",
                                   access_token="WB-AT", raw_subject="12345",
                                   raw={"uid": "12345"})
        ident = p.get_identity(token)
        self.assertEqual(ident.subject, "12345")
        self.assertEqual(ident.display_name, "合成昵称")
        self.assertTrue(ident.profile_fetched)

    def test_uid_mismatch_rejected(self):
        p = self._provider(lambda r: json_resp({"id": 999, "screen_name": "x"}))
        token = OAuthTokenResponse(provider="weibo", client_id="wb-appkey",
                                   access_token="WB-AT", raw_subject="12345",
                                   raw={"uid": "12345"})
        with self.assertRaises(ProviderProtocolError):
            p.get_identity(token)

    def test_profile_failure_keeps_verified_uid(self):
        """契约：UID 已核验但资料读取失败 -> 不因昵称/头像缺失产生错误关联。"""
        for handler in (
                lambda r: json_resp({"err": "x"}, status=500),
                lambda r: json_resp({"error": "permission denied",
                                     "error_code": 10006}),
                lambda r: json_resp({"error": "no permission",
                                     "error_code": 21332})):
            p = self._provider(handler)
            token = OAuthTokenResponse(provider="weibo", client_id="wb-appkey",
                                       access_token="WB-AT", raw_subject="12345",
                                       raw={"uid": "12345"})
            ident = p.get_identity(token)
            self.assertEqual(ident.subject, "12345")
            self.assertFalse(ident.profile_fetched)
            self.assertIsNone(ident.display_name)

    def test_identity_without_uid_rejected(self):
        p = self._provider(lambda r: json_resp({}))
        token = OAuthTokenResponse(provider="weibo", client_id="wb-appkey",
                                   access_token="WB-AT")
        with self.assertRaises(InvalidIdentity):
            p.get_identity(token)


# ================================================================ HTTP 客户端
class TestOAuthHttpClient(unittest.TestCase):
    def test_http_status_error_mapped(self):
        client = make_http(lambda r: json_resp({"err": "x"}, status=503))
        with self.assertRaises(ProviderHttpError) as ctx:
            client.get_text("https://api.test/x")
        self.assertEqual(ctx.exception.status_code, 503)

    def test_response_size_bounded(self):
        client = make_http(lambda r: text_resp("A" * 4096), max_bytes=64)
        with self.assertRaises(ProviderProtocolError):
            client.get_text("https://api.test/x")

    def test_timeout_mapped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("simulated")
        client = make_http(handler)
        with self.assertRaises(ProviderTimeout):
            client.get_text("https://api.test/x")

    def test_no_redirect_followed(self):
        """禁止跟随重定向（SSRF 逃生口）：302 不会触发第二次请求。"""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
        client = make_http(handler)
        client.get_text("https://api.test/x")
        self.assertEqual(calls, ["/x"])

    def test_redact_url_strips_query(self):
        self.assertEqual(redact_url("https://a.test/p?client_secret=S#f"),
                         "https://a.test/p")


if __name__ == "__main__":
    unittest.main()
