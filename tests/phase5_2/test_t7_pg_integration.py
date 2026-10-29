# -*- coding: utf-8 -*-
"""T7（B1 门禁，PostgreSQL 集成）：JSON/约束/事务/迁移在 PostgreSQL 上的真实验证。

纪律：
  * SQLite 通过**不代表** PostgreSQL 兼容（JSON 类型、约束、事务与迁移语义有差异）；
  * 未提供 PostgreSQL 环境时本组显式 **NOT_RUN**（skip），绝不冒充 PASS；
  * 提供方式：环境变量 JM_TEST_DATABASE_URL_POSTGRES=
    postgresql+psycopg2://user:pass@host:5432/dbname（密码来自环境/Secret，不入库）。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime

from _util import ROOT, run_downgrade, run_migrations  # noqa: E402


class T7PostgreSQLIntegration(unittest.TestCase):
    def setUp(self):
        self.pg_url = (os.environ.get("JM_TEST_DATABASE_URL_POSTGRES") or "").strip()
        if not self.pg_url:
            self.skipTest("NOT_RUN: 未提供 JM_TEST_DATABASE_URL_POSTGRES；"
                          "SQLite 通过不代表 PostgreSQL 兼容，本组不得计入 PASS")
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            self.skipTest("ENV_INCOMPATIBLE: 缺少 psycopg2，无法连接 PostgreSQL")

    def _engine(self):
        from sqlalchemy import create_engine
        return create_engine(self.pg_url, future=True)

    def test_migrate_and_schema_on_postgresql(self):
        run_migrations(self.pg_url)
        from sqlalchemy import inspect
        eng = self._engine()
        try:
            insp = inspect(eng)
            tables = set(insp.get_table_names())
            for t in ("users", "student_profiles", "recommendation_runs"):
                self.assertIn(t, tables)
            # JSONB 变体在 PostgreSQL 上生效
            cols = {c["name"]: c for c in insp.get_columns("student_profiles")}
            self.assertIn("profile_data", cols)
        finally:
            eng.dispose()

    def test_jsonb_query_and_constraints_on_postgresql(self):
        from sqlalchemy import text
        from job_matching.infra.persistence import (StudentProfile, User,
                                                    get_session_factory)
        from job_matching.service.accounts import hash_password

        run_migrations(self.pg_url)
        os.environ["JM_DATABASE_URL"] = self.pg_url
        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        fac = get_session_factory()
        s = fac()
        try:
            u = User(username="pg_user", password_hash=hash_password("Pg!2026pass"),
                     role="student", status="active", created_at=datetime.utcnow(),
                     updated_at=datetime.utcnow())
            s.add(u)
            s.flush()
            s.add(StudentProfile(user_id=u.id, profile_version=1, confirmed=0,
                                 profile_data={"profile": {"major": {"value": "软件工程"}}},
                                 created_at=datetime.utcnow(),
                                 updated_at=datetime.utcnow()))
            s.commit()
            # JSONB 路径查询（PostgreSQL 特有能力）
            rows = s.execute(text(
                "SELECT id FROM student_profiles "
                "WHERE profile_data->'profile'->'major'->>'value' = :v"),
                {"v": "软件工程"}).fetchall()
            self.assertEqual(len(rows), 1, "JSONB 路径查询未命中")
            # 唯一约束
            from sqlalchemy.exc import IntegrityError
            s.add(StudentProfile(user_id=u.id, profile_version=1, profile_data={},
                                 confirmed=0, created_at=datetime.utcnow(),
                                 updated_at=datetime.utcnow()))
            with self.assertRaises(IntegrityError):
                s.commit()
            s.rollback()
            # 事务回滚不落半成功记录
            before = s.query(StudentProfile).count()
            try:
                s.add(StudentProfile(user_id=u.id, profile_version=2, profile_data={},
                                     confirmed=0, created_at=datetime.utcnow(),
                                     updated_at=datetime.utcnow()))
                s.flush()
                raise RuntimeError("模拟失败事务")
            except RuntimeError:
                s.rollback()
            self.assertEqual(s.query(StudentProfile).count(), before)
        finally:
            s.close()
            dispose_engines()

    def test_downgrade_reupgrade_on_postgresql(self):
        run_migrations(self.pg_url)
        run_downgrade(self.pg_url, "base")
        run_migrations(self.pg_url)
        from sqlalchemy import inspect
        eng = self._engine()
        try:
            self.assertIn("users", set(inspect(eng).get_table_names()))
        finally:
            eng.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
