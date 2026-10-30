# -*- coding: utf-8 -*-
"""联调种子脚本：为本地业务 API 准备可演示数据。

用法（项目根目录）：
    set PYTHONPATH=src
    <python3.13> scripts/dev_seed_api.py

内容：
  1. 幂等创建账号：管理员 demo_admin / Admin@12345、学生 demo_student / Demo@12345
  2. 管理员录入 3 个校招岗位并解析岗位画像
  3. 学生上传合成简历（生成画像）→ 补全可编辑字段并 confirm
  4. 跑一次 baseline 推荐并提交一条反馈

依赖本地后端服务（uvicorn job_matching.service.business_api:create_business_app --factory --port 8000）。
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8000"

RESUME_TEXT = """张三
电话 13800000000 | 邮箱 zhangsan@example.com
求职意向：后端开发工程师 | 期望城市：北京 | 2026届本科毕业生

教育背景
2022.09 - 2026.06  示例大学 软件工程 本科

专业技能
- 熟悉 Python，掌握 Flask、FastAPI 后端开发
- 熟悉 MySQL、Redis，了解 SQL 调优
- 熟悉 Linux 常用命令，了解 Docker 部署
- 了解机器学习基础，使用过 scikit-learn

项目经历
2025.03 - 2025.08 校园二手交易平台（后端开发）
- 使用 FastAPI 开发 REST 接口，完成用户、商品、订单模块
- 使用 MySQL 设计表结构，Redis 缓存热点商品，QPS 提升 3 倍

实习经历
2025.07 - 2025.09 某科技公司 后端开发实习生
- 参与订单服务开发，编写单元测试覆盖率 85%
"""

JOBS = [
    ("后端开发工程师（校招）",
     "负责业务后端服务开发；要求熟悉 Python、SQL、Linux；本科及以上；2026届毕业生。"),
    ("算法工程师（校招）",
     "负责推荐算法研发；要求熟悉 Python、机器学习、深度学习；硕士及以上；2026届毕业生。"),
    ("前端开发工程师（校招）",
     "负责 Web 前端开发；要求熟悉 JavaScript、Vue、CSS；本科及以上；2026届毕业生。"),
]


def ensure_accounts() -> None:
    from job_matching.infra.persistence import get_session_factory
    from job_matching.service.accounts import AccountService

    accounts = AccountService(session_factory=get_session_factory())
    for username, password, email, role in [
        ("demo_admin", "Admin@12345", "admin@example.com", "admin"),
        ("demo_student", "Demo@12345", "demo@example.com", "student"),
    ]:
        try:
            accounts.register(username=username, password=password, email=email, role=role)
            print(f"[account] created {username} ({role})")
        except Exception as exc:  # noqa: BLE001
            print(f"[account] skip {username}: {exc}")


def login(c: httpx.Client, username: str, password: str) -> dict:
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def main() -> int:
    ensure_accounts()
    c = httpx.Client(base_url=BASE, timeout=60)

    admin = login(c, "demo_admin", "Admin@12345")
    for title, desc in JOBS:
        r = c.post("/api/v1/jobs", headers=admin, json={
            "title": title, "job_description": desc,
            "source": "manual", "is_synthetic": True})
        job = r.json().get("data", {}).get("job") or {}
        if not job.get("id"):
            print(f"[job] create failed {title}: {r.text[:200]}")
            continue
        c.post(f"/api/v1/jobs/{job['id']}/parse", headers=admin, json={})
        print(f"[job] ready {title} ({job['id']})")

    student = login(c, "demo_student", "Demo@12345")
    b64 = base64.b64encode(RESUME_TEXT.encode("utf-8")).decode("ascii")
    r = c.post("/api/v1/resumes/json", headers=student, json={
        "file_name": "zhangsan_resume.txt", "content_base64": b64,
        "is_synthetic": True, "data_source": "synthetic"})
    print(f"[resume] upload {r.status_code}")

    r = c.put("/api/v1/students/me/profile", headers=student, json={
        "edits": {"education_level": "本科", "major": "软件工程", "graduation_year": 2026,
                  "employment_intention": "后端开发", "preferred_cities": ["北京"],
                  "employment_type": "全职"},
        "confirm": True, "note": "dev_seed"})
    print(f"[profile] confirm {r.status_code}")

    r = c.post("/api/v1/recommendations", headers=student, json={"mode": "baseline", "top_k": 5})
    run = (r.json().get("data") or {}).get("run") or {}
    print(f"[reco] run {run.get('id')}")

    run_id = run.get("id")
    if run_id:
        detail = c.get(f"/api/v1/recommendations/{run_id}", headers=student).json()
        items = (detail.get("data", {}).get("run") or {}).get("items") or []
        if items:
            r = c.post(f"/api/v1/recommendations/{run_id}/feedback", headers=student, json={
                "item_id": items[0]["id"], "feedback_type": "interested", "note": "dev_seed"})
            print(f"[feedback] submit {r.status_code}")
    print("seed done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
