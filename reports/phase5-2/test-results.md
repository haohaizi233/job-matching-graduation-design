# Phase5-2 端到端测试报告

- 生成时间：2026-10-29T17:19:20 ｜ 模式：full ｜ 耗时 37.54s
- 总计 56 项：PASS=55 FAIL=0 SKIP=1 ｜ ok=True
- SKIP = NOT_RUN / ENV_INCOMPATIBLE，**不计入 PASS**；全部夹具为合成数据，不代表真实中文招聘场景模型效果。

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| T1 | 数据库 Schema/约束/迁移/事务 | 8 | 8 | 0 | 0 |
| T2 | 认证与权限（链路A） | 12 | 12 | 0 | 0 |
| T3 | 简历与画像（链路B） | 10 | 10 | 0 | 0 |
| T4 | 岗位与推荐闭环（链路C） | 9 | 9 | 0 | 0 |
| T5 | 数据隔离（链路D） | 6 | 6 | 0 | 0 |
| T6 | 异常事务（链路E） | 8 | 7 | 0 | 1 |
| T7 | PostgreSQL 集成 | 3 | 3 | 0 | 0 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | PASS |
| no_empty_run | PASS |
| modules_registered_non_empty | PASS |
