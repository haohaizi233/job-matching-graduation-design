# Phase8-A / M7：前端 Vue 3 集成验收报告（06-frontend-integration）

- 生成时间：2026-11-01
- 交付：`frontend/src/api/oauth.ts`、`frontend/src/composables/useOAuth.ts`、
  `frontend/src/views/OAuthCompleteView.vue`、`AuthCard.vue` 改造、`SettingsView.vue` 绑定区
- 相关测试：`frontend/e2e/e13-oauth-login.spec.ts`、`e14-oauth-account-binding.spec.ts`、
  `e15-oauth-security.spec.ts`（真实 Vue + 真实 FastAPI + 隔离测试库 + 模拟授权服务器）

## 1. 登录页三平台按钮（不重画 UI）

`AuthCard.vue` 的 `handleSocial(provider)` 从「UI 演示」toast 换成真实 API 调用：
`useOAuth().startLogin(provider)` → `POST /api/v1/auth/oauth/start` → 跳转授权 URL。
原有 UI 风格、间距、动画、图标全部保留。

按钮状态由 `GET /oauth/providers` 驱动：

| 后端状态 | 按钮表现 |
|---|---|
| `disabled` | 「暂未开放」，点击给出明确提示，**无假成功** |
| `configured_pending_verification` | 「配置中」，点击同样给明确提示 |
| `available` | 可用，发起真实授权 |

密码登录始终正常可用（回归确认）。

## 2. 前端 API 与状态

* `api/oauth.ts`：`fetchProviders / startOAuth / exchangeOAuthTicket /
  listBoundIdentities / unbindIdentity / setOAuthPassword`，全部走 `http.ts`
  统一信封 / ApiError；
* `composables/useOAuth.ts`：只管 OAuth 流程 UI 状态；**登录态仍归 `useAuth`**
  （无并行全局登录状态）；exchange 成功后调用 `useAuth` 既有更新入口；
* Secret 零出现：前端无 `client_secret` / `appsecret` 字样（doctor Frontend Routes 检查）。

## 3. 完成页（Hash 路由兼容）

`/#/oauth/complete`（`OAuthCompleteView.vue`）：

* 后端 callback 是真实 HTTP Path（`/api/v1/auth/oauth/{provider}/callback`），
  与 Vue Hash 路由分工清晰：后端 302 到 `/#/oauth/complete?rid=...`；
* 页面职责：识别状态（success / error / canceled）→ 携带票据 Cookie
  `POST /exchange` → 更新 `useAuth` → 跳转 `return_path`；
* 防重复提交（交换中/已消费按钮禁用）；
* 处理：授权取消（`OAUTH_ACCESS_DENIED`）、交换失败、刷新后票据已消费、
  过期票据——均有明确文案与「返回登录」出口；
* 页面与 URL 不显示任何第三方 Token（E13-6 断言）。

## 4. 设置页绑定区

`SettingsView.vue` 新增「第三方账号绑定」（微信 / QQ / 微博 各一行）：

* 查看绑定（`GET /identities`）、发起绑定（`start(mode=bind)`）、解绑
  （`DELETE /identities/{identity_ref}`）；
* 冲突（`OAUTH_IDENTITY_CONFLICT`）/ 最后登录方式（`OAUTH_LAST_LOGIN_METHOD`）/
  会话变化（`OAUTH_SESSION_CHANGED`）/ 账号失效均有显式提示；
* 绑定状态完成后自动刷新；
* **保留**既有修改密码、登录设备管理、个人设置功能；
* 纯 OAuth 用户不显示「输入原密码修改密码」，改为「设置本站密码」入口
  （`POST /oauth/set-password`），状态提示真实。

## 5. 浏览器 E2E 用例覆盖（E13–E15 共 18 例）

| 文件 | 用例 | 覆盖 |
|---|---|---|
| e13-oauth-login | E13-1…6 | 真实扫码链路进工作台、重复登录不重复建号、拒绝授权、退出真实失效、资料失败仍登录、URL 无 code/state/token |
| e14-oauth-account-binding | E14-1…5 | 主动绑定、抢绑冲突不静默转移、最后登录方式保护、设密码后解绑、未登录绑定被拒 |
| e15-oauth-security | E15-1…7 | 未配置无假成功、伪造 state、回调重放、票据重放、开放重定向拒绝、平台异常不伪装密码错误、code 过期明确错误 |

E2E 纪律：真实 Vue + 真实 FastAPI + Alembic 迁移库 + 真实跳转模拟授权页点击同意/拒绝；
**只替换外部身份平台**，本站业务 API 零 mock；退出后旧 Token 真实 401；
同一 subject 多次登录账号唯一。

真实平台 E2E Smoke（需资质）标记 `NOT_RUN_EXTERNAL_CREDENTIALS`，不冒充 PASS。

## 6. 验收结论

三平台按钮连接真实 OAuth 业务入口，完成页/绑定区/状态机齐备，Vue typecheck +
Vite build 通过（CI `oauth-frontend` 任务）。

**M7 = PASS**。
