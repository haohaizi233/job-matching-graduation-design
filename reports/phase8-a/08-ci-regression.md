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

## 6. CI 失败根因与整改记录（真实历史，不抹除）

前三轮推送（`0b68497` / `0086595` / `c753dd6`）真实出现过失败 Job，逐项定位并整改：

| Job | 失败用例 | 根因（证据） | 整改 |
|---|---|---|---|
| `core-ci (3.11)`、`oauth-backend` | `test_no_secret_material_in_tracked_files` | `tests/phase8a/test_provider_protocol.py` 的脱敏探针常量值被 C4 密钥扫描判定为疑似明文密钥 | 探针值改为 `example/` 前缀的占位符形态（C4 明确放行的测试夹具写法），语义不变 |
| `browser-e2e`（quality-gates） | E13-6（两轮稳定复现），E14-1/E14-2/E14-3（伴随出现） | **E2E 后端全局 API 限流（300/分钟）被全量套件击穿**：`api.py rate_limit_per_minute` 生产默认 300，E01–E15 一轮真实请求集中在若干 60s 窗口内超过上限，票据交换 / 注册被打成 429。证据：失败工件 `error-context.md` 显示完成页停在 `/?/oauth/complete` 且 detail=`RATE_LIMITED`，E14 注册报 `请求频率超过限制（300/分钟）` | `tests/e2e/serve_backend.py` 放宽 `JM_RATE_LIMIT_PER_MINUTE`（与既有 register/OAuth 限流放宽同口径，生产默认不变）；限流代码路径仍生效 |
| `browser-e2e`（伴随噪声） | 无直接失败，但加剧不稳定性 | **Vite dev watcher 把 Playwright 产物当页面变更**：outputDir `e2e/.artifacts/` 在 Vite 根内，trace 资源快照（`*.html`）测试中被实时写入，Vite 向客户端广播 `full-reload`，被测页面中途整页刷新（日志 `page reload e2e/.artifacts/.playwright-artifacts-*` 与失败窗口重合） | `frontend/vite.config.ts` 增加 `server.watch.ignored` 排除 `**/e2e/.artifacts/**`；两个 E2E 证据上传步骤补 `include-hidden-files: true`，失败 Trace/截图/error-context 可真正归档（本次根因正是靠该工件定位） |

整改后本地全量复跑：**E01–E15 35/35 PASS**，`page reload` 噪声降为 **0 次**，
复跑耗时从 6.1 分钟降到 2.6 分钟（整页刷新风暴被消除）。

## 7. 验收结论

新增 `phase8-oauth-gates` 无真实凭据亦全绿；既有核心回归（core-ci / phase5-2 /
phase5-2R / phase6 / phase7 / 浏览器 E2E）全部未被破坏。

**M10 = PASS**。
