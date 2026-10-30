# Phase5-3 M0 基线审计（本次实际执行结果）

> 本文件是 Phase5-3 里程碑 M0 的**真实执行记录**，全部数据来自 2026-10-31 本地实际运行。
> 旧报告（reports/phase5-1*、reports/phase5-2* 等）仅作为历史参照，**不冒充本次执行结果**。

## 1. 运行身份

| 项 | 值 |
|---|---|
| 审计时间 | 2026-10-31（UTC+8） |
| 工作区 | `D:\desktop\毕业设计` |
| 当前分支 | `main` |
| HEAD | `cb1f4819f48a5278dedac324c99b6720a5dccdc7` |
| HEAD 提交 | `cb1f481 feat(frontend): 简历解析失败横幅支持批量重新解析` |
| 是否 git 仓库 | 是 |
| 本次基线 JM_RUN_ID | `local-m0-baseline-20261031-*` |

### 1.1 工作区未提交变更（审计开始时）

审计开始时工作区只有一类可解释的改动：**测试运行器自动重写的测试结果归档**（`reports/phase5-1*/test-results.*` 等 7 个文件），由本次基线运行产生，属于证据更新，不涉及源码。

源码（含 `frontend/src/views/*`、`frontend/src/api/mappers.ts`、`frontend/src/components/dashboard/TopBar.vue`）经 `git ls-files` 确认**均已跟踪并已提交**（最近 15 个提交即前端联调系列）。会话开始时 `git_status` 快照中显示为未跟踪，属快照过期，已用 `git status --porcelain=v1 -uall` + `git ls-files` 复核澄清。

**未做任何 reset / checkout / 覆盖操作。**

## 2. 本机环境

| 组件 | 版本 / 状态 | 备注 |
|---|---|---|
| Python（默认 `python`） | 3.12.7（Anaconda） | **缺 numpy 等依赖，不能用于本项目** |
| Python（`py -3.13`） | 3.13.2（`D:\APP\python 3.13.2`） | **本项目实际解释器**，numpy/pandas/sklearn/fastapi/sqlalchemy/alembic/httpx 齐备 |
| 训练用 Conda 环境 `graduation-design` | 本机无 conda，`ENV_INCOMPATIBLE` | 历史训练环境（Python 3.11 + torch 2.1.2+cu121）未复建 |
| Node.js | v24.14.0 | |
| npm | 11.9.0 | `frontend/node_modules` 已安装 |
| Git | 2.45.1.windows.1 | |
| Docker | 29.6.1 可用 | 可用于临时 PostgreSQL（M4） |
| PostgreSQL 客户端 `psql` | 不在 PATH | 通过 Docker 容器内客户端替代 |
| 模型产物 `models/` | 本机存在（education/charcnn、education/tfidf、matching） | **Git 不跟踪（`.gitignore` → `models/**`）**，干净 checkout 中不存在 |
| 私有数据 `data/private/` | 本机存在 `dev.db`（SQLite，282 KB）+ 合成简历夹具 | Git 不跟踪 |
| `.env` | 未创建（仅 `.env.example`） | 业务 API 不依赖 python-dotenv |

## 3. 代码结构确认（实际阅读）

- 后端：`src/job_matching/{domain,infra/persistence,service,models,inference,training,evaluation,annotation,independent_eval,education}`
- 业务 API：`src/job_matching/service/business_api.py`，5 组路由前缀
  - `/api/v1/auth`（L285）
  - `/api/v1/students/me`（L337）
  - `/api/v1/resumes`（L368）
  - `/api/v1/jobs`（L443）
  - `/api/v1/recommendations`（L511）
- 持久层：`src/job_matching/infra/persistence/{base.py,models.py}`
- 迁移：`alembic/versions/{99510af3982b_initial_business_schema,b7d21c4a5f13_phase5_2r_consistency_fields}`
- 前端：Vue 3.5 + TypeScript 5.7 + Vite 6 + Vue Router 4，`frontend/src/{api,views,components,composables,router,data,types}`
- 前端页面 10 个视图齐备：Dashboard/Resume/Profile/Jobs/JobDetail/Matching/History/Feedback/Settings/Login
- 测试：`tests/{core_ci,phase5_1,phase5_1a,phase5_1r,phase5_2,phase5_2r,data_pipeline,environment,model_training,education_training,phase4_3a}`

## 4. 本次实际执行的测试基线（真实命令 + 退出码）

命令统一前缀：`$env:PYTHONUTF8='1'; py -3.13 <runner>`，cwd = 仓库根。

