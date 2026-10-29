# Phase5-2 端到端测试报告

- 生成时间：2026-10-29T16:05:26 ｜ 模式：partial:T3 ｜ 耗时 4.68s
- 总计 10 项：PASS=10 FAIL=0 SKIP=0 ｜ ok=True
- SKIP = NOT_RUN / ENV_INCOMPATIBLE，**不计入 PASS**；全部夹具为合成数据，不代表真实中文招聘场景模型效果。

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| T3 | 简历与画像（链路B） | 10 | 10 | 0 | 0 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | PASS |
| no_empty_run | PASS |
| modules_registered_non_empty | PASS |
