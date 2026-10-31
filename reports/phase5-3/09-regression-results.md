# Phase5-3 / 09 全量回归结果汇总（M6）

- 运行身份：`local-20261031`
- 执行日期：2026-10-31
- 执行环境：Windows 11（10.0.26200）、Python 3.13.2、Node.js 24、SQLAlchemy 2.0.45、
  Alembic 1.18.1、Playwright（Chromium）、PostgreSQL 16.15（Docker 隔离实例，M4 轮次）
- 基线提交：`feat/phase5-3-integration`（M5/M6 改动收敛后复跑）
- 纪律：全部为本轮真实执行结果；每行含命令、退出码、耗时与证据路径；
  旧报告不复用冒充本轮结果。

## 1. 后端测试套件

| Test Suite | Command | Environment | Total | PASS | FAIL | ERROR | SKIP | Exit | Duration | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| Core CI 门禁（C1–C5） | `py -3.13 tests/core_ci/run_all.py` | 纯 CPU 合成夹具 | 79 | 79 | 0 | 0 | 0 | 0 | 277.6s | `reports/phase5-2/ci/core-ci-test-results.json` |
| Phase5-1（S01–S24） | `py -3.13 tests/phase5_1/run_all.py` | 纯 CPU 合成夹具 | 92 | 92 | 0 | 0 | 0 | 0 | 9.4s | `reports/phase5-1/test-results.json` |
| Phase5-1R（R1–R6） | `py -3.13 tests/phase5_1r/run_all.py` | 纯 CPU 合成夹具 | 151 | 151 | 0 | 0 | 0 | 0 | 96.1s | `reports/phase5-1r/test-results.json` |
| Phase5-1A（A1–A7） | `py -3.13 tests/phase5_1a/run_all.py` | 纯 CPU 合成夹具 | 29 | 29 | 0 | 0 | 0 | 0 | 19.1s | `reports/phase5-1a/test-results.json` |
| Phase5-2（T1–T8） | `py -3.13 tests/phase5_2/run_all.py` | sqlite 隔离临时库 | 62 | 61 | 0 | 0 | 1 | 0 | 72.5s | `reports/phase5-2/test-results.json` |
| Phase5-2R（R1–R9） | `py -3.13 tests/phase5_2r/run_all.py` | sqlite 隔离临时库 | 70 | 70 | 0 | 0 | 0 | 0 | 68.7s | `reports/phase5-2r/test-results.json` |
| G0 合成夹具数据质量 | `py -3.13 tests/data_pipeline/test_g0_synth_data_quality.py` | 临时目录 | 61 | 61 | 0 | 0 | 0 | 0 | 4.3s | 本表 |
| 语法与导入检查 | `py -3.13 -m compileall -q src scripts tests` | — | — | — | — | — | — | 0 | 2s | 本表 |
| M5 推理契约探针（MS01–MS10） | `py -3.13 scripts/phase5_3/model_serving_probe.py` | 隔离临时库 + 合成夹具 | 10 | 10 | 0 | 0 | 0 | 0 | ~10s | `reports/phase5-3/model-serving-probe.json` |

**后端合计：543 PASS / 0 FAIL / 1 SKIP**（SKIP = Phase5-2 T6 一项依赖外部故障注入条件，
显式登记 `NOT_RUN`，不冒充通过）。

## 2. 前端与浏览器 E2E

| Test Suite | Command | Environment | Total | PASS | FAIL | ERROR | SKIP | Exit | Duration | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| TypeScript 类型检查 | `npx vue-tsc --noEmit` | Node 24 | — | 0 error | 0 | — | — | 0 | ~25s | 本表 |
| 生产构建 | `npm run build`（vue-tsc + vite build） | Node 24 | — | 构建成功 | 0 | — | — | 0 | 4.5s | `frontend/dist/` |
| 浏览器 E2E（E01–E12） | `npx playwright test` | 真实前后端 + 隔离库（8123/5173） | 17 | 17 | 0 | 0 | 0 | 0 | ~2.6m | `reports/phase5-3/e2e-results.json`、`frontend/e2e/.artifacts/` |

## 3. 数据库与产物专项（本轮早前真实执行，报告留存）

| Test Suite | Command | Environment | Result | Exit | Evidence |
|---|---|---|---|---|---|
| M4 PostgreSQL 十项验收 | `py -3.13 scripts/phase5_3/pg_acceptance_checks.py` | Docker PG16 隔离实例 | 10 PASS / 0 FAIL / 0 NOT_RUN | 0 | `reports/phase5-3/pg-acceptance.json`、`05-postgresql-validation.md` |
| PG 测试套件（T7 / R9） | `test_t7_pg_integration.py` / `test_r9_pg_contract.py` | Docker PG16 隔离实例 | 3 PASS + 9 PASS | 0 | `05-postgresql-validation.md` |
| 历史权重完整性 | `py -3.13 scripts/phase5_1a/check_history_weights_integrity.py` | 本地 `models/` | PASS（79 文件与冻结基线一致） | 0 | `reports/phase5-3/history-weights-integrity.json` |

## 4. 缺陷修复登记（本轮回归覆盖）

| 缺陷 | 修复 | 验证 |
|---|---|---|
| E04 画像编辑异步加载覆盖用户输入（时序竞争） | `ProfileView.vue` 表单 touched 标记 + E2E 状态等待（`waitForProfileLoaded`） | E04 通过；E2E 17/17 |
| 注册限流导致 E2E 套件前置批量撞限（20/小时） | `JM_REGISTER_RATE_LIMIT` 可配置；E2E 隔离后端放宽，生产默认不变 | E2E 17/17；R4 限流测试仍通过 |
| 画像并发保存竞态泄漏成 500 | `profile_store` 捕获唯一约束冲突转 `CONFLICT`（409，乐观锁语义） | Phase5-2/5-2R 全通过 |
| 推荐降级不可结构化追溯 | `degradation_info` 持久化 + API 透出 + 前端降级展示 | T6 新增断言；M5 探针 MS03/MS05 |

## 5. 结论

全量回归 **0 FAIL / 0 ERROR**：后端七套件 543 PASS（1 项显式 SKIP）、
前端类型检查与生产构建通过、浏览器 E2E 17/17、PG 专项 10/10、M5 推理探针 10/10、
历史权重完整性 PASS。所有通过均有命令与退出码支撑，未静默吞掉任何失败。
