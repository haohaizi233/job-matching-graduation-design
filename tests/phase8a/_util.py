# -*- coding: utf-8 -*-
"""tests/phase8a 共用夹具：临时库 + 真实业务 app + Fake Provider 注入 + 时钟快进。

纪律（与 tests/phase5_2/_util.py 同风格）：
  * 全部测试使用合成夹具与临时库（tests/e2e/.runtime 之外另起临时目录）；
  * 数据库经 Alembic 迁移创建（迁移本身也是被测对象）；
  * **只有外部身份 Provider** 被 Fake 替换，本站业务 API 不 Mock；
  * Fake Provider 只在这里注入（生产代码无任何开关可达）。
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fake_provider import FakeOAuthProvider, make_identity  # noqa: E402,F401

TEST_SECRET = "FAKE_SECRET_FOR_TESTS"
TEST_BASE_URL = "http://127.0.0.1:8000"
TEST_FRONTEND_ORIGIN = "http://127.0.0.1:5173"


def run_migrations(database_url: str) -> None:
    """对给定数据库执行 Alembic 迁移到 head（测试建库唯一入口）。"""
    from alembic import command
    from alembic.config import Config

    os.environ["JM_DATABASE_URL"] = database_url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


def run_downgrade(database_url: str, revision: str = "base") -> None:
    """把给定数据库回滚到指定 revision（默认 base）。"""
    from alembic import command
    from alembic.config import Config

    os.environ["JM_DATABASE_URL"] = database_url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.downgrade(cfg, revision)


def reset_pg_schema(database_url: str) -> None:
    """PostgreSQL 用例间硬重置：DROP SCHEMA public CASCADE + CREATE schema。

    迁移 downgrade 带有生产安全护栏——存在 password_hash IS NULL 的纯 OAuth
    账号时**拒绝回滚**（不静默删号/伪造密码）。该护栏不得为测试便利而削弱，
    因此用例间清理一律用整库 schema 重建，不用 downgrade。
    """
    from sqlalchemy import create_engine, text

    eng = create_engine(database_url, future=True)
    try:
        with eng.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        eng.dispose()


class MutableClock:
    """可快进的时钟（TTL 过期测试不 sleep）。"""

    def __init__(self, start: datetime | None = None):
        self.now = start or datetime.utcnow()

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now = self.now + timedelta(**kwargs)


class OAuthHarness:
    """一个测试类一套隔离环境：临时库 + 真实 app + Fake Provider + 可注入时钟。"""

    def __init__(self, *, frontend_origin: str = TEST_FRONTEND_ORIGIN,
                 state_ttl: int = 300, ticket_ttl: int = 60,
                 database_url: str | None = None):
        self.tmp = tempfile.TemporaryDirectory(prefix="jm_p8a_")
        base = Path(self.tmp.name)
        self.db_url = database_url or f"sqlite:///{base / 'oauth.db'}"
        self.storage_root = base / "storage"
        os.environ["JM_DATABASE_URL"] = self.db_url

        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        run_migrations(self.db_url)

        from job_matching.service.business_api import (create_business_app,
                                                       make_business_services)
        from job_matching.service.oauth.config import (OAuthProviderConfig,
                                                       OAuthSettings)
        from job_matching.service.oauth.http_client import OAuthHttpClient
        from job_matching.service.oauth.registry import build_registry

        self.clock = MutableClock()
        self.fake = FakeOAuthProvider(client_id="fake-appid",
                                      client_secret=TEST_SECRET)
        self.settings = OAuthSettings.for_test(
            public_base_url=TEST_BASE_URL,
            frontend_origins=(frontend_origin,),
            state_ttl_seconds=state_ttl, ticket_ttl_seconds=ticket_ttl,
            providers={"fake": OAuthProviderConfig(
                provider_id="fake", label="模拟平台（仅测试）", enabled=True,
                client_id="fake-appid", client_secret=TEST_SECRET,
                redirect_uri=f"{TEST_BASE_URL}/api/v1/auth/oauth/fake/callback")})
        self.http = OAuthHttpClient()
        registry = build_registry(
            self.settings, self.http, allowed_ids=("fake",),
            provider_factory=lambda pid, cfg, h: self.fake)

        self.biz = make_business_services(
            database_url=self.db_url, storage_root=self.storage_root,
            oauth_settings=self.settings, oauth_registry=registry,
            oauth_http=self.http)
        # 时钟注入：事务/票据 TTL 全部走可快进时钟
        self.biz.oauth.transactions._clock = self.clock
        self.biz.oauth.tickets._clock = self.clock
        self.oauth = self.biz.oauth

        self.app = create_business_app(self.biz)
        from fastapi.testclient import TestClient
        self.client = TestClient(self.app)
        self.client_quiet = TestClient(self.app, raise_server_exceptions=False)

    def close(self) -> None:
        from job_matching.infra.persistence import dispose_engines
        for c in (self.client, self.client_quiet):
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
        dispose_engines()
        self.tmp.cleanup()

    # ---------------------------------------------------------- 工具
    def new_client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app)

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def register(self, username: str, password: str = "Passw0rd!2026",
                 email: str | None = None, client=None) -> dict:
        c = client or self.client
        r = c.post("/api/v1/auth/register",
                   json={"username": username, "password": password,
                         "email": email})
        assert r.status_code == 200, r.text
        return r.json()["data"]["user"]

    def login(self, username: str, password: str = "Passw0rd!2026",
              client=None) -> tuple[dict, str]:
        c = client or self.client
        r = c.post("/api/v1/auth/login",
                   json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        return data["user"], data["token"]

    # ---------------------------------------------------------- OAuth 流程
    def start(self, *, provider: str = "fake", mode: str = "login",
              return_path: str | None = "/dashboard", token: str | None = None,
              client=None):
        """发起授权；返回 {rid, state, body, response}（state 从授权 URL 解析）。"""
        c = client or self.client
        headers = self.auth(token) if token else {}
        body = {"provider": provider, "mode": mode}
        if return_path is not None:
            body["return_path"] = return_path
        r = c.post("/api/v1/auth/oauth/start", json=body, headers=headers)
        if r.status_code != 200:
            return {"response": r, "body": None, "rid": "", "state": ""}
        data = r.json()["data"]
        query = parse_qs(urlsplit(data["authorization_url"]).query)
        return {"response": r, "body": data, "rid": data["rid"],
                "state": (query.get("state") or [""])[0],
                "code_challenge": (query.get("code_challenge") or [None])[0]}

    def callback(self, *, rid: str, state: str, code: str | None = "code-1",
                 error: str | None = None, provider: str = "fake",
                 client=None, drop_binding_cookie: bool = False):
        """模拟 Provider 回调（不跟随重定向；保留浏览器绑定 Cookie）。"""
        c = client or self.client
        params = {"state": state}
        if code is not None:
            params["code"] = code
        if error is not None:
            params["error"] = error
        if drop_binding_cookie:
            c.cookies.delete(f"jm_oauth_bb_{rid}", path="/api/v1/auth/oauth")
        return c.get(f"/api/v1/auth/oauth/{provider}/callback", params=params,
                     follow_redirects=False)

    def exchange(self, *, rid: str, token: str | None = None, client=None,
                 origin: str | None = None):
        c = client or self.client
        headers = self.auth(token) if token else {}
        if origin:
            headers["Origin"] = origin
        return c.post("/api/v1/auth/oauth/exchange", json={"rid": rid},
                      headers=headers, follow_redirects=False)


def parse_complete_url(location: str) -> dict:
    """解析前端完成页跳转参数（rid/mode/status/reason/return_path）。

    Hash 路由：查询串位于 URL 片段内（.../#/oauth/complete?rid=...），
    兼容解析片段内与常规位置的查询参数。
    """
    parts = urlsplit(location)
    query = parse_qs(parts.query)
    frag = parts.fragment or ""
    if "?" in frag:
        frag_path, frag_query = frag.split("?", 1)
        query = {**query, **parse_qs(frag_query)}
    else:
        frag_path = frag
    return {"path": parts.path, "fragment": frag_path,
            **{k: (v[0] if v else "") for k, v in query.items()}}


def extract_code_and_state_from_fake(callback_resp) -> tuple[str, str]:
    """辅助：从测试直接构造的回调参数（一般不用）。"""
    q = parse_qs(urlsplit(callback_resp.headers.get("location", "")).query)
    return (q.get("code") or [""])[0], (q.get("state") or [""])[0]
