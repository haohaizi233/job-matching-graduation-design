# -*- coding: utf-8 -*-
"""授权事务 / 一次性票据存储安全测试（Phase8-A / M4.2-M4.3 + M5）。

覆盖：state 摘要落库、TTL 过期、一次性消费、重放拒绝、Provider/模式不匹配、
浏览器绑定隔离、票据原子消费（并发双交换只成功一次）、错误消息不泄露用户 ID、
历史清理。时钟可快进，不使用 sleep。
"""
from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from _util import MutableClock, ROOT, run_migrations  # noqa: F401

TEST_SECRET = "FAKE_SECRET_FOR_TESTS"


class StoreHarness:
    """临时 SQLite + 真实迁移 + 可快进时钟（只测存储层，不建 HTTP app）。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jm_p8a_store_")
        base = Path(self.tmp.name)
        self.db_url = f"sqlite:///{base / 'store.db'}"
        import os
        os.environ["JM_DATABASE_URL"] = self.db_url
        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        run_migrations(self.db_url)
        self.clock = MutableClock()
        from job_matching.service.oauth.ticket_store import OAuthTicketStore
        from job_matching.service.oauth.transaction_store import OAuthTransactionStore
        self.transactions = OAuthTransactionStore(clock=self.clock)
        self.tickets = OAuthTicketStore(clock=self.clock)
        self._rid_seq = 0
        self.user_id = self.ensure_user("store-user-1")

    def ensure_user(self, user_id: str) -> str:
        """票据 user_id 有外键 -> 先落一个合成用户（临时库，非真实账号）。"""
        from job_matching.infra.persistence import User, get_session_factory
        s = get_session_factory()()
        try:
            if s.query(User).filter(User.id == user_id).first() is None:
                s.add(User(id=user_id, username=f"u_{user_id[:8]}",
                           password_hash=None, role="student", status="active",
                           failed_login_count=0,
                           created_at=self.clock(), updated_at=self.clock()))
                s.commit()
        finally:
            s.close()
        return user_id

    def close(self):
        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        self.tmp.cleanup()

    def make_tx(self, *, state="state-plain-1", rid=None, provider="fake",
                mode="login", ttl=300):
        self._rid_seq += 1
        rid = rid or f"{self._rid_seq:08x}"
        return self.transactions.create(
            rid=rid, provider=provider, mode=mode, state=state,
            browser_binding_digest=f"digest-of-binding-{rid}",
            browser_binding_key=rid,
            redirect_uri="http://127.0.0.1:8000/api/v1/auth/oauth/fake/callback",
            return_path="/dashboard", ttl_seconds=ttl)

    def make_ticket(self, *, mode="login", user_id=None, key="aabbccdd",
                    digest_value="digest-of-binding", ttl=60, payload=None):
        uid = self.ensure_user(user_id or self.user_id)
        return self.tickets.issue(
            mode=mode, user_id=uid,
            browser_binding_digest=digest_value,
            browser_binding_key=key, payload=payload, ttl_seconds=ttl)


class TestAuthTransaction(unittest.TestCase):
    def setUp(self):
        self.h = StoreHarness()

    def tearDown(self):
        self.h.close()

    # ---------------------------------------------------------- 生命周期
    def test_state_lifecycle_and_digest_only(self):
        """库里只落 state 摘要，明文不得持久化。"""
        from job_matching.infra.persistence import (OAuthAuthTransaction,
                                                   get_session_factory)
        from job_matching.service.oauth.security import digest
        self.h.make_tx(state="plain-state-abc", rid="aabbccdd")
        s = get_session_factory()()
        try:
            row = s.query(OAuthAuthTransaction).one()
            self.assertEqual(row.state_digest, digest("plain-state-abc"))
            self.assertNotEqual(row.state_digest, "plain-state-abc")
            self.assertFalse(hasattr(row, "state"), "不得存在 state 明文列")
        finally:
            s.close()
        out = self.h.transactions.consume(state="plain-state-abc", provider="fake")
        self.assertEqual(out["mode"], "login")
        self.assertIsNotNone(out["id"])

    def test_state_expired(self):
        self.h.make_tx(state="st", ttl=300)
        self.h.clock.advance(seconds=301)
        from job_matching.service.oauth.exceptions import StateExpired
        with self.assertRaises(StateExpired):
            self.h.transactions.consume(state="st", provider="fake")

    def test_state_replay_rejected(self):
        self.h.make_tx(state="st")
        self.h.transactions.consume(state="st", provider="fake")
        from job_matching.service.oauth.exceptions import CallbackReplay
        with self.assertRaises(CallbackReplay):
            self.h.transactions.consume(state="st", provider="fake")

    def test_state_mismatch_provider(self):
        self.h.make_tx(state="st", provider="fake")
        from job_matching.service.oauth.exceptions import InvalidState
        with self.assertRaises(InvalidState):
            self.h.transactions.consume(state="st", provider="wechat")

    def test_state_mismatch_mode(self):
        self.h.make_tx(state="st", mode="login")
        from job_matching.service.oauth.exceptions import InvalidState
        with self.assertRaises(InvalidState):
            self.h.transactions.consume(state="st", provider="fake", mode="bind")

    def test_state_missing_or_unknown(self):
        from job_matching.service.oauth.exceptions import InvalidState
        for bad in ("", None, "never-issued"):
            with self.assertRaises(InvalidState):
                self.h.transactions.consume(state=bad, provider="fake")

    def test_browser_binding_isolated_per_transaction(self):
        """多标签页并发授权：每笔事务独立绑定凭据与 key，互不覆盖。"""
        t1 = self.h.make_tx(state="s1", rid="11111111")
        t2 = self.h.make_tx(state="s2", rid="22222222")
        self.assertNotEqual(t1["browser_binding_digest"], t2["browser_binding_digest"])
        self.assertNotEqual(t1["browser_binding_key"], t2["browser_binding_key"])

    def test_cleanup_removes_expired(self):
        self.h.make_tx(state="old", ttl=60)
        self.h.clock.advance(seconds=7200)
        new_tx = self.h.make_tx(state="new", ttl=300)
        removed = self.h.transactions.cleanup(older_than_seconds=3600)
        self.assertGreaterEqual(removed, 1)
        from job_matching.service.oauth.exceptions import InvalidState, StateExpired
        # 清理后旧事务不再可消费（行已删除 -> InvalidState；未删时应 StateExpired）
        with self.assertRaises((StateExpired, InvalidState)):
            self.h.transactions.consume(state="old", provider="fake")
        self.assertEqual(
            self.h.transactions.consume(state="new", provider="fake")["rid"],
            new_tx["rid"])


class TestLoginTicket(unittest.TestCase):
    def setUp(self):
        self.h = StoreHarness()

    def tearDown(self):
        self.h.close()

    def test_ticket_lifecycle(self):
        ticket = self.h.make_ticket(user_id="user-1")
        self.assertGreaterEqual(len(ticket), 40, "票据明文熵不足")
        data = self.h.tickets.consume(ticket=ticket,
                                      browser_binding_digest="digest-of-binding",
                                      browser_binding_key="aabbccdd")
        self.assertEqual(data["user_id"], "user-1")
        self.assertEqual(data["mode"], "login")

    def test_ticket_digest_only_in_db(self):
        from job_matching.infra.persistence import (OAuthLoginTicket,
                                                   get_session_factory)
        from job_matching.service.oauth.security import digest
        ticket = self.h.make_ticket()
        s = get_session_factory()()
        try:
            row = s.query(OAuthLoginTicket).one()
            self.assertEqual(row.ticket_digest, digest(ticket))
            self.assertNotEqual(row.ticket_digest, ticket)
        finally:
            s.close()

    def test_ticket_expired(self):
        ticket = self.h.make_ticket(ttl=60)
        self.h.clock.advance(seconds=61)
        from job_matching.service.oauth.exceptions import TicketExpired
        with self.assertRaises(TicketExpired):
            self.h.tickets.consume(ticket=ticket)

    def test_ticket_replay(self):
        ticket = self.h.make_ticket()
        self.h.tickets.consume(ticket=ticket)
        from job_matching.service.oauth.exceptions import TicketAlreadyUsed
        with self.assertRaises(TicketAlreadyUsed):
            self.h.tickets.consume(ticket=ticket)

    def test_ticket_browser_binding_mismatch(self):
        ticket = self.h.make_ticket()
        from job_matching.service.oauth.exceptions import TicketExpired
        # 绑定凭据不匹配 / 事务 key 不匹配 -> 通用票据错误（不做存在性预言机）
        with self.assertRaises(TicketExpired):
            self.h.tickets.consume(ticket=ticket, browser_binding_digest="wrong")
        with self.assertRaises(TicketExpired):
            self.h.tickets.consume(ticket=ticket, browser_binding_key="99999999")
        with self.assertRaises(TicketExpired):
            self.h.tickets.consume(ticket="")
        with self.assertRaises(TicketExpired):
            self.h.tickets.consume(ticket="never-issued")

    def test_ticket_error_messages_do_not_leak_user_id(self):
        """错误票据不得泄露用户 ID / 账号存在性。"""
        from job_matching.service.oauth.exceptions import (TicketAlreadyUsed,
                                                           TicketExpired)
        secret_user = "user-DO-NOT-LEAK-9911"
        ticket = self.h.make_ticket(user_id=secret_user)
        cases = []
        try:
            self.h.tickets.consume(ticket="unknown-ticket")
        except TicketExpired as e:
            cases.append(e)
        self.h.tickets.consume(ticket=ticket)
        try:
            self.h.tickets.consume(ticket=ticket)
        except TicketAlreadyUsed as e:
            cases.append(e)
        self.assertEqual(len(cases), 2)
        for e in cases:
            self.assertNotIn(secret_user, str(e))
            self.assertNotIn(secret_user, repr(getattr(e, "detail", None)))

    def test_ticket_double_exchange_race(self):
        """并发双交换：原子消费保证只成功一次（其余 OAUTH_TICKET_*）。"""
        from job_matching.service.oauth.exceptions import (TicketAlreadyUsed,
                                                           TicketExpired)
        ticket = self.h.make_ticket(user_id="user-race")
        barrier_times = 8

        def attempt(_: int):
            try:
                self.h.tickets.consume(ticket=ticket)
                return "OK"
            except (TicketAlreadyUsed, TicketExpired):
                return "REJECTED"
            except Exception as e:  # noqa: BLE001
                return f"UNEXPECTED:{type(e).__name__}"

        with ThreadPoolExecutor(max_workers=barrier_times) as pool:
            results = list(pool.map(attempt, range(barrier_times)))
        self.assertEqual(results.count("OK"), 1,
                         f"并发消费必须只成功一次，实际 {results}")
        self.assertEqual(results.count("REJECTED"), barrier_times - 1,
                         f"其余请求必须被拒绝，实际 {results}")

    def test_ticket_cleanup(self):
        self.h.make_ticket(ttl=60)
        self.h.clock.advance(seconds=7200)
        removed = self.h.tickets.cleanup(older_than_seconds=3600)
        self.assertGreaterEqual(removed, 1)

    def test_ticket_mode_validation(self):
        with self.assertRaises(ValueError):
            self.h.make_ticket(mode="admin-takeover")


if __name__ == "__main__":
    unittest.main()
