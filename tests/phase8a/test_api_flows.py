# -*- coding: utf-8 -*-
"""OAuth API 集成测试（Phase8-A / M9-M10）：真实 FastAPI 应用 + Fake Provider。

纪律：
  * 只有外部身份 Provider 被 FakeOAuthProvider 替换（tests/phase8a/fake_provider.py）；
  * 本站业务链路（事务/票据/账号/会话/画像/简历）全部真实实现；
  * 断言 OAuth 登录**真正进入现有账号系统**（/auth/me / 会话 / 业务接口），
    不是只看 HTTP 200；
  * 错误路径断言稳定错误码与固定可信跳转（不传播 code/state/Token）。
"""
from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from _util import OAuthHarness, parse_complete_url  # noqa: F401
from fake_provider import make_identity

from job_matching.service.oauth.security import pkce_challenge_s256

TEST_SECRET = "FAKE_SECRET_FOR_TESTS"


def error_code(resp) -> str:
    try:
        return str(resp.json()["error"]["code"])
    except Exception:  # noqa: BLE001
        return f"<non-error-body:{resp.status_code}>"


class TestProviderStatusAPI(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def test_providers_status_shape_without_secrets(self):
        r = self.h.client.get("/api/v1/auth/oauth/providers")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("request_id", body)
        providers = body["data"]["providers"]
        self.assertEqual(len(providers), 1)
        item = providers[0]
        for key in ("id", "label", "enabled", "status", "reason_code"):
            self.assertIn(key, item)
        self.assertTrue(item["enabled"])
        # 绝不返回 Secret / client_secret 字段
        text = r.text
        self.assertNotIn(TEST_SECRET, text)
        self.assertNotIn("client_secret", text)

    def test_unconfigured_provider_rejected_without_fake_link(self):
        """未配置平台：明确 503，不生成任何假授权链接。"""
        r = self.h.client.post("/api/v1/auth/oauth/start",
                               json={"provider": "wechat", "mode": "login"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(error_code(r), "OAUTH_PROVIDER_NOT_CONFIGURED")
        self.assertNotIn("authorization_url", r.text)

    def test_unknown_provider_rejected(self):
        r = self.h.client.post("/api/v1/auth/oauth/start",
                               json={"provider": "evil-provider", "mode": "login"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(error_code(r), "OAUTH_PROVIDER_NOT_CONFIGURED")

    def test_invalid_mode_rejected(self):
        r = self.h.client.post("/api/v1/auth/oauth/start",
                               json={"provider": "fake", "mode": "admin"})
        self.assertIn(r.status_code, (400, 422))
        self.assertEqual(error_code(r), "INVALID_REQUEST")

    def test_invalid_return_path_rejected(self):
        """test_redirect_open_redirect_rejected（API 侧）。"""
        for bad in ("https://evil.example", "//evil.example", "/\\evil.example",
                    "/dashboard/../../etc", "/not-allowed"):
            r = self.h.client.post(
                "/api/v1/auth/oauth/start",
                json={"provider": "fake", "mode": "login", "return_path": bad})
            self.assertEqual(r.status_code, 400,
                             f"return_path={bad} 应被拒绝，实际 {r.status_code}")
            self.assertEqual(error_code(r), "OAUTH_INVALID_REDIRECT")

    def test_return_path_whitelisted_echoed(self):
        started = self.h.start(return_path="/settings")
        self.assertEqual(started["body"]["return_path"], "/settings")
        self.h.fake.register_code("code-rp", make_identity("sub-rp"))
        resp = self.h.callback(rid=started["rid"], state=started["state"],
                               code="code-rp")
        info = parse_complete_url(resp.headers["location"])
        self.assertEqual(info["status"], "ok")
        self.assertEqual(info["return_path"], "/settings")


class TestOAuthConfig(unittest.TestCase):
    """配置系统（M8）：状态三态、按平台独立、生产安全门禁。"""

    def test_config_status_states(self):
        from job_matching.service.oauth.config import (OAuthProviderConfig,
                                                       OAuthSettings)
        base = dict(provider_id="qq", label="QQ")
        disabled = OAuthProviderConfig(**base, enabled=False,
                                       client_id="a", client_secret="b")
        self.assertEqual(disabled.status(global_enabled=True)[0], "disabled")
        not_cfg = OAuthProviderConfig(**base, enabled=True, client_id="", client_secret="")
        status, reason = not_cfg.status(global_enabled=True)
        self.assertEqual((status, reason), ("disabled", "OAUTH_PROVIDER_NOT_CONFIGURED"))
        pending = OAuthProviderConfig(**base, enabled=True, client_id="a",
                                      client_secret="b")
        self.assertEqual(pending.status(global_enabled=True)[0],
                         "configured_pending_verification")
        verified = OAuthProviderConfig(**base, enabled=True, client_id="a",
                                       client_secret="b", verified=True)
        self.assertEqual(verified.status(global_enabled=True)[0], "available")

    def test_each_provider_independent(self):
        from job_matching.service.oauth.config import OAuthSettings
        settings = OAuthSettings.from_env({
            "JM_OAUTH_ENABLED": "true",
            "JM_OAUTH_PUBLIC_BASE_URL": "https://app.test",
            "JM_OAUTH_FRONTEND_ORIGIN": "https://app.test",
            "JM_OAUTH_QQ_ENABLED": "true",
            "JM_OAUTH_QQ_CLIENT_ID": "qq-id",
            "JM_OAUTH_QQ_CLIENT_SECRET": "qq-secret",
        })
        self.assertEqual(settings.provider_status("qq")[0],
                         "configured_pending_verification")
        self.assertEqual(settings.provider_status("wechat")[0], "disabled")
        self.assertEqual(settings.provider_status("weibo")[0], "disabled")
        self.assertEqual(settings.check_safety(), [])

    def test_production_http_rejected(self):
        from job_matching.service.oauth.config import OAuthSettings
        settings = OAuthSettings.from_env({
            "JM_API_ENV": "prod",
            "JM_OAUTH_ENABLED": "true",
            "JM_OAUTH_PUBLIC_BASE_URL": "http://app.test",
            "JM_OAUTH_FRONTEND_ORIGIN": "http://app.test",
            "JM_OAUTH_QQ_ENABLED": "true",
            "JM_OAUTH_QQ_CLIENT_ID": "qq-id",
            "JM_OAUTH_QQ_CLIENT_SECRET": "qq-secret",
        })
        problems = settings.check_safety()
        self.assertTrue(any("HTTPS" in p for p in problems), problems)

    def test_enabled_without_credentials_rejected(self):
        from job_matching.service.oauth.config import OAuthSettings
        settings = OAuthSettings.from_env({
            "JM_OAUTH_ENABLED": "true",
            "JM_OAUTH_PUBLIC_BASE_URL": "https://app.test",
            "JM_OAUTH_FRONTEND_ORIGIN": "https://app.test",
            "JM_OAUTH_WECHAT_ENABLED": "true",
        })
        problems = settings.check_safety()
        self.assertTrue(any("wechat" in p for p in problems), problems)


class TestLoginFlow(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def _full_login(self, subject="sub-login", code="code-1", **identity_kw):
        """start -> callback -> exchange；返回 (started, exchange_json)。"""
        started = self.h.start()
        self.assertEqual(started["response"].status_code, 200, started["response"].text)
        self.h.fake.register_code(code, make_identity(subject, **identity_kw))
        resp = self.h.callback(rid=started["rid"], state=started["state"], code=code)
        self.assertEqual(resp.status_code, 302)
        info = parse_complete_url(resp.headers["location"])
        self.assertEqual(info["status"], "ok", info)
        ex = self.h.exchange(rid=info["rid"])
        self.assertEqual(ex.status_code, 200, ex.text)
        return started, ex.json()["data"]

    def test_full_login_chain_enters_existing_account_system(self):
        """start → callback → exchange → /auth/me → 画像/简历 → logout → 旧 Token 401。"""
        _started, data = self._full_login("sub-chain")
        token = data["token"]
        # 与 /auth/login 一致的响应结构
        for key in ("token", "user", "token_type", "expires_at", "session_id"):
            self.assertIn(key, data)
        self.assertEqual(data["token_type"], "bearer")

        me = self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["data"]["user"]["id"], data["user"]["id"])
        self.assertEqual(me.json()["data"]["user"]["role"], "student")

        # 真实进入现有业务域：简历 / 画像接口按既有契约可访问
        resumes = self.h.client.get("/api/v1/resumes", headers=self.h.auth(token))
        self.assertEqual(resumes.status_code, 200, resumes.text)
        profile = self.h.client.get("/api/v1/students/me/profile",
                                    headers=self.h.auth(token))
        self.assertIn(profile.status_code, (200, 404))

        # 身份列表可见（已绑定）
        ids = self.h.client.get("/api/v1/auth/oauth/identities",
                                headers=self.h.auth(token))
        self.assertEqual(ids.status_code, 200, ids.text)
        self.assertEqual(len(ids.json()["data"]["items"]), 1)
        self.assertFalse(ids.json()["data"]["password_login_available"])

        # 退出 -> 旧 Token 真正失效
        out = self.h.client.post("/api/v1/auth/logout", headers=self.h.auth(token))
        self.assertEqual(out.status_code, 200, out.text)
        after = self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))
        self.assertEqual(after.status_code, 401)

    def test_exchange_shape_matches_password_login(self):
        self.h.register("pw_shape")
        login = self.h.login("pw_shape")
        login_keys = set(self.h.client.post(
            "/api/v1/auth/login",
            json={"username": "pw_shape", "password": "Passw0rd!2026"}
        ).json()["data"].keys())
        _s, data = self._full_login("sub-shape")
        self.assertEqual(set(data.keys()), login_keys)
        self.assertEqual(set(data["user"].keys()), set(login[0].keys()))

    def test_pkce_when_supported(self):
        """Fake Provider 支持 PKCE -> S256 挑战/验证器必须完整往返。"""
        started = self.h.start()
        self.assertTrue(started["code_challenge"], "支持 PKCE 的 Provider 必须发起挑战")
        self.h.fake.register_code("code-pkce", make_identity("sub-pkce"))
        resp = self.h.callback(rid=started["rid"], state=started["state"],
                               code="code-pkce")
        info = parse_complete_url(resp.headers["location"])
        ex = self.h.exchange(rid=info["rid"])
        self.assertEqual(ex.status_code, 200, ex.text)
        call = self.h.fake.exchange_calls[-1]
        self.assertTrue(call["code_verifier"])
        self.assertEqual(pkce_challenge_s256(call["code_verifier"]),
                         started["code_challenge"])

    def test_default_student_role_and_password_login_rejected(self):
        _s, data = self._full_login("sub-role")
        self.assertEqual(data["user"]["role"], "student")
        self.assertEqual(data["user"]["status"], "active")
        username = data["user"]["username"]
        r = self.h.client.post("/api/v1/auth/login",
                               json={"username": username, "password": "whatever"})
        ghost = self.h.client.post("/api/v1/auth/login",
                                   json={"username": "ghost_none_xx",
                                         "password": "whatever"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(error_code(r), error_code(ghost))
        self.assertEqual(r.json()["error"]["message"],
                         ghost.json()["error"]["message"])

    def test_second_login_same_identity_no_duplicate_account(self):
        _s1, first = self._full_login("sub-dup", code="code-a")
        self.h.client.cookies.clear()
        _s2, second = self._full_login("sub-dup", code="code-b")
        self.assertEqual(first["user"]["id"], second["user"]["id"])

    def test_oauth_issues_new_session_each_login(self):
        """防会话固定：每次 OAuth 完成都签发全新本站会话。"""
        _s1, first = self._full_login("sub-sess", code="code-s1")
        self.h.client.cookies.clear()
        _s2, second = self._full_login("sub-sess", code="code-s2")
        self.assertNotEqual(first["token"], second["token"])
        self.assertNotEqual(first["session_id"], second["session_id"])

    def test_multi_tab_authorization(self):
        """多标签页并发授权：事务按 rid 隔离，两个授权都可独立完成。"""
        s1 = self.h.start(return_path="/dashboard")
        s2 = self.h.start(return_path="/settings")
        self.assertNotEqual(s1["rid"], s2["rid"])
        self.assertNotEqual(s1["state"], s2["state"])
        self.h.fake.register_code("code-t1", make_identity("sub-tab1"))
        self.h.fake.register_code("code-t2", make_identity("sub-tab2"))
        r1 = self.h.callback(rid=s1["rid"], state=s1["state"], code="code-t1")
        r2 = self.h.callback(rid=s2["rid"], state=s2["state"], code="code-t2")
        i1 = parse_complete_url(r1.headers["location"])
        i2 = parse_complete_url(r2.headers["location"])
        self.assertEqual((i1["status"], i2["status"]), ("ok", "ok"))
        e1 = self.h.exchange(rid=i1["rid"])
        e2 = self.h.exchange(rid=i2["rid"])
        self.assertEqual((e1.status_code, e2.status_code), (200, 200))
        self.assertNotEqual(e1.json()["data"]["user"]["id"],
                            e2.json()["data"]["user"]["id"])


class TestCallbackErrors(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def _start(self):
        started = self.h.start()
        assert started["response"].status_code == 200
        return started

    def _reason(self, resp) -> dict:
        self.assertEqual(resp.status_code, 302)
        return parse_complete_url(resp.headers["location"])

    def test_callback_without_code(self):
        s = self._start()
        info = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                            code=None))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_INVALID_STATE"))

    def test_callback_without_state(self):
        s = self._start()
        info = self._reason(self.h.callback(rid=s["rid"], state="",
                                            code="code-1"))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_INVALID_STATE"))

    def test_callback_access_denied(self):
        s = self._start()
        info = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                            code=None, error="access_denied"))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_ACCESS_DENIED"))

    def test_state_expired(self):
        s = self._start()
        self.h.clock.advance(seconds=301)
        self.h.fake.register_code("code-x", make_identity("sub-x"))
        info = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                            code="code-x"))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_STATE_EXPIRED"))

    def test_state_mismatch(self):
        s = self._start()
        info = self._reason(self.h.callback(rid=s["rid"], state="forged-state",
                                            code="code-1"))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_INVALID_STATE"))

    def test_state_replay(self):
        s = self._start()
        self.h.fake.register_code("code-r", make_identity("sub-r"))
        first = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                             code="code-r"))
        self.assertEqual(first["status"], "ok")
        second = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                              code="code-r"))
        self.assertEqual((second["status"], second["reason"]),
                         ("error", "OAUTH_CALLBACK_REPLAY"))

    def test_state_browser_binding(self):
        """跨浏览器回调：无绑定 Cookie 的浏览器不得领取该授权事务。"""
        s = self._start()
        self.h.fake.register_code("code-bb", make_identity("sub-bb"))
        other_browser = self.h.new_client()
        resp = other_browser.get(
            f"/api/v1/auth/oauth/fake/callback?code=code-bb&state={s['state']}",
            follow_redirects=False)
        info = self._reason(resp)
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_INVALID_STATE"))
        other_browser.close()

    def test_state_wrong_provider(self):
        """state 与 Provider 绑定：其它平台回调不得消费本事务。"""
        s = self._start()
        resp = self.h.client.get(
            f"/api/v1/auth/oauth/weibo/callback?code=code-1&state={s['state']}",
            follow_redirects=False)
        info = self._reason(resp)
        self.assertEqual(info["status"], "error")
        # 未注册平台 -> 未配置错误；已注册平台 -> InvalidState（存储层已单测覆盖）
        self.assertIn(info["reason"],
                      ("OAUTH_PROVIDER_NOT_CONFIGURED", "OAUTH_INVALID_STATE"))

    def test_code_replay_rejected(self):
        """同一授权码重放：真实平台会拒绝，Fake 同样拒绝（不产生第二个会话）。"""
        s1 = self._start()
        self.h.fake.register_code("code-replay", make_identity("sub-crp"))
        ok = self._reason(self.h.callback(rid=s1["rid"], state=s1["state"],
                                          code="code-replay"))
        self.assertEqual(ok["status"], "ok")
        s2 = self._start()
        bad = self._reason(self.h.callback(rid=s2["rid"], state=s2["state"],
                                           code="code-replay"))
        self.assertEqual((bad["status"], bad["reason"]),
                         ("error", "OAUTH_TOKEN_EXCHANGE_FAILED"))

    def test_oauth_provider_timeout(self):
        s = self._start()
        self.h.fake.set_behavior("timeout")
        info = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                            code="code-t"))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_PROVIDER_UNAVAILABLE"))

    def test_oauth_provider_malformed_response(self):
        s = self._start()
        self.h.fake.set_behavior("malformed")
        info = self._reason(self.h.callback(rid=s["rid"], state=s["state"],
                                            code="code-m"))
        self.assertEqual((info["status"], info["reason"]),
                         ("error", "OAUTH_TOKEN_EXCHANGE_FAILED"))

    def test_provider_http_errors_mapped_not_password_error(self):
        for behavior, reason in (("http_429", "OAUTH_PROVIDER_UNAVAILABLE"),
                                 ("http_500", "OAUTH_PROVIDER_UNAVAILABLE"),
                                 ("code_expired", "OAUTH_TOKEN_EXCHANGE_FAILED"),
                                 ("token_unavailable", "OAUTH_TOKEN_EXCHANGE_FAILED"),
                                 ("identity_missing", "OAUTH_INVALID_IDENTITY")):
            h = OAuthHarness()
            try:
                s = h.start()
                h.fake.register_code("code-z", make_identity("sub-z"),
                                     behavior=behavior)
                resp = h.callback(rid=s["rid"], state=s["state"], code="code-z")
                info = parse_complete_url(resp.headers["location"])
                self.assertEqual((info["status"], info["reason"]),
                                 ("error", reason), f"behavior={behavior}")
            finally:
                h.close()

    def test_error_redirect_never_leaks_code_state_token(self):
        s = self._start()
        self.h.fake.register_code("code-leak", make_identity("sub-leak"))
        resp = self.h.callback(rid=s["rid"], state=s["state"], code="code-leak",
                               error="access_denied")
        location = resp.headers["location"]
        for secret in ("code-leak", s["state"], TEST_SECRET, "fake-at-"):
            self.assertNotIn(secret, location)
        self.assertTrue(location.startswith("http://127.0.0.1:5173/#/oauth/complete"))
        self.assertIn("reason=OAUTH_ACCESS_DENIED", location)


