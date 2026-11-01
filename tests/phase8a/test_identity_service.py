# -*- coding: utf-8 -*-
"""身份关联 / 账号合并纪律测试（Phase8-A / M4.1 + M5.3）。

覆盖：
  * OAuth-only 账号（password_hash=NULL、role=student）与密码登录拒绝；
  * 昵称 / 未验证邮箱**永不**参与账号识别（不合并）；
  * (provider, client_id, subject) 唯一性：DB 约束 + 并发注册回退；
  * 绑定策略：同一身份只绑一个账号、同 Provider 每账号一个身份、幂等绑定；
  * 解绑：最后登录方式保护、非本人身份防枚举。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from _util import ROOT, run_migrations  # noqa: F401
from fake_provider import make_identity

from job_matching.service.errors import ServiceError
from job_matching.service.oauth.exceptions import (IdentityConflict,
                                                   LastLoginMethod)


class IdentityHarness:
    """临时 SQLite + AccountService + OAuthIdentityService（无 HTTP 层）。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jm_p8a_ident_")
        base = Path(self.tmp.name)
        self.db_url = f"sqlite:///{base / 'ident.db'}"
        os.environ["JM_DATABASE_URL"] = self.db_url
        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        run_migrations(self.db_url)
        from job_matching.service.accounts import AccountService
        from job_matching.service.oauth.identity_service import OAuthIdentityService
        self.accounts = AccountService()
        self.identities = OAuthIdentityService()
        self._n = 0

    def close(self):
        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        self.tmp.cleanup()

    def new_username(self, prefix="pw_user") -> str:
        self._n += 1
        return f"{prefix}_{self._n}"

    def register(self, username=None, email=None) -> dict:
        username = username or self.new_username()
        self.accounts.register(username=username, password="Passw0rd!2026",
                               email=email)
        return self.accounts.authenticate(username=username,
                                          password="Passw0rd!2026")


class TestOAuthOnlyAccount(unittest.TestCase):
    def setUp(self):
        self.h = IdentityHarness()

    def tearDown(self):
        self.h.close()

    def _oauth_user(self, subject="sub-1", **kw):
        out = self.h.identities.resolve_or_create_user(make_identity(subject, **kw))
        return out

    def test_oauth_default_student_role(self):
        from job_matching.infra.persistence import User, get_session_factory
        out = self._oauth_user("sub-role")
        s = get_session_factory()()
        try:
            user = s.query(User).filter(User.id == out["user_id"]).one()
            self.assertEqual(user.role, "student")
            self.assertEqual(user.status, "active")
            self.assertIsNone(user.password_hash,
                              "纯 OAuth 账号不得有占位密码/固定密码")
        finally:
            s.close()

    def test_oauth_username_generated_not_nickname(self):
        from job_matching.infra.persistence import User, get_session_factory
        out = self._oauth_user("sub-name", display_name="张三丰")
        s = get_session_factory()()
        try:
            user = s.query(User).filter(User.id == out["user_id"]).one()
            self.assertTrue(user.username.startswith("fake_"), user.username)
            self.assertNotEqual(user.username, "张三丰")
            self.assertIsNone(user.email)
        finally:
            s.close()

    def test_oauth_only_password_login_rejected(self):
        """password_hash=NULL：密码登录拒绝且响应与"密码错误"完全一致。"""
        out = self._oauth_user("sub-pw")
        from job_matching.infra.persistence import User, get_session_factory
        s = get_session_factory()()
        try:
            username = s.query(User).filter(User.id == out["user_id"]).one().username
        finally:
            s.close()
        try:
            self.h.accounts.authenticate(username=username, password="whatever")
            self.fail("纯 OAuth 账号不得能用密码登录")
        except ServiceError as e:
            oauth_err = (e.code, e.http_status, e.message)
        try:
            self.h.accounts.authenticate(username="ghost_user_xx", password="whatever")
            self.fail("未知账号应拒绝")
        except ServiceError as e:
            ghost_err = (e.code, e.http_status, e.message)
        self.assertEqual(oauth_err, ghost_err,
                         "纯 OAuth 账号的密码登录响应不得泄露账号存在性")

    def test_change_password_requires_old_password(self):
        out = self._oauth_user("sub-chg")
        with self.assertRaises(ServiceError):
            self.h.accounts.change_password(
                user_id=out["user_id"], old_password="whatever",
                new_password="NewPassw0rd!2026")

    def test_set_password_only_for_oauth_only_accounts(self):
        out = self._oauth_user("sub-setpw")
        result = self.h.accounts.set_password(
            user_id=out["user_id"], new_password="NewPassw0rd!2026")
        self.assertTrue(result["password_set"])
        s_user = self.h.accounts.authenticate(
            username=self._username_of(out["user_id"]), password="NewPassw0rd!2026")
        self.assertEqual(s_user["id"], out["user_id"])
        # 已有密码的账号不得走 set-password 绕过原密码校验
        with self.assertRaises(ServiceError):
            self.h.accounts.set_password(user_id=out["user_id"],
                                         new_password="OtherPassw0rd!2026")

    def _username_of(self, user_id: str) -> str:
        from job_matching.infra.persistence import User, get_session_factory
        s = get_session_factory()()
        try:
            return s.query(User).filter(User.id == user_id).one().username
        finally:
            s.close()


