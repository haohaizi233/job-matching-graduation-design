# Phase5-2 端到端测试报告

- 生成时间：2026-10-29T16:55:07 ｜ 模式：full ｜ 耗时 5.23s
- 总计 9 项：PASS=0 FAIL=6 SKIP=3 ｜ ok=False
- SKIP = NOT_RUN / ENV_INCOMPATIBLE，**不计入 PASS**；全部夹具为合成数据，不代表真实中文招聘场景模型效果。

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| T7 | PostgreSQL 集成 | 3 | 0 | 0 | 3 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | FAIL |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | FAIL |
| no_empty_run | PASS |
| modules_registered_non_empty | PASS |
