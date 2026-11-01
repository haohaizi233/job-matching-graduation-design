# 故障排查（troubleshooting.md）

> 诊断顺序永远是：**oauth doctor → /oauth/providers 三态 → 浏览器网络面板 →
> 后端安全日志（reason_code）→ 库表**。绝不先改代码。

## 1. 快速体检

```powershell
py -3.13 scripts/phase8a/oauth_doctor.py
```

* 某平台 `CREDENTIALS_MISSING` → 先补配置（见 environment-configuration.md）；
* `Deployment Safety: WARN` → 生产缺 HTTPS 或缺前端 Origin 白名单；
* `Ticket Store / Redirect Policy: FAIL` → 代码级问题，跑 `tests/phase8a` 定位。

## 2. 按钮状态类

| 现象 | 原因 | 处理 |
|---|---|---|
| 三个按钮都「暂未开放」 | `JM_OAUTH_ENABLED=false` 或各平台未配置 | 补配置；这是预期的安全禁用态 |
| 某平台「配置中」点击无反应 | `configured_pending_verification` | 平台审核 + 真实联调后置 `*_VERIFIED=true` |
| 点击报「第三方登录未完成」 | 平台侧错误（未审核/凭据错） | 看安全日志 `reason_code`，对照平台专章 |

## 3. 授权跳转类

| 现象 | 原因 | 处理 |
|---|---|---|
| `OAUTH_INVALID_REDIRECT` | `return_path` 外跳/混淆 | 只允许站内路径；前端别传绝对 URL |
| `OAUTH_INVALID_STATE` | state 不匹配 / Cookie 丢失 | 确认 Cookie 未被禁用；跨站顶级 GET 回调需 SameSite=Lax |
| `OAUTH_STATE_EXPIRED` | 超过 TTL（默认 300s） | 重新发起授权 |
| `OAUTH_CALLBACK_REPLAY` | 回调重复消费 | 正常防护；刷新后重新登录 |
| 多标签页错绑 | 浏览器绑定 Cookie 被覆盖 | 本实现按事务隔离 Cookie（`jm_oauth_bb_<rid>`），如复现请报缺陷 |
| `OAUTH_SESSION_CHANGED` | 绑定期间登录态切换 | 重新登录后再次发起绑定 |

## 4. 令牌与票据类

| 现象 | 原因 | 处理 |
|---|---|---|
| `OAUTH_TOKEN_EXCHANGE_FAILED` | code 无效/过期/平台响应异常 | 看 reason_code；多数为重放或平台未审核 |
| `OAUTH_PROVIDER_UNAVAILABLE` | 平台超时 / 429 / 5xx | 稍后重试；限流保护生效 |
| `OAUTH_TICKET_EXPIRED` | 票据 TTL（默认 60s）内未交换 | 重新登录 |
| `OAUTH_TICKET_ALREADY_USED` | 票据重放（含刷新重复提交） | 正常防护；从登录页重新发起 |
| 交换后 401 | 票据 Cookie 与请求不匹配 | 确认同浏览器、同 tab 发起 |

## 5. 账号与绑定类

| 现象 | 原因 | 处理 |
|---|---|---|
| 登录产生新账号而非旧账号 | **设计如此**：禁止按昵称/邮箱自动合并 | 用旧账号登录后在设置页主动绑定 |
| `OAUTH_IDENTITY_CONFLICT` | 该第三方身份已绑他人 / 同平台多身份 | 先解绑或换账号 |
| `OAUTH_LAST_LOGIN_METHOD` | 解绑后将无任何登录方式 | 先设置本站密码或绑定其它平台 |
| `OAUTH_BIND_REQUIRES_AUTH` | 未登录发起绑定 | 先登录本站 |
| 解绑返回 NOT_FOUND | 解绑的是他人身份（防枚举） | 只能操作本人身份 |

## 6. 纯 OAuth 账号

* 密码登录被拒（与其他失败同文案）→ 预期行为（不泄露账号存在性）；
* 设置页没有「修改密码」而是「设置本站密码」→ 纯 OAuth 账号的正确入口；
* 设置密码后其它设备会话被撤销 → 预期安全行为（`revoked_sessions`）。

## 7. E2E / 测试排查

* `tests/phase8a` 报 `NOT_RUN: JM_TEST_DATABASE_URL_POSTGRES` → 未提供 PostgreSQL，
  该模块按纪律记 NOT_RUN（绝不冒充 PASS）；提供后重跑：
  ```powershell
  $env:JM_TEST_DATABASE_URL_POSTGRES = "postgresql+psycopg2://user:pass@localhost:5432/jm_test"
  py -3.13 tests/phase8a/run_all.py
  ```
* 浏览器 E2E 起不来 → 端口 8123/8125/5173 被占用；`playwright.config.ts`
  用 `reuseExistingServer: true`，先杀残留进程；
* 模拟授权服务器异常 → `POST http://127.0.0.1:8125/control/reset` 复位。

## 8. 日志与隐私

* 安全日志只记 `reason_code / duration_ms / client_ip_hash` 等元数据；
* 如果发现日志出现 AppSecret / access_token / code / state 明文 → **按安全缺陷处理**，
  用 `test_oauth_secret_not_logged` 回归；
* 不要在工单里粘贴完整回调 URL（含 code/state），只粘贴 reason_code。
