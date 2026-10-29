# -*- coding: utf-8 -*-
"""数据库连接与会话管理（配置驱动，SQLite / PostgreSQL 双后端）。

配置（环境变量）：
  JM_DATABASE_URL   SQLAlchemy 连接串。
                    默认 sqlite:///<项目根>/data/private/dev.db（本地开发）。
                    生产使用 PostgreSQL，例如 postgresql+psycopg2://user:pass@host/db
                    （密码来自部署环境/Secret，**绝不写入 Git**）。
  JM_DB_ECHO        1 输出 SQL（仅调试；生产禁止开启）。

事务纪律：
  * `session_scope()` 提供"要么整体提交、要么整体回滚"的事务边界；
  * 任何异常 -> rollback -> 重新抛出；调用方不得吞掉异常后继续用该 session；
  * 测试中可用 `session_scope()` 验证"失败事务回滚"不产生半成功记录。
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ...core import ROOT

DEFAULT_SQLITE_PATH = ROOT / "data" / "private" / "dev.db"

# 会话来源：既可传 DbSettings（按配置解析），也可直接注入 sessionmaker/工厂（依赖注入 & 测试）
SessionFactoryLike = "DbSettings | sessionmaker | Callable[[], Session] | None"


class Base(DeclarativeBase):
    """ORM 声明基类（全部业务表在 models.py 注册）。"""


@dataclass(frozen=True)
class DbSettings:
    """数据库配置（只读；来自环境，禁止硬编码连接串）。"""

    url: str
    echo: bool = False

    @classmethod
    def from_env(cls, env: dict | None = None) -> "DbSettings":
        """从环境变量构建配置（**配置构建边界**，业务方法不得随手改写环境）。

        保留历史 `JM_DATABASE_URL` / `JM_DB_ECHO` 默认读取能力；
        进程内多实例隔离请改用 `DbSettings.from_url(...)` 显式注入。
        """
        e = dict(os.environ if env is None else env)
        raw = (e.get("JM_DATABASE_URL") or "").strip()
        if not raw:
            url = f"sqlite:///{DEFAULT_SQLITE_PATH}"
        elif raw.startswith("sqlite:///") and not raw.startswith("sqlite:////"):
            # 相对路径 -> 相对项目根（禁止依赖调用方 cwd）
            rel = raw[len("sqlite:///"):]
            p = Path(rel)
            url = f"sqlite:///{p if p.is_absolute() else (ROOT / p)}"
        else:
            url = raw
        echo = str(e.get("JM_DB_ECHO", "")).strip().lower() in ("1", "true", "yes", "on")
        return cls(url=url, echo=echo)

    @classmethod
    def from_url(cls, url: str, *, echo: bool = False) -> "DbSettings":
        """显式构造配置（P1-05）：**不读取、不修改任何环境变量**。

        `make_business_services(database_url=...)` 等调用方必须走这里，
        禁止用 `os.environ["JM_DATABASE_URL"] = ...` 传参（会污染进程全局配置，
        并行测试 / 多应用实例 / 嵌入式调用会串库）。
        """
        raw = str(url or "").strip()
        if not raw:
            raise ValueError("DbSettings.from_url 需要非空 url")
        if raw.startswith("sqlite:///") and not raw.startswith("sqlite:////"):
            rel = raw[len("sqlite:///"):]
            p = Path(rel)
            raw = f"sqlite:///{p if p.is_absolute() else (ROOT / p)}"
        return cls(url=raw, echo=bool(echo))

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite:")

    @property
    def cache_key(self) -> tuple[str, bool]:
        """Engine/SessionFactory 缓存键（P1-05）：url + echo 都参与，避免同 URL 不同 echo 串用。"""
        return (self.url, bool(self.echo))


_ENGINES: dict[tuple[str, bool], Engine] = {}
_FACTORIES: dict[tuple[str, bool], sessionmaker] = {}
# 可重入锁：get_session_factory 会在持锁状态下调用 get_engine
_CACHE_LOCK = threading.RLock()


def get_engine(settings: DbSettings | None = None) -> Engine:
    st = settings or DbSettings.from_env()
    key = st.cache_key
    with _CACHE_LOCK:
        eng = _ENGINES.get(key)
        if eng is not None:
            return eng
        kwargs: dict = {"echo": st.echo, "future": True}
        if st.is_sqlite:
            # SQLite 多线程访问（FastAPI 线程池 + 测试并发）
            kwargs["connect_args"] = {"check_same_thread": False}
        if st.url.startswith("sqlite:"):
            # 保证本地开发库目录存在
            path_part = st.url[len("sqlite:///"):]
            if path_part and path_part != ":memory:":
                Path(path_part).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(st.url, **kwargs)
        if st.is_sqlite:
            # SQLite 默认不强制外键约束 -> 显式打开（级联/约束测试语义与 PostgreSQL 对齐）
            from sqlalchemy import event

            @event.listens_for(eng, "connect")
            def _fk_on(dbapi_conn, _rec):  # pragma: no cover - 连接钩子
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        _ENGINES[key] = eng
        return eng


def get_session_factory(settings: DbSettings | sessionmaker | Callable[[], Session] | None = None):
    """返回 session 工厂。

    `settings` 三种取值：
      * `None`        -> 按环境变量解析 DbSettings；
      * `DbSettings`  -> 按给定配置解析（可缓存 engine/factory）；
      * 可调用工厂（`sessionmaker` 或 `Callable[[], Session]`）
                      -> 原样返回（服务层依赖注入 / 测试隔离）。
    """
    if settings is not None and not isinstance(settings, DbSettings):
        # 注入的 session 工厂（sessionmaker 实例本身可调用）
        if not callable(settings):
            raise TypeError(f"session factory 必须可调用，收到 {type(settings).__name__}")
        return settings
    st = settings or DbSettings.from_env()
    key = st.cache_key
    with _CACHE_LOCK:
        fac = _FACTORIES.get(key)
        if fac is not None:
            return fac
        fac = sessionmaker(bind=get_engine(st), expire_on_commit=False,
                           class_=Session, future=True)
        _FACTORIES[key] = fac
        return fac


def get_session(settings: DbSettings | sessionmaker | Callable[[], Session] | None = None) -> Session:
    """打开一个新 session（调用方负责 commit/rollback/close）。"""
    return get_session_factory(settings)()


@contextmanager
def session_scope(settings: DbSettings | sessionmaker | Callable[[], Session] | None = None):
    """事务边界：成功提交，异常回滚并抛出。"""
    session = get_session(settings)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(settings: DbSettings | None = None) -> None:
    """开发/测试便捷建表（正式初始化以 Alembic 迁移为准）。"""
    from . import models  # noqa: F401  确保注册全部模型
    Base.metadata.create_all(get_engine(settings))


def dispose_engines() -> None:
    """释放连接池（测试隔离用）。"""
    with _CACHE_LOCK:
        engines = list(_ENGINES.values())
        _ENGINES.clear()
        _FACTORIES.clear()
    for eng in engines:
        eng.dispose()
