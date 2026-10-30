# -*- coding: utf-8 -*-
"""tests/phase5_2r 共用夹具：临时 SQLite/Alembic 数据库 + 合成简历/岗位 + HTTP 客户端。

纪律（与 phase5_2 同口径）：
  * 全部测试使用**合成夹具**（无真实简历、无真人信息、无 PII）；
  * 合成数据绝不进入正式 Gold 评估集（夹具只写临时目录，用完即删）；
  * 数据库通过 Alembic 迁移创建（迁移本身也是被测对象）；
  * 业务服务以 **显式 database_url 注入**（P1-05），禁止改写进程全局环境变量传参
    （Alembic CLI 唯一入口例外：用完即恢复原环境值）。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------- 合成夹具
SYNTHETIC_RESUME_TEXT = """\
王五（合成演示简历，非真人，仅供自动化测试）
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

# 与 SYNTHETIC_JOB_TEXT 相比：必备技能与学历要求不同（P0-01 失效用例）
SYNTHETIC_JOB_TEXT_V2 = """\
职位名称：Java 开发工程师
工作地点：上海
学历要求：硕士及以上
岗位职责：
1. 负责后端服务开发与维护；
2. 参与系统设计与技术方案评审。
任职要求：
1. 硕士及以上学历，计算机相关专业优先；
2. 熟练掌握 Go、Kubernetes、PostgreSQL；
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


# ---------------------------------------------------------------- Alembic
def _alembic_env_call(fn, database_url: str, *args):
    """Alembic CLI 唯一入口：临时设置 JM_DATABASE_URL，用完恢复（P1-05 纪律）。"""
    from alembic import command
    from alembic.config import Config

    saved = os.environ.get("JM_DATABASE_URL")
    os.environ["JM_DATABASE_URL"] = database_url
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        fn(command, cfg, *args)
    finally:
        if saved is None:
            os.environ.pop("JM_DATABASE_URL", None)
        else:
            os.environ["JM_DATABASE_URL"] = saved


def run_migrations(database_url: str) -> None:
    """对给定数据库执行 Alembic 迁移到 head（测试建库唯一入口）。"""
    _alembic_env_call(lambda cmd, cfg, *_a: cmd.upgrade(cfg, "head"), database_url)


def run_downgrade(database_url: str, revision: str = "base") -> None:
    _alembic_env_call(lambda cmd, cfg, *_a: cmd.downgrade(cfg, revision), database_url)


# ---------------------------------------------------------------- 夹具
class BusinessHarness:
    """一个测试类一套隔离环境：临时库 + 临时私有存储 + 业务 app + HTTP 客户端。"""

    def __init__(self, *, settings=None):
        self.tmp = tempfile.TemporaryDirectory(prefix="jm_p52r_",
                                               ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.db_url = f"sqlite:///{base / 'test.db'}"
        self.storage_root = base / "storage"
        # 记录全局环境是否被污染（P1-05 观测口径）
        self._env_before = dict(os.environ)

        from job_matching.infra.persistence import dispose_engines
        dispose_engines()
        run_migrations(self.db_url)

        from job_matching.service.business_api import (create_business_app,
                                                       make_business_services)
        # 显式注入 database_url（不写环境变量）
        self.biz = make_business_services(database_url=self.db_url,
                                          storage_root=self.storage_root,
                                          settings=settings)
        self.app = create_business_app(self.biz)

        from fastapi.testclient import TestClient
        self.client = TestClient(self.app)
        self.client_quiet = TestClient(self.app, raise_server_exceptions=False)

    def env_polluted(self) -> list[str]:
        """返回构造后被新增/改写的环境变量键（应为空）。"""
        return [k for k, v in os.environ.items() if self._env_before.get(k) != v]

    def close(self) -> None:
        import gc
        import time
        from job_matching.infra.persistence import dispose_engines
        self.client.close()
        self.client_quiet.close()
        dispose_engines()
        gc.collect()
        for _ in range(5):     # Windows 文件句柄释放有延迟，重试后再清理临时目录
            shutil.rmtree(self.tmp.name, ignore_errors=True)
            if not Path(self.tmp.name).exists():
                break
            time.sleep(0.2)

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
                      is_synthetic: bool | None = True, unique: bool = True):
        data = content if content is not None else synthetic_resume_bytes()
        if unique and data:
            # 默认每次上传内容唯一（幂等/并发用例显式传 unique=False）
            data = data + f"\n<!-- synth-nonce: {uuid.uuid4().hex} -->\n".encode("utf-8")
        return self.client.post(
            "/api/v1/resumes",
            headers=self.auth(token),
            files={"file": (filename, data, "text/plain")},
            data={"is_synthetic": ("true" if is_synthetic else "false")
                  if is_synthetic is not None else ""})

    # -------------------------------------------------------------- 岗位
    def create_job(self, admin_token: str, *, title: str,
                   job_description: str = SYNTHETIC_JOB_TEXT, **kw):
        body = {"title": title, "job_description": job_description,
                "source": kw.pop("source", "synthetic"),
                "source_license": kw.pop("source_license", "CC0-synthetic"),
                "status": kw.pop("status", "published")}
        body.update(kw)
        return self.client.post("/api/v1/jobs", headers=self.auth(admin_token), json=body)

    def create_parsed_job(self, admin_token: str, *, title: str,
                          job_description: str = SYNTHETIC_JOB_TEXT, **kw) -> str:
        r = self.create_job(admin_token, title=title,
                            job_description=job_description, **kw)
        assert r.status_code == 200, r.text
        jid = r.json()["data"]["job"]["id"]
        rp = self.client.post(f"/api/v1/jobs/{jid}/parse",
                              headers=self.auth(admin_token))
        assert rp.status_code == 200, rp.text
        return jid

    def import_jobs(self, admin_token: str, items: list[dict]):
        return self.client.post("/api/v1/jobs/import", headers=self.auth(admin_token),
                                json={"items": items})

    # -------------------------------------------------------------- 学生
    def student(self, name: str, password: str = "Stu!2026pass") -> str:
        """注册 -> 上传合成简历 -> 确认画像 -> 返回 token。"""
        self.register(name, password)
        _u, token = self.login(name, password)
        self.upload_resume(token)
        r = self.client.put("/api/v1/students/me/profile", headers=self.auth(token),
                            json={"confirm": True})
        assert r.status_code == 200, r.text
        return token

    def profile(self, token: str) -> dict:
        r = self.client.get("/api/v1/students/me/profile", headers=self.auth(token))
        assert r.status_code == 200, r.text
        return r.json()["data"]["profile"]

    def student_token(self, name: str, password: str = "Stu!2026pass") -> str:
        """只注册 + 登录（未上传简历/未确认画像）。"""
        self.register(name, password)
        _u, token = self.login(name, password)
        return token
