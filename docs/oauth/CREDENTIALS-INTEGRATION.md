# 真实凭据到位后的零代码接入手册（M11）

> **核心承诺**：拿到三家平台的 AppID / AppSecret 后，**只做配置、平台审核与真实联调，
> 不修改任何业务源码**。本文档给出逐平台操作与验收清单。

## 0. 总体流程（一次看完）

```text
1.  平台开发者后台申请应用（见各平台专章）        [人工]
2.  填写回调域名 = JM_OAUTH_PUBLIC_BASE_URL 派生  [人工]
3.  .env.example 复制为 .env，填写凭据            [配置]
4.  注入环境变量并启动 FastAPI / Vue              [配置]
5.  py -3.13 scripts/phase8a/oauth_doctor.py      [体检]
6.  GET /api/v1/auth/oauth/providers 看三态       [体检]
7.  真实扫码登录走通                              [联调]
8.  置 JM_OAUTH_<P>_VERIFIED=true                 [人工登记]
9.  验证库表 / 绑定 / 解绑 / 无 Token 泄露        [验收]
```

各平台申请细节见 [wechat-setup.md](wechat-setup.md) / [qq-setup.md](qq-setup.md) /
[weibo-setup.md](weibo-setup.md)；变量含义见
[environment-configuration.md](environment-configuration.md)。

## 1. 微信开放平台（PC 网站扫码）

| 项目 | 内容 |
|---|---|
| 应用类型 | **网站应用**（PC 网站扫码登录，不是公众号、不是小程序） |
| 审核前置 | 开发者资质认证 + 网站应用审核通过（域名需 ICP 备案） |
| AppID 填写位置 | `JM_OAUTH_WECHAT_CLIENT_ID` |
| AppSecret 填写位置 | `JM_OAUTH_WECHAT_CLIENT_SECRET`（只在服务端 `.env`） |
| 回调域名填写方式 | 平台侧填**域名**（如 `api.example.com`）；本站派生完整 URL `https://api.example.com/api/v1/auth/oauth/wechat/callback` |
| Scope | `snsapi_login`（网站扫码唯一 scope） |
| 最小权限 | 仅登录能力；不申请 UnionID 之外的用户资料权限 |
| 启动配置 | `JM_OAUTH_WECHAT_ENABLED=true` + 上述三项 + `JM_OAUTH_ENABLED=true` |

真实扫码过程：登录页点「微信登录」→ 跳 `open.weixin.qq.com/connect/qrconnect` →
手机微信扫码确认 → 302 回本站 callback → 自动换 token、取 openid → 票据交换 → 工作台。

登录成功检查：`GET /api/v1/auth/me` 返回本站用户；`oauth_identities` 出现
`(wechat, AppID, openid)` 一行。

常见回调域名不匹配：平台侧只填域名不含路径与协议时，检查 `JM_OAUTH_PUBLIC_BASE_URL`
是否与备案域名一致；错误统一表现为 `OAUTH_TOKEN_EXCHANGE_FAILED`（400029 invalid code
等 errcode 会记入安全日志 reason_code）。

应用尚未审核通过：授权页直接报错或回调带 `error`，本站呈现
「第三方登录未完成，请重试」；此时状态保持 `configured_pending_verification`。

UnionID 不存在（开放平台未绑定 UnionID 机制 / 权限不足）：**完全不影响登录**，
`union_id` 置空即可；账号关联只依赖 `(provider, client_id, openid)`。

## 2. QQ 互联

| 项目 | 内容 |
|---|---|
| 应用类型 | **网站应用**（QQ 互联 `connect.qq.com`） |
| 审核前置 | 开发者信息完整 + 网站应用审核（域名 ICP 备案） |
| AppID（App ID） | `JM_OAUTH_QQ_CLIENT_ID` |
| AppSecret（App Key） | `JM_OAUTH_QQ_CLIENT_SECRET` |
| 回调地址 | 平台侧可填完整回调 URL；本站为 `https://api.example.com/api/v1/auth/oauth/qq/callback` |
| Scope | `get_user_info`（登录必须）；其余按需最小化 |
| OpenID 获取 | 服务端 `https://graph.qq.com/oauth2.0/me`（`fmt=json` 优先，JSONP 安全解析兜底） |
| 用户信息 | `get_user_info` 可选；失败只降级展示，不阻断登录 |

