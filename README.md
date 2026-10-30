# 大学生就业岗位画像与简历智能匹配系统的设计与实现

面向大学生求职场景的「岗位画像 + 简历画像 + 智能匹配」机器学习系统毕业设计：
模型训练与独立评估（Python）+ 业务后端（FastAPI / SQLAlchemy / Alembic）+ 前端（Vue 3 / TypeScript / Vite）。

- **项目总览与快速开始**：[docs/project-overview.md](docs/project-overview.md)
  （内含**统一阶段状态清单**：Phase3 / Phase4-1 / Phase4-2 / Phase4-3A / Phase4-3A-2 / Phase5-1 / Phase5-1R / Phase5-1A
  / Phase5-2 / Phase5-2R / Phase5-3 与前后端实现的工程实现、自动化测试、独立复现、真实业务有效性与阻断项口径，
  其他文档一律引用该表）
- **项目结构**：[docs/project-structure.md](docs/project-structure.md)
- **环境搭建**：[docs/environment-setup.md](docs/environment-setup.md)
- **数据集索引**：[docs/datasets/README.md](docs/datasets/README.md)
- **API 文档**：[Phase5-1 推理服务 API](docs/api/phase5-1-api.md)；
  业务 API（Phase5-2）路由与分数/隐私口径见 `src/job_matching/service/business_api.py`
- **架构文档（Phase5-1A）**：[现状审计](docs/architecture/phase5-1a-current-state.md) ·
  [目标架构](docs/architecture/phase5-1a-target-state.md) ·
  [依赖规则](docs/architecture/phase5-1a-dependency-rules.md) ·
  [ADR 0001–0004](docs/architecture/adr/)
- **验收与测试报告**：[Phase5-1R 整改验收](reports/phase5-1r/phase5-1r-acceptance.md) ·
  [Phase5-1A 验收](reports/phase5-1a/phase5-1a-acceptance.md) ·
  [Phase5-2 端到端](reports/phase5-2/test-results.md) ·
  [Phase5-2R 一致性回归](reports/phase5-2r/test-results.md) ·
  [Core CI 门禁](reports/phase5-2/ci/core-ci-test-results.md) ·
  [Phase5-3 基线审计](reports/phase5-3/00-baseline-audit.md) ·
  [Phase5-3 CI 修复](reports/phase5-3/01-ci-remediation.md)

## 快速开始（本地联调）

```powershell
# 0) 解释器：Python 3.13（fastapi / sqlalchemy / alembic / httpx / uvicorn 就绪）+ Node.js 24

# 1) 启动业务 API（端口 8000；默认 SQLite data/private/dev.db，
#    可用 JM_DATABASE_URL 切换 PostgreSQL，如 sqlite:/// 或 postgresql://...）
$env:PYTHONPATH = "src"
py -3.13 -m uvicorn job_matching.service.business_api:create_business_app --factory --port 8000

# 2)（可选）灌入联调演示数据（幂等）：demo_admin / Admin@12345、demo_student / Demo@12345
py -3.13 scripts/dev_seed_api.py

# 3) 启动前端（端口 5173；/api 自动代理到 127.0.0.1:8000）
cd frontend
npm install
npm run dev

# 4) 自动化测试（纯 CPU 合成夹具，结果归档在 reports/ 下）
py -3.13 tests/core_ci/run_all.py     # Core CI 可移植门禁
py -3.13 tests/phase5_2/run_all.py    # 业务后端端到端（T1–T7）
py -3.13 tests/phase5_2r/run_all.py   # 业务一致性回归（R1–R9）
```

训练/评估环境（Conda `graduation-design`）、数据完整性校验与各阶段测试入口见
[docs/project-overview.md](docs/project-overview.md)。

前端 10 个页面视图：登录、工作台、简历管理、我的画像、岗位探索、岗位详情、智能匹配、
推荐历史、反馈中心、个人设置（`frontend/src/views/`）。

> ⚠ 业务有效性口径：自动化测试通过（含 Phase5-1R / Phase5-2 / Phase5-2R 工程验收）**不等于**
> 真实 Gold H2 通过；H2 维持 **BLOCKED**，直至真实中文简历、人工标签与合法盲测集完成。
> 分数（heuristic_score / model_raw_score）均为排序参考分，不是录用概率；
> 推荐反馈是用户业务反馈，不得当作人工 Gold 标签。
> Phase5-1 研究 API 默认仅本地开发使用（无认证）；Phase5-2 业务 API 已含认证（Argon2id + 会话）与多用户隔离，
> 但仍属本地联调口径，外网部署（HTTPS、鉴权加固等）为上线阻断项。

> 说明：原始数据集、模型权重（`models/`）与训练产物体积较大，默认不入库（见 `.gitignore`）；
> 历史权重有完整性基线自检（`configs/history-weights-baseline.json`）。
> 子项目 `chinese-skillspan-benchmark` 为独立仓库，另有远端。
