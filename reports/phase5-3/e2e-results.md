# Phase5-3 浏览器 E2E 验收结果

- 生成时间：2026-11-01T15:52:44+08:00
- Run ID：`p8a-full-final2`
- 原始结果：`frontend/e2e/.artifacts/e2e-raw.json`
- 环境：真实 Chromium + 真实前后端（隔离测试库 tests/e2e/.runtime/），夹具全部为合成数据

**汇总：35 个用例 / PASS 35 / FAIL 0 / SKIP 0 / 耗时 323.1s**

## 场景覆盖（任务书 E01–E12）

| 编号 | 场景 | 状态 | 用例 | 证据（用例） |
|---|---|---|---|---|
| E01 | 注册、登录、退出 | PASS | 2 | `e01-auth.spec.ts::UI 注册 → 登录 → 退出登录 → 再登录（真实会话撤销）`<br>`e01-auth.spec.ts::E01 登录凭证错误给出真实错误提示且不进入工作台` |
| E02 | 上传简历与解析 | PASS | 1 | `e02-resume-upload.spec.ts::上传合成简历 → 简历列表显示解析结果 → 我的画像呈现抽取字段` |
| E03 | 简历解析失败及重试 | PASS | 1 | `e03-resume-parse-failures.spec.ts::空文件 / 损坏文档报错，不可解析正文标记部分解析，并可重新解析` |
| E04 | 画像修改、确认、版本历史 | PASS | 1 | `e04-profile-edit-confirm.spec.ts::修改画像字段 → 保存新版本 → 确认 → 版本历史可回看` |
| E05 | 岗位查询、筛选与详情 | PASS | 1 | `e05-jobs.spec.ts::岗位列表真实加载 → 关键词筛选 → 详情页 → 返回列表` |
| E06 | 发起推荐与解释展示 | PASS | 1 | `e06-matching.spec.ts::发起匹配得到真实推荐结果并展示解释与免责声明` |
| E07 | 推荐历史与 CSV 导出 | PASS | 1 | `e07-history-export.spec.ts::推荐历史展示真实运行记录并可导出 CSV` |
| E08 | 反馈提交与状态回显 | PASS | 1 | `e08-feedback.spec.ts::提交反馈 → 提示成功 → 刷新后状态从服务端回显` |
| E09 | 未认证及 Token 失效 | PASS | 3 | `e09-auth-guard.spec.ts::未登录访问受保护页被引导到登录页`<br>`e09-auth-guard.spec.ts::未带 Token 的业务 API 由服务端拒绝（401）`<br>`e09-auth-guard.spec.ts::失效 Token 触发全局会话复位并回到登录页` |
| E10 | 多用户数据隔离 | PASS | 1 | `e10-isolation.spec.ts::用户 B 看不到用户 A 的简历、推荐历史与反馈` |
| E11 | 空数据、网络错误与 API 失败 | PASS | 3 | `e11-error-states.spec.ts::空数据展示合理空态与引导`<br>`e11-error-states.spec.ts::网络中断登记真实错误码并降级为空态（无假数据）`<br>`e11-error-states.spec.ts::服务端 500 展示真实错误码且不展示假数据` |
| E12 | 页面刷新与基础响应式检查 | PASS | 1 | `e12-refresh-responsive.spec.ts::刷新后会话保持，缩小视口核心功能仍可用` |

## 失败与错误明细（无）

## 用例耗时

