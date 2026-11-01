# 数据库 Schema（Phase8-A / M3）

Alembic 迁移：`alembic/versions/e8a0f1c2d3a4_phase8a_oauth.py`
（revision `e8a0f1c2d3a4`，down_revision `d7e8f9a0b1c2`）。
迁移**只新增三张表 + 放宽一个列**，不修改既有历史迁移文件。

```powershell
py -3.13 -m alembic upgrade head      # 升级
py -3.13 -m alembic downgrade -1      # 回滚本迁移（实测可回滚）
```

## 1. `oauth_identities`（第三方身份映射）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PK | UUID |
| `user_id` | VARCHAR(36) | FK → `users.id` ON DELETE CASCADE | 本站账号 |
| `provider` | VARCHAR(32) | NOT NULL | wechat / qq / weibo |
| `client_id` | VARCHAR(128) | NOT NULL | AppID（参与身份命名空间） |
| `subject` | VARCHAR(128) | NOT NULL | 平台稳定标识（openid / openid / uid） |
| `union_id` | VARCHAR(128) | NULL | 微信 UnionID（可空） |
| `display_name` | VARCHAR(255) | NULL | 昵称（仅展示，不参与识别） |
| `avatar_url` | VARCHAR(512) | NULL | 头像（仅展示） |
| `created_at` / `updated_at` | DATETIME | NOT NULL | |
| `last_login_at` | DATETIME | NULL | 最近一次以该身份登录 |

约束与索引：

```text
UNIQUE (provider, client_id, subject)   -- 同一平台身份只能绑一个本站用户
INDEX  (user_id)
INDEX  (user_id, provider)              -- 同一账号同一平台最多一个身份（服务层策略）
```

设计要点：

* **不同 AppID 的 OpenID 不会碰撞**（`client_id` 在唯一键内）；
* 同一平台身份不能绑定两个本站用户（数据库唯一约束保证，并发绑定靠约束而非先查后插）；
* 同一本站用户可绑定不同平台；同一平台多个身份由服务层显式拒绝
  （`OAUTH_IDENTITY_CONFLICT`），策略可查可改（见 `identity_service.bind_identity`）；
* 事务失败整体回滚，不留半成功记录。

## 2. `oauth_auth_transactions`（授权事务）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PK | UUID |
| `rid` | VARCHAR(16) | UNIQUE | 事务短标识（进 URL 定位 Cookie 名；非安全凭据） |
| `provider` | VARCHAR(32) | NOT NULL | |
| `mode` | VARCHAR(16) | NOT NULL | `login` / `bind` |
| `state_digest` | VARCHAR(64) | UNIQUE | state 的 SHA-256（**不存明文**） |
| `browser_binding_digest` | VARCHAR(64) | NOT NULL | 浏览器绑定凭据摘要 |
| `browser_binding_key` | VARCHAR(32) | NOT NULL | = rid（Cookie 名后缀，事务隔离） |
| `initiator_user_id` | VARCHAR(36) | FK → users.id ON DELETE SET NULL | bind 模式发起用户 |
| `initiator_session_digest` | VARCHAR(64) | NULL | bind 模式发起会话摘要（换绑一致性校验） |
| `redirect_uri` | VARCHAR(512) | NOT NULL | 受控配置解析出的回调地址 |
| `return_path` | VARCHAR(256) | NOT NULL | 站内白名单路由 |
| `code_verifier` | VARCHAR(128) | NULL | PKCE verifier（Provider 支持时才用） |
| `created_at` / `expires_at` | DATETIME | NOT NULL | TTL 默认 300s |
| `consumed_at` | DATETIME | NULL | 一次性消费标记 |

约束与索引：`UNIQUE(rid)`、`UNIQUE(state_digest)`、`INDEX(expires_at)`、`INDEX(state_digest)`。

消费语义（`transaction_store.consume`）：