真实登录测试：登录页点「QQ 登录」→ QQ 授权页 → 确认 → 回调 → 工作台。

失败诊断：

* `40001 invalid client secret` → `JM_OAUTH_QQ_CLIENT_SECRET` 错误；
* `100010 redirect_uri mismatch` → 平台侧回调地址与本站派生 URL 不一致；
* `400016 / 100017` → code 已消费或过期（本站已拒重放，属正常防护）；
* 换 openid 接口返回 JSONP 无法解析 → 记 `OAUTH_TOKEN_EXCHANGE_FAILED`，
  检查 `fmt=json` 是否被平台降级。

## 3. 微博开放平台

| 项目 | 内容 |
|---|---|
| 应用类型 | **网站接入**（`open.weibo.com`） |
| 审核前置 | 开发者认证 + 应用审核（网站域名备案） |
| App Key | `JM_OAUTH_WEIBO_CLIENT_ID` |
| App Secret | `JM_OAUTH_WEIBO_CLIENT_SECRET` |
| redirect_uri | 平台「高级设置 → OAuth2.0 授权设置」填 `https://api.example.com/api/v1/auth/oauth/weibo/callback`；本站派生 URL 必须逐字符一致 |
| Scope | 默认 `email` 以内；登录只需基础接口 |
| UID 获取 | code 换 token 响应内含 `uid`（服务端核验），这是唯一身份键 |
| 用户信息 | `2/users/show` 可选；失败不阻断（`identity_without_profile_allowed`） |

真实登录测试同上。失败诊断：

* `21322 redirect_uri_mismatch` → 回调 URL 与平台配置不一致；
* `21327 / 21325 token 过期` → code 已消费（重放被本站拒绝）；
* `21332 invalid access_token` → App Secret 错误；
* 用户资料接口 403（权限/资质不足）→ 登录仍成功，昵称头像为空。

## 4. 配置完成后的操作（可复制 PowerShell）

```powershell
# 1. 复制配置模板并填写（不要提交 .env）
Copy-Item .env.example .env
notepad .env                      # 填 JM_OAUTH_* 各项

# 2. 注入当前会话（项目不自动加载 .env）
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim()
  }
}

# 3. 确认 HTTPS 与回调域名（生产必须 HTTPS）
#    JM_OAUTH_PUBLIC_BASE_URL=https://<备案域名>
#    JM_OAUTH_FRONTEND_ORIGIN=https://<前端域名>

# 4. 数据库迁移（OAuth 三表 + password_hash 可空）
py -3.13 -m alembic upgrade head

# 5. 启动后端
py -3.13 -m uvicorn job_matching.service.business_api:app --host 0.0.0.0 --port 8000

# 6. 启动前端（开发模式）
cd frontend; npm run dev

# 7. 环境体检
py -3.13 scripts/phase8a/oauth_doctor.py

# 8. 检查 Provider 三态
curl http://127.0.0.1:8000/api/v1/auth/oauth/providers

# 9. 点击真实登录按钮（微信扫码 / QQ 授权 / 微博授权）

# 10. 验证数据落库
#     users 新增一行（password_hash 为空、role=student）
#     oauth_identities 新增 (provider, client_id, subject)
#     auth_sessions 新增本站会话（重复登录不重复建号）

# 11. 测试绑定 / 重复登录 / 解绑（设置页「第三方账号绑定」）

# 12. 验证不存在 Token 泄露：
#     浏览器地址栏无 token；响应体无 provider access_token；
#     日志无 AppSecret / code / state 明文
```

## 5. 真实联调状态登记（诚实口径）

真实凭据未到位时，一律保持：

```text
implementation            = COMPLETE
mock_integration          = PASS
real_provider_integration = NOT_RUN
provider_approval         = PENDING
```

**有凭据 ≠ 平台审核通过 ≠ 真实联调通过**。只有真实扫码登录成功后，才把该平台的
`real_provider_integration` 改为 `PASS` 并置 `JM_OAUTH_<P>_VERIFIED=true`。
严禁把 Mock 测试结果登记为真实授权成功。
