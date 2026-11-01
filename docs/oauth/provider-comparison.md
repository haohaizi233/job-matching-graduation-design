# 微信 / QQ / 微博 协议差异对照（Phase8-A / M2）

三家平台都走 OAuth 2.0 **Authorization Code** 流程，但细节差异很大。
差异全部封装在 `src/job_matching/service/oauth/providers/`，业务层只见 `OAuthIdentity`。

## 1. 一览表

| 维度 | 微信开放平台（网站扫码） | QQ 互联 | 微博开放平台 |
|---|---|---|---|
| 应用类型 | 网站应用（PC 扫码登录） | 网站应用 | 网站应用 |
| 授权入口 | `https://open.weixin.qq.com/connect/qrconnect` | `https://graph.qq.com/oauth2.0/authorize` | `https://api.weibo.com/oauth2/authorize` |
| Token 端点 | `https://api.weixin.qq.com/sns/oauth2/access_token` | `https://graph.qq.com/oauth2.0/token` | `https://api.weibo.com/oauth2/access_token` |
| 身份端点 | token 响应内 `openid` | `https://graph.qq.com/oauth2.0/me`（JSONP/`fmt=json`） | token 响应内 `uid` |
| 资料端点 | `https://api.weixin.qq.com/sns/userinfo` | `https://graph.qq.com/user/get_user_info` | `https://api.weibo.com/2/users/show.json` |
| Scope | `snsapi_login` | `get_user_info`（最小集） | `email`/`read` 按需，最小化申请 |
| 稳定身份 subject | `openid` | `openid`（应用级命名空间） | `uid` |
| 跨应用统一 ID | `unionid`（需绑定开放平台账号，**可空**） | 无 | 无 |
| 响应格式 | JSON | JSONP（`callback(...)`）或 `fmt=json` | JSON |
| 错误表达 | `errcode`/`errmsg` | 端点各异（`error`/`error_description`、`ret`） | `error`/`error_code`/`error_description` |
| 用户拒绝授权 | 回调 `error=access_denied` | 回调 `error=access_denied` | 回调 `error=access_denied` |
| PKCE 支持 | **未确认**（PROVIDER_VERIFICATION_PENDING） | **未确认** | **未确认** |
| 适配器 | `providers/wechat.py` | `providers/qq.py` | `providers/weibo.py` |

> 「未确认」表示官方公开文档在本轮可核实范围内没有明确说明网站授权流程接受
> 标准 PKCE 参数。**不虚构**：三家均按 `supports_pkce = False` 处理，
> 安全性由 state + client_secret + 回调白名单 + 一次性消费保证。
> 真实联调时若确认支持，只需把该 Provider 的 `supports_pkce` 置 True，
> PKCE 代码路径（`security.pkce_verifier/pkce_challenge_s256`）与测试已就绪。

## 2. 微信（`wechat.py`）

**唯一合法形态：开放平台「网站应用」扫码授权（`snsapi_login`）。**

```text
qrconnect 二维码授权 → code → sns/oauth2/access_token → openid(+unionid)
→ sns/userinfo（资料可选）→ OAuthIdentity
```

* 不混入公众号网页授权（`snsapi_userinfo` / `cgi-bin` 系列）与小程序 `wx.login()`；
  后续如需支持，另建独立 Provider 类型或配置扩展，不在本适配器内分支。
* `subject = openid`（服务端换 token 时核验）。
* `unionid` 仅在响应真实携带时采用；缺失 `unionid` **不影响登录**。
  只有当应用与开放平台账号完成绑定、且权限到位时才可能返回 `unionid`
  （登记 `PROVIDER_VERIFICATION_PENDING`，真实联调时核对）。
* `errcode` 分类映射：code 无效/已消费、access_token 失败、权限不足、
  频率限制、系统繁忙 -> `OAUTH_TOKEN_EXCHANGE_FAILED` / `OAUTH_PROVIDER_UNAVAILABLE`。
* 资料接口失败（`sns/userinfo` 异常）时：**身份仍有效**，
  `display_name/avatar_url` 置空、`profile_fetched=False`，不因此拒绝登录。

