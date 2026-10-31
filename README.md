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

## 数据库初始化与环境变量

```powershell
# 数据库初始化（SQLite 默认 data/private/dev.db；首次运行或升级后执行）
$env:PYTHONPATH = "src"
py -3.13 -m alembic upgrade head        # 迁移即建库；降级用 alembic downgrade base

# PostgreSQL（可选，本地/CI 均用可销毁的隔离库）
$env:JM_DATABASE_URL = "postgresql+psycopg2://user:pass@127.0.0.1:5432/job_matching"
```

常用环境变量（完整清单见 `src/job_matching/service/settings.py`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `JM_DATABASE_URL` | `sqlite:///data/private/dev.db` | 业务库连接串 |
| `JM_API_ENV` | `dev` | `production/staging` 启动时强制安全门禁（`assert_deployment_safety`） |
| `JM_RATE_LIMIT_PER_MINUTE` | 300 | 单客户端每分钟请求上限 |
| `JM_REGISTER_RATE_LIMIT` | 20 | 注册频率上限（次/小时/客户端；E2E 隔离环境放宽） |
| `JM_MAX_UPLOAD_BYTES` | 4194304 | 简历上传大小上限 |
| `JM_E2E_PORT` / `JM_E2E_PYTHON` | 8123 / `py -3.13` | 浏览器 E2E 隔离后端端口 / Python 命令 |
| `JM_TEST_DATABASE_URL_POSTGRES` | 无 | 提供后 PG 集成测试真实执行，缺省登记 `NOT_RUN` |

## 测试、E2E 与 CI

```powershell
# 单元/契约/回归（纯 CPU 合成夹具；均输出 PASS/FAIL/SKIP 汇总）
py -3.13 tests/phase5_1/run_all.py     # S01–S24 推理服务契约
py -3.13 tests/phase5_1r/run_all.py    # R1–R6 工程整改回归
py -3.13 tests/phase5_1a/run_all.py    # A1–A7 架构门禁
py -3.13 tests/core_ci/run_all.py      # 可信 CI 门禁（负向/隐私/契约）

# 浏览器 E2E（E01–E12；真实前后端 + 隔离测试库 tests/e2e/.runtime/，不碰 dev.db）
cd frontend
npm run typecheck && npm run build
npx playwright test                    # 自动拉起隔离后端与 vite
py ..\tests\e2e\build_report.py        # 生成 reports/phase5-3/e2e-results.*
```

CI 工作流（`.github/workflows/quality-gates.yml`）：Python Core CI / Frontend CI /
Database Integration（PG service）/ Browser E2E / Artifact-dependent Validation
（真实权重缺失即 `NOT_RUN`，不伪造）五个隔离 Job。

## 模型产物缺失处理

`models/`（历史 checkpoint）默认不入库。缺失时**不影响** Core CI 与业务演示
（baseline 启发式排序始终可用）；`experimental_model` 按 `allow_fallback` 显式降级或
显式报 `MODEL_MISSING`，绝不静默冒充模型输出。历史权重完整性自检：

```powershell
py -3.13 scripts/phase5_1a/check_history_weights_integrity.py   # 与 configs/history-weights-baseline.json 比对
```

## 常见故障排查

| 现象 | 处理 |
|---|---|
| 启动报数据库表不存在 | 先执行 `alembic upgrade head` |
| 前端 401 后停在登录页 | 会话已失效（改密/撤销/过期），重新登录即恢复 |
| 注册报 `RATE_LIMITED` | 一小时窗口 20 次；E2E 用隔离后端（`tests/e2e/serve_backend.py`）不受影响 |
| 推荐结果带"已降级"标记 | 模型不可用显式降级到启发式基线，`degradation_info` 可追溯原因码 |
| PG 测试显示 `NOT_RUN` | 未提供 `JM_TEST_DATABASE_URL_POSTGRES`（缺环境显式登记，不冒充通过） |
| Playwright 端口占用 | 结束残留的 8123/5173 进程，或改 `JM_E2E_PORT` |

## 毕业设计演示流程（约 5 分钟）

1. `alembic upgrade head` → 启动业务 API（8000）→ `scripts/dev_seed_api.py` 灌演示数据；
2. `npm run dev` 打开 `http://127.0.0.1:5173`，用 `demo_student / Demo@12345` 登录；
3. 上传简历（可用 `tests/fixtures` 合成简历）→ 查看解析画像 → 人工修订并**确认画像**；
4. 岗位探索筛选 → 智能匹配发起推荐 → 展示解释、评分口径与降级标记；
5. 推荐历史导出 CSV → 提交反馈 → 再次推荐观察历史累积；
6. （可选）`npx playwright test` 现场演示 17 条端到端自动化验收。

> 演示账号仅由本地种子脚本生成（`scripts/dev_seed_api.py`），默认凭证禁止带入线上环境。

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