* 未知 state → `OAUTH_INVALID_STATE`；
* 已消费 → `OAUTH_CALLBACK_REPLAY`（原子 `UPDATE ... WHERE consumed_at IS NULL`）；
* 过期 → `OAUTH_STATE_EXPIRED`；
* provider/mode 不匹配 → `OAUTH_INVALID_STATE`；
* 并发回调只有一个赢家。

## 3. `oauth_login_tickets`（一次性登录票据）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PK | UUID |
| `ticket_digest` | VARCHAR(64) | UNIQUE | 票据 SHA-256（明文只在 HttpOnly Cookie） |
| `mode` | VARCHAR(16) | NOT NULL | `login` / `bind` |
| `user_id` | VARCHAR(36) | FK → users.id ON DELETE CASCADE | 票据指向的本站用户 |
| `browser_binding_digest` | VARCHAR(64) | NOT NULL | 浏览器绑定校验 |
| `browser_binding_key` | VARCHAR(32) | NOT NULL | = rid |
| `payload_json` | JSON | NULL | bind：身份快照 + 发起会话摘要；login：identity_id/created |
| `created_at` / `expires_at` | DATETIME | NOT NULL | TTL 默认 60s（30–300s 可配） |
| `consumed_at` | DATETIME | NULL | 原子消费标记 |

安全属性：

* 明文熵 32 字节（`secrets.token_urlsafe(32)` = 256 位，≥128 位要求）；
* TTL 30–60 秒；只用于短时间内交换本站会话；
* 原子消费（并发双交换只成功一次）→ 重放返回 `OAUTH_TICKET_ALREADY_USED`；
* 未知/过期/绑定不匹配一律 `OAUTH_TICKET_EXPIRED`，**错误票据不泄露用户 ID**；
* `cleanup()` 删除过期超过窗口的历史票据。

## 4. `users.password_hash` 可空（纯 OAuth 账号）

```text
迁移前：password_hash VARCHAR(255) NOT NULL
迁移后：password_hash VARCHAR(255) NULL
```

业务规则（`identity_service` / `accounts` 强制）：

| 账号类型 | `password_hash` | 行为 |
|---|---|---|
| 普通密码注册 | Argon2id 哈希 | 原流程完全不变 |
| 纯 OAuth | `NULL` | 密码登录按「凭证无效」拒绝（不抛异常、不泄露账号存在） |
| 纯 OAuth 后补密码 | 设置后为 Argon2id 哈希 | `/auth/oauth/set-password`（要求当前登录态） |

* **不使用**固定密码 / 空密码 / 可预测密码创建 OAuth 用户；
* `change_password()` 不把 `NULL` 当作合法旧密码（需要旧密码的路径拒绝）；
* 原有账号无需重建、原有 Token 不失效、原有 `user_id` 引用不变
  （简历 / 画像 / 推荐记录全部保持）。

OAuth 新用户默认：`role = student`、`status = active`、`email = NULL`，
用户名形如 `qq_a1b2c3d4`（平台前缀 + 随机后缀，唯一），**不用第三方昵称当 username**。

## 5. 兼容性实测

| 检查项 | SQLite | PostgreSQL |
|---|---|---|
| `upgrade head` | PASS | PASS* |
| `downgrade` 回滚正确 | PASS | PASS* |
| 旧账号数据不丢失 | PASS | PASS* |
| `password_hash` 可空生效 | PASS | PASS* |
| `(provider, client_id, subject)` 唯一约束 | PASS | PASS* |
| 外键约束（CASCADE / SET NULL） | PASS | PASS* |
| OAuth-only 用户创建 + 登录链路 | PASS | PASS* |
| 事务回滚不留半成功记录 | PASS | PASS* |

\* PostgreSQL 由 `tests/phase8a/test_pg_integration.py` 覆盖；
未提供 `JM_TEST_DATABASE_URL_POSTGRES` 时该组显式记 **NOT_RUN**（绝不冒充 PASS），
CI 的 `postgres-integration` 作业提供真实 PostgreSQL 后运行。