class TestNoAutoMerge(unittest.TestCase):
    """test_oauth_login_does_not_merge_by_*：禁止昵称/邮箱驱动的自动合并。"""

    def setUp(self):
        self.h = IdentityHarness()

    def tearDown(self):
        self.h.close()

    def test_oauth_login_does_not_merge_by_nickname(self):
        existing = self.h.register(username="alice")
        out = self.h.identities.resolve_or_create_user(
            make_identity("sub-nick", display_name="alice"))
        self.assertNotEqual(out["user_id"], existing["id"],
                            "昵称等于本站用户名不得触发合并")
        self.assertTrue(out["created"])

    def test_oauth_login_does_not_merge_by_unverified_email(self):
        existing = self.h.register(username="bob", email="bob@synthetic.test")
        out = self.h.identities.resolve_or_create_user(
            make_identity("sub-mail", email="bob@synthetic.test",
                          email_verified=False))
        self.assertNotEqual(out["user_id"], existing["id"],
                            "未验证邮箱不得触发自动绑定")
        self.assertFalse(out["created"] is False)

    def test_oauth_login_does_not_merge_by_verified_email(self):
        """即便邮箱标记已验证，也不得自动绑定既有账号（必须用户主动绑定）。"""
        existing = self.h.register(username="carol", email="carol@synthetic.test")
        out = self.h.identities.resolve_or_create_user(
            make_identity("sub-mail2", email="carol@synthetic.test",
                          email_verified=True))
        self.assertNotEqual(out["user_id"], existing["id"])

    def test_same_identity_login_reuses_account(self):
        first = self.h.identities.resolve_or_create_user(make_identity("sub-same"))
        second = self.h.identities.resolve_or_create_user(
            make_identity("sub-same", display_name="改了昵称"))
        self.assertEqual(first["user_id"], second["user_id"])
        self.assertFalse(second["created"])

    def test_same_subject_different_appid_is_distinct_identity(self):
        """不同 AppID 的 OpenID 语义不同 -> 不同命名空间，不得碰撞。"""
        a = self.h.identities.resolve_or_create_user(
            make_identity("sub-ns", client_id="app-A"))
        b = self.h.identities.resolve_or_create_user(
            make_identity("sub-ns", client_id="app-B"))
        self.assertNotEqual(a["user_id"], b["user_id"])

    def test_same_subject_different_provider_is_distinct_identity(self):
        a = self.h.identities.resolve_or_create_user(
            make_identity("sub-x", provider="fake"))
        b = self.h.identities.resolve_or_create_user(
            make_identity("sub-x", provider="fake2"))
        self.assertNotEqual(a["user_id"], b["user_id"])


