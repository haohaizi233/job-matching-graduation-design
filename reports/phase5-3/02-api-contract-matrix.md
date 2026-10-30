# Phase5-3 · 02 接口契约矩阵（前端 API ↔ 后端路由）

- 生成时间：2026-10-31（Phase5-3 / M2 联调审计）
- 分支：`feat/phase5-3-integration`
- 审计方式：逐条比对 `src/job_matching/service/business_api.py` 路由定义与
  `frontend/src/api/*.ts` 调用点（grep `apiRequest`），并对关键链路执行
  `tests/phase5_2`（T1–T8）真实回归，结果见 `09-regression-results.md`。

## 0. 统一约定

| 约定 | 前端实现 | 后端实现 |
|---|---|---|
| 基础前缀 | `apiRequest` 统一加 `/api/v1` | `APIRouter(prefix="/api/v1/...")` |
| 成功信封 | `http.ts` 解包 `{data}` | `_envelope(request_id, data, warnings)` |
| 错误体 | 归一 `ApiError {code, message, status, detail}` | `{error: {code, message, request_id, detail}}` |
| 认证 | `Authorization: Bearer <token>`（`getToken()`） | `current_user` 依赖 → `accounts.resolve_token` |
| 分页 | `items/page/page_size/total` | 同左，`page_size` 上限 100 |
| 未认证 | 401 → 各页面显式处理/上抛 | `AUTH_REQUIRED`/`AUTH_TOKEN_EXPIRED`/`AUTH_INVALID_CREDENTIALS` |
| 越权资源 | — | 一律 404（防资源枚举），角色不足 403 |

## 1. 认证 `/api/v1/auth`

| 方法 | 路径 | 前端调用 | 状态 | 说明 |
|---|---|---|---|---|
| POST | `/register` | `api/auth.ts register()` | ✅ 一致 | 公开注册仅 student；注册限流 20/时/客户端 |
| POST | `/login` | `api/auth.ts login()` | ✅ 一致 | 返回 `{token, user, token_type, expires_at, session_id}` |
| POST | `/logout` | `api/auth.ts logout()` | ✅ 一致 | 服务端会话撤销（非仅清前端） |
| GET | `/me` | `api/auth.ts fetchMe()` | ✅ 一致 | 会话恢复 |
| POST | `/change-password` | `api/settings.ts changePassword()` | ✅ Phase5-3 新增 | 验证原凭证；改密撤销其他会话保留当前 |
| GET | `/sessions` | `api/settings.ts listSessions()` | ✅ Phase5-3 新增 | 活跃会话列表（设备管理），当前会话带 `current` |
| DELETE | `/sessions/{id}` | `api/settings.ts revokeSession()` | ✅ Phase5-3 新增 | 真实撤销；非本人/不存在 404 |
| POST | `/sessions/revoke-others` | `api/settings.ts revokeOtherSessions()` | ✅ Phase5-3 新增 | 保留当前会话 |

## 2. 学生 `/api/v1/students/me`

| 方法 | 路径 | 前端调用 | 状态 | 说明 |
|---|---|---|---|---|
| GET | `/settings` | `api/settings.ts getUserSettings()` | ✅ Phase5-3 新增 | 分区合并默认值；不含主题 |
| PUT | `/settings` | `api/settings.ts saveUserSettings()` | ✅ Phase5-3 新增 | 分区级合并；严格校验（未知分区/字段 422） |
| GET | `/profile` | `api/profile.ts getProfile()` | ✅ 一致 | 无画像时 `NOT_FOUND`→前端按"无画像"处理 |
| PUT | `/profile` | `api/profile.ts saveProfile()` | ✅ 一致 | `edits/confirm/note/expected_version` |
| GET | `/profile/versions` | `api/profile.ts listProfileVersions()` | ✅ 一致 | 画像版本历史 |
| GET | `/profile/versions/{v}` | `api/profile.ts getProfileVersion()` | ✅ 一致 | 单版本预览 |

## 3. 简历 `/api/v1/resumes`

| 方法 | 路径 | 前端调用 | 状态 | 说明 |
|---|---|---|---|---|
| POST | ``（multipart） | `ResumeView` 上传链路 | ✅ 一致 | 合成标记 `is_synthetic` 随上传声明 |
| POST | `/json` | `api/resumes.ts uploadResumeJson()` | ✅ 一致 | Base64 上传（有大小上限） |
| GET | `` | `api/resumes.ts listResumes()` | ✅ 一致 | 工作台/简历页共用 |
| GET | `/{id}` | `api/resumes.ts getResume()` | ✅ 一致 | |
| DELETE | `/{id}` | `api/resumes.ts deleteResume()` | ✅ 一致 | |
| POST | `/{id}/reparse` | `api/resumes.ts reparseResume()` | ✅ 一致 | 解析失败批量重试（cb1f481） |

## 4. 岗位 `/api/v1/jobs`

| 方法 | 路径 | 前端调用 | 状态 | 说明 |
|---|---|---|---|---|
| GET | `` | `api/jobs.ts listJobs/listJobsPaged` | ✅ 一致 | `total` 供工作台真实统计（1573f3a） |
| GET | `/{id}` | `api/jobs.ts getJob()` | ✅ 一致 | 岗位详情 |
| POST | `` | `api/jobs.ts createJob()` | ✅ 一致 | admin only |
| POST | `/import` | （管理端批量导入） | ⚠️ 后端有、前端管理界面未接 | admin only |
| PATCH | `/{id}` | （同上） | ⚠️ 后端有、前端管理界面未接 | |
| POST | `/{id}/status` | （同上） | ⚠️ 后端有、前端管理界面未接 | |
| POST | `/{id}/parse` | `api/jobs.ts parseJob()` | ✅ 一致 | admin only |

> ⚠️ 项说明：岗位**管理**端点服务于管理员维护流程，学生端 UI 不暴露是产品边界而非缺陷；
> 若后续补管理界面，按本表契约直连接口即可。

## 5. 推荐 `/api/v1/recommendations`

| 方法 | 路径 | 前端调用 | 状态 | 说明 |
|---|---|---|---|---|
| POST | `` | `api/recommendations.ts createRecommendation()` | ✅ 一致 | `Idempotency-Key` 头可选；幂等/409 语义 |
| GET | `` | `api/recommendations.ts listRuns()` | ✅ 一致 | 推荐历史 |
| GET | `/{runId}` | `api/recommendations.ts getRun()` | ✅ 一致 | 解释快照 |
| POST | `/{runId}/feedback` | `api/recommendations.ts submitFeedback()` | ✅ 一致 | 业务反馈≠Gold 标签 |
| GET | `/feedback` | `api/recommendations.ts listFeedback()` | ✅ 一致 | |

## 6. Phase5-1 遗留端点

| 路径 | 状态 |
|---|---|
| `/api/v1/profiles/*`、`/api/v1/matching/*` | ⚠️ 开发演示端点；production/staging 被中间件阻断（`assert_deployment_safety` + `_block_legacy_demo`），前端不再依赖 |

## 7. 结论

- 核心业务端点（认证/画像/简历/岗位/推荐/反馈/设置）**前后端一一对应**，
  请求参数与响应信封与统一约定一致；
- Phase5-3 新增 6 个端点（改密/会话管理/设置读写）补齐了任务书 4.3 的服务端能力；
- 未接线端点仅剩 admin 岗位管理三处（见 §4 注），不构成学生端业务缺口；
- 契约正确性证据：`tests/phase5_2`（T1–T8，62 项，58 PASS / 0 FAIL / 4 SKIP-PostgreSQL），
  其中 T8 6 项专测设置/改密/设备管理契约。
