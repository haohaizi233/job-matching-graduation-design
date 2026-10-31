# Core CI 可移植门禁报告

- 生成时间：2026-10-31T12:02:50 ｜ 模式：full
- 总计 79 项：PASS=79 FAIL=0 SKIP=0 ｜ ok=True

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| C2 | 完整性检查器退出码语义 | 32 | 32 | 0 | 0 |
| C3 | 测试运行器聚合一致性 | 12 | 12 | 0 | 0 |
| C4 | 密钥与泄漏门禁 | 19 | 19 | 0 | 0 |
| C5 | Core CI 工作流契约 | 16 | 16 | 0 | 0 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | PASS |
| no_empty_run | PASS |
| no_unexpected_skip_flood | PASS |
| modules_registered_non_empty | PASS |
