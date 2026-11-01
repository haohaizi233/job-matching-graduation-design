# 微信开放平台接入指南（wechat-setup.md）

> 适用场景：**PC 网站微信扫码登录**（开放平台「网站应用」）。
> 公众号网页授权、小程序 `wx.login()` **不在本文范围**，未来接入时另立 Provider 配置扩展。

## 1. 申请前准备

* 已备案的网站域名（ICP 备案号与主体一致）；
* 可访问的 HTTPS 站点（审核期间需能打开）；
* 企业/个人开发者资质（开放平台需实名认证，个人主体部分能力受限）。

## 2. 申请步骤

1. 登录 [微信开放平台](https://open.weixin.qq.com/) → 管理中心 → 创建应用 → **网站应用**；
2. 填写网站信息：名称、简介、官网地址、**授权回调域**；
3. 「授权回调域」只填**域名**，例如 `api.example.com`（不带协议、不带路径）；
   本站完整回调 URL 固定为：
   `https://api.example.com/api/v1/auth/oauth/wechat/callback`
4. 等待审核（通常数个工作日），通过后获得 **AppID / AppSecret**；
5. 如需 UnionID，确认开放平台账号已绑定 UnionID 机制（不绑定也不影响登录）。

## 3. 本站配置

```dotenv
JM_OAUTH_ENABLED=true
JM_OAUTH_PUBLIC_BASE_URL=https://api.example.com
JM_OAUTH_FRONTEND_ORIGIN=https://app.example.com
JM_OAUTH_WECHAT_ENABLED=true
JM_OAUTH_WECHAT_CLIENT_ID=wx..............        # AppID
JM_OAUTH_WECHAT_CLIENT_SECRET=................    # AppSecret（只在服务端）
JM_OAUTH_WECHAT_REDIRECT_URI=                    # 留空 -> 自动派生
```

## 4. 协议要点（适配器 `providers/wechat.py` 已处理）

* 授权入口：`https://open.weixin.qq.com/connect/qrconnect`，`scope=snsapi_login`；
* code 换 token：`https://api.weixin.qq.com/sns/oauth2/access_token`；
* 身份：`openid` 为唯一键；`unionid` 可选；
* 资料：`https://api.weixin.qq.com/sns/userinfo`（昵称头像，可失败降级）；
* 错误：`errcode != 0` 时按 errcode 分类（40029/40163 → code 问题，
  -1/45009 → 平台繁忙/限流，其余 → `OAUTH_TOKEN_EXCHANGE_FAILED`）。

## 5. 验收清单

* [ ] `oauth doctor` 显示微信 `CONFIGURED_PENDING_VERIFICATION`；
* [ ] 登录页点「微信登录」出现官方二维码；
* [ ] 扫码确认后进入工作台，`/auth/me` 返回本站用户；
* [ ] `oauth_identities` 存在 `(wechat, AppID, openid)`；
* [ ] 再次扫码登录**不**新建账号；
* [ ] 日志无 AppSecret / access_token；
* [ ] 真实登录成功后执行 `JM_OAUTH_WECHAT_VERIFIED=true` 并复跑验收。

## 6. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 回调报 redirect_uri 错误 | 平台「授权回调域」与 `JM_OAUTH_PUBLIC_BASE_URL` 域名不一致 |
| 授权页提示 scope 错误 | 使用了公众号 scope；网站应用必须 `snsapi_login` |
| code 换 token 40029 | code 已过期/已消费（重放被拒，属防护） |
| 无 unionid | 未绑定 UnionID 机制或权限不足，不影响登录 |
| 应用审核中点登录 | 平台直接报错 → 前端展示「第三方登录未完成，请重试」 |
