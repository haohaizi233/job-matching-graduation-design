# -*- coding: utf-8 -*-
"""tests/phase5_2 共用夹具：临时 SQLite/Alembic 数据库 + 合成简历/岗位 + HTTP 客户端。

纪律：
  * 全部测试使用**合成夹具**（无真实简历、无真人信息、无 PII）；
  * 合成数据绝不进入正式 Gold 评估集（夹具只写临时目录，用完即删）；
  * 数据库通过 Alembic 迁移创建（不用 create_all 走捷径），迁移本身也是被测对象。
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase5_1a")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------- 合成夹具
SYNTHETIC_RESUME_TEXT = """\
李四（合成演示简历，非真人，仅供自动化测试）
求职意向：Java 开发工程师
最高学历：本科
专业：软件工程
毕业年份：2027
期望城市：上海、杭州
工作性质：全职

专业技能
- 熟练掌握 Java、Spring Boot、MySQL
- 熟悉 Python、Docker、Linux

教育背景
2023-2027 合成大学 软件工程专业 本科

项目经历
- 开发招聘管理演示系统，使用 Java 与 Spring Boot，负责简历解析模块
- 参与数据平台建设，使用 Python 与 SQL 完成数据清洗

实习经历
- 合成科技公司 后端开发实习生，负责接口开发与联调

证书
- CET-6
"""

SYNTHETIC_JOB_TEXT = """\
职位名称：Java 开发工程师
工作地点：上海
学历要求：本科及以上
岗位职责：
1. 负责后端服务开发与维护；
2. 参与系统设计与技术方案评审。
任职要求：
1. 本科及以上学历，计算机相关专业优先；
2. 熟练掌握 Java、Spring Boot、MySQL；
3. 熟悉 Docker、Linux，有实习或项目经验优先。
"""

SYNTHETIC_JOB_TEXT_2 = """\
职位名称：Python 数据开发工程师
工作地点：杭州
学历要求：本科及以上
岗位职责：
1. 负责数据管道开发；
2. 参与数据质量治理。
任职要求：
1. 本科及以上学历；
2. 熟练掌握 Python、SQL；
3. 熟悉 Linux。
"""


def synthetic_resume_bytes() -> bytes:
    return SYNTHETIC_RESUME_TEXT.encode("utf-8")


def run_migrations(database_url: str) -> None:
    """对给定数据库执行 Alembic 迁移到 head（测试建库唯一入口）。"""
    from alembic import command
    from alembic.config import Config

    os.environ["JM_DATABASE_URL"] = database_url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


def run_downgrade(database_url: str, revision: str = "base") -> None:
    from alembic import command
    from alembic.config import Config

    os.environ["JM_DATABASE_URL"] = database_url
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.downgrade(cfg, revision)


class BusinessHarness:
    """一个测试类一套隔离环境：临时库 + 临时私有存储 + 业务 app + HTTP 客户端。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jm_p52_")
        base = Path(self.tmp.name)
        self.db_url = f"sqlite:///{base / 'test.db'}"
        self.storage_root = base / "storage"
        os.environ["JM_DATABASE_URL"] = self.db_url

        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        run_migrations(self.db_url)

        from job_matching.service.business_api import (create_business_app,
                                                       make_business_services)
        self.biz = make_business_services(storage_root=self.storage_root)
        self.app = create_business_app(self.biz)

        from fastapi.testclient import TestClient
        self.client = TestClient(self.app)
        self.client_quiet = TestClient(self.app, raise_server_exceptions=False)

    def close(self) -> None:
        from job_matching.infra.persistence import dispose_engines
        self.client.close()
        self.client_quiet.close()
        dispose_engines()
        self.tmp.cleanup()

    # -------------------------------------------------------------- 账号
    def register(self, username: str, password: str = "Passw0rd!2026",
                 email: str | None = None) -> dict:
        r = self.client.post("/api/v1/auth/register",
                             json={"username": username, "password": password,
                                   "email": email})
        assert r.status_code == 200, r.text
        return r.json()["data"]["user"]

    def make_admin(self, username: str = "admin_synth",
                   password: str = "Adm1n!2026pass") -> dict:
        """管理员经内部种子创建（不开放公开注册）。"""
        return self.biz.accounts.register(username=username, password=password,
                                          role="admin")

    def login(self, username: str, password: str = "Passw0rd!2026") -> tuple[dict, str]:
        r = self.client.post("/api/v1/auth/login",
                             json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        return data["user"], data["token"]

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # -------------------------------------------------------------- 简历
    def upload_resume(self, token: str, *, content: bytes | None = None,
                      filename: str = "synthetic_resume.txt",
                      is_synthetic: bool = True, unique: bool = True):
        data = content if content is not None else synthetic_resume_bytes()
        if unique and data:
            # 默认每次上传内容唯一（幂等/去重用例显式传 unique=False）
            # 空内容是"空文件"用例的合法输入，不得被补充字节污染
            data = data + f"\n<!-- synth-nonce: {uuid.uuid4().hex} -->\n".encode("utf-8")
        return self.client.post(
            "/api/v1/resumes",
            headers=self.auth(token),
            files={"file": (filename, data, "text/plain")},
            data={"is_synthetic": "true" if is_synthetic else "false"})

    # -------------------------------------------------------------- 岗位
    def import_jobs(self, admin_token: str, items: list[dict]):
        return self.client.post("/api/v1/jobs/import", headers=self.auth(admin_token),
                                json={"items": items})
