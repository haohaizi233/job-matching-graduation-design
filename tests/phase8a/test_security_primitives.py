# -*- coding: utf-8 -*-
"""OAuth 安全原语单测（Phase8-A / M5）：state / 摘要 / PKCE / 重定向白名单 / Cookie。

不依赖数据库与 HTTP，纯原语级验证（负向用例先行）。
"""
from __future__ import annotations

import unittest

from _util import ROOT  # noqa: F401  确保 sys.path 已注入 src 与 tests/phase8a

from job_matching.service.oauth.exceptions import InvalidRedirect
from job_matching.service.oauth.security import (
    BINDING_COOKIE_PREFIX, OAUTH_COOKIE_PATH, TICKET_COOKIE_PREFIX,
    binding_cookie_name, clear_binding_cookie, clear_ticket_cookie, digest,
    is_trusted_frontend_origin, new_binding_secret, new_state, new_ticket,
    pkce_challenge_s256, pkce_verifier, sanitize_return_path, set_binding_cookie,
    set_ticket_cookie, ticket_cookie_name)


class _FakeResponse:
    """最小 Cookie 载体（只记录 set_cookie / delete_cookie 调用）。"""

    def __init__(self):
        self.set_calls: list[tuple] = []
        self.delete_calls: list[tuple] = []

    def set_cookie(self, name, value, **kwargs):
        self.set_calls.append((name, value, kwargs))

    def delete_cookie(self, name, **kwargs):
        self.delete_calls.append((name, kwargs))


class TestStateAndRandomness(unittest.TestCase):
    """test_state_randomness：state / 票据 / 绑定凭据必须来自 CSPRNG。"""

    def test_state_randomness(self):
        states = [new_state() for _ in range(200)]
        self.assertEqual(len(states), len(set(states)), "state 出现重复，随机源不合格")
        for s in states:
            self.assertGreaterEqual(len(s), 32, "state 明文熵不足（token_urlsafe(32)）")
        tickets = [new_ticket() for _ in range(200)]
        self.assertEqual(len(tickets), len(set(tickets)), "票据出现重复")
        bindings = [new_binding_secret() for _ in range(200)]
        self.assertEqual(len(bindings), len(set(bindings)), "浏览器绑定凭据出现重复")

    def test_digest_is_one_way_sha256(self):
        state = new_state()
        d = digest(state)
        self.assertEqual(len(d), 64)
        self.assertNotEqual(d, state)
        self.assertEqual(d, digest(state))
        self.assertNotEqual(d, digest(state + "x"))


