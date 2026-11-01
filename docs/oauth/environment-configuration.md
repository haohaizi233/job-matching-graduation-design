# 环境配置与凭据注入（Phase8-A / M8）

## 1. 环境变量总表

所有配置集中在 `OAuthSettings.from_env()` 一处读取（`src/job_matching/service/oauth/config.py`），
业务方法内**禁止**改写 `os.environ`。`.env.example` 已包含下列模板（本项目**不自动加载
`.env`**，需按第 4 节显式注入环境）。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `JM_OAUTH_ENABLED` | `false` | 全局开关。`false` 时任何平台不发起真实授权 |
| `JM_OAUTH_PUBLIC_BASE_URL` | 空 | 后端对外公开 HTTPS 地址（回调域名基址） |
| `JM_OAUTH_FRONTEND_ORIGIN` | 空 | 前端可信 Origin，逗号分隔可多个，首个为主 |
| `JM_OAUTH_STATE_TTL_SECONDS` | `300` | 授权事务 TTL（钳制 60–900） |
| `JM_OAUTH_TICKET_TTL_SECONDS` | `60` | 一次性登录票据 TTL（钳制 30–300） |
| `JM_OAUTH_<P>_ENABLED` | `false` | 单平台开关（P ∈ WECHAT / QQ / WEIBO） |
| `JM_OAUTH_<P>_CLIENT_ID` | 空 | AppID / App Key |
| `JM_OAUTH_<P>_CLIENT_SECRET` | 空 | AppSecret / App Key Secret（**只在服务端**） |
| `JM_OAUTH_<P>_REDIRECT_URI` | 空 | 回调地址；留空则由 `PUBLIC_BASE_URL` 派生固定路径 |
| `JM_OAUTH_<P>_VERIFIED` | `false` | **真实扫码登录成功后人工置 `true`**，才显示 `available` |
| `JM_API_ENV` | `dev` | `prod/production/staging` 触发生产安全门禁 |

派生规则：`REDIRECT_URI` 留空时为
`{JM_OAUTH_PUBLIC_BASE_URL}/api/v1/auth/oauth/{provider}/callback`，
路径由受控代码决定，**不接受**请求侧传入回调地址。

## 2. 三态语义（绝不把「有配置」当「已验收」）

| 状态 | 触发条件 | 含义 |
|---|---|---|
| `disabled` | 未启用 或 缺凭据 | 前端按钮「暂未开放」 |
| `configured_pending_verification` | 启用 + 凭据齐全 | **仅表示配置完整**，未真实联调 |
| `available` | 且 `JM_OAUTH_<P>_VERIFIED=true` | 真实扫码登录成功后人工登记 |

`/api/v1/auth/oauth/providers` 与此完全一致；API 永不返回 AppSecret。

## 3. 配置独立性要求（有测试覆盖）

* 全部未配置 → 系统正常启动，三平台 `disabled`；
* 仅 QQ 配置 → 微信/微博不受影响；
* 仅微信配置 → QQ/微博不受影响；
* 某平台配置错误（缺 Secret / 回调不在白名单）→ 仅该平台不可用；
* 生产缺少回调白名单 → `check_safety()` 拒绝启用；
* 生产 HTTP（非 HTTPS）→ `check_safety()` 拒绝启用。

## 4. PowerShell 注入（项目不自动加载 .env）

```powershell
# 方式 A：会话内逐项注入（本地开发）
$env:JM_OAUTH_ENABLED = "true"
$env:JM_OAUTH_PUBLIC_BASE_URL = "https://api.example.com"
$env:JM_OAUTH_FRONTEND_ORIGIN = "https://app.example.com"
$env:JM_OAUTH_QQ_ENABLED = "true"
$env:JM_OAUTH_QQ_CLIENT_ID = "<AppID>"
$env:JM_OAUTH_QQ_CLIENT_SECRET = "<AppSecret>"
py -3.13 -m uvicorn job_matching.service.business_api:app --port 8000

# 方式 B：从 .env 读入当前会话（.env.example 复制为 .env 后手动编辑）
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim()
  }
}
```

> **注意**：`.env` 不会自动生效，也不得提交到 Git（已在 `.gitignore`）。
> 生产部署应使用进程管理器/容器的环境注入，不落盘 Secret。

## 5. Secret 纪律

* 只从服务端配置读取；不进 Vue / `VITE_*` / API 响应 / 日志 / Git / CI Artifact / 测试快照；
* 测试一律使用合成 Secret（如 `FAKE_SECRET_FOR_TESTS`），禁止真实 AppSecret；
* `JM_OAUTH_ENABLED=false` 时不会发出任何真实授权请求；
* 安全日志只记 `reason_code`，禁止记 code / state 明文 / ticket / Token。

## 6. oauth doctor

```powershell
py -3.13 scripts/phase8a/oauth_doctor.py          # 文本报告
py -3.13 scripts/phase8a/oauth_doctor.py --json   # 机器可读
```

输出示例（无凭据时）：

```text
微信: DISABLED / CREDENTIALS_MISSING（缺 AppID/AppSecret/回调地址）
QQ: DISABLED / CREDENTIALS_MISSING（缺 AppID/AppSecret/回调地址）
微博: DISABLED / CREDENTIALS_MISSING（缺 AppID/AppSecret/回调地址）
Database Migration: PASS (迁移链 head=...)
OAuth Provider Registry: PASS (白名单=wechat/qq/weibo；未登记 Provider 被拒绝)
Redirect Policy: PASS (return_path 白名单生效；外跳/混淆路径全部拒绝)
Ticket Store: PASS (票据摘要落库；一次性消费；重放拒绝)
Frontend Routes: PASS (OAuth 完成页/路由/API 文件齐备且无 Secret)
Deployment Safety: PASS
overall: PASS
```

退出码 `0` = 基础检查全 PASS；`1` = 有 FAIL。脚本**绝不打印 Secret**。

四态区分（不得混为一谈）：

```text
代码就绪            -> oauth doctor 各项 PASS
凭据完整            -> CONFIGURED_PENDING_VERIFICATION
平台已审核          -> 平台开发者后台人工确认
真实授权联调通过     -> VERIFIED（真实扫码登录成功后置 JM_OAUTH_<P>_VERIFIED=true）
```
