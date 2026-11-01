# Phase8-A / M11：真实凭据就绪度报告（09-credentials-readiness）

- 生成时间：2026-11-01
- 结论：**凭据未到位，`real_provider_integration = NOT_RUN`**。
  拿到凭据后按 `docs/oauth/CREDENTIALS-INTEGRATION.md` 操作即可，无需改业务源码。

## 1. 就绪状态（诚实口径）

```text
implementation            = COMPLETE
mock_integration          = PASS
real_provider_integration = NOT_RUN
provider_approval         = PENDING
```

## 2. 逐平台凭据清单（只登记状态，不打印任何 Secret）

### 微信开放平台（wechat）

```text
Provider:       微信开放平台（网站应用 / PC 扫码）
AppID:          未提供（待填 JM_OAUTH_WECHAT_CLIENT_ID）
AppSecret:      未提供（待填 JM_OAUTH_WECHAT_CLIENT_SECRET，只在服务端）
审核状态:        未申请（PENDING）
回调域名:        未登记（需与 JM_OAUTH_PUBLIC_BASE_URL 域名一致）
授权 Scope:      snsapi_login
权限状态:        未申请（PENDING）
真实联调状态:     NOT_RUN
```

### QQ 互联（qq）

```text
Provider:       QQ 互联（网站应用）
AppID:          未提供（待填 JM_OAUTH_QQ_CLIENT_ID）
AppSecret:      未提供（待填 JM_OAUTH_QQ_CLIENT_SECRET，只在服务端）
审核状态:        未申请（PENDING）
回调域名:        未登记（完整回调 URL 必须逐字符一致）
授权 Scope:      get_user_info
权限状态:        未申请（PENDING）
真实联调状态:     NOT_RUN
```

### 微博开放平台（weibo）

```text
Provider:       微博开放平台（网站接入）
AppID:          未提供（待填 JM_OAUTH_WEIBO_CLIENT_ID，App Key）
AppSecret:      未提供（待填 JM_OAUTH_WEIBO_CLIENT_SECRET，只在服务端）
审核状态:        未申请（PENDING）
回调域名:        未登记（OAuth2.0 授权设置内配置）
授权 Scope:      基础登录接口
权限状态:        未申请（PENDING；用户资料接口权限随资质变化）
真实联调状态:     NOT_RUN
```

## 3. 零代码接入验证

凭据到位后的操作全部是**配置 + 平台侧登记 + 真实联调**：

1. `.env.example` → `.env` 填 `JM_OAUTH_<P>_*`；
2. `py -3.13 -m alembic upgrade head`（迁移已在 CI/测试验证）；
3. 启动 FastAPI / Vue；
4. `py -3.13 scripts/phase8a/oauth_doctor.py`（状态应变为
   `CONFIGURED_PENDING_VERIFICATION`）；
5. `GET /api/v1/auth/oauth/providers` 核对三态；
6. 真实扫码登录；
7. 验证 `users` / `oauth_identities` / `auth_sessions`；
8. 绑定 / 重复登录 / 解绑；
9. 确认无 Token 泄露；
10. 置 `JM_OAUTH_<P>_VERIFIED=true`，状态变为 `available`。

无需修改：Provider 适配器、OAuthService、数据库、前端组件、API 契约。

## 4. 风险与等待项

| 项 | 状态 | 影响 |
|---|---|---|
| 三家 AppID/AppSecret | 等待开发者提供 | 未配置时三平台安全禁用，密码登录不受影响 |
| 平台应用审核 | 等待平台 | 审核中点登录 → 明确错误文案，无假成功 |
| HTTPS + 备案回调域名 | 等待部署环境 | 生产非 HTTPS 会被 `check_safety()` 拒绝启用 |
| PostgreSQL 测试库 | **已提供**（Docker postgres:16-alpine，`JM_TEST_DATABASE_URL_POSTGRES`） | PG 集成测试真实执行并全绿（见 07/08 证据） |
| 微信 UnionID 机制 / QQ JSONP 触发条件 / 微博资料权限 | PROVIDER_VERIFICATION_PENDING | 联调时复核，不虚构字段 |
