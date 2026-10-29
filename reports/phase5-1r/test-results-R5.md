# Phase5-1R 整改回归测试报告

- 生成时间：2026-10-29T14:26:05 ｜ 耗时：0.11s ｜ 模式：partial:R5
- 运行模块：test_r5_metrics_input
- Python 3.13.2 ｜ commit `0225fcb91a17feec486afb81ae4de3d0e44b342d`（dirty）
- 总计 20 项：PASS=20 FAIL=0 ERROR=0 SKIP=0 ｜ ok=True

| 组 | 内容 | 总数 | 通过 | 失败 | 错误 | 跳过 |
|---|---|---|---|---|---|---|
| R5 | 独立评估输入物化与非法输入拒绝（F-009） | 20 | 20 | 0 | 0 | 0 |

## 聚合一致性断言

| 断言 | 结果 |
|---|---|
| sum_groups_total_eq_totals_tests | PASS |
| sum_groups_pass_eq_totals_pass | PASS |
| sum_groups_fail_eq_totals_fail | PASS |
| sum_groups_skip_eq_totals_skip | PASS |
| all_records_have_legal_group | PASS |
| all_records_belong_to_loaded_module | PASS |
| loaded_modules_registered | PASS |
| no_empty_run | PASS |

## 端到端正向链路

| 链路 | 状态 | 通过/总数 |
|---|---|---|
| chain_a_gold_freeze_engineering | NOT_RUN | 0/0 |
| chain_b_resume_job_recommendation | NOT_RUN | 0/0 |
| chain_c_model_error_and_degradation | NOT_RUN | 0/0 |

说明：R1–R6 覆盖 F-001–F-009 修复回归、正向/异常/边界路径、
模型降级、数据保护与冻结不可变性；全部使用合成夹具；
链路 A 为冻结工程模拟，**不构成真实 H2 PASS**（H2 维持 BLOCKED）。
分组由 TEST_MODULES 注册表确定，与测试类名前缀无关。
