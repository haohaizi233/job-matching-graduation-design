# -*- coding: utf-8 -*-
"""T2（B2 门禁，链路A）：注册 -> 密码哈希 -> 登录 -> 当前用户 -> 权限 -> 登出 -> 会话失效。

安全断言：
  * 密码只存 Argon2id 哈希；响应/日志不含密码哈希与 Token 明文；
  * 登录失败 5 次锁定（423），无效/过期 Token 一律 401；
  * 公开注册只能得到 student；管理端点对学生 403；
  * 服务端会话登出立即失效。
"""
from __future__ import annotations

import logging
import unittest

from _util import BusinessHarness  # noqa: E402


class T2AuthChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 链路 A
    def test_link_a_full_auth_chain(self):
        h = self.h
        user = h.register("alice", "Al1ce!2026pass", email="alice@synth.example")
        self.assertEqual(user["role"], "student")
        self.assertNotIn("password_hash", user)

        # 密码哈希断言（直接查库：哈希存在、不是明文、是 Argon2id）
        from job_matching.infra.persistence import User, get_session
        session = get_session()
        try:
            row = session.query(User).filter(User.username == "alice").first()
        finally:
            session.close()
        self.assertTrue(row.password_hash.startswith("$argon2id$"),
                        f"密码哈希算法非 Argon2id: {row.password_hash[:16]}")
        self.assertNotIn("Al1ce!2026pass", row.password_hash)

        me_user, token = h.login("alice", "Al1ce!2026pass")
        self.assertEqual(me_user["username"], "alice")
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["user"]["username"], "alice")

        # 会话 Token 只存摘要
        from job_matching.infra.persistence import AuthSession
        session = get_session()
        try:
            sessions = session.query(AuthSession).all()
        finally:
            session.close()
        self.assertTrue(sessions)
        for s in sessions:
            self.assertNotEqual(s.token_sha256, token, "Token 明文不得入库")

        # 登出 -> 会话立即失效
        r = h.client.post("/api/v1/auth/logout", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["data"]["revoked"])
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token))
        self.assertEqual(r.status_code, 401, r.text)

    # ---------------------------------------------------------- 凭据与策略
    def test_password_policy_rejects_weak_password(self):
        for weak in ("short1", "alllettersonly", "1234567890"):
            r = self.h.client.post("/api/v1/auth/register",
                                   json={"username": f"weak_{weak[:5]}", "password": weak})
            self.assertEqual(r.status_code, 422, f"{weak} 未被拒绝: {r.text}")
            self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_duplicate_username_is_conflict(self):
        self.h.register("dup_user", "Dup!2026pass")
        r = self.h.client.post("/api/v1/auth/register",
                               json={"username": "dup_user", "password": "Dup!2026pass2"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()["error"]["code"], "CONFLICT")

    def test_register_ignores_admin_role(self):
        """公开注册即使声称 role=admin 也只得到 student（管理员走内部种子）。"""
        r = self.h.client.post("/api/v1/auth/register",
                               json={"username": "sneaky", "password": "Sneaky!2026x",
                                     "role": "admin"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["user"]["role"], "student")

    def test_invalid_credentials_401(self):
        self.h.register("bob", "B0b!2026pass")
        r = self.h.client.post("/api/v1/auth/login",
                               json={"username": "bob", "password": "wrong-pass-2026"})
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(r.json()["error"]["code"], "AUTH_INVALID_CREDENTIALS")

    def test_missing_or_invalid_token_401(self):
        r = self.h.client.get("/api/v1/auth/me")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["code"], "AUTH_REQUIRED")
        r = self.h.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
        self.assertEqual(r.status_code, 401, r.text)

    def test_login_failure_lockout(self):
        self.h.register("locky", "L0cky!2026pass")
        codes = []
        for _ in range(6):
            r = self.h.client.post("/api/v1/auth/login",
                                   json={"username": "locky", "password": "bad-pass-2026x"})
            codes.append(r.status_code)
        self.assertIn(423, codes, f"连续失败未触发锁定: {codes}")
        self.assertEqual(codes[-1], 423)
        # 锁定期间即使密码正确也拒绝
        r = self.h.client.post("/api/v1/auth/login",
                               json={"username": "locky", "password": "L0cky!2026pass"})
        self.assertEqual(r.status_code, 423, r.text)
        self.assertEqual(r.json()["error"]["code"], "AUTH_ACCOUNT_LOCKED")

    def test_expired_token_rejected(self):
        self.h.register("timer", "T1mer!2026pass")
        _u, token = self.h.login("timer", "T1mer!2026pass")
        r = self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))
        self.assertEqual(r.status_code, 200)
        # 时钟快进超过 TTL（注入时钟，不 sleep）
        from datetime import datetime, timedelta
        self.h.biz.accounts._clock = lambda: datetime.utcnow() + timedelta(hours=13)
        try:
            r = self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))
            self.assertEqual(r.status_code, 401, r.text)
            self.assertEqual(r.json()["error"]["code"], "AUTH_TOKEN_EXPIRED")
        finally:
            from job_matching.service.accounts import _now
            self.h.biz.accounts._clock = _now

    # ---------------------------------------------------------- 泄漏防护
    def test_no_password_or_token_leak_in_responses(self):
        self.h.register("leaky", "Leaky!2026pass")
        r = self.h.client.post("/api/v1/auth/login",
                               json={"username": "leaky", "password": "Leaky!2026pass"})
        token = r.json()["data"]["token"]
        for resp in (r, self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))):
            body = resp.text
            self.assertNotIn("password_hash", body)
            self.assertNotIn("$argon2", body)
            self.assertNotIn("Leaky!2026pass", body)

    def test_token_not_written_to_logs(self):
        records: list[str] = []

        class _Cap(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        log = logging.getLogger("job_matching.service")
        handler = _Cap()
        old_level = log.level
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)
        try:
            self.h.register("loggy", "L0ggy!2026pass")
            r = self.h.client.post("/api/v1/auth/login",
                                   json={"username": "loggy", "password": "L0ggy!2026pass"})
            token = r.json()["data"]["token"]
            self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))
        finally:
            log.removeHandler(handler)
            log.setLevel(old_level)
        joined = "\n".join(records)
        self.assertNotIn(token, joined, "Token 明文进入日志")
        self.assertNotIn("L0ggy!2026pass", joined, "密码进入日志")

    # ---------------------------------------------------------- 权限
    def test_student_cannot_use_admin_endpoints(self):
        self.h.register("sty", "Sty!2026pass")
        _u, token = self.h.login("sty", "Sty!2026pass")
        r = self.h.client.post("/api/v1/jobs", headers=self.h.auth(token),
                               json={"title": "x", "job_description": "y"})
        self.assertEqual(r.status_code, 403, r.text)
        self.assertEqual(r.json()["error"]["code"], "FORBIDDEN")
        r = self.h.client.post("/api/v1/jobs/import", headers=self.h.auth(token),
                               json={"items": [{"title": "x", "job_description": "y"}]})
        self.assertEqual(r.status_code, 403, r.text)

    def test_admin_seed_can_login(self):
        self.h.make_admin("admin_t2")
        _u, token = self.h.login("admin_t2", "Adm1n!2026pass")
        r = self.h.client.get("/api/v1/auth/me", headers=self.h.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["user"]["role"], "admin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
