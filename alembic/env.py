# -*- coding: utf-8 -*-
"""Alembic 迁移环境（Phase5-2）。

连接串来源：环境变量 JM_DATABASE_URL（经 job_matching.infra.persistence.DbSettings），
禁止在仓库内写死连接串或密码。

支持：
  * 在线模式：alembic upgrade head / downgrade -1；
  * 离线模式：alembic upgrade head --sql 生成 SQL 脚本（审计用）。
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from job_matching.infra.persistence import Base, DbSettings  # noqa: E402
from job_matching.infra.persistence import models as _models  # noqa: E402,F401  注册全部表

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_db_settings = DbSettings.from_env()
config.set_main_option("sqlalchemy.url", _db_settings.url)


def run_migrations_offline() -> None:
    context.configure(
        url=_db_settings.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
