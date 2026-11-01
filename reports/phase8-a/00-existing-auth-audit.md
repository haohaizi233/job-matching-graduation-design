# Phase8-A / M0：现有认证链路审计报告

- 生成时间：2026-11-01
- 基线 commit：`2970e14e8c81acf0a1712ce06cdfbc56ad593d19`（origin/main，已 `git fetch --prune` 核对）
- 工作分支：`feat/phase8a-unified-oauth`
- 解释器：Python 3.13.2（本地）/ CI Python 3.11
- 审计范围：`src/job_matching/service/{accounts,business_api,errors,settings}.py`、
  `src/job_matching/infra/persistence/{models,base}.py`、`alembic/`、`frontend/src/{api,composables,router,views,components/login}`、
  `frontend/e2e/`、`tests/phase5_2|phase6|phase7/`、`.github/workflows/quality-gates.yml`、`.env.example`

---

## 1. 现有登录链路（用户名 / 密码）

事实来源：`src/job_matching/service/accounts.py::AccountService`、
`src/job_matching/service/business_api.py`。

```text
前端 AuthCard（用户名/密码表单）
  → POST /api/v1/auth/register | /api/v1/auth/login
  → AccountService.register() / authenticate()
       register：用户名/密码强度校验（≥10 位 + 字母 + 数字）、用户名/邮箱唯一、
                 Argon2id（argon2-cffi，type=ID）哈希后落库
       authenticate：用户名查库 → status 必须 active → 锁定期检查（连续 5 次失败锁 15 分钟）
                 → Argon2id verify → 失败原子自增 failed_login_count
  → create_session()：签发不透明 Bearer Token（secrets.token_urlsafe(32)，256 位熵）
  → 响应 {token, user, token_type, expires_at, session_id}（Token 只在此出现一次）
  → 前端 useAuth 存 localStorage（jm_token / jm_user）
  → 后续请求 Authorization: Bearer <token> → resolve_token()（只查 SHA-256 摘要）
```

关键既有 API（契约必须保持不变）：

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
POST /api/v1/auth/change-password
GET  /api/v1/auth/sessions
DELETE /api/v1/auth/sessions/{session_id}
POST /api/v1/auth/sessions/revoke-others
```

统一响应信封：`{request_id, api_version, app_version, data, warnings}`；
错误体：`{error: {code, message, request_id, detail}}`，错误码登记在 `service/errors.py::ERROR_CODES`
（`ServiceError` 构造时强制校验错误码已登记 —— 避免重现 `MODEL_ARTIFACT_TAMPERED` 未注册问题）。

## 2. 现有数据库关系

事实来源：`infra/persistence/models.py`、`alembic/versions/`（head = `c3a1f5d27e44`）。

```text
users(id, username UNIQUE, email UNIQUE NULL, password_hash NOT NULL,
      role, status, failed_login_count, locked_until, created_at, updated_at)
  ├─ auth_sessions(id, user_id FK CASCADE, token_sha256 UNIQUE, created_at,
  │                expires_at, last_seen_at, revoked_at, user_agent)
  ├─ student_profiles(user_id FK CASCADE, profile_version, ...)
  ├─ resumes(user_id FK CASCADE, ...)
  ├─ recommendation_runs / recommendation_feedback(user_id FK CASCADE, ...)
  └─ user_settings(user_id FK PK CASCADE, payload JSON)
```

- 双后端：SQLite（开发/测试）与 PostgreSQL（生产）；`DbSettings.from_url/from_env` 注入，
  禁止业务方法改写 `os.environ`。
- 建表唯一正规入口：Alembic 迁移（`tests/phase5_2/_util.py::run_migrations`）；
  `init_db()` 仅开发便捷，不作为迁移替代。
- **OAuth 相关表目前完全不存在**；`password_hash` 为 `NOT NULL`，纯 OAuth 账号无法落库。

## 3. 前端登录状态管理

- `frontend/src/api/http.ts`：`apiRequest()` 自动带 Bearer、解包 `{data}`、错误归一 `ApiError`；
  401 且请求带了 Token → 清 localStorage 并广播 `jm:session-expired`，回 `#/login`。
- `frontend/src/composables/useAuth.ts`：单例 `reactive` 状态 `{user, token, restored}`，
  `login/register/logout/restore` 四个动作；**禁止**再建第二套全局登录态。
- `frontend/src/router/index.ts`：`createWebHashHistory()`，`beforeEach` 只认 `localStorage.jm_token`，
  非 public 页无 Token 一律回 `/login`。
