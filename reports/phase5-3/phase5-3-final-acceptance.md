# Phase5-3 最终验收报告（M6）

- 运行身份：`local-20261031`
- 执行日期：2026-10-31
- 工作分支：`feat/phase5-3-integration`
- 报告体系：`reports/phase5-3/00`–`09` + 本文件（各里程碑明细见对应报告）

---

## A. 工程交付

### A1. 里程碑完成情况

| 里程碑 | 主要交付 | 验收 | 证据 |
|---|---|---|---|
| M0 基线审计 | HEAD / 环境 / 问题清单 | PASS | `00-baseline-audit.md` |
| M1 CI 修复 | Core CI 模型检查改合成夹具自检；历史权重检查归位 Artifact-dependent | PASS | `01-ci-remediation.md`；Core CI 79/79 |
| M2 前端业务联调 | 10 页面真实 API；工作台真实统计；设置服务端持久化；接口契约矩阵 | PASS | `02-api-contract-matrix.md`、`03-frontend-integration.md` |
| M3 浏览器 E2E | Playwright E01–E12（17 用例）+ 隔离测试环境 | PASS | `04-e2e-acceptance.md`、`e2e-results.json` |
| M4 PostgreSQL 集成 | 十项验收（真实 PG16 隔离库）+ R9 事务缺陷修复 + PG CI Job | PASS | `05-postgresql-validation.md`、`pg-acceptance.json` |
| M5 推理契约与安全 | 三模式契约、`allow_fallback`、降级可追溯持久化、安全审计 | PASS | `06-model-serving-validation.md`、`07-security-review.md`、`model-serving-probe.json` |
| M6 最终报告与交付 | 全量回归归档、真实评估就绪度、文档同步、根目录清理、本报告 | PASS | `08`/`09`、本文件 |

### A2. 主要功能（可演示闭环）

注册/登录/退出 → 上传简历 → 文本抽取 → 生成画像 → 人工修订并确认（乐观锁版本化）→
岗位查询/筛选/详情 → 发起推荐（含模型降级标记与解释）→ 推荐历史（不可篡改快照）→
CSV 导出 → 提交反馈 → 再次推荐（幂等/去重）→ 个人设置（服务端持久化、改密、设备下线）。

### A3. 新增或修改的接口/能力（Phase5-3 轮）

- `POST /api/v1/auth/register|login`：注册限流上限可配置（`JM_REGISTER_RATE_LIMIT`，默认不变）；
- `PUT /api/v1/students/me/profile`：并发保存冲突返回 `409 CONFLICT`（原泄漏 500）；
- `POST/GET /api/v1/recommendations[...]`：`result_summary.degradation` +
  运行记录 `degradation_info`（模型不可用降级可追溯，Alembic `d7e8f9a0b1c2`）；
- 用户设置/密码/设备管理（M2 轮，迁移 `c3a1f5d27e44`）；
- CI 新增 Job：`postgres-integration`、`browser-e2e`、`frontend-ci`、`artifact-validation`。

### A4. 关键技术决策

1. Core CI 与 Artifact-dependent Validation 分离：干净 checkout 不依赖私有权重；
   真实权重检查缺失即 `NOT_RUN`，不伪造 checkpoint；
2. 降级信息"只加不减"：未降级运行保持 `NULL`，不乐观回填；
3. 模型未注册仅在显式 `model_id` 时按 `allow_fallback` 降级，避免线上静默退化；
4. E2E 隔离：独立 sqlite + 私有存储（`tests/e2e/.runtime/`），不触碰开发/生产库；
5. PG 验证只用可销毁隔离实例，凭证仅经环境变量注入。

### A5. 修改文件（Phase5-3 轮核心）

后端：`src/job_matching/service/{business_api,reco_store,profile_store,settings,...}.py`、
`src/job_matching/infra/persistence/models.py`、`alembic/versions/*`；
前端：`frontend/src/views/*`、`frontend/src/api/*`、`frontend/e2e/*`；
工程：`.github/workflows/quality-gates.yml`、`tests/e2e/*`、`scripts/phase5_3/*`、
`tests/phase5_2/test_t6_failures.py`；
文档/报告：`README.md`、`docs/project-overview.md`、`reports/phase5-3/*`。

### A6. Git 提交

`feat/phase5-3-integration` 分支语义化提交（M1→M6 每里程碑独立提交，
含 M4/M5 修复与 M6 报告文档）；未擅自合并 main、未覆盖远端历史。

---

## B. 测试结果（逐条，全部本轮实测）

