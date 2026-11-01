# OAuth API 契约（Phase8-A / M6）

全部接口挂在既有认证体系下，**复用项目统一响应信封与错误体**：

```json
{
  "request_id": "req_...",
  "api_version": "v1",
  "app_version": "...",
  "data": { },
  "warnings": []
}
```

错误体：

```json
{
  "error": {
    "code": "OAUTH_INVALID_STATE",
    "message": "OAuth state 缺失或不匹配（疑似 CSRF/伪造回调）",
    "request_id": "req_...",
    "detail": { }
  }
}
```

## 1. 接口清单

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/auth/oauth/providers` | 否 | 平台状态（绝不返回 Secret） |
| POST | `/api/v1/auth/oauth/start` | login 模式否 / bind 模式是 | 发起授权，创建授权事务 + 浏览器绑定 Cookie |
| GET | `/api/v1/auth/oauth/{provider}/callback` | 否（凭 state + 绑定 Cookie） | Provider 回调，302 到前端完成页 |
| POST | `/api/v1/auth/oauth/exchange` | login 模式否 / bind 模式是 | 一次性票据交换本站会话 / 完成绑定 |
| GET | `/api/v1/auth/oauth/identities` | 是 | 已绑定身份列表 |
| DELETE | `/api/v1/auth/oauth/identities/{ref}` | 是 | 解绑（`ref` = provider 或 identity_id） |
| POST | `/api/v1/auth/oauth/set-password` | 是 | 纯 OAuth 账号补设本站密码 |

既有接口契约保持不变：`/auth/register`、`/auth/login`、`/auth/logout`、`/auth/me`。

## 2. GET `/providers`

```json
{
  "data": {
    "providers": [
      { "id": "wechat", "label": "微信", "enabled": true,  "status": "configured_pending_verification", "reason_code": null },
      { "id": "qq",     "label": "QQ",   "enabled": true,  "status": "configured_pending_verification", "reason_code": null },
      { "id": "weibo",  "label": "微博", "enabled": false, "status": "disabled", "reason_code": "OAUTH_PROVIDER_NOT_CONFIGURED" }
    ]
  }
}
```

状态语义（**有配置 ≠ 已验收**）：

| status | enabled | 含义 |
|---|---|---|
| `disabled` | false | 未启用 / 未配置（`reason_code` 说明原因） |
| `configured_pending_verification` | true | 配置齐全但**未真实联调**（默认落点） |
| `available` | true | 真实扫码登录成功后人工置 `JM_OAUTH_<PROVIDER>_VERIFIED=true` |

响应不包含 `client_secret`、token、任何凭据。

## 3. POST `/start`

请求：

```json
{ "provider": "qq", "mode": "login", "return_path": "/dashboard" }
```

成功（200）：

```json
{
  "data": {
    "authorization_url": "https://graph.qq.com/oauth2.0/authorize?...",
    "expires_in": 300,
    "rid": "8c6403e4a9fade44",
    "mode": "login",
    "return_path": "/dashboard"
  }
}
```

同时下发 HttpOnly Cookie（浏览器绑定凭据，**不进响应体**）：

```text
Set-Cookie: jm_oauth_bb_<rid>=<secret>; HttpOnly; SameSite=Lax; Path=/api/v1/auth/oauth
```

失败：

| 情况 | HTTP | code |
|---|---|---|
| 平台未配置 | 503 | `OAUTH_PROVIDER_NOT_CONFIGURED` |
| 平台被显式禁用 | 503 | `OAUTH_PROVIDER_DISABLED` |
| bind 模式未登录 | 401 | `OAUTH_BIND_REQUIRES_AUTH` |
| `return_path` 越界（开放重定向） | 400 | `OAUTH_INVALID_REDIRECT` |
| mode 非法 | 400 | `INVALID_REQUEST` |
| 发起频率超限 | 429 | `RATE_LIMITED` |

## 4. GET `/{provider}/callback`

输入（Provider 302 回来）：`?code=...&state=...` 或 `?error=access_denied&state=...`。

行为：

1. 校验 provider 状态、state 摘要、TTL、一次性消费、浏览器绑定 Cookie；
2. code 换 token（单次、无重试）→ 取回身份；
3. login：事务内解析/创建本站用户；bind：签发携带身份快照的票据；
4. 签发一次性票据 Cookie：`jm_oauth_ticket_<rid>`；
5. **302 到固定可信前端地址**：

```text
{JM_OAUTH_FRONTEND_ORIGIN}/#/oauth/complete?rid=...&mode=login&status=ok&return_path=/dashboard
```

错误路径同样只跳固定可信地址：

```text
.../#/oauth/complete?rid=-&mode=login&status=error&reason=OAUTH_INVALID_STATE
```

**回调处理完成后不把 `code` / `state` / token 传播到前端 URL**（`rid` 是非秘密短标识）。

## 5. POST `/exchange`

请求：`{ "rid": "8c6403e4a9fade44" }`（票据与绑定凭据从 HttpOnly Cookie 读取）。

login 模式成功（200）——结构与 `/auth/login` 的 `data` **完全一致**：

```json
{
  "data": {
    "token": "<本站会话 Token>",
    "user": {
      "id": "<本站用户 ID>",
      "username": "qq_a1b2c3d4",
      "email": null,
      "role": "student",
      "status": "active"
    },
    "token_type": "bearer",
    "expires_at": "<到期时间>",
    "session_id": "<本站会话 ID>"
  }
}
```

bind 模式成功：

```json
{ "data": { "bound": true, "identity": { "id": "...", "provider": "qq", "display_name": null, "avatar_url": null, "created_at": "...", "last_login_at": null }, "already_bound": false } }
```

失败：

| 情况 | HTTP | code |
|---|---|---|
| 票据过期 / 不存在 / 绑定不匹配 | 400 | `OAUTH_TICKET_EXPIRED` |
| 票据已消费（重放） | 400 | `OAUTH_TICKET_ALREADY_USED` |
| bind 时登录态变化 | 409 | `OAUTH_SESSION_CHANGED` |
| bind 未登录 | 401 | `OAUTH_BIND_REQUIRES_AUTH` |
| 身份已被他人绑定 | 409 | `OAUTH_IDENTITY_CONFLICT` |
| Origin 不在可信白名单 | 400 | `OAUTH_INVALID_REDIRECT` |
| 交换频率超限 | 429 | `RATE_LIMITED` |

> 不自创 JWT；不改变既有 Bearer Token 校验方式；不把本站 Bearer Token 放入回调 URL。

## 6. GET `/identities`

```json
{
  "data": {
    "items": [
      { "id": "...", "provider": "qq", "display_name": "合成昵称", "avatar_url": "https://img.fake.test/a.png", "created_at": "...", "last_login_at": "..." }
    ],
    "password_login_available": false
  }
}
```

`password_login_available` 供前端决定展示「修改密码」还是「设置本站密码」。

## 7. DELETE `/identities/{ref}`

* `ref` 可以是 `provider`（如 `qq`）或 `identity_id`（同平台多身份时精确指定）；
* 只有账号所有者能解绑自己的身份（他人 identity 返回 `NOT_FOUND`，防枚举）；
* 要求**近期重新认证**的会话（默认 30 分钟窗口，`require_recent_session`）；
* 解绑后账号将失去全部登录方式 → 403 `OAUTH_LAST_LOGIN_METHOD`。

成功：`{ "data": { "unbound": true, "identity": { ... } } }`

## 8. POST `/set-password`

请求：`{ "new_password": "至少10位含字母与数字" }`

成功：`{ "data": { "password_set": true, "revoked_sessions": 2 } }`
（除当前设备外的会话全部撤销；当前 Token 保持有效。）

## 9. 错误码全表

| code | HTTP | 含义 |
|---|---|---|
| `OAUTH_PROVIDER_NOT_CONFIGURED` | 503 | 平台未配置（缺 AppID/AppSecret/回调） |
| `OAUTH_PROVIDER_DISABLED` | 503 | 平台被显式禁用 |
| `OAUTH_INVALID_STATE` | 400 | state 缺失/不匹配（疑似 CSRF） |
| `OAUTH_STATE_EXPIRED` | 400 | 授权事务过期 |
| `OAUTH_CALLBACK_REPLAY` | 400 | 回调已消费，拒绝重放 |
| `OAUTH_ACCESS_DENIED` | 400 | 用户取消/拒绝授权 |
| `OAUTH_TOKEN_EXCHANGE_FAILED` | 502 | code 换 token 失败或响应非法 |
| `OAUTH_PROVIDER_UNAVAILABLE` | 502 | 平台超时/限流/服务异常 |
| `OAUTH_INVALID_IDENTITY` | 502 | 平台未返回稳定身份标识 |
| `OAUTH_IDENTITY_CONFLICT` | 409 | 第三方身份已绑定其他账号 |
| `OAUTH_BIND_REQUIRES_AUTH` | 401 | 绑定需先登录本站 |
| `OAUTH_SESSION_CHANGED` | 409 | 发起与完成绑定的会话不一致 |
| `OAUTH_TICKET_EXPIRED` | 400 | 票据过期/无效 |
| `OAUTH_TICKET_ALREADY_USED` | 400 | 票据已消费，拒绝重放 |
| `OAUTH_LAST_LOGIN_METHOD` | 403 | 该身份是唯一登录方式，禁止解绑 |
| `OAUTH_INVALID_REDIRECT` | 400 | return_path / 回调地址非法 |

全部错误码注册在 `src/job_matching/service/errors.py::ERROR_CODES`，
**不抛未注册错误码**（避免重现 `MODEL_ARTIFACT_TAMPERED` 类问题）。

## 10. 限流

| 接口 | 默认上限（每客户端每分钟） | 环境变量 |
|---|---|---|
| `/start` | 30 | `JM_OAUTH_START_RATE_LIMIT` |
| `/callback`（失败计数） | 30 | `JM_OAUTH_CALLBACK_RATE_LIMIT` |
| `/exchange` | 60 | `JM_OAUTH_EXCHANGE_RATE_LIMIT` |

单进程内存实现；多实例部署需在网关侧再加一层。
