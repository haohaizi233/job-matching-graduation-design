# 统一 OAuth 架构（Phase8-A）

## 1. 分层总览

```mermaid
flowchart TD
    A[Vue Login / Settings] -->|POST /auth/oauth/start| B[OAuth API router.py]
    B --> C[OAuthService service.py]
    C --> D[OAuthProviderRegistry registry.py]
    D --> E[WeChat wechat.py]
    D --> F[QQ qq.py]
    D --> G[Weibo weibo.py]
    C --> H[OAuthIdentityService]
    H --> I[(PostgreSQL / SQLite)]
    C --> J[OAuthTransactionStore]
    C --> K[OAuthTicketStore]
    H --> L[AccountService]
    L --> M[AuthSession 本站 Bearer 会话]
    M --> N[Vue useAuth]
```

依赖方向自上而下，**业务层不感知平台差异**：

* `service.py` / `identity_service.py` 中不存在 `if provider == "wechat"`；
* QQ 的 JSONP、微信的 `openid` 字段名、微博的 `uid` 来源全部封装在 `providers/`；
* 业务层只认 `OAuthIdentity(provider, client_id, subject, ...)` 与 `OAuthTokenResponse`。

## 2. 关键模块职责

| 模块 | 职责 | 不做什么 |
|---|---|---|
| `config.py` | 唯一配置入口（环境变量 -> `OAuthSettings`），回调地址解析与安全门禁 | 业务方法内不读写 `os.environ` |
| `registry.py` | Provider 白名单注册、状态查询（disabled / pending / available） | 不接受任意 Provider 名或动态端点（SSRF 防线） |
| `providers/*` | 授权 URL 构建、code 换 token、身份取回与错误映射 | 不做账号关联决策 |
| `transaction_store.py` | 授权事务（state 摘要、浏览器绑定摘要、TTL、一次性消费） | 不存 state 明文 |
| `ticket_store.py` | 一次性登录票据（256 位熵、摘要存储、原子消费） | 不做长期凭据 |
| `identity_service.py` | 身份解析/建号/绑定/解绑、合并纪律 | 不按昵称/头像/邮箱识别账号 |
| `security.py` | state/摘要/Cookie 指令/return_path 白名单/PKCE | — |
| `http_client.py` | 受约束 httpx（超时、限体、零重试、不跟随跳转、可注入 Transport） | 不做无条件重试 |
| `router.py` | HTTP 契约、限流、固定可信跳转 | 不把 code/state/token 带到前端 URL |

## 3. 第三方登录时序

```mermaid
sequenceDiagram
    participant B as 浏览器
    participant F as Vue 前端
    participant A as FastAPI OAuth 路由
    participant S as OAuthService
    participant P as 第三方平台(微信/QQ/微博)
    participant DB as PostgreSQL

    B->>F: 点击「微信登录」
    F->>A: POST /api/v1/auth/oauth/start
    A->>S: start_authorization(provider, mode=login)
    S->>DB: 写 oauth_auth_transactions(state_digest, browser_binding_digest)
    S-->>F: authorization_url + rid（绑定凭据只进 HttpOnly Cookie）
    F->>B: window.location.href = authorization_url
    B->>P: 扫码 / 确认授权
    P->>B: 302 callback?code&state
    B->>A: GET /api/v1/auth/oauth/{provider}/callback（携带绑定 Cookie）
    A->>S: handle_callback
    S->>DB: 原子消费事务（一次性，重放拒绝）
    S->>P: code 换 access_token（单次、无重试）
    S->>P: 取回身份（openid / uid）
    S->>DB: resolve_or_create_user（同一事务：建 user + oauth_identities）
    S->>DB: 签发一次性票据（摘要落库，明文进 HttpOnly Cookie）
    S-->>B: 302 前端 /#/oauth/complete?rid&mode&status
    B->>F: 打开完成页
    F->>A: POST /api/v1/auth/oauth/exchange（携带票据 Cookie）
    A->>S: exchange_login_ticket（原子消费票据）
    S->>DB: AccountService.create_session() 签发**全新**本站会话
    S-->>F: LoginResult（与 /auth/login 完全一致）
    F->>B: useAuth 更新登录态 -> /#/dashboard
```

**事务提交顺序**：`users` 与 `oauth_identities` 在同一数据库事务内
（`identity_service._create_user_with_identity`），要么同时成功、要么整体回滚，
不存在「有用户没映射」的孤儿账号；并发重复创建由唯一约束兜底并回查既有映射。

## 4. 账号绑定时序（已登录用户主动绑定）

