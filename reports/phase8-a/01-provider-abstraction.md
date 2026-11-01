# Phase8-A / M1：统一 OAuth Provider 抽象层验收报告

- 生成时间：2026-11-01
- 工作分支：`feat/phase8a-unified-oauth`
- 交付目录：`src/job_matching/service/oauth/`（13 个模块 + `providers/` 3 个适配器）
- 相关测试：`tests/phase8a/test_provider_protocol.py`（39 例）、`test_security_primitives.py`（14 例）

## 1. 模块划分（单一职责，无巨型 oauth.py）

| 模块 | 职责 | 行数量级 |
|---|---|---|
| `config.py` | `OAuthSettings` / `OAuthProviderConfig`，唯一配置入口 + 部署安全门禁 | ~330 |
| `schemas.py` | `OAuthIdentity` / `OAuthTokenResponse`（平台差异到此为止） | ~110 |
| `exceptions.py` | `OAUTH_*` ServiceError + Provider 层非 ServiceError 异常 | ~110 |
| `registry.py` | `OAuthProviderRegistry`：白名单注册 / get / list / get_status | ~130 |
| `service.py` | `OAuthService`：start / callback / exchange / bind / unbind 编排 | ~350 |
| `router.py` | `/api/v1/auth/oauth/*`，复用统一信封与错误体 | ~230 |
| `transaction_store.py` | `oauth_auth_transactions`（state 摘要 + 一次性消费） | ~160 |
| `ticket_store.py` | `oauth_login_tickets`（256 位票据 + 原子消费） | ~170 |
| `identity_repository.py` | `oauth_identities` 数据访问（唯一约束兜底并发） | ~180 |
| `identity_service.py` | 账号解析/创建/绑定/解绑（合并纪律） | ~200 |
| `security.py` | state / 摘要 / Cookie 契约 / return_path 白名单 / PKCE | ~230 |
| `http_client.py` | 受约束 httpx：超时 / 限体 / 零重试 / 不跟随跳转 | ~170 |

## 2. OAuthProvider 协议（`providers/base.py`）

```python
class OAuthProvider(Protocol):
    provider_id: str
    supports_pkce: bool
    identity_without_profile_allowed: bool

    def build_authorization_url(self, *, state, redirect_uri,
                                code_challenge=None) -> str: ...
    async def exchange_code(self, *, code, redirect_uri,
                            code_verifier=None) -> OAuthTokenResponse: ...
    async def get_identity(self, token) -> OAuthIdentity: ...
```

满足的隔离要求（全部有对应测试）：

* 三家差异封装在适配层，业务层无 `if provider == "wechat"` 分支；
* 业务层不解析 QQ JSONP（`providers/qq.py` 内安全括号解析，无 `eval`）；
* 业务层不依赖微信 OpenID 字段名、不感知微博 UID 来源；
* 对外统一 `OAuthIdentity(provider, client_id, subject, union_id?, display_name?,
  avatar_url?, email?, email_verified)`；`subject` 均为服务端核验的稳定标识
  （微信 openid / QQ openid / 微博 uid）；
* `client_id` 参与身份命名空间（`test_same_subject_different_appid_is_distinct_identity`）；
* 昵称/头像/未核验邮箱永不参与身份识别（`TestNoAutoMerge` 6 例负向测试）。

## 3. 注册表（防 SSRF）

* 白名单固定 `("wechat", "qq", "weibo")`；
* `get("evil-provider")` 显式拒绝（`oauth doctor` 的 Registry 检查同口径）；
* 端点由受控代码/配置决定，**不存在**任何 HTTP 传入端点动态创建 Provider 的路径。

## 4. 验收结论

| 检查项 | 结果 |
|---|---|
| Provider 协议完整（3 家可执行实现） | PASS |
| 平台差异全部封装在适配层 | PASS |
| OAuthIdentity 统一身份对象 | PASS |
| 注册表白名单 + 拒绝动态 Provider | PASS |
| 协议测试（39 例） | PASS（`reports/phase8-a/07-provider-mock-tests.json`） |

**M1 = PASS**。
