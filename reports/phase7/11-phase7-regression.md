# Phase7 纯软件协议测试回归结果

- run_id：`phase7-reg-20261031-222247`
- git_sha：`fa14c4fb2e37fd12334b647e6d25441c5edc07fc`
- python_version：`3.13.2` / Windows-11-10.0.26200-SP0（本地 3.13；GitHub Core CI 固定 3.11，跨版本兼容性以远端 CI 为准）
- dataset_version：none (Phase7 真实 Gold 未建立；测试仅使用合成夹具)
- model_version：n/a（本套件不加载模型权重）
- execution_command：`py -3.13 tests/phase7/run_all.py`
- exit_code：0
- 运行用例：34，耗时 0.23s
- PASS=34 FAIL=0 ERROR=0 SKIP=0 NOT_RUN=0 BLOCKED=0
- 结论：全部通过

## 说明

- 本套件是**纯软件协议测试**（预注册锁定、样本规划确定性、标注工具链演练），
  不依赖真实人工数据，可进入公开 CI；
- 真实人工简历、授权文件与标注原文**不得**进入 GitHub Actions 公开 Runner；
- 本结果不能替代 Phase4-3B / Phase5-x / Phase6 历史回归，也**不构成** H2 通过。

## 运行模块（确定性顺序）

- `test_annotation_drill`
- `test_preregistration`
- `test_sample_size_planning`

## 逐项结果