class TestBindingPolicy(unittest.TestCase):
    def setUp(self):
        self.h = IdentityHarness()

    def tearDown(self):
        self.h.close()

    def test_oauth_identity_conflict(self):
        """同一第三方身份绑定第二个本站账号 -> 显式 409 冲突。"""
        u1 = self.h.identities.resolve_or_create_user(make_identity("sub-bind"))
        u2 = self.h.register(username="dave")
        with self.assertRaises(IdentityConflict):
            self.h.identities.bind_identity(
                user_id=u2["id"],
                identity=make_identity("sub-bind", display_name=None))
        # 且原绑定保持不变
        items = self.h.identities.list_identities(u1["user_id"])
        self.assertEqual(len(items["items"]), 1)

    def test_bind_is_idempotent_for_same_user(self):
        u1 = self.h.identities.resolve_or_create_user(make_identity("sub-idem"))
        out = self.h.identities.bind_identity(
            user_id=u1["user_id"], identity=make_identity("sub-idem"))
        self.assertTrue(out["already_bound"])

    def test_one_identity_per_provider_policy(self):
        """同一 Provider 下每账号最多 1 个身份（超出显式冲突，不静默多绑）。"""
        u = self.h.register(username="erin")
        self.h.identities.bind_identity(user_id=u["id"],
                                        identity=make_identity("sub-p1"))
        with self.assertRaises(IdentityConflict):
            self.h.identities.bind_identity(user_id=u["id"],
                                            identity=make_identity("sub-p2"))
        # 不同 Provider 允许并存
        self.h.identities.bind_identity(user_id=u["id"],
                                        identity=make_identity("sub-p3",
                                                               provider="fake2"))
        self.assertEqual(len(self.h.identities.list_identities(u["id"])["items"]), 2)

    def test_oauth_duplicate_concurrent_register(self):
        """并发重复注册（先查后插竞态）：DB 唯一约束兜底 -> 同一账号，不重复建。"""
        first = self.h.identities.resolve_or_create_user(make_identity("sub-race"))
        svc = self.h.identities
        orig_get = svc._repo.get
        calls = {"n": 0}

        def racy_get(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return None     # 模拟竞态窗口：查询时映射尚不可见
            return orig_get(**kw)

        svc._repo.get = racy_get
        try:
            second = svc.resolve_or_create_user(make_identity("sub-race"))
        finally:
            svc._repo.get = orig_get
        self.assertFalse(second["created"])
        self.assertEqual(second["user_id"], first["user_id"])
        # 底层唯一约束仍然成立
        with self.assertRaises(IdentityConflict):
            svc._repo.insert(user_id=self.h.register(username="fred")["id"],
                             provider="fake", client_id="fake-appid",
                             subject="sub-race")


class TestUnbind(unittest.TestCase):
    def setUp(self):
        self.h = IdentityHarness()

    def tearDown(self):
        self.h.close()

    def test_oauth_last_login_method_cannot_unbind(self):
        out = self.h.identities.resolve_or_create_user(make_identity("sub-last"))
        with self.assertRaises(LastLoginMethod):
            self.h.identities.unbind_identity(user_id=out["user_id"],
                                              provider="fake")

    def test_unbind_allowed_when_password_exists(self):
        u = self.h.register(username="grace")
        self.h.identities.bind_identity(user_id=u["id"],
                                        identity=make_identity("sub-g"))
        result = self.h.identities.unbind_identity(user_id=u["id"], provider="fake")
        self.assertTrue(result["unbound"])
        self.assertEqual(self.h.identities.list_identities(u["id"])["items"], [])

    def test_unbind_allowed_when_other_identity_exists(self):
        out = self.h.identities.resolve_or_create_user(
            make_identity("sub-two1", provider="fake"))
        self.h.identities.bind_identity(
            user_id=out["user_id"],
            identity=make_identity("sub-two2", provider="fake2"))
        result = self.h.identities.unbind_identity(user_id=out["user_id"],
                                                   provider="fake")
        self.assertTrue(result["unbound"])
        left = self.h.identities.list_identities(out["user_id"])["items"]
        self.assertEqual([i["provider"] for i in left], ["fake2"])

    def test_unbind_other_users_identity_hidden(self):
        """非本人 identity_id -> NOT_FOUND（防枚举），且不删除任何映射。"""
        u1 = self.h.identities.resolve_or_create_user(make_identity("sub-h1"))
        u2 = self.h.register(username="henry")
        target = self.h.identities.list_identities(u1["user_id"])["items"][0]
        with self.assertRaises(ServiceError) as ctx:
            self.h.identities.unbind_identity(user_id=u2["id"],
                                              identity_id=target["id"])
        self.assertEqual(ctx.exception.code, "NOT_FOUND")
        self.assertEqual(len(self.h.identities.list_identities(u1["user_id"])["items"]), 1)


if __name__ == "__main__":
    unittest.main()
