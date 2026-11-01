# Phase8-A / M5：OAuth 安全基线验证报告

- 生成时间：2026-11-01
- 相关测试：`tests/phase8a/test_security_primitives.py`（14 例）、
  `test_transaction_ticket.py`（17 例）、`test_api_flows.py` 安全分组（17 例）
- 结论先行：**M5 全部负向测试通过；未开启真实 Provider 前的安全门禁满足。**

## 1. 要求 → 实现 → 证据对照

| # | 要求 | 实现 | 测试证据 |
|---|---|---|---|
| 1 | state 用 CSPRNG、不可预测 | `secrets.token_urlsafe(32)` | `test_state_randomness`（大样本无碰撞） |
| 2 | 服务端可核对（摘要比对） | `state_digest` UNIQUE 落库 | `test_state_lifecycle_and_digest_only` |
| 3 | 与 Provider 绑定 | 事务含 provider，回调逐项比对 | `test_state_wrong_provider` |
| 4 | 与浏览器绑定 | 按事务 Cookie `jm_oauth_bb_<rid>` + 摘要比对 | `test_state_browser_binding` |
| 5 | 与 login/bind 模式绑定 | 事务 mode 比对 | `test_state_mismatch_mode` |
| 6 | TTL + 一次性消费 | `expires_at` / `consumed_at` 原子更新 | `test_state_expired`、`test_state_replay` |
| 7 | 空值/不匹配拒绝 | 显式校验 | `test_state_missing_or_unknown`、`test_state_mismatch` |
| 8 | 多标签页隔离 | 每事务独立 Cookie | `test_multi_tab_authorization`、`test_per_transaction_cookie_isolation` |
| 9 | Cookie 契约 | HttpOnly + SameSite=Lax + 短 TTL + 受限 Path（HTTPS 时 Secure） | `test_binding_cookie_flags`、`test_ticket_cookie_flags_and_clear` |
| 10 | PKCE S256（按契约启用） | `supports_pkce` 逐平台；三家未确认 → 默认关闭 | `test_pkce_s256_rfc7636_vector`、`test_pkce_when_supported` |
| 11 | return_path 白名单 | 标准 URL 解析 + 站内路径白名单 | `test_redirect_open_redirect_rejected`（5 类攻击样例全拒）、`test_rejects_overlong` |
| 12 | 回调地址受控 | 配置派生固定路径，无请求侧输入 | `test_config_status_states`、doctor Redirect Policy |
| 13 | 三种 Token 隔离 | Provider token 不出服务端；票据一次性；Bearer 复用既有会话 | `test_api_responses_never_contain_provider_token` |
| 14 | Session Fixation | OAuth 完成签发**新**会话 | `test_oauth_issues_new_session_each_login` |
| 15 | 票据 256 位 + 摘要落库 + 原子消费 | `OAuthTicketStore` | `test_ticket_digest_only_in_db`、`test_ticket_double_exchange_race` |
| 16 | 票据重放/过期拒绝 | 唯一约束 + consumed_at | `test_ticket_replay`、`test_ticket_expired` |
| 17 | 错误票据不泄露用户 | 统一错误文案 | `test_ticket_error_messages_do_not_leak_user_id`、`test_exchange_unknown_ticket_not_leaking_user` |
| 18 | callback 异常分类 | 超时/429/5xx/畸形响应映射 | `test_oauth_provider_timeout`、`test_oauth_provider_malformed_response`、`test_provider_http_errors_mapped_not_password_error` |
| 19 | code 重放拒绝 | 平台侧 code 一次性 + 事务一次性 | `test_code_replay_rejected` |
| 20 | 限流 | start / callback 失败 / exchange 三处 | `test_oauth_start_rate_limited`、`test_callback_failure_rate_limited` |
| 21 | 安全日志不泄密 | 结构化日志仅元数据 | `test_oauth_secret_not_logged`（Secret/state/ticket/Token 全不在日志） |
| 22 | 绑定防抢绑/会话漂移 | initiator 校验 | `test_oauth_unauthorized_binding`、`test_oauth_binding_user_changed`、`test_oauth_identity_conflict` |
| 23 | 并发建号唯一 | 数据库唯一约束 + 回滚回查 | `test_oauth_duplicate_concurrent_register` |
| 24 | 纯 OAuth 账号密码登录拒绝 | `password_hash=NULL` 显式拒绝且不泄露存在性 | `test_oauth_only_password_login_rejected` |
| 25 | 最后登录方式保护 | 解绑前检查 | `test_oauth_last_login_method_cannot_unbind` |
| 26 | 禁止昵称/邮箱合并 | 身份键唯一化 | `test_oauth_login_does_not_merge_by_nickname`、`..._by_unverified_email` |
| 27 | Origin 校验 | exchange 校验 Origin 白名单 | `test_exchange_wrong_origin_rejected` |
| 28 | 明文不落库 | state/ticket 只存 SHA-256 摘要 | `test_digest_is_one_way_sha256` |

## 2. Token 隔离三分法（落实情况）

```text
Provider Access Token  → 只在服务端换身份期间存在于内存，不进响应/日志/URL/库
一次性本站登录票据      → HttpOnly 短时 Cookie + 服务端摘要，30-60s，原子消费
本站 Bearer Token       → 复用既有会话系统（useAuth 存储行为本轮不改）
```

已登记遗留风险（不在本阶段突然改写）：`useAuth` 的 localStorage Token 存在 XSS 暴露面，
转 HttpOnly Cookie Session 作为独立安全阶段实施（见 `05` 遗留项 / README）。

## 3. 安全日志纪律

允许：`request_id / provider / flow_type / outcome / reason_code / duration_ms /
client_ip_hash / oauth_transaction_id`；
禁止：AppSecret、Provider token、refresh token、code、state 明文、ticket、
Bearer Token、完整用户资料。有回归测试持续看护（`test_oauth_secret_not_logged`）。

## 4. 验收结论

**M5 = PASS**。28 项安全要求全部有实现与负向测试证据；
真实 Provider 开启前的安全门禁满足。
