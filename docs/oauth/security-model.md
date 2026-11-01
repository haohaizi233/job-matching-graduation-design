# OAuth 安全模型（Phase8-A / M5，最高优先级）

> 未通过本节测试不允许开启真实 Provider。
> 对应负向测试：`tests/phase8a/test_security_primitives.py`、`test_api_flows.py`
> 与浏览器 E2E `frontend/e2e/e15-oauth-security.spec.ts`。

## 1. State 与 CSRF

`state` 生成与校验（`security.py` / `transaction_store.py`）：

* `secrets.token_urlsafe(32)`（CSPRNG，256 位熵），不可预测；
* 服务端只落 SHA-256 摘要，`UNIQUE(state_digest)`；
* 与 **Provider** 绑定（`consume` 校验 `row.provider == provider`）；
* 与 **浏览器** 绑定（`jm_oauth_bb_<rid>` Cookie 摘要比对）；
* 与 **login/bind 模式** 绑定（`row.mode` 校验）；
* TTL（默认 300s，60–900s 可配）；
* **一次性消费**：原子 `UPDATE ... WHERE consumed_at IS NULL`；
* 不接受空值、不接受不匹配值、不允许跨浏览器重放（绑定 Cookie 缺失即拒）。

浏览器绑定 Cookie：

```text
jm_oauth_bb_<rid>=<256位随机>; HttpOnly; SameSite=Lax; Path=/api/v1/auth/oauth
（HTTPS 部署自动附加 Secure）
```

* 按**事务 rid 隔离** Cookie 名 → 多标签页并发授权互不覆盖；
* OAuth 回调是第三方发起的**顶级 GET 导航**，`SameSite=Lax` 恰好允许携带
  既有绑定 Cookie —— 这是浏览器绑定方案可行的前提（已在 E2E 中验证）；
* 绑定凭据只在服务端与 Cookie 中流转，不进 URL、不进响应体、不进日志。

## 2. PKCE

* S256 辅助实现齐备（`pkce_verifier` / `pkce_challenge_s256`），
  verifier 存 `oauth_auth_transactions.code_verifier`，回调时校验；
* **是否启用由 Provider 官方契约决定**：微信 / QQ / 微博网站授权流程的支持情况
  登记为 `PROVIDER_VERIFICATION_PENDING`，当前一律 `supports_pkce = False`；
* 不支持时依靠：严格 state + client_secret + 回调白名单 + 一次性消费；
* 测试 `test_pkce_when_supported` 用支持 PKCE 的 Fake Provider 覆盖该代码路径。

## 3. Redirect URI / return_path

**回调地址**只来自受控配置（`OAuthSettings.callback_url`）：

* 显式 `JM_OAUTH_<PROVIDER>_REDIRECT_URI`，或由 `JM_OAUTH_PUBLIC_BASE_URL` 派生固定路径
  `/api/v1/auth/oauth/{provider}/callback`；
* 请求侧**不可能**传入回调地址（接口无此参数）；
* `check_safety()` 校验回调必须落在公开基址内、路径必须是固定回调路径、
  生产环境必须 HTTPS。

**return_path**（前端站内回跳）白名单校验（`sanitize_return_path`）：

| 攻击样例 | 结果 |
|---|---|
| `https://evil.example` | 拒绝 `OAUTH_INVALID_REDIRECT` |
| `//evil.example`（协议相对） | 拒绝 |
| `/\evil.example`（反斜杠混淆） | 拒绝 |
| `/%2F%2Fevil.example`（编码外跳） | 拒绝（解码后二次检查） |
| `/dashboard/../../evil`（路径穿越） | 拒绝 |
| `/settings`（站内白名单路由） | 放行 |

校验方式是**标准 URL 解析 + 解码检查 + 路径段校验**，不是 `startswith()` 草率匹配。
前端完成页另有同口径白名单（`OAuthCompleteView.safeReturnPath`）。

## 4. 三种 Token 的隔离

| | Provider Access Token | OAuth 一次性票据 | 本站 Bearer Token |
|---|---|---|---|
| 生命期 | 单次登录过程 | 30–60 秒 | 既有会话周期 |
| 存放 | 仅服务端内存 | HttpOnly Cookie + DB 摘要 | localStorage（现状） |
| 进 URL | 绝不 | 绝不 | 绝不 |
| 进日志 | 绝不 | 绝不 | 绝不 |
| 持久化 | 本项目仅登录用，用完即弃，不存库 | 只存摘要 | 只存 SHA-256 摘要（既有设计） |

Provider Token 不交给浏览器、不写日志、不写公开资料；本项目不做不必要的
refresh token 持久化。

**已登记风险（不在本任务内擅自重写）**：本站 Bearer Token 目前存 localStorage，
存在 XSS 暴露面。整体改造为 HttpOnly Cookie Session 应作为独立安全阶段实施，
本次保持 `useAuth` 存储行为以保证全部旧业务兼容。

