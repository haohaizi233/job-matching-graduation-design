# -*- coding: utf-8 -*-
"""E2E 合成夹具（**全部为合成数据，无真人简历、无 PII、绝不进入 Gold 评估集**）。

纪律（与 tests/phase5_2/_util.py 同口径）：
  * 夹具只写 E2E 临时运行目录（tests/e2e/.runtime/），用完可整体删除；
  * 岗位/简历文本均显式标注"合成"，经 is_synthetic=True 声明入库；
  * 测试账号密码仅用于本地隔离测试环境，禁止进入任何线上环境。
"""
from __future__ import annotations

# --------------------------------------------------------------- 账号（合成）
ADMIN_USERNAME = "e2e_admin_synth"
ADMIN_PASSWORD = "E2eAdmin!2026pass"
STUDENT_PASSWORD = "E2eStudent!2026"

# --------------------------------------------------------------- 简历（合成）
SYNTHETIC_RESUME_TEXT = """\
王五（E2E 合成简历，非真人，仅供自动化端到端测试）
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

实习经历
- 合成科技公司 后端开发实习生，负责接口开发与联调

证书
- CET-6
"""

# 解析必然失败的合成输入（乱码正文，无法抽出任何结构化字段 -> parse_status=failed）
SYNTHETIC_BAD_RESUME_TEXT = """\
E2E-SYNTHETIC unparseable payload @#$%^&* ~!@#$%^&*()_+
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""

# --------------------------------------------------------------- 岗位（合成）
SYNTHETIC_JOBS: list[dict] = [
    {
        "title": "Java 开发工程师（E2E 合成岗位）",
        "job_description": (
            "岗位职责：\n1. 负责后端服务开发与维护；\n2. 参与系统设计与技术方案评审。\n"
            "任职要求：\n1. 本科及以上学历，计算机相关专业优先；\n"
            "2. 熟练掌握 Java、Spring Boot、MySQL；\n3. 熟悉 Docker、Linux，有实习或项目经验优先。"
        ),
    },
    {
        "title": "Python 数据开发工程师（E2E 合成岗位）",
        "job_description": (
            "岗位职责：\n1. 负责数据管道开发；\n2. 参与数据质量治理。\n"
            "任职要求：\n1. 本科及以上学历；\n2. 熟练掌握 Python、SQL；\n3. 熟悉 Linux。"
        ),
    },
    {
        "title": "前端开发工程师（E2E 合成岗位）",
        "job_description": (
            "岗位职责：\n1. 负责 Web 前端开发；\n2. 参与组件库建设。\n"
            "任职要求：\n1. 本科及以上学历；\n2. 熟练掌握 JavaScript、Vue、CSS；\n3. 了解前端工程化。"
        ),
    },
]