| 测试套件 | 命令 | Total | PASS | FAIL | ERROR | SKIP | 退出码 | 耗时 | 证据 |
|---|---|---|---|---|---|---|---|---|---|
| Phase5-1R 契约与可移植 | `py -3.13 tests/phase5_1r/run_all.py` | 151 | 151 | 0 | 0 | 0 | 0 | 65.0s | `reports/phase5-1r/test-results.json` |
| Phase5-1 业务服务 | `py -3.13 tests/phase5_1/run_all.py` | 92 | 92 | 0 | 0 | 0 | 0 | 5.3s | `reports/phase5-1/test-results.json` |
| Core CI 可信门禁 | `py -3.13 tests/core_ci/run_all.py` | 78 | 78 | 0 | 0 | 0 | 0 | 218.9s | `reports/phase5-2/ci/` |
| Phase5-1A 架构守卫 | `py -3.13 tests/phase5_1a/run_all.py` | 26 | 26 | 0 | 0 | 0 | 0 | 4.1s | `reports/phase5-1a/test-results.json` |
| Phase5-2 端到端业务 | `py -3.13 tests/phase5_2/run_all.py` | 56 | 52 | 0 | 0 | 4 | 0 | 21.7s | `reports/phase5-2/` |
| Phase5-2R 业务一致性 | `py -3.13 tests/phase5_2r/run_all.py` | 70 | 68 | 0 | 0 | 2 | 0 | 33.4s | `reports/phase5-2r/` |
| **合计** | | **473** | **467** | **0** | **0** | **6** | **0** | ~348s | |

6 项 SKIP 全部为 **PostgreSQL 专项（NOT_RUN 口径）**，跳过理由原文：
> `NOT_RUN: 未提供 JM_TEST_DATABASE_URL_POSTGRES；SQLite 通过不代表 PostgreSQL 兼容，本组不得计入 PASS`

对应测试：`tests/phase5_2/test_t7_pg_integration.py`（4 项）与 `tests/phase5_2r/test_r9_pg_contract.py`（2 项）。

## 5. GitHub Actions 现状（P0 缺陷确认）

- 工作流：`.github/workflows/quality-gates.yml`，两个层级
  - `core-ci`（push / PR / 手动）
  - `artifact-dependent-validation`（仅 `workflow_dispatch`）
  - `model-artifact-compat-manual`（仅手动）
- 已知失败：Run ID `41108847531`，commit `cb1f4819`
  - Phase5-1R 151/151 PASS
  - Phase5-1A 25 PASS / 1 FAIL

### 5.1 本地复现（干净 checkout 模拟，真实执行）

复现方法：用 `scripts/phase5_1a/verify_fresh_checkout.py` 的 `export_clean_checkout()` 导出"全新 checkout 会拿到的文件"到临时目录，再在其中运行失败测试。

```
TMP= C:\WINDOWS\TEMP\jm_repro_e0fuu644
COPIED= 1140
FORBIDDEN= []
models exists in clean checkout: False
RETURNCODE= 1
>> test_history_checkpoints_untouched (__main__.A4ModelErrorTaxonomy.test_history_checkpoints_untouched) ... FAIL
>> Ran 26 tests in 23.774s
>> FAILED (failures=1)
!! AssertionError: False is not true
```

**与 CI 第 54 次运行完全一致：25 PASS / 1 FAIL。**

### 5.2 根因

`tests/phase5_1a/test_a1_a7_gates.py` 的 `A4ModelErrorTaxonomy.test_history_checkpoints_untouched`：

```python
probe = ROOT / "models"
self.assertTrue(probe.exists())
```

该断言要求仓库根下存在 `models/` 目录。但 `.gitignore` 有 `models/**`，且 `git ls-files models` 为空（连 `models/README.md` 都未跟踪），因此干净 checkout 中 `models/` **必然不存在**，测试**必然失败**。

**本质缺陷**：把"历史权重是否被改动"这项 **Artifact-dependent（依赖真实产物）** 的检查，错误地放进了 **Core CI（要求全新 checkout 可通过）**，且断言的是"目录存在"而非"内容未被修改"，语义上也不成立。

## 6. 问题清单（按优先级）

### P0

| 编号 | 问题 | 状态 | 证据 |
|---|---|---|---|
| P0-1 | Core CI 依赖 Git 未跟踪的 `models/`，干净 checkout 必然失败 | **FAIL（已复现）** | 见 §5.1 |
| P0-2 | `test_history_checkpoints_untouched` 断言"目录存在"而非"权重未被修改"，无法真正发现权重篡改 | **FAIL（设计缺陷）** | 见 §5.2 |

### P1

