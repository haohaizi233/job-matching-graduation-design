# Phase8-A / M3：数据库迁移验收报告（Alembic / SQLite / PostgreSQL）

- 生成时间：2026-11-01
- 迁移文件：`alembic/versions/e8a0f1c2d3a4_phase8a_oauth.py`
  （revision `e8a0f1c2d3a4`，down_revision `d7e8f9a0b1c2`，head 链完整）
- 纪律：**未修改任何既有历史迁移文件**；有真实 `upgrade()` / `downgrade()`。

## 1. 变更内容

### 1.1 `oauth_identities`

```text
id, user_id FK(users.id, CASCADE), provider, client_id, subject,
union_id NULL, display_name NULL, avatar_url NULL,
created_at, updated_at, last_login_at NULL
UNIQUE(provider, client_id, subject)  -- uq_oauth_identities_subject
```

* 同一平台身份不能绑定两个本站用户（唯一约束，不靠先查后插）；
* `client_id` 参与唯一键 → 不同 AppID 的 OpenID 不碰撞；
* 索引：`ix_oauth_identities_user_id`、`ix_oauth_identities_user_provider`。

### 1.2 `oauth_auth_transactions`

```text
id, rid UNIQUE, provider, mode(login|bind), state_digest UNIQUE,
browser_binding_digest, browser_binding_key,
initiator_user_id NULL FK(users.id, SET NULL), initiator_session_digest NULL,
redirect_uri, return_path, code_verifier NULL,
created_at, expires_at, consumed_at NULL
```

* `state` 明文**不落库**（只存 SHA-256 摘要）；
* TTL + 一次性消费（`consumed_at`）；PKCE verifier 按平台契约可选。

### 1.3 `oauth_login_tickets`

```text
id, ticket_digest UNIQUE, mode, user_id FK(users.id, CASCADE),
browser_binding_digest, browser_binding_key, payload_json,
created_at, expires_at, consumed_at
```

* 256 位随机票据、摘要落库、原子消费、30–60s TTL、重放拒绝。

### 1.4 `users.password_hash` → NULLABLE

* 只放宽约束、**不改任何既有值**；原有账号 / 会话 Token / 简历 / 画像 /
  推荐记录的 `user_id` 全部不变；
* 普通注册用户仍必有 Argon2id 哈希；纯 OAuth 用户 `password_hash = NULL`，
  禁止固定/空/可预测密码占位（`test_oauth_only_password_login_rejected` 等）。

## 2. downgrade 纪律

回滚顺序：先删三张 OAuth 表，再收回 `password_hash NOT NULL`；
收回前检查 `password_hash IS NULL` 的纯 OAuth 账号数量，**存在则拒绝回滚并显式报错**
（不静默删号、不伪造密码），运维先处置后再回滚。

## 3. 实测矩阵

| 检查 | SQLite | PostgreSQL |
|---|---|---|
| `alembic upgrade head` 全链 | PASS（每套测试夹具建库都真实执行） | NOT_RUN（无 `JM_TEST_DATABASE_URL_POSTGRES`） |
| `alembic downgrade base` 回滚正确性 | PASS（`run_downgrade` 夹具 + 迁移链重建） | NOT_RUN |
| 旧账号迁移（数据不丢失） | PASS（既有 users 行值不变，只放宽约束） | NOT_RUN |
| 外键约束 | PASS（`test_unique_constraint_and_fk` 口径） | NOT_RUN |
| 唯一约束（并发兜底） | PASS（`test_oauth_duplicate_concurrent_register`） | NOT_RUN |
| NULL 密码兼容 | PASS（`test_oauth_only_password_login_rejected`） | NOT_RUN |
| 事务失败回滚无孤儿 | PASS（`test_transaction_rollback_leaves_no_partial_rows`） | NOT_RUN |

PostgreSQL 组（`tests/phase8a/test_pg_integration.py` 5 例）在无测试库时按纪律记
**NOT_RUN**，绝不冒充 PASS；提供 `JM_TEST_DATABASE_URL_POSTGRES` 后可直接复跑。

## 4. 验收结论

SQLite 全绿 + 迁移链/回滚真实执行；PostgreSQL 待环境（NOT_RUN）。

**M3 = PASS**（PostgreSQL 集成标记 NOT_RUN，不计入 PASS 也不计入 FAIL）。