class TestPkce(unittest.TestCase):
    """PKCE S256 辅助函数（是否启用由 Provider 契约决定，这里验证算法正确）。"""

    def test_pkce_s256_rfc7636_vector(self):
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        self.assertEqual(pkce_challenge_s256(verifier),
                         "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_pkce_verifier_entropy(self):
        vs = {pkce_verifier() for _ in range(100)}
        self.assertEqual(len(vs), 100)
        for v in vs:
            self.assertGreaterEqual(len(v), 64)

    def test_pkce_verifier_respects_random_source(self):
        v = pkce_verifier(lambda n: "x" * n)
        self.assertEqual(v, "x" * 64)


class TestReturnPathWhitelist(unittest.TestCase):
    """test_redirect_open_redirect_rejected：return_path 站内白名单。"""

    def test_accepts_internal_routes(self):
        for path in ("/dashboard", "/settings", "/resume", "/profile", "/jobs",
                     "/job/123", "/matching", "/history", "/feedback"):
            self.assertEqual(sanitize_return_path(path), path)

    def test_default_when_missing(self):
        self.assertEqual(sanitize_return_path(None), "/dashboard")
        self.assertEqual(sanitize_return_path(""), "/dashboard")
        self.assertEqual(sanitize_return_path("   "), "/dashboard")

    def test_redirect_open_redirect_rejected(self):
        bad = [
            "https://evil.example/steal",      # 绝对外链
            "//evil.example",                  # 协议相对
            "///evil.example",
            "/\\evil.example",                 # 反斜杠混淆
            "/%5C%5Cevil.example",             # 编码反斜杠
            "/%2F%2Fevil.example",             # 编码协议相对
            "/dashboard?next=https://evil",    # 查询夹带外跳
            "/dashboard#//evil.example",       # 片段夹带
            "javascript:alert(1)",
            "/dashboard/../../etc/passwd",     # 路径穿越
            "/dashboard/%2e%2e/%2e%2e/etc",    # 编码穿越
            "/not-allowed-page",               # 非白名单业务页
            "\x00/dashboard",                  # 控制字符
            "/dash\\board",
            "dashboard",                       # 非绝对路径
        ]
        for path in bad:
            with self.assertRaises(InvalidRedirect, msg=f"应拒绝 return_path={path!r}"):
                sanitize_return_path(path)

    def test_rejects_overlong(self):
        with self.assertRaises(InvalidRedirect):
            sanitize_return_path("/dashboard/" + "a" * 400)


class TestOriginCheck(unittest.TestCase):
    def test_origin_must_match_whitelist(self):
        allowed = ("http://127.0.0.1:5173",)
        self.assertTrue(is_trusted_frontend_origin("http://127.0.0.1:5173", allowed))
        self.assertTrue(is_trusted_frontend_origin("http://127.0.0.1:5173/", allowed))
        self.assertFalse(is_trusted_frontend_origin("https://evil.example", allowed))
        self.assertFalse(is_trusted_frontend_origin("http://127.0.0.1:5173.evil", allowed))
        self.assertFalse(is_trusted_frontend_origin("http://evil@127.0.0.1:5173", allowed))
        self.assertFalse(is_trusted_frontend_origin("", allowed))
        self.assertFalse(is_trusted_frontend_origin(None, allowed))
        self.assertFalse(is_trusted_frontend_origin("null", allowed))


class TestCookieContract(unittest.TestCase):
    """浏览器绑定 / 票据 Cookie：HttpOnly + SameSite=Lax + 受限 Path + 事务隔离。"""

    def test_binding_cookie_flags(self):
        resp = _FakeResponse()
        set_binding_cookie(resp, "a1b2c3d4", "secret-value", max_age=300, secure=True)
        (name, value, kw), = resp.set_calls
        self.assertEqual(name, BINDING_COOKIE_PREFIX + "a1b2c3d4")
        self.assertEqual(value, "secret-value")
        self.assertTrue(kw["httponly"])
        self.assertEqual(kw["samesite"], "lax")
        self.assertTrue(kw["secure"])
        self.assertEqual(kw["path"], OAUTH_COOKIE_PATH)
        self.assertEqual(kw["max_age"], 300)

    def test_ticket_cookie_flags_and_clear(self):
        resp = _FakeResponse()
        set_ticket_cookie(resp, "a1b2c3d4", "ticket-value", max_age=60, secure=False)
        (name, value, kw), = resp.set_calls
        self.assertEqual(name, TICKET_COOKIE_PREFIX + "a1b2c3d4")
        self.assertTrue(kw["httponly"])
        self.assertFalse(kw["secure"])
        clear_ticket_cookie(resp, "a1b2c3d4", secure=False)
        clear_binding_cookie(resp, "a1b2c3d4", secure=False)
        self.assertEqual(len(resp.delete_calls), 2)

    def test_cookie_names_reject_bad_rid(self):
        for bad in ("../x", "ABCD", "a1b2", "", "a1b2c3d4x" * 4, "zzzzzzzz"):
            with self.assertRaises(InvalidRedirect):
                binding_cookie_name(bad)
            with self.assertRaises(InvalidRedirect):
                ticket_cookie_name(bad)

    def test_per_transaction_cookie_isolation(self):
        """多标签页并发授权：每个事务独立 Cookie 名，互不覆盖。"""
        n1 = binding_cookie_name("a1b2c3d4")
        n2 = binding_cookie_name("ffee0011")
        self.assertNotEqual(n1, n2)
        self.assertNotEqual(ticket_cookie_name("a1b2c3d4"),
                            ticket_cookie_name("ffee0011"))


if __name__ == "__main__":
    unittest.main()
