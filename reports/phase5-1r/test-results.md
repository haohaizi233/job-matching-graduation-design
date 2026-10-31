# Phase5-1R 整改回归测试报告

- 生成时间：2026-10-31T16:53:05 ｜ 耗时：44.42s ｜ 模式：full
- 运行模块：test_r1_gold_freeze, test_r2_annotation_quality, test_r3_business_constraints, test_r4_api_boundary, test_r5_metrics_input, test_r6_e2e_chains
- Python 3.11.18 ｜ commit `21ae6e5d6762d4965648371fca96c0940d210049`（dirty）
- 总计 151 项：PASS=151 FAIL=0 ERROR=0 SKIP=0 ｜ ok=True

| 组 | 内容 | 总数 | 通过 | 失败 | 错误 | 跳过 |
|---|---|---|---|---|---|---|
| R1 | Gold 冻结循环门禁修复（F-001，兼 F-003/F-004 CLI 链路） | 15 | 15 | 0 | 0 | 0 |
| R2 | 标注独立性 / 仲裁 / 完成状态门禁（F-002、F-003） | 33 | 33 | 0 | 0 | 0 |
| R3 | 毕业届别 / 工作经验约束判定（F-005、F-006） | 39 | 39 | 0 | 0 | 0 |
| R4 | API 边界与安全加固（F-007） | 21 | 21 | 0 | 0 | 0 |
| R5 | 独立评估输入物化与非法输入拒绝（F-009） | 20 | 20 | 0 | 0 | 0 |
| R6 | 端到端正向链路 B 简历岗位推荐 / 链路 C 模型错误与降级 | 23 | 23 | 0 | 0 | 0 |

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
| chain_a_gold_freeze_engineering | PASS | 15/15 |
| chain_b_resume_job_recommendation | PASS | 8/8 |
| chain_c_model_error_and_degradation | PASS | 15/15 |

说明：R1–R6 覆盖 F-001–F-009 修复回归、正向/异常/边界路径、
模型降级、数据保护与冻结不可变性；全部使用合成夹具；
链路 A 为冻结工程模拟，**不构成真实 H2 PASS**（H2 维持 BLOCKED）。
分组由 TEST_MODULES 注册表确定，与测试类名前缀无关。
