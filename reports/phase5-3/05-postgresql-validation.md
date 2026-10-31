# Phase5-3 / M4 PostgreSQL 集成与数据库验收报告

- 运行身份：`local-20261031`（本地隔离测试库）
- 执行日期：2026-10-31
- 执行环境：Windows 11（10.0.26200）、Python 3.13.2（`D:\APP\python 3.13.2`）、SQLAlchemy 2.0.45、Alembic 1.18.1、psycopg2 2.9.10
- PostgreSQL：**Docker 隔离临时实例** `jm-pg-test`（`postgres:16-alpine`，PostgreSQL 16.15，仅绑定 `127.0.0.1`，专用测试库）
- 纪律：只操作隔离临时测试库（用例结束执行 downgrade 清理），未触碰任何开发/生产业务库；
  凭证仅经环境变量 `JM_TEST_DATABASE_URL_POSTGRES` 注入，不写入仓库任何文件。

## 1. 验收范围

任务书第六节要求的 10 项验证，全部在真实 PostgreSQL 上执行并逐项登记。

## 2. 十项验收登记（`reports/phase5-3/pg-acceptance.json`）

命令：

```powershell
$env:JM_TEST_DATABASE_URL_POSTGRES="postgresql+psycopg2://<user>:<pass>@127.0.0.1:<port>/<db>"
py -3.13 scripts\phase5_3\pg_acceptance_checks.py --out reports\phase5-3\pg-acceptance.json
```

退出码 **0**，登记结果 **PASS=10 / FAIL=0 / NOT_RUN=0**：

| 编号 | 验收项 | 状态 | 实测证据 |
|---|---|---|---|
| PG01 | `alembic upgrade head` | PASS | head 迁移完成，6 张业务表齐备（users / student_profiles / resumes / jobs / recommendation_runs / recommendation_items） |
| PG02 | 初始 Schema 与约束 | PASS | `pg_constraint` 实查：唯一约束含 `uq_reco_runs_user_fingerprint`、外键约束存在 |
| PG03 | 外键与唯一索引 | PASS | 孤儿 `student_profiles(user_id=999999)` 被外键拒绝（IntegrityError） |
| PG04 | JSON/JSONB 行为 | PASS | 原生 `->>` 路径查询命中 1 行；SQLAlchemy `as_string()` JSON 路径查询命中；`profile_data` 列类型实测 `jsonb` |
| PG05 | 数据库事务回滚 | PASS | 模拟失败事务 rollback 后行数 1 → 1，无半成功记录 |
| PG06 | 多用户隔离 | PASS | 用户 A / B 各命中 1 行，跨用户泄漏 0 行 |
| PG07 | 并发推荐幂等 | PASS | 4 线程并发插入相同 `request_fingerprint`：落库 1 条、被唯一约束拦截 3 条 |
| PG08 | 简历文件与数据库记录一致性 | PASS | 同 `file_sha256` 重复登记被唯一约束拦截；登记行 sha256 与文件实算值一致 |
| PG09 | 迁移前后数据兼容 | PASS | 在旧版本 `99510af3982b` 播种数据，经 `b7d21c4a5f13` → `c3a1f5d27e44` 升级后数据保留 |
| PG10 | PostgreSQL 与 SQLite 行为差异 | PASS | JSON 路径查询双库均命中（PG `->>` / SQLite `json_extract`）；确认 PG 侧为 `jsonb`、SQLite 侧为 JSON 文本，差异已知并在 ORM 层归一 |

## 3. PostgreSQL 相关测试套件（真实 PG 环境）

| 测试套件 | 命令 | 结果 | 退出码 | 证据 |
|---|---|---|---|---|
| Phase5-2 T7 PostgreSQL 集成 | `py -3.13 tests\phase5_2\test_t7_pg_integration.py` | **3 PASS / 0 FAIL**（6.8s） | 0 | 本报告 §3 |
| Phase5-2 全套（T1–T8） | `py -3.13 tests\phase5_2\run_all.py` | **61 PASS / 0 FAIL / 1 SKIP**（62 项，49.1s） | 0 | `reports/phase5-2/test-results.json` |
| Phase5-2R 全套（R1–R9） | `py -3.13 tests\phase5_2r\run_all.py` | **70 PASS / 0 FAIL / 0 SKIP**（56.0s） | 0 | `reports/phase5-2r/test-results.json` |
| R9 PG+契约（单跑） | `py -3.13 tests\phase5_2r\test_r9_pg_contract.py` | **9 PASS / 0 FAIL**（13.9s） | 0 | 本报告 §3 |

说明：
- 未提供 `JM_TEST_DATABASE_URL_POSTGRES` 时，T7 / R9 中 PG 用例按纪律显式 `NOT_RUN`（skip），
  SQLite 通过不冒充 PG 兼容；本轮是**提供真实 PG 后的全量真实执行**。
- 唯一 SKIP 为 Phase5-2 T6 中 1 项依赖外部故障注入条件的事务用例（历史口径，非 PG 项）。
- Phase5-2 从历史 52 PASS / 4 SKIP 变为 61 PASS / 1 SKIP，增量来自 Phase5-3 新增 T8
  （用户设置/密码/设备管理）6 项与 T7 3 项 PG 用例在真实 PG 下从 SKIP 转为真实 PASS。

## 4. 本轮发现并修复的缺陷（R9 修复点）

**缺陷**：`tests/phase5_2r/test_r9_pg_contract.py::test_pg_constraints_jsonb_and_transactions`
中前置数据（用户 + 画像）通过 `flush()` 挂在事务里未提交；后续唯一约束负向用例触发
`IntegrityError` 后 `rollback()`，在 PostgreSQL 上把**整个事务**回滚，连带丢掉前置数据，
导致并发幂等段取不到用户而报错。

**复现（修复前）**：

```text
py -3.13 -m unittest test_r9_pg_contract.R9PostgreSQLAndContract.test_pg_constraints_jsonb_and_transactions
→ Ran 1 test in 16.1s / FAILED (errors=1) / EXIT=1
```

**修复**：在唯一约束负向用例前显式 `s.commit()`，让 rollback 只回滚失败语句。
修复后单跑 `OK（8.8s，EXIT=0）`，全套 70/70 通过。

## 5. CI 集成

PostgreSQL 集成测试已纳入独立 CI Job `postgres-integration`
（`.github/workflows/quality-gates.yml`，GitHub Actions PostgreSQL 16 service），
运行 `test_t7_pg_integration.py` + `test_r9_pg_contract.py` + `pg_acceptance_checks.py`，
凭证由 CI service 临时生成，不接触任何业务库。

## 6. 结论

- **M4 PostgreSQL 集成验收：PASS**（10/10 项真实执行通过，全部有命令与退出码证据）；
- 降级/重升级/重建全部只在隔离临时测试库执行；
- 测试缺前置环境时的 NOT_RUN 机制保留且未被绕过（本轮为环境齐备后的真实 PASS）。
