# Phase8-A / M2：微信 / QQ / 微博协议适配器验收报告

- 生成时间：2026-11-01
- 交付：`src/job_matching/service/oauth/providers/{wechat,qq,weibo}.py`
- 相关测试：`tests/phase8a/test_provider_protocol.py`（39 例：微信 15 / QQ 17 / HTTP 客户端 5 / 微博 9 中的对应分组）
- 纪律：**不使用真实开发者凭据执行外部授权**；协议行为以官方文档 + 模拟响应双重校验，
  文档不明确处登记 `PROVIDER_VERIFICATION_PENDING`。

## 1. 微信开放平台网站扫码（`wechat.py`）

* 授权：`https://open.weixin.qq.com/connect/qrconnect?scope=snsapi_login`（PC 扫码，
  与公众号网页授权 / 小程序 `wx.login()` 严格分离，未混入任何公众号/小程序代码路径）；
* code 换 token：`sns/oauth2/access_token`；`errcode != 0` 分类映射
  （40029/40163 code 问题、-1/45009 平台繁忙 → `OAUTH_PROVIDER_UNAVAILABLE`）；
* 身份：`openid` 必须存在（缺失 → `OAUTH_INVALID_IDENTITY`）；`unionid` 可选；
* 资料：`sns/userinfo` 可选，HTTP 失败 / errcode 降级 `profile_fetched=False`；
* 身份完整性：userinfo 的 openid 与 token 侧不一致 → `InvalidIdentity` 阻断。

测试证据：`test_exchange_code_happy_path`、`test_exchange_code_without_unionid`、
`test_errcode_maps_to_token_exchange_failed`、`test_provider_busy_maps_to_unavailable`、
`test_missing_openid_rejected`、`test_get_identity_openid_mismatch_rejected`、
`test_get_identity_profile_http_failure_degrades`、`test_exchange_timeout_raises_provider_timeout`、
`test_exception_messages_do_not_leak_secret`。

## 2. QQ 互联（`qq.py`）

* 授权：`graph.qq.com/oauth2.0/authorize`；token：`oauth2.0/token`（表单编码）；
* token 响应兼容表单格式与 `fmt=json` JSON；
* OpenID：`oauth2.0/me` 优先 `fmt=json`；仅当返回 JSONP 时走**安全括号解析**
  （不用 `eval()`、不执行动态脚本，恶意载荷 `test_jsonp_malicious_payload_rejected_without_eval` 明确拒绝）；
* `oauth_consumer_key` 与本站 `client_id` 不一致 → 拒绝（防跨应用串号）；
* `get_user_info` 可选（权限 errcode / HTTP 失败均降级）；
* 昵称永不作为身份（`test_nickname_alone_never_identity`）。

## 3. 微博开放平台（`weibo.py`）

* 授权：`api.weibo.com/oauth2/authorize`；token：`oauth2/access_token`
  （POST 表单：grant_type / code / redirect_uri / client_id / client_secret）；
* 身份：token 响应内 `uid`（服务端核验）为唯一键，缺失 → 拒绝；
* 资料：`2/users/show` 可选；**已确认 UID 但资料失败时登录仍成立**
  （`test_profile_failure_keeps_verified_uid`），不产生错误关联；
* uid 前后不一致 → 阻断（`test_uid_mismatch_rejected`）；
* `error_code`（21322/21327/21325/21332…）映射到明确 `OAUTH_*` 错误。

## 4. HTTP Client 纪律（`http_client.py`）

| 要求 | 实现 | 测试 |
|---|---|---|
| 连接/读取/总超时 | httpx Timeout 三段显式 | `test_timeout_mapped` |
| 有界响应体 | 流式读取 + 上限截断 | `test_response_size_bounded` |
| 零无限重试 | 无重试逻辑（code 换 token 非幂等，不重复提交） | 代码审计 |
| 不跟随跳转 | `follow_redirects=False`（防 Provider 响应指向内网） | `test_no_redirect_followed` |
| HTTPS 固定端点 | 端点为模块常量 | 代码审计 |
| Secret 脱敏 | URL 去 query、异常信息剔除 secret | `test_redact_url_strips_query`、`test_exception_messages_do_not_leak_secret` |
| 可替换 Transport | 构造注入 httpx client/transport | 全部协议测试使用 MockTransport |

## 5. PROVIDER_VERIFICATION_PENDING 登记

| 项 | 说明 |
|---|---|
| 微信 UnionID 返回条件 | 与开放平台账号绑定机制相关，未绑定时无 unionid（登录不受影响） |
| QQ `oauth2.0/me` 的 JSONP 触发条件 | `fmt=json` 不可用时降级 JSONP，具体触发条件以联调为准 |
| 微博用户资料接口权限随资质变化 | `2/users/show` 可能 403，按契约降级不阻断 |
| 三家 PKCE 支持 | 均未确认支持标准 PKCE 参数，**默认不启用**（`supports_pkce=False`），
  联调时以平台文档为准，确认后仅改适配器配置即可开启 S256 |

## 6. 验收结论

三家适配器均为**完整可执行实现**（无空函数），协议测试全绿：
`test_provider_protocol` 39/39 PASS。

**M2 = PASS**（Provider Adapter Ready；Real Provider Verified = NOT_RUN）。
