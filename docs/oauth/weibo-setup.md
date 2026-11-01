# 微博开放平台接入指南（weibo-setup.md）

> 适用场景：**网站 OAuth 2.0 授权登录**（微博开放平台 `open.weibo.com`）。

## 1. 申请前准备

* 已 ICP 备案的网站域名；
* 微博开放平台开发者账号（实名认证）；
* HTTPS 站点（生产）。

## 2. 申请步骤

1. 登录 [微博开放平台](https://open.weibo.com/) → 微连接 → 创建应用 → **网站**；
2. 填写网站信息并提交审核；
3. 审核通过后在「高级信息 → OAuth2.0 授权设置」填写**授权回调页**：
   `https://api.example.com/api/v1/auth/oauth/weibo/callback`
   （与本站派生 URL 逐字符一致）；
4. 获得 **App Key / App Secret**；
5. 权限按需最小化（登录只需基础接口；用户资料接口 `2/users/show` 可选）。

## 3. 本站配置

```dotenv
JM_OAUTH_ENABLED=true
JM_OAUTH_PUBLIC_BASE_URL=https://api.example.com
JM_OAUTH_FRONTEND_ORIGIN=https://app.example.com
JM_OAUTH_WEIBO_ENABLED=true
JM_OAUTH_WEIBO_CLIENT_ID=............       # App Key
JM_OAUTH_WEIBO_CLIENT_SECRET=..........     # App Secret（只在服务端）
JM_OAUTH_WEIBO_REDIRECT_URI=                # 留空 -> 自动派生
```

## 4. 协议要点（适配器 `providers/weibo.py` 已处理）

* 授权：`https://api.weibo.com/oauth2/authorize`；
* Token：`https://api.weibo.com/oauth2/access_token`（POST 表单：
  `grant_type=authorization_code` + `code` + `redirect_uri` + `client_id` + `client_secret`）；
* 身份唯一键：token 响应中的 **`uid`**（服务端核验）；
* 资料：`2/users/show`（可选；失败时**保留已核验 uid** 完成登录，
  昵称/头像置空，绝不因资料缺失产生错误关联）；
* 错误：`error_code`（21322 redirect_uri 不匹配、21327/21325 code/token 无效、
  21332 secret 错误）分别映射到明确的 `OAUTH_*` 错误，不伪装成本站错误。

## 5. 验收清单

* [ ] `oauth doctor` 显示微博 `CONFIGURED_PENDING_VERIFICATION`；
* [ ] 登录页点「微博登录」出现官方授权页；
* [ ] 确认后进入工作台；`oauth_identities` 存在 `(weibo, App Key, uid)`；
* [ ] 重复登录不重复建号；
* [ ] 用户资料接口被拒时（权限不足）登录仍成功、昵称为空、**无错误关联**；
* [ ] 日志无 App Secret / access_token；
* [ ] 真实登录成功后置 `JM_OAUTH_WEIBO_VERIFIED=true`。

## 6. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 21322 redirect_uri_mismatch | 回调 URL 与平台配置不一致（https/路径逐字符核对） |
| 21327 / 21325 | code 已消费或过期（重放被拒） |
| 21332 invalid access_token | App Secret 错误 |
| 用户资料 403 / 400 | 应用权限或资质不足 → 登录仍成功，仅展示降级 |
| 平台接口随资质变化 | 已登记 `PROVIDER_VERIFICATION_PENDING`，联调时以平台文档为准复核 |
