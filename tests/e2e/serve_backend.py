# -*- coding: utf-8 -*-
"""E2E 隔离后端入口：显式注入测试数据库与测试存储根，uvicorn 启动业务 app。

与生产入口（uvicorn job_matching.service.business_api:create_business_app --factory）的区别仅在
**配置注入**：数据库连接串 / 私有存储根来自 E2E 环境变量（默认指向 tests/e2e/.runtime/ 临时目录），
绝不指向开发库（data/private/dev.db）或生产库。

环境变量：
  JM_E2E_RUN_DIR     运行目录（默认 tests/e2e/.runtime）；其下自动建 sqlite 与 storage
  JM_E2E_DB_URL      显式数据库连接串（优先于 RUN_DIR 推导）
  JM_E2E_STORAGE     显式私有存储根（优先于 RUN_DIR 推导）
  JM_E2E_PORT        监听端口（默认 8000；前端 vite 代理固定指向 127.0.0.1:8000）
  JM_E2E_SEED        1=启动前写入合成种子数据（管理员 + 合成岗位），默认 1

用法（项目根目录）：
  set PYTHONPATH=src
  py -3.13 tests/e2e/serve_backend.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RUN_DIR = Path(os.environ.get("JM_E2E_RUN_DIR") or (HERE / ".runtime")).resolve()
RUN_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = (os.environ.get("JM_E2E_DB_URL") or f"sqlite:///{RUN_DIR / 'e2e.db'}").strip()
STORAGE_ROOT = Path(os.environ.get("JM_E2E_STORAGE") or (RUN_DIR / "storage")).resolve()
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("JM_E2E_PORT") or 8000)
DO_SEED = str(os.environ.get("JM_E2E_SEED", "1")).strip().lower() not in ("0", "false", "no")


def run_migrations(database_url: str) -> None:
    """E2E 建库唯一入口：走 Alembic 迁移（迁移本身也是被测对象）。"""
    from alembic import command
    from alembic.config import Config

    os.environ["JM_DATABASE_URL"] = database_url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


def seed(biz) -> None:
    """写入合成种子数据：1 个合成管理员 + 3 个合成岗位（全部显式 is_synthetic）。

    幂等：账号/岗位已存在时跳过，不重复写入。
    """
    from fixtures import ADMIN_PASSWORD, ADMIN_USERNAME, SYNTHETIC_JOBS

    try:
        biz.accounts.register(username=ADMIN_USERNAME, password=ADMIN_PASSWORD,
                              role="admin")
        print(f"[e2e-seed] admin created: {ADMIN_USERNAME}")
    except Exception as exc:  # noqa: BLE001
        print(f"[e2e-seed] admin exists/skip: {exc}")

    admin = biz.accounts.authenticate(username=ADMIN_USERNAME, password=ADMIN_PASSWORD)
    existing = biz.jobs.list_jobs(admin, include_unpublished=True, page=1, page_size=100)
    have = {str(it.get("title") or "") for it in existing.get("items") or []}
    for item in SYNTHETIC_JOBS:
        if item["title"] in have:
            print(f"[e2e-seed] job exists/skip: {item['title']}")
            continue
        out = biz.jobs.create_job(admin, title=item["title"],
                                  job_description=item["job_description"],
                                  source="manual", is_synthetic=True)
        # create_job 直接返回岗位行字典（非 {"job": ...} 包装）
        job_id = str(out.get("id") or "")
        if job_id:
            try:
                biz.jobs.parse_profile(admin, job_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[e2e-seed] job parse warn: {exc}")
        print(f"[e2e-seed] job created: {item['title']} ({job_id})")


def main() -> int:
    os.environ["PYTHONUTF8"] = "1"
    os.environ.setdefault("JM_API_ENV", "dev")

    from job_matching.infra.persistence import dispose_engines
    dispose_engines()
    run_migrations(DB_URL)

    from job_matching.service.business_api import (create_business_app,
                                                   make_business_services)
    biz = make_business_services(database_url=DB_URL, storage_root=STORAGE_ROOT)
    if DO_SEED:
        seed(biz)
    app = create_business_app(biz)

    import uvicorn
    print(f"[e2e-backend] db={DB_URL}")
    print(f"[e2e-backend] storage={STORAGE_ROOT}")
    print(f"[e2e-backend] listening 127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
