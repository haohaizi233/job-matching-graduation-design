# Phase8-A / M10：CI 与兼容性回归报告（08-ci-regression）

- 生成时间：2026-11-01
- 目标：新增 `phase8-oauth-gates` 质量门禁，且**不破坏**既有 `core-ci` /
  `frontend-ci` / `postgres-integration` / `browser-e2e` / `phase6-gates` / `phase7-gates`。
- 结论先行：**新增门禁全绿（无真实凭据亦全绿）；既有核心回归全部未被破坏。**

## 1. 新增质量门禁

`.github/workflows/phase8-oauth-gates.yml`（独立工作流，只做加法）：

| Job | 内容 | 无凭据时 |
|---|---|---|
| `oauth-backend` | Python 3.11 + SQLite：`oauth doctor` + `tests/phase8a/run_all.py` + `tests/core_ci/run_all.py` | 全绿 |
| `oauth-postgres` | PostgreSQL 16 服务容器：迁移 / 唯一约束 / 原子消费 / 纯 OAuth 账号 | 全绿 |
| `oauth-frontend` | Node 22：`vue-tsc` typecheck + `vite build` | 全绿 |
| `oauth-browser-e2e` | 真实前后端 + 本地模拟授权服务器：E13–E15 | 全绿 |
| `real-provider-status` | 真实联调状态登记（本轮固定 `NOT_RUN`） | 如实登记 |

纪律：外部身份 Provider 一律由测试侧 `FakeOAuthProvider` / `fake_oauth_server.py` 替代
（仅测试注入，生产代码无任何开关可达）；业务链路（事务 / 票据 / 账号 / 会话 / 数据库）全部真实执行。

## 2. 既有门禁保持

`phase8-oauth-gates.yml` 未改动任何既有工作流文件，仅新增。既有门禁触发路径、
依赖版本、验收口径均保持不变。既有 `core-ci` 在本工作流的 `oauth-backend` job 中
也被一并复跑（防止 OAuth 改动破坏核心账号 / 会话 / 业务链路）。

## 3. 本地真实回归证据（本机 Python 3.13 逐一实跑）

| 套件 | 命令 | tests | PASS | FAIL | ERROR | SKIP | 耗时 | 结论 |
|---|---|---|---|---|---|---|---|---|
| core-ci | `tests/core_ci/run_all.py` | 87 | 87 | 0 | 0 | 0 | 307.7s | PASS |
| phase5-2 | `tests/phase5_2/run_all.py` | 62 | 61 | 0 | 0 | 1 | 50.5s | PASS |
| phase5-2R | `tests/phase5_2r/run_all.py` | 70 | 70 | 0 | 0 | 0 | 87.1s | PASS |
| phase6 | `tests/phase6/run_all.py` | 81 | 79 | 0 | 0 | 2 | 48.9s | PASS |
| phase7（主套件） | `tests/phase7/run_all.py` | 74 | 74 | 0 | 0 | 0 | 3.3s | PASS |
| phase8a OAuth | `tests/phase8a/run_all.py` | 144 | 144 | 0 | 0 | 0 | 340.5s | PASS |
| 浏览器 E2E | `tests/e2e/run_e2e.ps1` | 35 | 35 | 0 | 0 | 0 | 323.1s | PASS |

- SKIP 均为**既有**条件跳过（如 PostgreSQL 未提供、模型工件缺失），非本次新增；
  PostgreSQL 在 `JM_TEST_DATABASE_URL_POSTGRES` 提供时相关用例真实执行并全绿。
- phase7 另含「运行器元测试」（`test_run_identity`）：用**故意** FAIL / ERROR / 零测试的
  子运行器校验主运行器「能正确发现失败并返回非零退出码」，其内层 FAIL/ERROR 是被断言的
  期望行为，不代表 phase7 回归失败；phase7 主套件 `PASS=74 FAIL=0`。

## 4. 浏览器 E2E（E01–E15）分组

| 分组 | 用例数 | 结果 | 说明 |
|---|---|---|---|
| E01–E12（既有业务） | 17 | 全 PASS | 注册/登录/退出、简历解析、画像、岗位、推荐、历史、隔离、错误态、刷新响应式 |
| E13 OAuth 登录 | 6 | 全 PASS | 扫码登录进工作台、重复登录不重复建号、拒绝授权、退出真实失效、资料失败仍登录、URL 无 code/state/token |
| E14 绑定/解绑 | 5 | 全 PASS | 主动绑定、抢绑冲突不静默转移、最后登录方式保护、设密码后解绑、未登录绑定被拒 |
| E15 安全基线 | 7 | 全 PASS | 未配置无假成功、伪造 state、回调重放、票据重放、开放重定向拒绝、平台异常不伪装密码错误、code 过期明确错误 |

E2E 纪律：真实 Vue + 真实 FastAPI + Alembic 迁移库 + 真实跳转模拟授权页点击同意/拒绝；
**只替换外部身份平台**，本站业务 API 零 mock。运行证据：`reports/phase5-3/e2e-results.md`
（Run ID `p8a-full-final2`，35/35 PASS）。

## 5. 兼容性红线（全部维持）

- 普通用户密码登录 / 注册 / 修改密码：core-ci + E01 + E14-4 覆盖，均 PASS；
- 登录设备管理 / 会话撤销：core-ci + E09 + E13-4 覆盖，均 PASS；
- 简历、画像、推荐、反馈的用户级隔离：core-ci + E10 覆盖，均 PASS；
- 既有 `/api/v1/auth/*` 契约不变：core-ci + E01/E09 覆盖，均 PASS。

## 6. 验收结论

新增 `phase8-oauth-gates` 无真实凭据亦全绿；既有核心回归（core-ci / phase5-2 /
phase5-2R / phase6 / phase7 / 浏览器 E2E）全部未被破坏。

**M10 = PASS**。
