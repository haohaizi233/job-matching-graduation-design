# Phase5-3 浏览器 E2E 验收结果

- 生成时间：2026-10-31T13:45:19+08:00
- Run ID：`m3-e2e-20261031-110657`
- 原始结果：`frontend/e2e/.artifacts/e2e-raw.json`
- 环境：真实 Chromium + 真实前后端（隔离测试库 tests/e2e/.runtime/），夹具全部为合成数据

**汇总：17 个用例 / PASS 17 / FAIL 0 / SKIP 0 / 耗时 134.0s**

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
| `e01-auth.spec.ts::UI 注册 → 登录 → 退出登录 → 再登录（真实会话撤销）` | PASSED | 8.7s |
| `e01-auth.spec.ts::E01 登录凭证错误给出真实错误提示且不进入工作台` | PASSED | 2.8s |
| `e02-resume-upload.spec.ts::上传合成简历 → 简历列表显示解析结果 → 我的画像呈现抽取字段` | PASSED | 6.4s |
| `e03-resume-parse-failures.spec.ts::空文件 / 损坏文档报错，不可解析正文标记部分解析，并可重新解析` | PASSED | 8.3s |
| `e04-profile-edit-confirm.spec.ts::修改画像字段 → 保存新版本 → 确认 → 版本历史可回看` | PASSED | 9.3s |
| `e05-jobs.spec.ts::岗位列表真实加载 → 关键词筛选 → 详情页 → 返回列表` | PASSED | 7.0s |
| `e06-matching.spec.ts::发起匹配得到真实推荐结果并展示解释与免责声明` | PASSED | 11.1s |
| `e07-history-export.spec.ts::推荐历史展示真实运行记录并可导出 CSV` | PASSED | 10.5s |
| `e08-feedback.spec.ts::提交反馈 → 提示成功 → 刷新后状态从服务端回显` | PASSED | 12.2s |
| `e09-auth-guard.spec.ts::未登录访问受保护页被引导到登录页` | PASSED | 1.9s |
| `e09-auth-guard.spec.ts::未带 Token 的业务 API 由服务端拒绝（401）` | PASSED | 0.8s |
| `e09-auth-guard.spec.ts::失效 Token 触发全局会话复位并回到登录页` | PASSED | 6.0s |
| `e10-isolation.spec.ts::用户 B 看不到用户 A 的简历、推荐历史与反馈` | PASSED | 13.9s |
| `e11-error-states.spec.ts::空数据展示合理空态与引导` | PASSED | 5.1s |
| `e11-error-states.spec.ts::网络中断登记真实错误码并降级为空态（无假数据）` | PASSED | 11.8s |
| `e11-error-states.spec.ts::服务端 500 展示真实错误码且不展示假数据` | PASSED | 7.6s |
| `e12-refresh-responsive.spec.ts::刷新后会话保持，缩小视口核心功能仍可用` | PASSED | 10.7s |
