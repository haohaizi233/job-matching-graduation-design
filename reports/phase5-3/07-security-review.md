# Phase5-3 / M5 安全审计报告

- 运行身份：`local-20261031`
- 执行日期：2026-10-31
- 审计范围：认证与会话、授权与数据隔离、输入校验、错误与日志脱敏、
  部署门禁、依赖与产物管理、前端凭证存储（任务书 4.4 / 九 / M5 安全要求）
- 证据来源：`tests/core_ci`（可信 CI 门禁 **79/79 PASS**，含 C4 隐私与安全 20 项）、
  `tests/phase5_2`（T2 认证 / T5 隔离 / T6 异常事务 / T8 用户设置）、
  `tests/phase5_2r`（R4 边界 / R5 隔离 / R6 上传上限）、代码逐项走查
- 纪律：只登记实测与走查结论；未验证项明确标记，不以"未发现"冒充"不存在"。

## 1. 结论摘要

**无 P0 / P1 未解决安全缺陷**。历史整改项（Phase5-1R F-001–F-009 含 PII 脱敏缺口）
保持修复状态。P2 残余风险 3 项（Token 存储介质、HTTPS、演示账号纪律）在
"上线阻断项"登记，不影响本地毕业设计演示交付。

## 2. 认证与会话

| 项 | 实现 | 证据 | 结论 |
|---|---|---|---|
| 口令哈希 | Argon2（`argon2-cffi`），非明文/非裸 SHA | `accounts.hash_password/verify_password` | PASS |
| 口令强度 | 长度 + 字母 + 数字校验，设上限防 DoS | `accounts.validate_password`（T8 `test_settings_strict_validation` 同口径） | PASS |
| 会话令牌 | 服务端只存 `sha256(token)` 摘要，明文令牌不落库 | `accounts._token_digest` | PASS |
| 登录失败锁定 | `failed_login_count` 累计，超阈值 `AUTH_ACCOUNT_LOCKED`（423） | `accounts.authenticate`（T2 覆盖） | PASS |
| 令牌失效 | 退出 / 改密 / 设备下线均真实撤销会话（非前端删除一项） | T8 `test_change_password_verifies_old_and_revokes_other_sessions`、`test_session_revoke_others_and_cross_user_404`；E09 三条 | PASS |
| 登录错误反馈 | `AUTH_INVALID_CREDENTIALS` 不区分账号/密码存在性 | E01 负向用例 | PASS |

## 3. 授权与数据隔离

- 所有业务路由经 `current_user` / `current_admin` 依赖注入，服务端强制校验
  （不依赖前端路由守卫；E09"未带 Token 的业务 API 由服务端拒绝（41/401）"实测）；
- 跨用户访问一律 404/403（T5 六项、R5、E10）：简历、画像、推荐、反馈、设置均按 `user_id` 收窄；
- 管理员无学生数据后门（T5 `test_admin_has_no_resume_or_reco_backdoor`）。

## 4. 输入校验与资源上限

| 项 | 实现 | 证据 |
|---|---|---|
| 上传大小 | `max_upload_bytes`（默认 4MB），Content-Length 预检 + 有界读取双保险 | `business_api.py`、`read_upload_bounded`；R6 六项 |
| 文件生命周期 | 失败上传清理已写文件，无孤儿 | T6 `test_db_write_failure_after_file_save_leaves_no_orphan` |
| Pydantic 校验 | 请求体类型/长度/枚举严格校验（422） | T8 `test_settings_strict_validation`、R4 |
| 注册限流 | 单客户端固定窗口（默认 20/小时；`JM_REGISTER_RATE_LIMIT` 可配置） | `business_api.py`；R4 `test_rate_limit*` |
| 通用限流 | 单客户端每分钟上限（`rate_limit_per_minute`，默认 300） | `service/api.py`；R4 |
| 反序列化 | 无 `eval`/`exec`（AST 静态检查）；服务层无网络下载器 | C4 `test_ast_no_eval_or_exec_in_service`、`test_service_source_no_network_downloader` |
| SQL 注入 | 全程 SQLAlchemy ORM 参数化，无拼接 SQL | 走查 |

## 5. 错误与日志脱敏

- 统一错误码体系（`errors.py`）：错误响应**不携带** password / token 字段
  （C4 `test_error_payload_never_carries_password_or_token_fields`）；
- 敏感键名值一律 `***REDACTED***`（保留键名便于定位）；
- 本地绝对路径在错误 detail 中脱敏（C4 `test_local_absolute_paths_redacted_in_error_detail`）；
- 日志只记元信息不记简历正文/PII（R4 `test_logs_record_metadata_not_body`；
  C4 PII 掩码覆盖手机号/邮箱/证件号）；
- E2E 报告与 Trace 目录不含 Token / 密码 / 真实个人信息（合成夹具显式标注）。

## 6. 部署门禁

- `assert_deployment_safety`：`production/staging` 未达安全要求拒绝启动
  （C4 `test_service_settings_refuse_prod_without_auth`）；
- Phase5-1 遗留的无认证演示端点在 prod-like 环境**阻断注册**（`business_api.create_business_app`）；
- `settings.py` 无秘密默认值（C4 `test_no_secret_env_defaults_in_settings`）；
- `.env` 被 gitignore 且不入库；`models/`、原始数据不被 Git 跟踪（C4 四项）；
- 仓库无秘密材料（C4 `test_no_secret_material_in_tracked_files`）。

## 7. 前端凭证与会话（4.4 要求）

| 项 | 现状 | 结论 |
|---|---|---|
| 会话恢复 | `localStorage` 持久化 Token，刷新后恢复（E12） | 可用 |
| 失效 Token | 401 触发全局会话复位回登录页（E09 三条） | 正确 |
| 退出登录 | 前端清 Token + 服务端会话撤销 | 正确 |
| 未登录防泄露 | 受保护页先查令牌再取数（E09）；无"短暂泄露用户数据" | 通过 |
| Token 存储风险 | **P2**：`localStorage` 对 XSS 暴露面大于 HttpOnly Cookie | 残余风险登记（§9） |
| 敏感凭证入日志 | 错误提示与控制台无 Token/密码打印（走查 + C4） | 通过 |

## 8. 数据与研究诚信（防"伪造"）

- 合成夹具显式 `is_synthetic=True` / `synthetic_not_gold`，永不进真实 Gold；
- 报告中无简历正文导出（C4 `test_no_resume_text_exported_to_reports`）、无 PII 形态字符串；
- 历史权重只读哈希自检（79 文件与冻结基线一致），**不重训不修改**；
- 评分口径强制"排序参考分，不是录用概率"（M5 MS09）。

## 9. 残余风险与上线阻断项（如实登记，不隐瞒）

| 级别 | 项 | 状态 | 说明 |
|---|---|---|---|
| P2 | Token 存于 `localStorage` | OPEN | 毕业设计演示口径可接受；上生产应迁移 HttpOnly Cookie + CSRF 防护 |
| P2 | 无 HTTPS / 外网部署 | OPEN | 上线阻断项；本地演示不受影响 |
| P2 | 演示账号纪律 | 约定 | 演示账号只能由本地开发种子脚本生成（`tests/e2e` 合成账号、`scripts` 演示种子），默认凭证禁止进线上 |

## 10. 结论

**M5 安全审计：PASS（无新增 P0/P1）**。认证、授权、隔离、输入校验、
脱敏、部署门禁均有实现与测试证据支撑；三项 P2 残余风险已登记为上线阻断/改进建议，
不以任何形式伪称已消除。
