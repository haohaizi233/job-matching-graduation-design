# Phase8-A / M4+M6：OAuth 业务编排与 API 契约验收报告

- 生成时间：2026-11-01
- 交付：`src/job_matching/service/oauth/{service,identity_service,router}.py`
- 相关测试：`tests/phase8a/test_api_flows.py`（49 例）、`test_identity_service.py`（19 例）
- 契约文档：`docs/oauth/api-contracts.md`

## 1. OAuthService 方法清单

| 方法 | 职责 |
|---|---|
| `start_authorization()` | 校验 Provider 三态 → 创建授权事务（state 摘要 + 浏览器绑定 Cookie）→ 返回授权 URL |
| `handle_callback()` | state / Cookie / TTL / 一次性消费校验 → code 换身份 → 账号解析 → 签发一次性票据 → 固定跳转完成页 |
| `exchange_login_ticket()` | 原子消费票据 → `AccountService.create_session()` → 返回既有 LoginResult 结构 |
| `bind_identity()` | 校验发起/完成会话一致 → 身份冲突检查 → 插入映射 |
| `list_identities()` | 当前用户绑定列表 |
| `unbind_identity()` | 本人 + 近期重认证 + 最后登录方式保护 |
| `set_password()` | 纯 OAuth 账号补设密码（撤销其它设备会话） |

## 2. 登录链路（真实跑通，非 200 断言）

`test_full_login_chain_enters_existing_account_system` 验证：

```text
POST /oauth/start → 模拟 Provider callback → POST /oauth/exchange
→ GET /auth/me → 简历/画像查询 → POST /auth/logout → 旧 Token 401
```

**核心断言：OAuth 登录最终确实进入现有账号系统**（users 行、auth_sessions 行、
业务数据隔离均按 `user_id` 归属），不是只返回 200。

其他关键用例：

* `test_exchange_shape_matches_password_login`：exchange 返回与 `/auth/login`
  完全一致的 `{token, user, token_type, expires_at, session_id}`；
* `test_second_login_same_identity_no_duplicate_account`：同一身份重复登录不重复建号；
* `test_oauth_issues_new_session_each_login`：每次登录签发**新**会话（Session Fixation 防护）；
* `test_multi_tab_authorization`：多标签页并发授权互不串号（按事务隔离 Cookie）；
* 绑定：`test_bind_full_flow` / `test_oauth_binding_user_changed`（`OAUTH_SESSION_CHANGED`）/
  `test_oauth_identity_conflict`（409 不静默转移）/ `test_oauth_unauthorized_binding`（401）；
* 解绑：`test_unbind_flow_and_last_login_method`（`OAUTH_LAST_LOGIN_METHOD` 403）/
  `test_unbind_requires_recent_session` / `test_unbind_other_users_identity_not_found`（防枚举）。

## 3. API 契约（`/api/v1/auth/oauth/*`，挂载在既有 `/api/v1/auth` 体系）

| 接口 | 说明 | 兼容性 |
|---|---|---|
| `GET /providers` | 三平台状态（不返回 Secret） | 复用统一信封 |
| `POST /start` | 创建真实授权事务 + 浏览器绑定 Cookie | 未配置时 503 `OAUTH_PROVIDER_NOT_CONFIGURED`，不生成假链接 |
| `GET /{provider}/callback` | 校验→换身份→票据→302 完成页 | 错误路径也走固定可信跳转；URL 不残留 code/state/token |
| `POST /exchange` | 原子消费票据 → 既有 LoginResult | 与 `/auth/login` 返回结构逐字段一致 |
| `GET /identities` | 绑定列表 | 需登录 |
| `DELETE /identities/{identity_ref}` | 解绑（支持 provider 或 identity_id） | 需登录 + 近期重认证 |
| `POST /set-password` | 纯 OAuth 账号设密码 | 撤销其它设备会话 |

既有 `POST /register`、`POST /login`、`POST /logout`、`GET /me`、
`POST /change-password`、会话管理接口**契约全部不变**（回归套件 PASS）。

## 4. 错误码与 HTTP 状态（全部登记于 `errors.py::ERROR_CODES`）

400：`OAUTH_INVALID_STATE` / `OAUTH_STATE_EXPIRED` / `OAUTH_CALLBACK_REPLAY` /
`OAUTH_ACCESS_DENIED` / `OAUTH_TICKET_EXPIRED` / `OAUTH_TICKET_ALREADY_USED` /
`OAUTH_INVALID_REDIRECT`；
401：`OAUTH_BIND_REQUIRES_AUTH`；
403：`OAUTH_LAST_LOGIN_METHOD`；
409：`OAUTH_IDENTITY_CONFLICT` / `OAUTH_SESSION_CHANGED`；
429：`RATE_LIMITED`（start 30 次/窗、callback 失败 30 次/窗、exchange 限频）；
502：`OAUTH_TOKEN_EXCHANGE_FAILED` / `OAUTH_PROVIDER_UNAVAILABLE` / `OAUTH_INVALID_IDENTITY`；
503：`OAUTH_PROVIDER_NOT_CONFIGURED` / `OAUTH_PROVIDER_DISABLED`。

`ServiceError` 构造强制校验错误码已登记，无未注册码可外泄。

## 5. 验收结论

登录/绑定/解绑/设密码链路可实际运行，API 与既有契约兼容。

**M4 = PASS，M6 = PASS**。