- `frontend/src/components/login/AuthCard.vue`：已有 QQ/微信/微博三个按钮，
  `handleSocial(provider)` 目前只弹「UI 演示，尚未接入 OAuth 授权」。

**Hash 路由与 OAuth 回调的兼容性约束**：Provider 回调必须落到 FastAPI 的真实 HTTP Path
（`/api/v1/auth/oauth/{provider}/callback`），而不是 Vue 的 `/#/` Hash 路由；
回调完成后再 302 到前端 `#/oauth/complete`。二者是两条链路，不能混淆。

## 4. Token 生命周期（现状）

| 阶段 | 行为 |
|---|---|
| 签发 | `secrets.token_urlsafe(32)`；明文仅出现在 login 响应一次 |
| 存储 | 服务端只存 `sha256(token)`（auth_sessions.token_sha256，UNIQUE） |
| 校验 | `resolve_token()`：摘要查库 → 未撤销 → 未过期 → 用户 active |
| 过期 | 12 小时（SESSION_TTL_HOURS） |
| 撤销 | logout / change-password（撤销其它会话）/ revoke_session / revoke_user_sessions |
| 前端 | localStorage `jm_token`（XSS 可读 —— 已登记为独立风险，见 §8） |

会话 Token ≠ Provider Access Token ≠ OAuth 一次性票据（后者为 Phase8-A 新增，三者必须隔离）。

## 5. FastAPI 路由组织

- `service/api.py::create_app()`：Phase5-1 推理服务（/api/v1/health、profiles、matching、models），
  含 request_id 中间件、请求体上限、限流、统一错误处理。
- `service/business_api.py::create_business_app()`：在 create_app() 之上挂载
  auth / students / resumes / jobs / recommendations 五组 APIRouter，
  依赖注入通过 `app.state.business`（`BusinessServices` 容器）。
- 认证依赖：`current_user`（Bearer → resolve_token）/ `current_admin`（role 校验）。
- OAuth 路由应挂载为第六组 router：`/api/v1/auth/oauth/*`，复用同一信封与错误体。

## 6. 项目配置方式

- `ServiceSettings.from_env()`（`JM_*` 环境变量）+ `to_config_dict()` 兼容视图；
  `assert_deployment_safe()` 在 production/staging 强制门禁。
- 数据库：`JM_DATABASE_URL` / `JM_DB_ECHO`（`DbSettings.from_env` 是唯一读取边界）。
- `.env.example` 仅作文档；**项目不自动加载 `.env`**（代码不依赖 python-dotenv），
  需 shell 显式设置环境变量 —— Phase8-A 文档必须延续这一事实。
- 服务端 Secret 只允许来自服务端配置；禁止进入 `VITE_*` / API 响应 / 日志 / Git / CI Artifact。

## 7. 需要修改的最小代码范围（Phase8-A 变更边界）

新增（不改动既有行为）：

```text
src/job_matching/service/oauth/**            全部新增（Provider 抽象/适配器/编排/存储/安全）
alembic/versions/<rev>_phase8a_oauth.py      新迁移（oauth_identities / oauth_auth_transactions
                                             / oauth_login_tickets + users.password_hash 可空）
frontend/src/api/oauth.ts                    新增
frontend/src/composables/useOAuth.ts         新增
frontend/src/views/OAuthCompleteView.vue     新增
scripts/phase8a/oauth_doctor.py              新增
tests/phase8a/**                             新增
docs/oauth/**                                新增
```

修改（必须向后兼容、增量式）：

```text
src/job_matching/service/errors.py           只新增 OAUTH_* 错误码登记（不动既有码）
src/job_matching/service/accounts.py         password_hash=NULL 的安全拒绝路径 + has_password 支持
src/job_matching/infra/persistence/models.py 新增三张 OAuth 表 + password_hash 改可空
src/job_matching/infra/persistence/__init__.py 导出新模型
src/job_matching/service/business_api.py     挂载 oauth router；BusinessServices 增加 oauth 字段
frontend/src/components/login/AuthCard.vue   handleSocial 换成真实 API 调用（UI 不动）
frontend/src/views/SettingsView.vue          新增"第三方账号绑定"区（原功能保留）
frontend/src/router/index.ts                 新增 /oauth/complete 路由（public）
.env.example                                 新增 JM_OAUTH_* 段
.github/workflows/quality-gates.yml          新增 phase8-oauth-gates job（不动既有 job）
```

明确不改：登录 UI 视觉、Vue Router 模式、既有 `/api/v1/auth/*` 契约、既有表结构语义、
既有 E01–E12 E2E、既有测试套件的断言。

## 8. 安全风险清单