class TestExchangeSecurity(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def _to_ticket(self, subject="sub-ex", code="code-e"):
        s = self.h.start()
        self.h.fake.register_code(code, make_identity(subject))
        resp = self.h.callback(rid=s["rid"], state=s["state"], code=code)
        info = parse_complete_url(resp.headers["location"])
        return s, info

    def test_ticket_expired(self):
        s, info = self._to_ticket()
        self.h.clock.advance(seconds=61)
        ex = self.h.exchange(rid=info["rid"])
        self.assertEqual(ex.status_code, 400)
        self.assertEqual(error_code(ex), "OAUTH_TICKET_EXPIRED")

    def test_ticket_replay(self):
        """已消费票据重放（携带捕获的 Cookie）-> OAUTH_TICKET_ALREADY_USED。"""
        s, info = self._to_ticket()
        rid = info["rid"]
        ticket = self.h.client.cookies.get(f"jm_oauth_ticket_{rid}")
        binding = self.h.client.cookies.get(f"jm_oauth_bb_{rid}")
        cookie_header = (f"jm_oauth_ticket_{rid}={ticket}; jm_oauth_bb_{rid}={binding}")
        first = self.h.exchange(rid=rid)
        self.assertEqual(first.status_code, 200)
        # 重放：即使 Cookie 已被清理，攻击者重新提交捕获的票据也必须被拒绝
        replay = self.h.new_client()
        try:
            second = replay.post("/api/v1/auth/oauth/exchange", json={"rid": rid},
                                 headers={"Cookie": cookie_header},
                                 follow_redirects=False)
        finally:
            replay.close()
        self.assertEqual(second.status_code, 400)
        self.assertEqual(error_code(second), "OAUTH_TICKET_ALREADY_USED")

    def test_ticket_double_exchange_race(self):
        """并发双交换（API 层）：只成功一次，另一个被拒绝。"""
        s, info = self._to_ticket()
        ticket = self.h.client.cookies.get(f"jm_oauth_ticket_{info['rid']}")
        binding = self.h.client.cookies.get(f"jm_oauth_bb_{info['rid']}")
        self.assertTrue(ticket and binding)
        cookie_header = (f"jm_oauth_ticket_{info['rid']}={ticket}; "
                         f"jm_oauth_bb_{info['rid']}={binding}")

        def attempt(_: int):
            c = self.h.new_client()
            try:
                r = c.post("/api/v1/auth/oauth/exchange", json={"rid": info["rid"]},
                           headers={"Cookie": cookie_header},
                           follow_redirects=False)
                return r.status_code
            finally:
                c.close()

        with ThreadPoolExecutor(max_workers=4) as pool:
            codes = list(pool.map(attempt, range(4)))
        self.assertEqual(codes.count(200), 1, f"并发交换必须只成功一次：{codes}")
        self.assertEqual(codes.count(400), 3, f"其余必须被拒绝：{codes}")

    def test_exchange_wrong_origin_rejected(self):
        """CSRF：不可信 Origin 的票据交换拒绝（OAUTH_INVALID_REDIRECT）。"""
        s, info = self._to_ticket()
        ex = self.h.exchange(rid=info["rid"], origin="https://evil.example")
        self.assertEqual(ex.status_code, 400)
        self.assertEqual(error_code(ex), "OAUTH_INVALID_REDIRECT")

    def test_exchange_without_ticket_cookie(self):
        s, info = self._to_ticket()
        self.h.client.cookies.delete(f"jm_oauth_ticket_{info['rid']}")
        ex = self.h.exchange(rid=info["rid"])
        self.assertEqual(ex.status_code, 400)
        self.assertEqual(error_code(ex), "OAUTH_TICKET_EXPIRED")

    def test_exchange_without_browser_binding(self):
        s, info = self._to_ticket()
        self.h.client.cookies.delete(f"jm_oauth_bb_{info['rid']}")
        ex = self.h.exchange(rid=info["rid"])
        self.assertEqual(ex.status_code, 400)
        self.assertEqual(error_code(ex), "OAUTH_TICKET_EXPIRED")

    def test_exchange_unknown_ticket_not_leaking_user(self):
        ex = self.h.exchange(rid="deadbeef")
        self.assertEqual(ex.status_code, 400)
        self.assertEqual(error_code(ex), "OAUTH_TICKET_EXPIRED")
        self.assertNotIn("user", ex.text.lower())


class TestBindFlows(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def _password_login(self, username):
        self.h.register(username)
        _user, token = self.h.login(username)
        return token

    def _bind_flow(self, token, subject, code, client=None):
        started = self.h.start(mode="bind", token=token, return_path="/settings",
                               client=client)
        self.assertEqual(started["response"].status_code, 200,
                         started["response"].text)
        self.assertEqual(started["body"]["mode"], "bind")
        self.h.fake.register_code(code, make_identity(subject))
        resp = self.h.callback(rid=started["rid"], state=started["state"],
                               code=code, client=client)
        info = parse_complete_url(resp.headers["location"])
        self.assertEqual(info["mode"], "bind")
        return info

    def test_oauth_unauthorized_binding(self):
        """未登录发起绑定 -> 401 OAUTH_BIND_REQUIRES_AUTH。"""
        r = self.h.client.post("/api/v1/auth/oauth/start",
                               json={"provider": "fake", "mode": "bind",
                                     "return_path": "/settings"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(error_code(r), "OAUTH_BIND_REQUIRES_AUTH")

    def test_bind_full_flow(self):
        token = self._password_login("bind_user1")
        info = self._bind_flow(token, "sub-bind1", "code-b1")
        ex = self.h.exchange(rid=info["rid"], token=token)
        self.assertEqual(ex.status_code, 200, ex.text)
        data = ex.json()["data"]
        self.assertTrue(data["bound"])
        self.assertFalse(data["already_bound"])
        self.assertEqual(data["identity"]["provider"], "fake")

        ids = self.h.client.get("/api/v1/auth/oauth/identities",
                                headers=self.h.auth(token))
        self.assertEqual(len(ids.json()["data"]["items"]), 1)
        self.assertTrue(ids.json()["data"]["password_login_available"])

    def test_oauth_binding_user_changed(self):
        """发起绑定与完成绑定的本站会话不一致 -> 409 OAUTH_SESSION_CHANGED。"""
        token_a = self._password_login("bind_userA")
        info = self._bind_flow(token_a, "sub-switch", "code-sw")
        token_b = self._password_login("bind_userB")
        ex = self.h.exchange(rid=info["rid"], token=token_b)
        self.assertEqual(ex.status_code, 409)
        self.assertEqual(error_code(ex), "OAUTH_SESSION_CHANGED")
        # 两个账号都没有被错误绑定
        for t in (token_a, token_b):
            ids = self.h.client.get("/api/v1/auth/oauth/identities",
                                    headers=self.h.auth(t))
            self.assertEqual(ids.json()["data"]["items"], [])

    def test_oauth_identity_conflict(self):
        """第三方账号抢绑定：身份已绑他人 -> 409 OAUTH_IDENTITY_CONFLICT。"""
        token_a = self._password_login("bind_userC")
        info_a = self._bind_flow(token_a, "sub-grab", "code-g1")
        ex_a = self.h.exchange(rid=info_a["rid"], token=token_a)
        self.assertEqual(ex_a.status_code, 200, ex_a.text)

        token_b = self._password_login("bind_userD")
        info_b = self._bind_flow(token_b, "sub-grab", "code-g2")
        ex_b = self.h.exchange(rid=info_b["rid"], token=token_b)
        self.assertEqual(ex_b.status_code, 409)
        self.assertEqual(error_code(ex_b), "OAUTH_IDENTITY_CONFLICT")

    def test_bind_mode_requires_same_mode_transaction(self):
        """login 事务不得被当作 bind 完成（模式绑定在 state 事务上）。"""
        started = self.h.start()   # login 模式
        self.h.fake.register_code("code-mode", make_identity("sub-mode"))
        resp = self.h.callback(rid=started["rid"], state=started["state"],
                               code="code-mode")
        info = parse_complete_url(resp.headers["location"])
        self.assertEqual(info["mode"], "login")
        token = self._password_login("bind_userE")
        ex = self.h.exchange(rid=info["rid"], token=token)
        # login 事务换出的是新会话，不会把身份绑到当前登录用户头上
        self.assertEqual(ex.status_code, 200, ex.text)
        ids = self.h.client.get("/api/v1/auth/oauth/identities",
                                headers=self.h.auth(token))
        self.assertEqual(ids.json()["data"]["items"], [])

    def test_unbind_flow_and_last_login_method(self):
        """OAuth-only 账号唯一登录方式不可解绑；有密码后可解绑。"""
        started = self.h.start()
        self.h.fake.register_code("code-u1", make_identity("sub-unbind"))
        resp = self.h.callback(rid=started["rid"], state=started["state"],
                               code="code-u1")
        info = parse_complete_url(resp.headers["location"])
        data = self.h.exchange(rid=info["rid"]).json()["data"]
        token = data["token"]

        # 唯一登录方式 -> OAUTH_LAST_LOGIN_METHOD
        r = self.h.client.delete("/api/v1/auth/oauth/identities/fake",
                                 headers=self.h.auth(token))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(error_code(r), "OAUTH_LAST_LOGIN_METHOD")

        # 补设密码后允许解绑
        sp = self.h.client.post("/api/v1/auth/oauth/set-password",
                                json={"new_password": "NewPassw0rd!2026"},
                                headers=self.h.auth(token))
        self.assertEqual(sp.status_code, 200, sp.text)
        r2 = self.h.client.delete("/api/v1/auth/oauth/identities/fake",
                                  headers=self.h.auth(token))
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json()["data"]["unbound"])
        ids = self.h.client.get("/api/v1/auth/oauth/identities",
                                headers=self.h.auth(token))
        self.assertEqual(ids.json()["data"]["items"], [])

    def test_unbind_requires_recent_session(self):
        """安全敏感解绑要求近期重新认证（不依赖长期旧登录态）。"""
        token = self._password_login("bind_userF")
        info = self._bind_flow(token, "sub-recent", "code-rc")
        self.assertEqual(self.h.exchange(rid=info["rid"], token=token).status_code, 200)

        accounts = self.h.biz.accounts
        real_clock = accounts._clock
        from datetime import datetime, timedelta
        accounts._clock = lambda: datetime.utcnow() + timedelta(minutes=45)
        try:
            r = self.h.client.delete("/api/v1/auth/oauth/identities/fake",
                                     headers=self.h.auth(token))
        finally:
            accounts._clock = real_clock
        self.assertEqual(r.status_code, 403)
        self.assertEqual(error_code(r), "FORBIDDEN")

    def test_unbind_other_users_identity_not_found(self):
        token_a = self._password_login("bind_userG")
        info = self._bind_flow(token_a, "sub-owner", "code-ow")
        self.assertEqual(self.h.exchange(rid=info["rid"], token=token_a).status_code, 200)
        ids = self.h.client.get("/api/v1/auth/oauth/identities",
                                headers=self.h.auth(token_a))
        identity_id = ids.json()["data"]["items"][0]["id"]

        token_b = self._password_login("bind_userH")
        r = self.h.client.delete(f"/api/v1/auth/oauth/identities/{identity_id}",
                                 headers=self.h.auth(token_b))
        self.assertEqual(r.status_code, 404)
        # 原绑定仍在
        ids2 = self.h.client.get("/api/v1/auth/oauth/identities",
                                 headers=self.h.auth(token_a))
        self.assertEqual(len(ids2.json()["data"]["items"]), 1)


class TestSecurityLogging(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def test_oauth_secret_not_logged(self):
        """日志白名单：AppSecret / code / state / Token / 票据一律不得出现。"""
        import logging
        with self.assertLogs("job_matching", level=logging.INFO) as cm:
            started = self.h.start()
            self.h.fake.register_code("code-log", make_identity("sub-log"))
            resp = self.h.callback(rid=started["rid"], state=started["state"],
                                   code="code-log")
            info = parse_complete_url(resp.headers["location"])
            self.h.exchange(rid=info["rid"])
        blob = "\n".join(cm.output)
        for secret in (TEST_SECRET, started["state"], "code-log", "fake-at-"):
            self.assertNotIn(secret, blob, f"日志泄露了敏感值：{secret}")
        ticket = self.h.client.cookies.get(f"jm_oauth_ticket_{info['rid']}")
        if ticket:
            self.assertNotIn(ticket, blob)

    def test_api_responses_never_contain_provider_token(self):
        started = self.h.start()
        self.h.fake.register_code("code-resp", make_identity("sub-resp"))
        resp = self.h.callback(rid=started["rid"], state=started["state"],
                               code="code-resp")
        self.assertNotIn("fake-at-", resp.headers["location"])
        info = parse_complete_url(resp.headers["location"])
        ex = self.h.exchange(rid=info["rid"])
        self.assertNotIn("fake-at-", ex.text)
        self.assertNotIn(TEST_SECRET, ex.text)


class TestRateLimit(unittest.TestCase):
    def setUp(self):
        self.h = OAuthHarness()

    def tearDown(self):
        self.h.close()

    def test_oauth_start_rate_limited(self):
        for _ in range(30):
            r = self.h.client.post("/api/v1/auth/oauth/start",
                                   json={"provider": "fake", "mode": "login"})
            self.assertEqual(r.status_code, 200)
        r = self.h.client.post("/api/v1/auth/oauth/start",
                               json={"provider": "fake", "mode": "login"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(error_code(r), "RATE_LIMITED")

    def test_callback_failure_rate_limited(self):
        for _ in range(30):
            r = self.h.client.get(
                "/api/v1/auth/oauth/fake/callback?code=x&state=forged",
                follow_redirects=False)
            info = parse_complete_url(r.headers["location"])
            self.assertEqual(info["status"], "error")
        r = self.h.client.get(
            "/api/v1/auth/oauth/fake/callback?code=x&state=forged",
            follow_redirects=False)
        info = parse_complete_url(r.headers["location"])
        self.assertEqual(info["reason"], "RATE_LIMITED")


if __name__ == "__main__":
    unittest.main()
