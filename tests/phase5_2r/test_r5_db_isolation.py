# -*- coding: utf-8 -*-
"""R5（P1-05 门禁）：数据库配置注入与运行时隔离。

不变量：
  * 业务服务以显式 DbSettings.from_url 构造，**不改写进程全局环境变量**；
  * Engine/Session 工厂缓存键包含 (url, echo)，多实例/多库不串库；
  * 不同 database_url 的应用实例数据完全隔离；
  * dispose_engines 后实例仍可正常工作（连接池可重建）。
"""
from __future__ import annotations

import os
import unittest

from _util import SYNTHETIC_JOB_TEXT, BusinessHarness  # noqa: E402


class R5DbInjectionIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r5")
        _u, cls.admin_token = cls.h.login("admin_r5", "Adm1n!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_construction_does_not_mutate_process_env(self):
        before = {k: v for k, v in os.environ.items() if k.startswith("JM_")}
        h2 = BusinessHarness()
        try:
            after = {k: v for k, v in os.environ.items() if k.startswith("JM_")}
            self.assertEqual(before, after,
                             "make_business_services 不得改写 JM_* 环境变量传参")
            self.assertEqual(h2.env_polluted(), [],
                             "夹具构造过程不得新增/改写任何环境变量")
        finally:
            h2.close()

    def test_two_instances_two_databases_no_cross_talk(self):
        h2 = BusinessHarness()
        try:
            # A 库已有管理员与岗位
            r = self.h.create_job(self.admin_token, title="R5-A库岗",
                                  job_description=SYNTHETIC_JOB_TEXT)
            self.assertEqual(r.status_code, 200, r.text)

            # A 库注册用户
            self.h.register("stu_r5_a", "Stu!2026pass")
            _u, token_a = self.h.login("stu_r5_a", "Stu!2026pass")

            # B 库看不到 A 库的用户
            r = h2.client.post("/api/v1/auth/login",
                               json={"username": "stu_r5_a", "password": "Stu!2026pass"})
            self.assertNotEqual(r.status_code, 200,
                                "不同 database_url 的实例不得串库")

            # B 库看不到 A 库的岗位
            admin_b = h2.make_admin("admin_r5_b")
            _u2, token_b = h2.login("admin_r5_b", "Adm1n!2026pass")
            r = h2.client.get("/api/v1/jobs", headers=h2.auth(token_b),
                              params={"q": "R5-A库岗", "include_unpublished": True})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["data"]["total"], 0)

            # A 库数据完好（互不影响）
            r = self.h.client.get("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                                  params={"q": "R5-A库岗", "include_unpublished": True})
            self.assertEqual(r.json()["data"]["total"], 1)
            self.assertIsNotNone(token_a)
            self.assertIsNotNone(admin_b)
        finally:
            h2.close()

    def test_engine_cache_keyed_by_url_and_echo(self):
        from job_matching.infra.persistence import DbSettings, get_engine
        import tempfile
        with tempfile.TemporaryDirectory(prefix="jm_r5_cache_") as td:
            url = f"sqlite:///{td}/cache.db"
            a1 = get_engine(DbSettings.from_url(url))
            a2 = get_engine(DbSettings.from_url(url))
            b = get_engine(DbSettings.from_url(url, echo=True))
            c = get_engine(DbSettings.from_url(url + "?alt=1"))
            self.assertIs(a1, a2, "同 (url, echo) 必须复用同一 Engine")
            self.assertIsNot(a1, b, "echo 不同不得复用缓存")
            self.assertIsNot(a1, c, "url 不同不得复用缓存")
            for e in (a1, b, c):
                e.dispose()

    def test_dispose_engines_then_requests_still_work(self):
        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        r = self.h.client.get("/api/v1/jobs", headers=self.h.auth(self.admin_token))
        self.assertEqual(r.status_code, 200, r.text)
        r = self.h.client.get("/api/v1/auth/me", headers=self.h.auth(self.admin_token))
        self.assertEqual(r.status_code, 200, r.text)

    def test_session_factory_accepts_explicit_settings(self):
        from job_matching.infra.persistence import DbSettings, get_session_factory
        st = DbSettings.from_url(self.h.db_url)
        fac = get_session_factory(st)
        s = fac()
        try:
            s.execute(__import__("sqlalchemy").text("SELECT 1"))
        finally:
            s.close()
        # 显式 settings 与默认缓存命中同一工厂
        self.assertIs(fac, get_session_factory(DbSettings.from_url(self.h.db_url)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
