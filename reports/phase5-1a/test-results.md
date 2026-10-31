# Phase5-1A 门禁自检报告

- 生成时间：2026-10-31T18:47:59 ｜ 模式：full
- 总计 29 项：PASS=29 FAIL=0 SKIP=0 ｜ ok=True

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| A1 | 测试可信性：分组 / 0 测试 / 聚合一致性 | 4 | 4 | 0 | 0 |
| A2 | 架构边界：依赖方向守卫 | 9 | 9 | 0 | 0 |
| A4 | 模型兼容：加载失败分类与历史权重保护 | 9 | 9 | 0 | 0 |
| A6 | 测试回归：历史基线保护与旧套件运行器可信性 | 3 | 3 | 0 | 0 |
| A7 | 文档交付：配置默认值与部署安全声明 | 4 | 4 | 0 | 0 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | PASS |
| no_empty_run | PASS |