| 用例 | 状态 | 耗时 |
|---|---|---|
| `e01-auth.spec.ts::UI 注册 → 登录 → 退出登录 → 再登录（真实会话撤销）` | PASSED | 8.5s |
| `e01-auth.spec.ts::E01 登录凭证错误给出真实错误提示且不进入工作台` | PASSED | 2.6s |
| `e02-resume-upload.spec.ts::上传合成简历 → 简历列表显示解析结果 → 我的画像呈现抽取字段` | PASSED | 6.8s |
| `e03-resume-parse-failures.spec.ts::空文件 / 损坏文档报错，不可解析正文标记部分解析，并可重新解析` | PASSED | 6.4s |
| `e04-profile-edit-confirm.spec.ts::修改画像字段 → 保存新版本 → 确认 → 版本历史可回看` | PASSED | 6.6s |
| `e05-jobs.spec.ts::岗位列表真实加载 → 关键词筛选 → 详情页 → 返回列表` | PASSED | 7.0s |
| `e06-matching.spec.ts::发起匹配得到真实推荐结果并展示解释与免责声明` | PASSED | 8.9s |
| `e07-history-export.spec.ts::推荐历史展示真实运行记录并可导出 CSV` | PASSED | 9.2s |
| `e08-feedback.spec.ts::提交反馈 → 提示成功 → 刷新后状态从服务端回显` | PASSED | 11.3s |
| `e09-auth-guard.spec.ts::未登录访问受保护页被引导到登录页` | PASSED | 1.7s |
| `e09-auth-guard.spec.ts::未带 Token 的业务 API 由服务端拒绝（401）` | PASSED | 0.4s |
| `e09-auth-guard.spec.ts::失效 Token 触发全局会话复位并回到登录页` | PASSED | 6.7s |
| `e10-isolation.spec.ts::用户 B 看不到用户 A 的简历、推荐历史与反馈` | PASSED | 12.5s |
| `e11-error-states.spec.ts::空数据展示合理空态与引导` | PASSED | 4.3s |
| `e11-error-states.spec.ts::网络中断登记真实错误码并降级为空态（无假数据）` | PASSED | 14.0s |
| `e11-error-states.spec.ts::服务端 500 展示真实错误码且不展示假数据` | PASSED | 8.4s |
| `e12-refresh-responsive.spec.ts::刷新后会话保持，缩小视口核心功能仍可用` | PASSED | 8.8s |
| `e13-oauth-login.spec.ts::E13-1 微信扫码授权登录 → 进入工作台且登录态真实生效` | PASSED | 6.2s |
| `e13-oauth-login.spec.ts::E13-2 同一第三方身份重复登录不创建重复本地账号` | PASSED | 15.4s |
| `e13-oauth-login.spec.ts::E13-3 用户拒绝授权 → 明确提示且不产生登录态` | PASSED | 5.9s |
| `e13-oauth-login.spec.ts::E13-4 OAuth 登录后退出登录 → 会话真实失效` | PASSED | 12.5s |
| `e13-oauth-login.spec.ts::E13-5 平台资料读取失败时仍以已核验身份完成登录` | PASSED | 10.1s |
| `e13-oauth-login.spec.ts::E13-6 登录成功后的 URL 与页面不传播第三方 code/state/token` | PASSED | 6.9s |
| `e14-oauth-account-binding.spec.ts::E14-1 已登录用户主动绑定 QQ → 设置页显示已绑定` | PASSED | 20.1s |
| `e14-oauth-account-binding.spec.ts::E14-2 第三方身份已被其他账号绑定 → 显式冲突且不静默转移` | PASSED | 28.4s |
| `e14-oauth-account-binding.spec.ts::E14-3 纯 OAuth 账号解绑唯一登录方式被拒绝（OAUTH_LAST_LOGIN_METHOD）` | PASSED | 16.7s |
| `e14-oauth-account-binding.spec.ts::E14-4 设置本站密码后可解绑第三方身份且密码登录可用` | PASSED | 23.5s |
| `e14-oauth-account-binding.spec.ts::E14-5 未登录发起绑定被拒绝（OAUTH_BIND_REQUIRES_AUTH）` | PASSED | 0.1s |
| `e15-oauth-security.spec.ts::E15-1 未配置凭据的平台显示暂未开放且不产生假成功` | PASSED | 4.7s |
| `e15-oauth-security.spec.ts::E15-2 伪造 state 的回调被拒绝（CSRF 防线）` | PASSED | 2.1s |
| `e15-oauth-security.spec.ts::E15-3 回调重放（state/code 二次消费）被拒绝` | PASSED | 7.8s |
| `e15-oauth-security.spec.ts::E15-4 一次性登录票据重放被拒绝` | PASSED | 19.6s |
| `e15-oauth-security.spec.ts::E15-5 return_path 开放重定向被拒绝` | PASSED | 0.2s |
| `e15-oauth-security.spec.ts::E15-6 第三方平台异常不伪装成密码错误` | PASSED | 8.2s |
| `e15-oauth-security.spec.ts::E15-7 code 换 token 失败（code 过期）给出明确错误` | PASSED | 10.5s |