## 5. Session Fixation

OAuth 完成后调用 `AccountService.create_session()` 签发**全新**本站会话：

* 不升级 OAuth 前的未认证会话、不保留旧 Session ID；
* 不复用任何可能被攻击者控制的会话标识；
* 一次性票据只换一次会话（原子消费），票据重放不会产生第二个会话
  （`test_ticket_double_exchange_race` + E2E `E15-4`）。

## 6. 一次性票据

* 明文 ≥128 位熵（实际 256 位），只经短期 HttpOnly Cookie 交给同一浏览器；
* 库里只存 SHA-256 摘要；TTL 30–60 秒；
* 原子消费，并发消费只能成功一次；
* 错误票据消息固定、不泄露用户 ID（无存在性预言机）；
* 过期自动失效；历史已消费票据定期清理。

## 7. 限流与异常

| 防线 | 覆盖 |
|---|---|
| `/start` 频率限制 | 30/分钟/客户端（可配） |
| `/callback` 失败限制 | 30/分钟/客户端（可配） |
| `/exchange` 频率限制 | 60/分钟/客户端（可配） |
| state 猜测 | 摘要比对 + 不匹配即 `OAUTH_INVALID_STATE` |
| code 重放 | 平台侧单次消费 + 本站事务一次性消费 |
| ticket 重放 | 原子消费 + `OAUTH_TICKET_ALREADY_USED` |
| 并发创建账号 | 唯一约束 + 同事务回查（`test_oauth_duplicate_concurrent_register`） |
| Provider 超时 | `ProviderTimeout` → `OAUTH_PROVIDER_UNAVAILABLE` |
| Provider 429 / 5xx | `ProviderHttpError` → `OAUTH_PROVIDER_UNAVAILABLE` |
| malformed JSON / JSONP | `ProviderProtocolError` → `OAUTH_TOKEN_EXCHANGE_FAILED` |
| 服务器关闭 | `OAuthHttpClient.close()` / 事务与票据 store 会话均 `close()` |
| 平台不可用前端状态 | 完成页明确错误文案 + 按钮禁用态（不假成功） |

**任意外部平台异常都不会被伪装成「密码错误」**（E2E `E15-6` 断言错误文案）。

### HTTP 客户端硬约束（`http_client.py`）

* 明确连接/读写/池超时与单请求总预算；
* 有界响应体（1 MiB，超限拒绝）；
* **零重试**：交换授权码不可幂等，禁止重复提交已消费 code；
* `follow_redirects=False`：不跟随平台响应里的任意 URL（防 SSRF 逃生口）；
* 只访问受控常量端点；Transport 可注入（测试用 `httpx.MockTransport`）；
* Secret 脱敏：`client_secret` 不进异常消息与日志（异常只回显 `scheme://host/path`）。

## 8. 安全日志

允许记录（`service._log` 白名单）：

```text
event / provider / flow(login|bind) / outcome(OK|ERR) / reason_code /
duration_ms / rid(事务短标识，非安全凭据) / request_id / client_ip(网关侧哈希)
```

禁止记录：

```text
AppSecret、Provider access_token、refresh_token、authorization code、
原始 state、一次性票据明文、本站 Bearer Token、完整用户资料
```

关联外部用户时使用受限内部摘要（如 `sha256(provider|client_id|subject)` 前缀），
**不把 OpenID / UID 当作公开追踪标识**。

## 9. 威胁模型对照

| 威胁 | 防线 | 验证 |
|---|---|---|
| 授权 CSRF（伪造回调） | state 摘要 + 浏览器绑定 + 一次性消费 | `test_state_mismatch`、E15-2 |
| 登录会话固定 | OAuth 后签发全新会话 | `test_state_*`、E13-1 |
| 跨浏览器抢授权事务 | 按事务隔离的绑定 Cookie | `test_state_browser_binding`、`test_multi_tab_authorization` |
| 开放重定向 | return_path 白名单 + 回调地址受控 | `test_redirect_open_redirect_rejected`、E15-5 |
| 票据重放 | 原子消费 + TTL + 摘要存储 | `test_ticket_replay`、`test_ticket_double_exchange_race`、E15-4 |
| 第三方账号抢绑定 | 已绑他人显式 409 | `test_oauth_identity_conflict`、E14-2 |
| 登录态切换后错绑 | 发起/完成会话摘要一致性校验 | `test_oauth_binding_user_changed`、E14 |
| 昵称/邮箱撞库合并 | 只按 (provider, client_id, subject) 关联 | `test_oauth_login_does_not_merge_by_nickname` 等 |
| 越权解绑 | 本人校验 + 近期重认证 | `test_oauth_unauthorized_binding`、E14-3 |
| Secret 泄露 | 只在服务端配置；不进响应/日志/CI | `test_oauth_secret_not_logged`、E15-1 |
| SSRF | 固定端点 + 不跟随跳转 + 有界响应 | `http_client` 契约 + 协议测试 |
