# -*- coding: utf-8 -*-
"""OAuth PostgreSQL 集成测试（Phase8-A / M3 + M9）。

纪律（与 tests/phase5_2/test_t7_pg_integration.py 同口径）：
  * SQLite 通过**不代表** PostgreSQL 兼容（JSON/约束/事务语义有差异）；
  * 未提供 PostgreSQL 环境时本组显式 **NOT_RUN**（skip），绝不冒充 PASS；
  * 提供方式：环境变量 JM_TEST_DATABASE_URL_POSTGRES=
    postgresql+psycopg2://user:pass@host:5432/dbname（密码来自环境 Secret，不入库）。

覆盖：Alembic 迁移 / password_hash 可空 / 唯一约束 / 外键 / OAuth-only 用户创建 /
登录-绑定-解绑链路 / 事务回滚不留半成功记录。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime

from _util import (OAuthHarness, ROOT, reset_pg_schema, run_downgrade,  # noqa: F401
                   run_migrations)
from fake_provider import make_identity  # noqa: F401

PG_ENV = "JM_TEST_DATABASE_URL_POSTGRES"
# Phase8-A 迁移的前一个版本（downgrade 目标：只回滚 e8a0f1c2d3a4 本轮迁移）
PRE_PHASE8A_REVISION = "d7e8f9a0b1c2"


class PGIntegrationBase(unittest.TestCase):
    def setUp(self):
        self.pg_url = (os.environ.get(PG_ENV) or "").strip()
        if not self.pg_url:
            self.skipTest("NOT_RUN: 未提供 JM_TEST_DATABASE_URL_POSTGRES；"
                          "SQLite 通过不代表 PostgreSQL 兼容，本组不得计入 PASS")
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            self.skipTest("ENV_INCOMPATIBLE: 缺少 psycopg2，无法连接 PostgreSQL")
        # 每个用例重建干净 schema：
        # downgrade 有「存在纯 OAuth 账号拒绝回滚」的生产安全护栏（不得为测试
        # 削弱），用例间清理改用整库 schema 硬重置；downgrade 双向由
        # test_downgrade_guard_and_rollback 专门验证。
        reset_pg_schema(self.pg_url)
        run_migrations(self.pg_url)

    def tearDown(self):
        # 本组会制造 password_hash IS NULL 的纯 OAuth 账号（迁移安全护栏的
        # 触发条件），用例结束必须把共享测试库清干净，绝不给其它回归套件
        # （phase5_2 T7 / phase5_2r R9 的 downgrade 用例）留下护栏阻塞状态。
        if getattr(self, "pg_url", ""):
            reset_pg_schema(self.pg_url)

    def _harness(self) -> OAuthHarness:
        return OAuthHarness(database_url=self.pg_url)


class TestPgMigration(PGIntegrationBase):
    def test_oauth_tables_and_nullable_password(self):
        from sqlalchemy import inspect
        from sqlalchemy import create_engine
        eng = create_engine(self.pg_url, future=True)
        try:
            insp = inspect(eng)
            tables = set(insp.get_table_names())
            for t in ("oauth_identities", "oauth_auth_transactions",
                      "oauth_login_tickets", "users"):
                self.assertIn(t, tables, f"缺少表 {t}")
            cols = {c["name"]: c for c in insp.get_columns("users")}
            self.assertTrue(cols["password_hash"]["nullable"],
                            "password_hash 必须可空（纯 OAuth 账号）")
        finally:
            eng.dispose()

    def test_unique_constraint_and_fk(self):
        from sqlalchemy.exc import IntegrityError
        from job_matching.infra.persistence import (OAuthIdentity, User,
                                                   get_session_factory)
        from job_matching.service.accounts import hash_password
        fac = get_session_factory()
        s = fac()
        try:
            u1 = User(username="pg_u1", password_hash=hash_password("Pg!2026pass"),
                      role="student", status="active",
                      created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            u2 = User(username="pg_u2", password_hash=hash_password("Pg!2026pass"),
                      role="student", status="active",
                      created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            s.add_all([u1, u2])
            s.flush()
            s.add(OAuthIdentity(user_id=u1.id, provider="qq", client_id="app-1",
                                subject="oid-1", created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()))
            s.commit()
            # 唯一约束 (provider, client_id, subject)
            s.add(OAuthIdentity(user_id=u2.id, provider="qq", client_id="app-1",
                                subject="oid-1", created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()))
            with self.assertRaises(IntegrityError):
                s.commit()
            s.rollback()
            # 不同 client_id 不碰撞
            s.add(OAuthIdentity(user_id=u2.id, provider="qq", client_id="app-2",
                                subject="oid-1", created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()))
            s.commit()
            # 外键：不存在的 user_id 必须拒绝
            s.add(OAuthIdentity(user_id="no-such-user", provider="qq",
                                client_id="app-3", subject="oid-9",
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()))
            with self.assertRaises(IntegrityError):
                s.commit()
            s.rollback()
        finally:
            s.close()

    def test_transaction_rollback_leaves_no_partial_rows(self):
        from job_matching.infra.persistence import (OAuthAuthTransaction,
                                                   get_session_factory)
        fac = get_session_factory()
        s = fac()
        try:
            before = s.query(OAuthAuthTransaction).count()
            s.add(OAuthAuthTransaction(
                rid="pgtx0001", provider="fake", mode="login",
                state_digest="d" * 64, browser_binding_digest="b",
                browser_binding_key="k", redirect_uri="https://x/cb",
                return_path="/dashboard", created_at=datetime.utcnow(),
                expires_at=datetime.utcnow()))
            s.flush()
            raise RuntimeError("模拟业务失败")
        except RuntimeError:
            s.rollback()
        finally:
            s.close()
        s2 = fac()
        try:
            self.assertEqual(s2.query(OAuthAuthTransaction).count(), before,
                             "失败事务必须整体回滚")
        finally:
            s2.close()

    def test_downgrade_guard_and_rollback(self):
        """回滚正确性（PostgreSQL）：
        1) 存在纯 OAuth 账号（password_hash IS NULL）时 downgrade 被安全护栏拒绝；
        2) 账号处置（设置本站密码）后 downgrade 成功，OAuth 三表删除且
           password_hash 收回 NOT NULL，旧账号数据不丢失。
        """
        from sqlalchemy import create_engine, inspect, text as sa_text
        from job_matching.infra.persistence import (User, dispose_engines,
                                                   get_session_factory)
        from job_matching.service.accounts import hash_password

        fac = get_session_factory()
        s = fac()
        try:
            s.add(User(username="pg_oauth_only", password_hash=None,
                       role="student", status="active",
                       created_at=datetime.utcnow(),
                       updated_at=datetime.utcnow()))
            s.commit()
        finally:
            s.close()

        with self.assertRaises(RuntimeError):
            run_downgrade(self.pg_url, PRE_PHASE8A_REVISION)
        # 护栏拒绝后 schema 不受影响（OAuth 表仍在，可继续使用）
        eng = create_engine(self.pg_url, future=True)
        try:
            self.assertIn("oauth_identities", set(inspect(eng).get_table_names()))
        finally:
            eng.dispose()

        # 运维处置：为纯 OAuth 账号设置本站密码后，回滚被允许
        s = fac()
        try:
            u = s.query(User).filter_by(username="pg_oauth_only").one()
            u.password_hash = hash_password("Pg!2026pass")
            s.commit()
        finally:
            s.close()
        dispose_engines()

        run_downgrade(self.pg_url, PRE_PHASE8A_REVISION)
        eng = create_engine(self.pg_url, future=True)
        try:
            insp = inspect(eng)
            tables = set(insp.get_table_names())
            for t in ("oauth_identities", "oauth_auth_transactions",
                      "oauth_login_tickets"):
                self.assertNotIn(t, tables, f"downgrade 后 {t} 应已删除")
            cols = {c["name"]: c for c in insp.get_columns("users")}
            self.assertFalse(cols["password_hash"]["nullable"],
                             "downgrade 后 password_hash 必须收回 NOT NULL")
            # 旧账号数据不丢失
            with eng.connect() as conn:
                n = conn.execute(sa_text(
                    "SELECT COUNT(*) FROM users WHERE username='pg_oauth_only'"
                )).scalar()
            self.assertEqual(n, 1, "downgrade 不得删号")
        finally:
            eng.dispose()

        # 恢复 head，不影响后续用例
        dispose_engines()
        run_migrations(self.pg_url)


class TestPgOAuthFlow(PGIntegrationBase):
    def test_oauth_only_user_and_login_chain_on_postgresql(self):
        h = self._harness()
        try:
            s = h.start()
            h.fake.register_code("pg-code-1", make_identity("pg-sub-1"))
            from _util import parse_complete_url
            resp = h.callback(rid=s["rid"], state=s["state"], code="pg-code-1")
            info = parse_complete_url(resp.headers["location"])
            self.assertEqual(info["status"], "ok", info)
            data = h.exchange(rid=info["rid"]).json()["data"]
            self.assertEqual(data["user"]["role"], "student")
            token = data["token"]

            me = h.client.get("/api/v1/auth/me", headers=h.auth(token))
            self.assertEqual(me.status_code, 200)

            # 同一身份再次登录 -> 同一账号
            h.client.cookies.clear()
            s2 = h.start()
            h.fake.register_code("pg-code-2", make_identity("pg-sub-1"))
            resp2 = h.callback(rid=s2["rid"], state=s2["state"], code="pg-code-2")
            info2 = parse_complete_url(resp2.headers["location"])
            data2 = h.exchange(rid=info2["rid"]).json()["data"]
            self.assertEqual(data2["user"]["id"], data["user"]["id"])

            # 纯 OAuth 账号拒绝密码登录
            r = h.client.post("/api/v1/auth/login",
                              json={"username": data["user"]["username"],
                                    "password": "whatever"})
            self.assertEqual(r.status_code, 401)

            # 最后登录方式不可解绑
            bad = h.client.delete("/api/v1/auth/oauth/identities/fake",
                                  headers=h.auth(data2["token"]))
            self.assertEqual(bad.status_code, 403)
            self.assertEqual(bad.json()["error"]["code"], "OAUTH_LAST_LOGIN_METHOD")
        finally:
            h.close()

    def test_bind_and_unbind_on_postgresql(self):
        h = self._harness()
        try:
            h.register("pg_bind_user")
            _user, token = h.login("pg_bind_user")
            s = h.start(mode="bind", token=token)
            h.fake.register_code("pg-bind-code", make_identity("pg-bind-sub"))
            from _util import parse_complete_url
            resp = h.callback(rid=s["rid"], state=s["state"], code="pg-bind-code")
            info = parse_complete_url(resp.headers["location"])
            self.assertEqual(info["mode"], "bind")
            ex = h.exchange(rid=info["rid"], token=token)
            self.assertEqual(ex.status_code, 200, ex.text)
            self.assertTrue(ex.json()["data"]["bound"])

            # 冲突：同一第三方身份绑第二个账号 -> 409
            h.register("pg_bind_user2")
            _u2, token2 = h.login("pg_bind_user2")
            s2 = h.start(mode="bind", token=token2)
            h.fake.register_code("pg-bind-code-2", make_identity("pg-bind-sub"))
            resp2 = h.callback(rid=s2["rid"], state=s2["state"], code="pg-bind-code-2")
            info2 = parse_complete_url(resp2.headers["location"])
            ex2 = h.exchange(rid=info2["rid"], token=token2)
            self.assertEqual(ex2.status_code, 409)
            self.assertEqual(ex2.json()["error"]["code"], "OAUTH_IDENTITY_CONFLICT")

            # 有密码账号可以解绑
            ok = h.client.delete("/api/v1/auth/oauth/identities/fake",
                                 headers=h.auth(token))
            self.assertEqual(ok.status_code, 200, ok.text)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