## 3. QQ（`qq.py`）

```text
oauth2.0/authorize → code → oauth2.0/token → access_token
→ oauth2.0/me → openid → user/get_user_info（资料可选）→ OAuthIdentity
```

QQ 特有的坑（适配器内消化）：

* **不同端点响应格式不同**：token 端点是表单编码 `k=v&k=v`（也支持 JSON），
  `oauth2.0/me` 默认返回 **JSONP**（`callback( {...} );`），`get_user_info` 返回 JSON。
* `fmt=json` 可用时**优先使用**，避免 JSONP 解析。
* JSONP 解析采用**安全的括号定位 + JSON 解析**（`json.loads`），
  **绝不 `eval()`、绝不动态执行脚本**；解析失败按 `ProviderProtocolError` 处理。
* `oauth_consumer_key` 必须与 `client_id` 一致校验，防止串应用。
* `subject = openid`，且 openid 是**应用级命名空间**：不同 AppID 的 openid 不同语义，
  因此 `client_id` 参与唯一键 `(provider, client_id, subject)`。
* 仅凭 `get_user_info` 的昵称**不能**确认唯一身份（昵称可变、可重复）。

## 4. 微博（`weibo.py`）

```text
oauth2/authorize → code → oauth2/access_token → access_token + uid
→ users/show.json（资料可选）→ OAuthIdentity
```

* `subject = uid`（token 响应内已核验返回）。
* 平台错误字段：`error` / `error_code` / `error_description`，逐类映射。
* 授权取消（用户拒绝）由回调 `error=access_denied` 表达。
* 平台部分用户信息接口与权限随应用资质变化：**已确认 UID 但资料读取失败时，
  仍然完成账号关联**（`identity_without_profile_allowed = True`），
  昵称/头像缺失绝不产生错误关联；是否允许「仅凭已核验 UID 登录」由
  Provider 的 `identity_without_profile_allowed` 显式契约控制。
* 令牌过期 / 权限不足分别映射为明确错误，不伪装成密码错误。

## 5. 统一身份对象

```python
@dataclass(frozen=True)
class OAuthIdentity:
    provider: str          # wechat | qq | weibo
    client_id: str         # 参与身份命名空间（不同 AppID 不碰撞）
    subject: str           # 平台服务端核验的稳定标识（openid / openid / uid）
    union_id: str | None = None
    display_name: str | None = None     # 仅展示
    avatar_url: str | None = None       # 仅展示
    email: str | None = None
    email_verified: bool = False
    profile_fetched: bool = False       # 资料是否成功读取
```

识别纪律（写死在代码与测试里）：

* 唯一键 = `(provider, client_id, subject)`；
* **不能**用昵称、头像识别用户；
* 未核验邮箱不能作为已验证邮箱，也不能用于自动绑定既有账号；
* 不假设 QQ / 微博 / 微信之间用户 ID 具有相同语义；
* `unionid` 只在平台真实可用时使用，缺失不影响账号关联。

## 6. 平台文档校验记录

实现前已核对官方入口（`open.weixin.qq.com` / `connect.qq.com` / `open.weibo.com`）。
以下条目官方文档不明确或存在版本差异，登记为
**`PROVIDER_VERIFICATION_PENDING`**，真实联调时逐项核对（不虚构字段）：

| 项 | 平台 | 状态 |
|---|---|---|
| 网站扫码流程是否接受 PKCE 参数 | 微信 | PROVIDER_VERIFICATION_PENDING |
| `unionid` 返回的前置绑定条件 | 微信 | PROVIDER_VERIFICATION_PENDING |
| 网站授权流程 PKCE 支持 | QQ | PROVIDER_VERIFICATION_PENDING |
| 网站授权流程 PKCE 支持 | 微博 | PROVIDER_VERIFICATION_PENDING |
| 资料接口（`users/show` 等）权限随资质变化 | 微博 | PROVIDER_VERIFICATION_PENDING |
| 回调域名是否允许 localhost / 端口号 | 三家 | PROVIDER_VERIFICATION_PENDING（以平台控制台实际校验为准） |
