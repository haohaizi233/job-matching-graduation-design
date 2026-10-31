# Core CI 可移植门禁报告

- 生成时间：2026-10-31T16:45:07 ｜ 模式：partial:C4
- 总计 24 项：PASS=24 FAIL=0 SKIP=0 ｜ ok=True

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| C4 | 密钥与泄漏门禁 | 24 | 24 | 0 | 0 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | PASS |
| no_empty_run | PASS |
| no_unexpected_skip_flood | PASS |
| modules_registered_non_empty | PASS |
