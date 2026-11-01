# QQ 互联接入指南（qq-setup.md）

> 适用场景：**网站应用 QQ 授权登录**（QQ 互联 `connect.qq.com`）。

## 1. 申请前准备

* 已 ICP 备案的网站域名；
* 可访问的站点（审核需能打开）；
* QQ 互联开发者账号（个人/企业均可，需实名）。

## 2. 申请步骤

1. 登录 [QQ 互联](https://connect.qq.com/) → 应用管理 → 创建应用 → **网站**；
2. 填写网站信息：名称、域名、**回调地址**；
3. 回调地址填完整 URL：
   `https://api.example.com/api/v1/auth/oauth/qq/callback`
   （必须与本站派生 URL 逐字符一致，含协议与路径）；
4. 审核通过后获得 **App ID / App Key**；
5. 确认「获取用户信息」等权限按需最小化（登录只需 `get_user_info`）。

## 3. 本站配置

```dotenv
JM_OAUTH_ENABLED=true
JM_OAUTH_PUBLIC_BASE_URL=https://api.example.com
JM_OAUTH_FRONTEND_ORIGIN=https://app.example.com
JM_OAUTH_QQ_ENABLED=true
JM_OAUTH_QQ_CLIENT_ID=102......            # App ID
JM_OAUTH_QQ_CLIENT_SECRET=............     # App Key（只在服务端）
JM_OAUTH_QQ_REDIRECT_URI=                  # 留空 -> 自动派生
```

## 4. 协议要点（适配器 `providers/qq.py` 已处理）

* 授权：`https://graph.qq.com/oauth2.0/authorize`；
* Token：`https://graph.qq.com/oauth2.0/token`（表单编码；响应可能为
  `k=v&...` 表单格式或 JSON，两种都解析）；
* OpenID：`https://graph.qq.com/oauth2.0/me`（优先 `fmt=json`；
  仅当返回 JSONP 时走**安全括号解析**——不用 `eval()`、不执行动态脚本，
  且校验返回的 `client_id`（`oauth_consumer_key`）与本站 AppID 一致，
  防跨应用串号）；
* 资料：`https://graph.qq.com/user/get_user_info`（可选，失败降级）；
* 身份唯一键：`(qq, AppID, openid)`——**昵称永远不能当身份**。

## 5. 验收清单

* [ ] `oauth doctor` 显示 QQ `CONFIGURED_PENDING_VERIFICATION`；
* [ ] 登录页点「QQ 登录」出现官方授权页；
* [ ] 确认后进入工作台；`oauth_identities` 存在 `(qq, AppID, openid)`；
* [ ] 同一 QQ 重复登录不重复建号；
* [ ] 换一个 QQ 号登录产生独立账号（不与昵称相同的账号合并）；
* [ ] 日志无 App Key / access_token；
* [ ] 真实登录成功后置 `JM_OAUTH_QQ_VERIFIED=true`。

## 6. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 100010 redirect_uri_mismatch | 回调地址与平台配置不一致（注意 https 与路径） |
| 40001 invalid client secret | App Key 错误 |
| 400016 / 100017 | code 已消费或过期（重放被本站拒绝） |
| openid 接口返回被解析拒绝 | JSONP 载荷异常或 client_id 不匹配，安全阻断 |
| 昵称显示为空 | 资料接口失败降级，登录不受影响 |
