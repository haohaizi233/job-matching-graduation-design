# Phase5-3 · 03 前端业务联调验收

- 生成时间：2026-10-31（Phase5-3 / M2）
- 分支：`feat/phase5-3-integration`
- 验证命令：`cd frontend && npm run typecheck`（0 错误）、`npm run build`（生产构建）、
  后端 `py -3.13 tests/phase5_2/run_all.py`（T1–T8 回归，见 09-regression-results.md）。

## 1. 核心页面逐页审计（任务书 4.1）

| 页面 | 数据来源 | 关键提交 | 401/错误处理 | 加载/空态/重试 | 结论 |
|---|---|---|---|---|---|
| DashboardView | 真实 API 聚合（简历/画像/岗位/推荐/反馈） | `1573f3a` | 401 显式提示；单项失败登记 `dataNotes` 不伪造 | 加载中/空态/失败重试 | ✅ |
| ResumeView | `/resumes` 上传/列表/重试 | `b60d70c`、`cb1f481` | 解析失败横幅 + 批量重解析 | 解析中/失败/重试 | ✅ |
| ProfileView | `/students/me/profile*` | `0361fd3`、`b60d70c` | 无画像空态；确认/版本历史真实 | 空态/版本预览 | ✅ |
| JobsView | `/jobs`（替换本地 mock） | `39b7596` | 筛选/分页真实参数 | 空态/加载 | ✅ |
| JobDetailView | `/jobs/{id}` | `39b7596` | 404 空态 | — | ✅ |
| MatchingView | `/recommendations` 创建/详情/重新推荐 | `d46124c` | 幂等/失败提示真实 | 空态/解释展示 | ✅ |
| HistoryView | `/recommendations` 历史 + CSV 前端真实导出 | `7136a4b` | 空态 | — | ✅ |
| FeedbackView | `/recommendations/feedback` 提交/回显 | `c8f2946` | 提交成功以服务端回读为准 | 空态 | ✅ |
| SettingsView | `/students/me/settings` + `/auth/sessions` | `0c7ed89` | 保存失败/401 提示；加载失败可重试 | 加载中/错误横幅 | ✅ |
| LoginView | `/auth/register|login` | `8cc053c`、`df59adc` | 凭证错误/锁定提示 | — | ✅ |

统一 HTTP 层（`api/http.ts`）：Bearer 自动附加、`{data}` 信封解包、错误归一
`ApiError {code, message, status, detail}`、网络异常 `NETWORK_ERROR`；密码/Token
不入日志。请求竞态控制见 `composables/useDashboardSummary.ts`（inflight 去重 + TTL 缓存）。

## 2. 工作台真实数据化（任务书 4.2）

改造前：`DashboardView` 依赖 `@/data/dashboard` 静态数据（statCards/jobItems/
activityItems/progressSteps/progressStatus）。
改造后（提交 `1573f3a`）：`api/dashboard.ts` + `composables/useDashboardSummary.ts`
从真实业务 API 聚合，页面视觉/布局/图片/图标不变。

| 指标 | 真实来源 | 口径 |
|---|---|---|
| 简历状态卡 | `GET /resumes` | 最新一条 `parse_status` 映射 |
| 画像版本卡 | `GET /students/me/profile` | `profile_version` + 更新时间 |
| 可投递岗位卡 | `GET /jobs?page=1&page_size=1` 的 `total` | **"较上周 +12%"无历史快照数据源，不伪造**，标注"暂无周环比数据源" |
| 最近推荐卡 | `GET /recommendations` `total` | 累计推荐运行次数 |
| 求职进度 | 简历/画像确认/推荐/反馈的真实状态推导 | 无数据即"待完成" |
| 推荐卡片 | 最新推荐运行的 items（真实岗位快照） | 无推荐 → 空态，不塞 mock 岗位 |
| 最近活动 | 真实上传/画像/推荐事件 | 无操作 → 空列表 |
| 顶栏通知 | 真实统计推导 | 空 → "暂无新通知" |

匹配分为启发式/研究匹配分，展示层带口径说明，**未**表述为录用概率。

## 3. 个人设置真实持久化（任务书 4.3，提交 `0c7ed89`）

| 类别 | 处理方式 | 状态 |
|---|---|---|
| 用户基本资料 | 服务端 `user_settings.basic` | ✅ |
| 通知偏好 | `user_settings.notifications` | ✅ |
| 简历解析偏好 | `user_settings.resume_prefs`（OCR 为预留偏好，页面已注明解析链路未接 OCR） | ✅ |
| 求职意向 | `user_settings.job_intent.intentTags`（≤20 个、单个≤24 字） | ✅ |
| 隐私权限 | `user_settings.privacy` | ✅ |
| 主题/显示偏好 | 仅 localStorage，不上传 | ✅ |
| 修改密码 | `POST /auth/change-password`：验证原密码 + 强度校验 + 改密后其他会话立即失效 | ✅ |
| 登录设备管理 | `GET/DELETE /auth/sessions*`：真实服务端会话撤销（非前端数组删除） | ✅ |
| 绑定手机/邮箱/二次验证 | 后端无安全实现 → UI 标"未接入"、按钮禁用，**不模拟成功** | ⚠️ 明确标注 |
| 安全事件审计 | 仅真实会话登录记录；设置变更/改密事件无审计存储，页面已注明 | ⚠️ 明确标注 |

数据模型：`user_settings` 表（Alembic `c3a1f5d27e44`），一行一用户，payload 分区 JSON
严格校验（未知分区/字段/超长 → 422），按当前登录用户隔离（`tests/phase5_2/test_t8_user_settings.py`）。

## 4. 登录态与权限（任务书 4.4）

- 会话恢复：启动时 `GET /auth/me` 校验（`useAuth`）；
- 失效 Token：统一 401 → 页面提示并引导重新登录，不泄露受保护数据；
- 退出登录：`POST /auth/logout` 真实撤销服务端会话 + 清除本地 token/user；
- 权限隔离：服务端 `current_user/current_admin` 强制，前端守卫仅改善体验；
- Token 存储风险：localStorage 持有不透明会话 Token（可撤销），风险与缓解已登记
  `07-security-review.md`；
- 未认证页面不预取业务数据（`useDashboardSummary` 无 token 直接跳过）。

## 5. 智能推荐闭环（任务书 4.5）

真实链路（种子脚本 + E2E 覆盖计划，M3 执行证据见 04-e2e-acceptance.md）：
注册/登录 → 上传简历 → 抽取文本 → 生成画像 → 人工修改/确认 → 查询岗位 →
发起匹配 → 评分与解释 → 推荐历史 → 提交反馈 → 再次推荐。

后端契约保障（`tests/phase5_2r` 回归）：推荐绑定画像版本与内容指纹、岗位画像过期失效、
请求指纹幂等（重复提交 409/复用）、历史快照不可静默篡改、用户隔离、模型不可用降级标记。

## 6. 遗留（不在 M2 阻塞项）

1. 绑定手机/邮箱/2FA 依赖短信/邮件等外部服务，未接入（UI 已如实标注）；
2. 安全事件审计表未建（登录记录已可用真实会话呈现）；
3. admin 岗位管理三端点无学生端 UI（见 02 契约矩阵 §4）。