```mermaid
sequenceDiagram
    participant B as 浏览器
    participant F as Vue 设置页
    participant A as FastAPI
    participant S as OAuthService
    participant P as 第三方平台
    participant DB as PostgreSQL

    B->>F: 设置页点击「绑定 QQ」
    F->>A: POST /auth/oauth/start（携带本站 Bearer）
    A->>S: start_authorization(mode=bind)
    S->>DB: 记录 initiator_user_id + initiator_session_digest
    F->>B: 跳转 QQ 授权
    P->>B: 302 callback
    B->>A: GET callback（绑定 Cookie）
    A->>S: handle_callback -> 票据（payload 含身份快照 + 发起会话摘要）
    B->>F: /#/oauth/complete?mode=bind
    F->>A: POST /auth/oauth/exchange（携带当前 Bearer）
    A->>S: exchange_login_ticket(mode=bind)
    S->>S: 校验发起用户 == 完成用户 且会话摘要一致（否则 OAUTH_SESSION_CHANGED）
    S->>DB: bind_identity（唯一约束；已绑他人 -> OAUTH_IDENTITY_CONFLICT）
    S-->>F: 绑定结果 -> 跳回 /#/settings
```

## 5. 异常流程

```mermaid
flowchart TD
    X[回调异常] --> Y{异常类型}
    Y -->|用户拒绝/取消| Z1[OAUTH_ACCESS_DENIED]
    Y -->|state 缺失/伪造| Z2[OAUTH_INVALID_STATE]
    Y -->|state 已消费| Z3[OAUTH_CALLBACK_REPLAY]
    Y -->|事务过期| Z4[OAUTH_STATE_EXPIRED]
    Y -->|浏览器绑定不匹配| Z5[OAUTH_INVALID_STATE]
    Y -->|code 换 token 失败| Z6[OAUTH_TOKEN_EXCHANGE_FAILED]
    Y -->|平台超时/429/5xx| Z7[OAUTH_PROVIDER_UNAVAILABLE]
    Y -->|无稳定身份标识| Z8[OAUTH_INVALID_IDENTITY]
    Y -->|票据过期/已消费| Z9[OAUTH_TICKET_EXPIRED / ALREADY_USED]
    Z1 & Z2 & Z3 & Z4 & Z5 & Z6 & Z7 & Z8 & Z9 --> R[302 固定可信前端 /#/oauth/complete?status=error&reason=CODE]
    R --> U[完成页展示明确错误，绝不回显 code/state/token]
```

所有错误路径都跳**固定可信**前端地址（`JM_OAUTH_FRONTEND_ORIGIN` 首个 Origin +
`/#/oauth/complete`），URL 上只携带 `rid / mode / status / reason / return_path`
等非秘密信息。

## 6. ER 图

```mermaid
erDiagram
    users ||--o{ oauth_identities : "绑定"
    users ||--o{ auth_sessions : "本站会话"
    users ||--o{ oauth_login_tickets : "票据指向"
    oauth_identities {
        string id PK
        string user_id FK
        string provider
        string client_id
        string subject
        string union_id NULL
        string display_name NULL
        string avatar_url NULL
        datetime last_login_at NULL
    }
    oauth_auth_transactions {
        string id PK
        string rid UK
        string provider
        string mode
        string state_digest UK
        string browser_binding_digest
        string browser_binding_key
        string initiator_user_id NULL
        string initiator_session_digest NULL
        string redirect_uri
        string return_path
        string code_verifier NULL
        datetime expires_at
        datetime consumed_at NULL
    }
    oauth_login_tickets {
        string id PK
        string ticket_digest UK
        string mode
        string user_id FK
        string browser_binding_digest
        string browser_binding_key
        json payload_json NULL
        datetime expires_at
        datetime consumed_at NULL
    }
```

详见 [database-schema.md](database-schema.md)。

## 7. 三种 Token 严格隔离

| 名称 | 生命期 | 存放 | 用途 |
|---|---|---|---|
| Provider Access Token | 单次登录内 | 仅服务端内存 | 取回第三方身份；不进浏览器/URL/日志，用完即弃 |
| OAuth 一次性登录票据 | 30–60 秒 | HttpOnly Cookie + DB 摘要 | 回调后换本站会话；一次性、原子消费 |
| 本站 AuthSession Bearer | 既有会话周期 | localStorage（现状，沿用 `useAuth`） | 现有业务 API 鉴权 |

> 当前 `useAuth` 沿用 localStorage 存 Bearer Token（保持全部旧业务兼容）。
> 其 XSS 暴露风险已在安全模型中登记，改 HttpOnly Cookie Session 属独立安全阶段，
> 不在 OAuth 基础设施任务中突然重写。

## 8. 反依赖约束（可自动检查）

* `src/job_matching/service/oauth/service.py`、`identity_service.py`、
  `identity_repository.py`、`ticket_store.py`、`transaction_store.py`
  不得 import 具体 Provider，不得出现平台名分支；
* `providers/` 内端点是**受控常量**，禁止由请求侧传入 URL；
* 测试专用 Fake Provider 只存在于 `tests/` 下，生产代码不 import，
  也没有任何请求参数 / 环境变量能打开 Fake Provider。
