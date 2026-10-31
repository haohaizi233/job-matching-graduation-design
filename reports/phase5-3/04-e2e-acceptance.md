# Phase5-3 / M3 浏览器 E2E 验收报告

- 执行时间：2026-10-31 11:06–11:10（+08:00）
- Run ID：`m3-e2e-20261031-110657`
- 结论：**PASS（17/17 用例，E01–E12 全覆盖）**

## 1. 验收结论

| 项 | 结果 |
|---|---|
| 用例总数 / PASS / FAIL / SKIP | 17 / 17 / 0 / 0 |
| 场景覆盖（任务书 E01–E12） | 12/12 PASS |
| 执行耗时 | 131.3s（单 worker，串行，无并发竞态） |
| 浏览器 | Playwright 1.64.1 / Chromium（Desktop Chrome） |
| 证据 | `reports/phase5-3/e2e-results.json`、`reports/phase5-3/e2e-results.md`、`frontend/e2e/.artifacts/e2e-raw.json`（原始）、失败时 Trace/Screenshot |

## 2. 测试环境与隔离纪律

| 项 | 方案 |
|---|---|
| 后端 | `tests/e2e/serve_backend.py`：真实业务 app（`create_business_app`），Alembic 建库（迁移本身也是被测对象） |
| 数据库 | 隔离 sqlite `tests/e2e/.runtime/e2e.db`（每次全量运行重建），**不触碰** `data/private/dev.db` 与任何生产库 |
| 文件存储 | 隔离私有存储 `tests/e2e/.runtime/storage` |
| 前端 | Vite dev server（`--host 127.0.0.1 --strictPort`），`VITE_API_TARGET` 指向隔离后端 |
| 种子数据 | `tests/e2e/fixtures.py`：1 个合成管理员 + 3 个合成岗位（`is_synthetic=True`） |
| 测试账号 | 用例内注册（`e2e_s_xxxxxx` 随机后缀），密码仅用于隔离测试环境 |
| 简历夹具 | 合成文本（正文显式标注"E2E 合成简历，非真人"），无真人简历、无 PII，**绝不进入 Gold 评估集** |
| Mock 纪律 | 业务流程**零 mock**；仅 E11 使用 `page.route` 注入网络中断 / 500 以测试前端错误状态机（断言的是失败处理，不是假成功） |

## 3. 场景覆盖明细

见 `reports/phase5-3/e2e-results.md` 的"场景覆盖"表（逐条列出用例名）。要点：

| 编号 | 关键断言（真实链路） |
|---|---|
| E01 | UI 注册 → 登录 → 退出（服务端会话撤销）→ 再登录；凭证错误显示真实错误且不进工作台 |
| E02 | 上传合成简历 → 解析完成 → 列表/统计真实 → 画像页回填抽取字段（专业=软件工程、求职意向=Java） |
| E03 | 空文件→`EMPTY_INPUT`；损坏 docx→`DOCX 文件损坏或不是合法 zip 包`；乱码正文→如实标记「部分解析」；行内「重新解析」走真实 reparse |
| E04 | 人工修订保存为新版本（乐观锁 expectedVersion）→ 确认画像 → 版本历史 ≥2 个真实版本 → 回看历史版本 |
| E05 | 岗位真实加载（3 个合成岗位）→ 关键词过滤 → 详情页 JD（岗位职责/任职要求）→ 返回 |
| E06 | 确认画像后发起匹配 → 结果卡片（匹配度、匹配原因解释）→ 免责声明"不代表录用概率"→ 运行元信息（画像/模型版本）→ 刷新后加载最近运行 |
| E07 | 推荐历史展示真实运行 → CSV 导出（真实浏览器下载事件，文件名 `推荐历史_YYYY-MM-DD.csv`，内容含"匹配时间/画像版本"表头） |
| E08 | 反馈中心待反馈记录来自推荐明细 → 提交「感兴趣」→ 刷新后状态从服务端回显 |
| E09 | 未登录访问受保护路由→登录页；无 Token 的 API→服务端 401；失效 Token→全局会话复位、回登录页、不再显示用户信息 |
| E10 | 用户 B 看不到 A 的简历/推荐历史/反馈（服务端隔离 + 空态文案） |
| E11 | 空数据空态引导；网络中断→`数据来源提示：…暂不可用（NETWORK_ERROR）` 且不伪造统计，恢复后提示消失；500→`暂不可用（INTERNAL_ERROR）` 且保持空态 |
| E12 | 刷新后会话与数据保持；1024×768 与 1280×800 下导航与内容可用；记录横向溢出度量（1280 视口下 scrollWidth=1280，无溢出） |