| 模块 | 用例 | 状态 | 耗时(ms) | 说明 |
|---|---|---|---|---|
| test_annotation_drill | test_all_required_capabilities_covered (test_annotation_drill.TestAnnotationDrill.test_all_required_capabilities_covered) | PASS | 0.114 |  |
| test_annotation_drill | test_drill_is_explicitly_marked_synthetic (test_annotation_drill.TestAnnotationDrill.test_drill_is_explicitly_marked_synthetic) | PASS | 0.047 |  |
| test_annotation_drill | test_drill_overall_pass (test_annotation_drill.TestAnnotationDrill.test_drill_overall_pass) | PASS | 0.038 |  |
| test_annotation_drill | test_each_capability_passed (test_annotation_drill.TestAnnotationDrill.test_each_capability_passed) | PASS | 0.051 |  |
| test_annotation_drill | test_freeze_refused_without_real_data (test_annotation_drill.TestAnnotationDrill.test_freeze_refused_without_real_data) | PASS | 0.47 |  |
| test_annotation_drill | test_mirror_detection_flags_full_mirror_only (test_annotation_drill.TestAnnotationDrill.test_mirror_detection_flags_full_mirror_only) | PASS | 0.719 |  |
| test_annotation_drill | test_same_person_rejected (test_annotation_drill.TestAnnotationDrill.test_same_person_rejected) | PASS | 0.69 |  |
| test_annotation_drill | test_synthetic_pairs_never_gold (test_annotation_drill.TestAnnotationDrill.test_synthetic_pairs_never_gold) | PASS | 0.345 |  |
| test_annotation_drill | test_workspace_guard_blocks_real_data_dirs (test_annotation_drill.TestAnnotationDrill.test_workspace_guard_blocks_real_data_dirs) | PASS | 28.77 |  |
| test_preregistration | test_blind_test_unlock_requires_locked_model (test_preregistration.TestPreregistrationLock.test_blind_test_unlock_requires_locked_model) | PASS | 1.57 |  |
| test_preregistration | test_no_blind_test_outputs_exist (test_preregistration.TestPreregistrationLock.test_no_blind_test_outputs_exist) | PASS | 2.436 |  |
| test_preregistration | test_no_downgrade_rule_present (test_preregistration.TestPreregistrationLock.test_no_downgrade_rule_present) | PASS | 0.683 |  |
| test_preregistration | test_not_computable_policy_forbids_fabrication (test_preregistration.TestPreregistrationLock.test_not_computable_policy_forbids_fabrication) | PASS | 0.66 |  |
| test_preregistration | test_pinned_hash_matches_file (test_preregistration.TestPreregistrationLock.test_pinned_hash_matches_file) | PASS | 0.462 |  |
| test_preregistration | test_primary_metric_is_ndcg_at_10 (test_preregistration.TestPreregistrationLock.test_primary_metric_is_ndcg_at_10) | PASS | 0.737 |  |
| test_preregistration | test_protocol_file_exists (test_preregistration.TestPreregistrationLock.test_protocol_file_exists) | PASS | 0.123 |  |
| test_preregistration | test_protocol_id_and_status_locked (test_preregistration.TestPreregistrationLock.test_protocol_id_and_status_locked) | PASS | 0.706 |  |
| test_preregistration | test_sidecar_lock_matches_file (test_preregistration.TestPreregistrationLock.test_sidecar_lock_matches_file) | PASS | 0.906 |  |
| test_preregistration | test_split_is_group_level_by_resume (test_preregistration.TestPreregistrationLock.test_split_is_group_level_by_resume) | PASS | 0.573 |  |
| test_preregistration | test_verify_script_detects_tampering (test_preregistration.TestPreregistrationLock.test_verify_script_detects_tampering) | PASS | 12.357 |  |
| test_preregistration | test_verify_script_passes (test_preregistration.TestPreregistrationLock.test_verify_script_passes) | PASS | 3.375 |  |
| test_sample_size_planning | test_all_planning_values_marked_as_assumptions (test_sample_size_planning.TestSampleSizePlanning.test_all_planning_values_marked_as_assumptions) | PASS | 0.098 |  |
| test_sample_size_planning | test_deterministic_output (test_sample_size_planning.TestSampleSizePlanning.test_deterministic_output) | PASS | 0.4 |  |
| test_sample_size_planning | test_mde_decreases_with_groups (test_sample_size_planning.TestSampleSizePlanning.test_mde_decreases_with_groups) | PASS | 0.029 |  |
| test_sample_size_planning | test_mde_formula_consistency (test_sample_size_planning.TestSampleSizePlanning.test_mde_formula_consistency) | PASS | 0.024 |  |
| test_sample_size_planning | test_mde_zero_groups_is_none (test_sample_size_planning.TestSampleSizePlanning.test_mde_zero_groups_is_none) | PASS | 0.017 |  |
| test_sample_size_planning | test_report_payload_is_planning_not_fact (test_sample_size_planning.TestSampleSizePlanning.test_report_payload_is_planning_not_fact) | PASS | 0.569 |  |
| test_sample_size_planning | test_required_groups_inverse_of_mde (test_sample_size_planning.TestSampleSizePlanning.test_required_groups_inverse_of_mde) | PASS | 0.044 |  |
| test_sample_size_planning | test_scenario_a_blind_groups_below_stability_threshold (test_sample_size_planning.TestSampleSizePlanning.test_scenario_a_blind_groups_below_stability_threshold) | PASS | 0.049 |  |
| test_sample_size_planning | test_scenario_b_meets_stability_threshold (test_sample_size_planning.TestSampleSizePlanning.test_scenario_b_meets_stability_threshold) | PASS | 0.039 |  |
| test_sample_size_planning | test_scenario_c_has_smallest_mde (test_sample_size_planning.TestSampleSizePlanning.test_scenario_c_has_smallest_mde) | PASS | 0.05 |  |
| test_sample_size_planning | test_split_groups_sums_to_total (test_sample_size_planning.TestSampleSizePlanning.test_split_groups_sums_to_total) | PASS | 0.035 |  |
| test_sample_size_planning | test_split_is_group_level_not_pair_level (test_sample_size_planning.TestSampleSizePlanning.test_split_is_group_level_not_pair_level) | PASS | 0.041 |  |
| test_sample_size_planning | test_unjudgeable_sensitivity_monotone (test_sample_size_planning.TestSampleSizePlanning.test_unjudgeable_sensitivity_monotone) | PASS | 0.045 |  |