| # | 风险 | 现状 | Phase8-A 处置 |
|---|---|---|---|
| R1 | `users.password_hash NOT NULL` 与纯 OAuth 账号冲突 | 未处理 | 迁移改可空 + NULL 时密码登录/改密安全拒绝 |
| R2 | localStorage Token 的 XSS 暴露 | 既有 | **登记为独立风险**，本阶段不改（避免破坏旧业务）；文档记录 |
| R3 | OAuth state CSRF / 重放 | 不存在 | CSPRNG state + 摘要落库 + TTL + 一次性消费 + 浏览器绑定 |
| R4 | 开放重定向（return_path / redirect_uri） | 不存在 | 配置白名单 + 标准 URL 解析 + 站内路由白名单 |
| R5 | 一次性票据重放 / 并发双消费 | 不存在 | 256 位票据 + 摘要落库 + 原子消费 + 30–60s TTL |
| R6 | Session Fixation | 不存在 | OAuth 完成后经 AccountService.create_session 签发全新会话 |
| R7 | 第三方账号抢绑定 / 跨用户绑定 | 不存在 | 唯一约束 + 事务内插入 + 会话绑定校验（OAUTH_SESSION_CHANGED） |
| R8 | 昵称/头像/未验证邮箱误合并账号 | 不存在 | 禁止自动合并；只按 (provider, client_id, subject) 关联 |
| R9 | Provider Token / code / state 进日志或 URL | 不存在 | 日志白名单字段 + 重定向剥离 code/state + 脱敏链复用 |
| R10 | SSRF（动态端点）/ 恶意 Provider 注册 | 不存在 | Provider 白名单 + 端点由受控代码决定 + 禁止请求体传端点 |
| R11 | QQ JSONP eval 执行 | 不存在 | 严格括号剥离 + json.loads，禁止 eval/动态脚本 |
| R12 | code 换 token 非幂等被盲目重试 | 不存在 | 单次交换、无重试、超时/失败映射明确错误 |
| R13 | 解绑后账号永久无法登录 | 不存在 | OAUTH_LAST_LOGIN_METHOD 保护 |
| R14 | 限流缺失导致 state/ticket 爆破 | 既有仅全局限流 | start/callback/exchange 分别限流 |
| R15 | 固定/可预测密码创建 OAuth 用户 | 不存在 | password_hash=NULL，禁止占位密码 |

## 9. 兼容性约束（硬约束）

1. `/api/v1/auth/register|login|logout|me|change-password|sessions*` 请求/响应结构不变。
2. 既有错误码与 HTTP 状态映射不变；新增 OAUTH_* 只做加法。
3. 既有用户、Token、简历、画像、推荐记录的 user_id 语义不变；迁移不得重建既有账号。
4. Alembic 历史迁移文件（`99510af3982b`/`b7d21c4a5f13`/`c3a1f5d27e44`/`d7e8f9a0b1c2`）不得修改。
5. 前端 `useAuth` 仍是唯一登录态来源；不引入第二套状态。
6. 现有 E2E E01–E12、`core-ci`/`frontend-ci`/`postgres-integration`/`browser-e2e`/
   `phase6-gates`/`phase7-gates` 必须继续全绿。
7. SQLite 与 PostgreSQL 双后端语义一致（唯一约束、外键、NULL 密码），PG 用集成测试实测。
8. 无真实凭据时系统必须正常启动且 Provider 安全禁用（`OAUTH_PROVIDER_NOT_CONFIGURED`）。

## 10. 测试基础设施现状（Phase8-A 将复用）

- `tests/phase5_2/_util.py::BusinessHarness`：临时 SQLite + Alembic 建库 + 真实 app + TestClient。
- `tests/phase*/run_all.py`：stdlib unittest 聚合运行器，真实进程身份 + 零测试发现显式失败 +
  JSON/Markdown 证据；Phase8-A 的 `tests/phase8a/run_all.py` 沿用该风格。
- PostgreSQL 集成测试惯例：`JM_TEST_DATABASE_URL_POSTGRES` 存在才执行，否则显式 SKIP
  （绝不用 SQLite 结果冒充 PG）。
- E2E：`frontend/playwright.config.ts` 双 webServer（tests/e2e/serve_backend.py + vite），
  Fake Provider 只能在该测试入口注入，生产代码不得有请求级开关。

---

结论：现有认证系统（Argon2id + 服务端不透明会话）边界清晰、可复用；
Phase8-A 的最小侵入点是「新增 oauth 包 + 一张迁移 + 路由挂载 + 前端三个新文件」，
既有密码登录链路不需要任何语义改动。