## 4. E2E 暴露并修复的真实缺陷

| 缺陷 | 修复 | 影响面 |
|---|---|---|
| Windows 下 Vite 默认只监听 `::1`，`127.0.0.1:5173` 无法连接（CI/探活不稳定） | `playwright.config.ts` webServer 改为 `npm run dev -- --host 127.0.0.1 --strictPort` | 前端开发/CI |
| 窄视口（≤1100px）侧边栏折叠为纯图标后按钮无无障碍名称（读屏不可用） | `SideNav.vue` 按钮补 `:aria-label="item.label"`（不改视觉） | 无障碍 |
| 画像加载完成前点「确认当前画像」静默无效果、无反馈 | `ProfileView.vue` 确认按钮改为 `:disabled="confirming \|\| !profile"`（与「保存修改」同口径） | 交互一致性 |

## 5. 覆盖边界（如实登记，不夸大）

1. **解析失败批量重试横幅**（`解析失败提示` + 批量「重新解析」）仅在 `parse_status=failed` 的简历行出现。UI 上传链路中该状态只在画像解析抛错时产生（文本解析器返回 `needs_review`→`partial`），E2E 以「部分解析 + 行内重新解析」覆盖可到达路径；`failed` 行为由后端测试（`tests/phase5_2`）覆盖。
2. 「绑定手机/邮箱/2FA」「反馈撤回」等 UI 明确标注"未接入/暂未开放"，E2E 不模拟其成功。
3. 评分口径、解释快照、版本绑定等契约级断言由 `tests/phase5_2r` 回归负责，E2E 只验证浏览器侧呈现一致。

## 6. 复现方式

```powershell
# 一键：清库 + 重启隔离后端 + 真实浏览器运行 + 生成报告
powershell -ExecutionPolicy Bypass -File tests\e2e\run_e2e.ps1
# 只跑部分用例
powershell -ExecutionPolicy Bypass -File tests\e2e\run_e2e.ps1 -Filter e06
```

注意：注册限流为进程内内存桶（20/小时/客户端 IP）。`run_e2e.ps1` 每次全量运行前重启隔离后端，保证限流预算只属于本次运行（全量 17 用例共 16 次注册 < 20）。

## 7. 测试基础设施清单

```text
frontend/playwright.config.ts        # E2E 配置（隔离 webServer、trace/screenshot 保留策略、json reporter）
frontend/e2e/helpers.ts              # 账号/上传/画像确认/发起匹配等共享助手（合成夹具口径）
frontend/e2e/e01-auth.spec.ts        # E01
frontend/e2e/e02-resume-upload.spec.ts
frontend/e2e/e03-resume-parse-failures.spec.ts
frontend/e2e/e04-profile-edit-confirm.spec.ts
frontend/e2e/e05-jobs.spec.ts
frontend/e2e/e06-matching.spec.ts
frontend/e2e/e07-history-export.spec.ts
frontend/e2e/e08-feedback.spec.ts
frontend/e2e/e09-auth-guard.spec.ts
frontend/e2e/e10-isolation.spec.ts
frontend/e2e/e11-error-states.spec.ts
frontend/e2e/e12-refresh-responsive.spec.ts
tests/e2e/fixtures.py                # 合成夹具（账号/简历/岗位，全部显式合成）
tests/e2e/serve_backend.py           # 隔离后端入口（独立 sqlite + 独立存储 + Alembic 建库 + 种子）
tests/e2e/run_e2e.ps1                # 一键清库运行 + 报告
tests/e2e/build_report.py            # Playwright 原始结果 → e2e-results.json/md（纯格式转换）
reports/phase5-3/e2e-results.json    # 验收数据
reports/phase5-3/e2e-results.md      # 验收报告
```
