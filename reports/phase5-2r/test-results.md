# Phase5-2R 业务一致性测试报告

- 生成时间：2026-10-31T05:31:43 ｜ 模式：full ｜ 耗时 29.92s
- 总计 70 项：PASS=68 FAIL=0 SKIP=2 ｜ ok=True
- SKIP = NOT_RUN / ENV_INCOMPATIBLE，**不计入 PASS**；全部夹具为合成数据，不代表真实中文招聘场景模型效果。

| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |
|---|---|---|---|---|---|
| R1 | 岗位画像失效与版本管理（P0-01） | 7 | 7 | 0 | 0 |
| R2 | 推荐幂等指纹与并发唯一（P0-02） | 10 | 10 | 0 | 0 |
| R3 | 数据来源与合成标记（P1-03） | 10 | 10 | 0 | 0 |
| R4 | 文件并发生命周期（P1-04） | 7 | 7 | 0 | 0 |
| R5 | 数据库配置注入与实例隔离（P1-05） | 5 | 5 | 0 | 0 |
| R6 | 上传资源上限（P1-06） | 10 | 10 | 0 | 0 |
| R7 | 岗位筛选与分页语义（P1-07） | 6 | 6 | 0 | 0 |
| R8 | 推荐快照与画像版本一致性（P2） | 6 | 6 | 0 | 0 |
| R9 | PostgreSQL 集成 + API 契约与安全边界（P1-08/P1-09） | 9 | 7 | 0 | 2 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| all_records_have_legal_group | PASS |
| no_empty_run | PASS |
| modules_registered_non_empty | PASS |