| Test Suite | Command | Environment | Total | PASS | FAIL | ERROR | SKIP | Exit Code | Duration | Evidence Path |
|---|---|---|---|---|---|---|---|---|---|---|
| Core CI（C1–C5） | `py -3.13 tests/core_ci/run_all.py` | CPU 合成夹具 | 79 | 79 | 0 | 0 | 0 | 0 | 277.6s | `reports/phase5-2/ci/core-ci-test-results.json` |
| Phase5-1（S01–S24） | `py -3.13 tests/phase5_1/run_all.py` | CPU 合成夹具 | 92 | 92 | 0 | 0 | 0 | 0 | 9.4s | `reports/phase5-1/test-results.json` |
| Phase5-1R（R1–R6） | `py -3.13 tests/phase5_1r/run_all.py` | CPU 合成夹具 | 151 | 151 | 0 | 0 | 0 | 0 | 96.1s | `reports/phase5-1r/test-results.json` |
| Phase5-1A（A1–A7） | `py -3.13 tests/phase5_1a/run_all.py` | CPU 合成夹具 | 29 | 29 | 0 | 0 | 0 | 0 | 19.1s | `reports/phase5-1a/test-results.json` |
| Phase5-2（T1–T8） | `py -3.13 tests/phase5_2/run_all.py` | sqlite 隔离库 | 62 | 61 | 0 | 0 | 1 | 0 | 72.5s | `reports/phase5-2/test-results.json` |
| Phase5-2R（R1–R9） | `py -3.13 tests/phase5_2r/run_all.py` | sqlite 隔离库 | 70 | 70 | 0 | 0 | 0 | 0 | 68.7s | `reports/phase5-2r/test-results.json` |
| G0 数据质量 | `py -3.13 tests/data_pipeline/test_g0_synth_data_quality.py` | 临时目录 | 61 | 61 | 0 | 0 | 0 | 0 | 4.3s | `09-regression-results.md` |
| M5 推理探针 | `py -3.13 scripts/phase5_3/model_serving_probe.py` | 隔离库 | 10 | 10 | 0 | 0 | 0 | 0 | ~10s | `model-serving-probe.json` |
| 前端类型检查 | `npx vue-tsc --noEmit` | Node 24 | — | 0 error | 0 | — | — | 0 | ~25s | 本表 |
| 前端生产构建 | `npm run build` | Node 24 | — | 成功 | 0 | — | — | 0 | 4.5s | `frontend/dist/` |
| 浏览器 E2E（E01–E12） | `npx playwright test` | 真实前后端 + 隔离库 | 17 | 17 | 0 | 0 | 0 | 0 | ~2.6m | `e2e-results.json` |
| PG 十项验收 | `scripts/phase5_3/pg_acceptance_checks.py` | Docker PG16 | 10 | 10 | 0 | 0 | 0 | 0 | — | `pg-acceptance.json` |
| 历史权重完整性 | `scripts/phase5_1a/check_history_weights_integrity.py` | 本地 models/ | 79 文件 | PASS | 0 | — | — | 0 | — | `history-weights-integrity.json` |

汇总：**后端 543 PASS / 0 FAIL / 1 SKIP**（唯一 SKIP 显式登记 `NOT_RUN`）；
E2E 17/17；PG 10/10；M5 探针 10/10。

---

## C. 未解决问题（按优先级，含状态标记）

### P0：无

### P1

| 项 | 状态 | 说明 |
|---|---|---|
| 中文人岗匹配模型缺失（`future_verified` 仅预留） | BLOCKED | 前置 = Phase4-3B = H2 真实 Gold；不伪造权重 |
| H2 真实 Gold 评估集 | BLOCKED | 真实中文简历 0 / 真实配对 0 / 人工标注未开始（`08-real-evaluation-readiness.md`） |
| CI 修复与新 Job 的远端复核 | NOT_RUN | 需推送 GitHub 触发真实 Actions 运行（本地等价命令已全绿） |

### P2

| 项 | 状态 | 说明 |
|---|---|---|
| Token 存 `localStorage`（XSS 暴露面） | OPEN | 上线改 HttpOnly Cookie + CSRF；演示口径可接受 |
| 无 HTTPS / 外网部署 | OPEN | 上线阻断项 |
| `education_normalizer_v1` 未挂载业务注册表 | NOT_RUN | 研究侧可用；不冒充业务可用 |
| Phase5-2 T6 一项依赖外部故障注入 | NOT_RUN | 缺前置环境显式登记，不冒充 PASS |
| GBM checkpoint 跨 sklearn 版本不可加载 | ENV_INCOMPATIBLE | 登记口径不变，禁止重训掩盖 |
| 根目录临时文件 | PASS（已清理） | M6 清理 47 项草稿 + 2 项探针残留，历史报告未删 |

---

## D. 毕业设计交付能力

| 能力 | 结论 | 证据 |
|---|---|---|
| 可启动 | ✅ | README 快速开始（uvicorn + vite + alembic） |
| 可登录 | ✅ | E01（注册/登录/退出/再登录） |
| 可上传简历 | ✅ | E02 / E03（含失败重试） |
| 可生成画像 | ✅ | E02 / E04（抽取 + 人工修订 + 确认 + 版本历史） |
| 可管理岗位 | ✅ | E05（查询/筛选/详情） |
| 可执行推荐 | ✅ | E06（含模型降级显式标记） |
| 可展示解释 | ✅ | E06（评分构成 + 口径声明 + 免责声明） |
| 可保存历史 | ✅ | E07（快照不可静默篡改 + CSV 导出） |
| 可提交反馈 | ✅ | E08（提交 + 刷新回显） |
| 可重复演示 | ✅ | 演示种子幂等；E2E 隔离环境可反复执行 |
| 可自动化验收 | ✅ | E2E 17/17 + 后端 543 PASS + PG 10/10 |
| 可复现核心算法实验 | ✅ | 历史权重哈希基线一致（79 文件）、固定种子、运行身份校验 |

**最终结论：B. 有条件通过（工程交付 PASS）**

- **工程交付（A 项）：完全通过** —— M0–M6 全部完成，测试 0 FAIL，
  演示闭环完整，可自动化验收；
- **有条件**在两处，且条件明确、不以任何方式隐瞒：
  1. **模型真实有效性未验证**（H2 = BLOCKED）：系统闭环可演示 ≠ 中文真实招聘
     场景有效性已证明；分数仅为排序参考分，不是录用概率；
  2. **CI 远端复核 NOT_RUN**：改动需推送 GitHub 后由真实 Actions 复核；
     本地等价命令已逐条通过并留有退出码证据。

演示与答辩口径（必须遵守）：区分"工程可运行 / 模型实验可复现 / 中文业务有效性已证明"
三层结论（详见 `08-real-evaluation-readiness.md`），不把合成数据、代理标签或
工程测试通过表述为真实就业有效性验证。
