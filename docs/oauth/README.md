# 统一 OAuth 2.0 第三方登录（Phase8-A）

本目录是「大学生就业岗位画像与简历智能匹配系统」统一第三方登录框架的完整文档。
框架目标：**微信开放平台（PC 网站扫码）/ QQ 互联 / 微博开放平台** 三家真实平台
的接入基础设施全部就绪；真实开发者凭据到位后**只做配置与联调，不改业务源码**。

## 当前状态（诚实口径）

| 维度 | 状态 | 说明 |
|---|---|---|
| Framework Ready（统一基础架构） | **PASS** | Provider 抽象 / 注册表 / 事务 / 票据 / 身份映射 / API / 前端全部就绪 |
| Provider Adapter Ready（三家适配器） | **PASS** | 微信 / QQ / 微博适配器可执行实现 + 模拟响应协议测试 |
| Mock Integration Passed（本地模拟全链路） | **PASS** | 单测 + API 集成 + SQLite + 浏览器 E2E 全绿 |
| Real Provider Verified（真实平台授权） | **NOT_RUN** | 无真实 AppID / AppSecret / 审核通过的回调域名 |
| Platform Approval（平台审核） | **PENDING** | 待开发者账号与应用资质 |

> **重要**：Mock 测试通过 ≠ 真实平台授权成功。`available` 状态只在真实扫码登录成功后
> 由人工置位（`JM_OAUTH_<PROVIDER>_VERIFIED=true`），代码不会自动宣称已验收。

## 文档索引

| 文档 | 内容 |
|---|---|
| [architecture.md](architecture.md) | 总体架构、模块职责、登录/绑定时序图、异常流程 |
| [provider-comparison.md](provider-comparison.md) | 微信 / QQ / 微博协议差异与适配策略 |
| [database-schema.md](database-schema.md) | 三张 OAuth 表 + `users.password_hash` 可空迁移 |
| [api-contracts.md](api-contracts.md) | `/api/v1/auth/oauth/*` 接口契约与错误码 |
| [security-model.md](security-model.md) | state / CSRF / PKCE / 票据 / Token 隔离 / 日志纪律 |
| [account-linking.md](account-linking.md) | 绑定、解绑、账号合并纪律、最后登录方式保护 |
| [environment-configuration.md](environment-configuration.md) | 环境变量、状态语义、`oauth doctor` |
| [CREDENTIALS-INTEGRATION.md](CREDENTIALS-INTEGRATION.md) | **拿到凭据后的零代码接入手册** |
| [wechat-setup.md](wechat-setup.md) | 微信开放平台申请与配置 |
| [qq-setup.md](qq-setup.md) | QQ 互联申请与配置 |
| [weibo-setup.md](weibo-setup.md) | 微博开放平台申请与配置 |
| [troubleshooting.md](troubleshooting.md) | 常见故障与诊断路径 |

阶段实施与验收报告见 `reports/phase8-a/`。

## 代码位置

```text
src/job_matching/service/oauth/
├── config.py               OAuthSettings / OAuthProviderConfig（唯一配置入口）
├── schemas.py              OAuthIdentity / OAuthTokenResponse（平台差异到此为止）
├── exceptions.py           OAUTH_* 异常 -> errors.py 错误码
├── registry.py             OAuthProviderRegistry（白名单 + 状态查询）
├── service.py              OAuthService（start/callback/exchange/bind/unbind 编排）
├── router.py               /api/v1/auth/oauth/*（复用统一信封与错误体）
├── transaction_store.py    oauth_auth_transactions（state 摘要 + 一次性消费）
├── ticket_store.py         oauth_login_tickets（256 位一次性票据 + 原子消费）
├── identity_repository.py  oauth_identities 数据访问
├── identity_service.py     账号解析/创建/绑定/解绑（合并纪律）
├── security.py             state/摘要/Cookie/return_path 白名单/PKCE
├── http_client.py          受约束 httpx 客户端（超时/限体/零重试/不跟随跳转）
└── providers/
    ├── base.py             OAuthProvider 协议 + 适配器基类
    ├── wechat.py           微信开放平台网站扫码（snsapi_login）
    ├── qq.py               QQ 互联（含 JSONP 安全解析）
    └── weibo.py            微博开放平台 OAuth2

frontend/src/
├── api/oauth.ts                    OAuth API 客户端（复用 http.ts 信封）
├── composables/useOAuth.ts         OAuth UI 状态（登录态仍归 useAuth）
├── views/OAuthCompleteView.vue     /#/oauth/complete 票据交换完成页
├── components/login/AuthCard.vue   登录页三平台按钮（真实 API 调用）
└── views/SettingsView.vue          第三方账号绑定 / 纯 OAuth 账号设置密码

tests/phase8a/                      单测 + API 集成 + PostgreSQL 集成 + Fake Provider
tests/e2e/fake_oauth_server.py      浏览器可访问的模拟第三方授权服务器（仅测试）
frontend/e2e/e13-oauth-login.spec.ts          浏览器 E2E：登录
frontend/e2e/e14-oauth-account-binding.spec.ts 浏览器 E2E：绑定/解绑
frontend/e2e/e15-oauth-security.spec.ts       浏览器 E2E：安全基线
```

## 快速检查

```powershell
# 配置与安全门禁体检（不打印任何 Secret）
py -3.13 scripts/phase8a/oauth_doctor.py

# OAuth 测试套件（单测 + 集成 + 模拟 Provider 全链路）
py -3.13 tests/phase8a/run_all.py

# 浏览器 E2E（真实前后端 + 本地模拟授权服务器）
powershell -ExecutionPolicy Bypass -File tests\e2e\run_e2e.ps1
```