| 编号 | 问题 | 状态 |
|---|---|---|
| P1-1 | PostgreSQL 集成测试未执行（6 项 NOT_RUN），未接入独立 CI Job | **NOT_RUN** |
| P1-2 | 前端无 CI 质量门禁（`npm ci` / `typecheck` / `build` 未纳入 GitHub Actions） | **NOT_RUN** |
| P1-3 | 无浏览器 E2E（Playwright 未引入），智能推荐闭环无可信自动化验收 | **NOT_RUN** |
| P1-4 | `DashboardView.vue` 统计卡 / 推荐卡 / 活动流 / 进度条仍来自 `@/data/dashboard` 静态数据 | **FAIL** |
| P1-5 | `TopBar.vue` 通知列表仍来自 `@/data/dashboard` 静态数据 | **FAIL** |
| P1-6 | `SettingsView.vue` 全部设置只写 `localStorage`，无服务端持久化 | **FAIL** |
| P1-7 | 部分视图仍引入 `@/data/*`（profile/resume/history/feedback/matching/jobs/settings/trend/nav）需逐项确认是纯展示文案还是业务数据 | **待审计（M2）** |
| P1-8 | 真实中文简历 = 0、真实人岗配对 = 0、Gold 未冻结 → H2 维持 BLOCKED | **BLOCKED（保留，禁止伪造）** |

### P2

| 编号 | 问题 | 状态 |
|---|---|---|
| P2-1 | 根目录遗留 `.tmp_*` / `_tmp_*` / `_probe*` / `_scan*.txt` 等约 45 个临时文件 | **待清理（M6，先判引用）** |
| P2-2 | `docs/project-overview.md` 阶段状态表中"前后端实现 ⚠ 未开始"与实际代码不符 | **FAIL（M6 更新）** |
| P2-3 | 本地启动 / 环境变量 / 演示流程文档缺失 | **NOT_RUN（M6 补齐）** |

## 7. 已实现功能（据代码与测试确认）

**业务推理服务（Phase5-1）**：中文简历 / JD 解析、业务画像、Baseline 排序、可解释结果、FastAPI 服务，92/92 PASS。

**工程整改（Phase5-1R）**：F-001–F-009 全部修复 + 二轮审计补漏，151/151 PASS。

**架构治理（Phase5-1A）**：模块化单体分层（domain/infra 抽取 + 兼容 re-export）、类型化配置、模型加载失败三分类、测试运行器可信化、最小 CI，26/26 PASS。

**业务一致性（Phase5-2 / 5-2R）**：数据库、认证、画像、岗位、推荐、多用户隔离、失败处理、上传限制、技能分页、画像快照、推荐幂等、岗位画像失效、文件生命周期，120/126 PASS（6 项 PG NOT_RUN）。

**前端联调（部分，最近 15 提交）**：登录态与退出、简历上传解析、个人档案读取、岗位列表/详情、推荐创建/详情/重跑、反馈提交、推荐历史导出 CSV、画像确认与版本预览、简历解析失败重试横幅。

## 8. 外部依赖与阻断

| 依赖 | 状态 | 影响 |
|---|---|---|
| 真实中文简历样本 | 缺失（合法授权数据） | H2 BLOCKED，无法证明中文就业有效性 |
| 真实人岗配对 Gold | 缺失（人工标注未完成） | H2 BLOCKED |
| 历史模型权重（GBM checkpoint） | 本机有部分；跨 sklearn 版本不可加载（`MODEL_ENV_INCOMPATIBLE`） | 端到端推理不可执行，登记为 ENV_INCOMPATIBLE，**禁止重训掩盖** |
| 训练 Conda 环境 | 本机无 conda | 训练复现 ENV_INCOMPATIBLE |
| PostgreSQL 实例 | 本机无 psql；Docker 可用 | M4 用 Docker 临时实例解决 |
| GitHub Actions runner | 无法直接控制 | 修复后需推送触发真实运行 |

## 9. M0 验收结论

- ✅ HEAD、分支、环境、依赖、模型产物状态已确证
- ✅ 本地 6 个测试套件真实执行，467 PASS / 0 FAIL / 6 SKIP（PG NOT_RUN）
- ✅ P0 CI 失败已在干净 checkout 模拟中**真实复现**（25 PASS / 1 FAIL，与 Run 54 一致）
- ✅ 根因定位准确（Core CI 误放 Artifact-dependent 检查 + 断言语义错误）
- ✅ 问题清单按 P0/P1/P2 分类并标注真实状态
- ✅ 未伪造任何测试结果，未修改历史权重/基线/评估协议

**M0 状态：PASS**

下一步 → M1（CI 修复）。
