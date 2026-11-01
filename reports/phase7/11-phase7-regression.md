# Phase7 纯软件协议测试回归结果

- run_id：`phase7-reg-20261101-091426`
- git_sha：`b34158dcc76ea6bddad8d17591c44f680eb11120`
- python_version：`3.13.2`（CPython）
- actual_python_executable：`D:\APP\python 3.13.2\python.exe`
- sys_argv：`tests/phase7/run_all.py`
- working_directory：`D:\desktop\毕业设计`
- platform：Windows-11-10.0.26200-SP0
- dataset_version：none (Phase7 真实 Gold 未建立；测试仅使用合成夹具)
- model_version：n/a（本套件不加载模型权重）
- execution_command：`'D:\APP\python 3.13.2\python.exe' tests/phase7/run_all.py`
- started_at / finished_at：2026-11-01T09:14:25 / 2026-11-01T09:14:26（耗时 1.473s）
- exit_code：0
- 运行用例：64
- PASS=64 FAIL=0 ERROR=0 SKIP=0 NOT_RUN=0 BLOCKED=0
- 结论：全部通过

## 说明

- 本套件是**纯软件协议测试**（预注册锁定、样本规划确定性、标注工具链演练、
  模型哈希门禁、盲测状态机），不依赖真实人工数据，可进入公开 CI；
- 真实人工简历、授权文件与标注原文**不得**进入 GitHub Actions 公开 Runner；
- 本结果不能替代 Phase4-3B / Phase5-x / Phase6 历史回归，也**不构成** H2 通过；
- 运行身份字段取自真实进程（sys.executable / sys.argv / os.getcwd()），
  CI 与本地分别登记实际环境，禁止手工伪造执行命令。

## 运行模块（确定性顺序）

- `test_annotation_drill`
- `test_blind_eval_state_machine`
- `test_model_artifact_guard`
- `test_preregistration`
- `test_run_identity`
- `test_sample_size_planning`

## 逐项结果

| 模块 | 用例 | 状态 | 耗时(ms) | 说明 |
|---|---|---|---|---|
| test_annotation_drill | test_all_required_capabilities_covered (test_annotation_drill.TestAnnotationDrill.test_all_required_capabilities_covered) | PASS | 0.087 |  |
| test_annotation_drill | test_drill_is_explicitly_marked_synthetic (test_annotation_drill.TestAnnotationDrill.test_drill_is_explicitly_marked_synthetic) | PASS | 0.042 |  |
| test_annotation_drill | test_drill_overall_pass (test_annotation_drill.TestAnnotationDrill.test_drill_overall_pass) | PASS | 0.033 |  |
| test_annotation_drill | test_each_capability_passed (test_annotation_drill.TestAnnotationDrill.test_each_capability_passed) | PASS | 0.044 |  |
| test_annotation_drill | test_freeze_refused_without_real_data (test_annotation_drill.TestAnnotationDrill.test_freeze_refused_without_real_data) | PASS | 0.415 |  |
| test_annotation_drill | test_mirror_detection_flags_full_mirror_only (test_annotation_drill.TestAnnotationDrill.test_mirror_detection_flags_full_mirror_only) | PASS | 0.729 |  |
| test_annotation_drill | test_same_person_rejected (test_annotation_drill.TestAnnotationDrill.test_same_person_rejected) | PASS | 0.769 |  |
| test_annotation_drill | test_synthetic_pairs_never_gold (test_annotation_drill.TestAnnotationDrill.test_synthetic_pairs_never_gold) | PASS | 0.276 |  |
| test_annotation_drill | test_workspace_guard_blocks_real_data_dirs (test_annotation_drill.TestAnnotationDrill.test_workspace_guard_blocks_real_data_dirs) | PASS | 17.394 |  |
| test_blind_eval_state_machine | test_blocked_marker_not_misread (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_blocked_marker_not_misread) | PASS | 22.07 |  |
| test_blind_eval_state_machine | test_chain_tamper_detected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_chain_tamper_detected) | PASS | 21.549 |  |
| test_blind_eval_state_machine | test_dataset_hash_mismatch_rejected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_dataset_hash_mismatch_rejected) | PASS | 16.319 |  |
| test_blind_eval_state_machine | test_duplicate_blind_rejected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_duplicate_blind_rejected) | PASS | 32.835 |  |
| test_blind_eval_state_machine | test_forged_lock_record_rejected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_forged_lock_record_rejected) | PASS | 20.58 |  |
| test_blind_eval_state_machine | test_full_legal_flow_single_blind (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_full_legal_flow_single_blind) | PASS | 23.59 |  |
| test_blind_eval_state_machine | test_model_version_mismatch_rejected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_model_version_mismatch_rejected) | PASS | 18.033 |  |
| test_blind_eval_state_machine | test_premature_blind_metrics_rejected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_premature_blind_metrics_rejected) | PASS | 17.498 |  |
| test_blind_eval_state_machine | test_protocol_hash_mismatch_rejected (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_protocol_hash_mismatch_rejected) | PASS | 20.875 |  |
| test_blind_eval_state_machine | test_real_gold_missing_no_fake_unlock (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_real_gold_missing_no_fake_unlock) | PASS | 14.292 |  |
| test_blind_eval_state_machine | test_unlock_rejected_without_gold_frozen (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_unlock_rejected_without_gold_frozen) | PASS | 11.59 |  |
| test_blind_eval_state_machine | test_unlock_rejected_without_model_lock (test_blind_eval_state_machine.TestBlindEvalStateMachine.test_unlock_rejected_without_model_lock) | PASS | 19.308 |  |
| test_model_artifact_guard | test_content_tamper_detected_after_registration (test_model_artifact_guard.TestModelArtifactGuard.test_content_tamper_detected_after_registration) | PASS | 5.747 |  |
| test_model_artifact_guard | test_load_event_not_recorded_on_refusal (test_model_artifact_guard.TestModelArtifactGuard.test_load_event_not_recorded_on_refusal) | PASS | 3.207 |  |
| test_model_artifact_guard | test_load_ok_when_checksum_matches (test_model_artifact_guard.TestModelArtifactGuard.test_load_ok_when_checksum_matches) | PASS | 2.91 |  |
| test_model_artifact_guard | test_load_refused_when_artifact_missing (test_model_artifact_guard.TestModelArtifactGuard.test_load_refused_when_artifact_missing) | PASS | 1.224 |  |
| test_model_artifact_guard | test_load_refused_when_checksum_mismatched (test_model_artifact_guard.TestModelArtifactGuard.test_load_refused_when_checksum_mismatched) | PASS | 2.956 |  |
| test_model_artifact_guard | test_no_artifacts_registered_skips_check (test_model_artifact_guard.TestModelArtifactGuard.test_no_artifacts_registered_skips_check) | PASS | 1.374 |  |
| test_model_artifact_guard | test_no_sha256_registered_skips_check (test_model_artifact_guard.TestModelArtifactGuard.test_no_sha256_registered_skips_check) | PASS | 2.192 |  |
| test_model_artifact_guard | test_untrusted_source_documented (test_model_artifact_guard.TestModelArtifactGuard.test_untrusted_source_documented) | PASS | 1.576 |  |
| test_model_artifact_guard | test_verify_can_be_disabled_explicitly (test_model_artifact_guard.TestModelArtifactGuard.test_verify_can_be_disabled_explicitly) | PASS | 1.928 |  |
| test_preregistration | test_blind_test_unlock_requires_locked_model (test_preregistration.TestPreregistrationLock.test_blind_test_unlock_requires_locked_model) | PASS | 0.621 |  |
| test_preregistration | test_blocked_marker_is_not_flagged (test_preregistration.TestPreregistrationLock.test_blocked_marker_is_not_flagged) | PASS | 0.548 |  |
| test_preregistration | test_no_blind_test_outputs_exist (test_preregistration.TestPreregistrationLock.test_no_blind_test_outputs_exist) | PASS | 1.517 |  |
| test_preregistration | test_no_downgrade_rule_present (test_preregistration.TestPreregistrationLock.test_no_downgrade_rule_present) | PASS | 0.354 |  |
| test_preregistration | test_non_json_blind_output_always_flagged (test_preregistration.TestPreregistrationLock.test_non_json_blind_output_always_flagged) | PASS | 2.038 |  |
| test_preregistration | test_not_computable_policy_forbids_fabrication (test_preregistration.TestPreregistrationLock.test_not_computable_policy_forbids_fabrication) | PASS | 0.373 |  |
| test_preregistration | test_pinned_hash_matches_file (test_preregistration.TestPreregistrationLock.test_pinned_hash_matches_file) | PASS | 0.234 |  |
| test_preregistration | test_primary_metric_is_ndcg_at_10 (test_preregistration.TestPreregistrationLock.test_primary_metric_is_ndcg_at_10) | PASS | 0.328 |  |
| test_preregistration | test_protocol_file_exists (test_preregistration.TestPreregistrationLock.test_protocol_file_exists) | PASS | 0.042 |  |
| test_preregistration | test_protocol_id_and_status_locked (test_preregistration.TestPreregistrationLock.test_protocol_id_and_status_locked) | PASS | 0.301 |  |
| test_preregistration | test_real_results_file_would_be_flagged (test_preregistration.TestPreregistrationLock.test_real_results_file_would_be_flagged) | PASS | 2.98 |  |
| test_preregistration | test_sidecar_lock_matches_file (test_preregistration.TestPreregistrationLock.test_sidecar_lock_matches_file) | PASS | 0.613 |  |
| test_preregistration | test_split_is_group_level_by_resume (test_preregistration.TestPreregistrationLock.test_split_is_group_level_by_resume) | PASS | 0.364 |  |
| test_preregistration | test_verify_script_detects_tampering (test_preregistration.TestPreregistrationLock.test_verify_script_detects_tampering) | PASS | 7.651 |  |
| test_preregistration | test_verify_script_passes (test_preregistration.TestPreregistrationLock.test_verify_script_passes) | PASS | 2.824 |  |
| test_run_identity | test_report_status_count_consistency (test_run_identity.TestRunIdentity.test_report_status_count_consistency) | PASS | 265.836 |  |
| test_run_identity | test_run_identity_actual_interpreter (test_run_identity.TestRunIdentity.test_run_identity_actual_interpreter) | PASS | 141.871 |  |
| test_run_identity | test_run_identity_current_git_sha (test_run_identity.TestRunIdentity.test_run_identity_current_git_sha) | PASS | 347.507 |  |
| test_run_identity | test_runner_import_failure_nonzero (test_run_identity.TestRunIdentity.test_runner_import_failure_nonzero) | PASS | 107.235 |  |
| test_run_identity | test_runner_no_tests_discovered_nonzero (test_run_identity.TestRunIdentity.test_runner_no_tests_discovered_nonzero) | PASS | 99.423 |  |
| test_run_identity | test_runner_report_freshness (test_run_identity.TestRunIdentity.test_runner_report_freshness) | PASS | 102.311 |  |
| test_sample_size_planning | test_all_planning_values_marked_as_assumptions (test_sample_size_planning.TestSampleSizePlanning.test_all_planning_values_marked_as_assumptions) | PASS | 0.081 |  |
| test_sample_size_planning | test_deterministic_output (test_sample_size_planning.TestSampleSizePlanning.test_deterministic_output) | PASS | 0.259 |  |
| test_sample_size_planning | test_mde_decreases_with_groups (test_sample_size_planning.TestSampleSizePlanning.test_mde_decreases_with_groups) | PASS | 0.023 |  |
| test_sample_size_planning | test_mde_formula_consistency (test_sample_size_planning.TestSampleSizePlanning.test_mde_formula_consistency) | PASS | 0.022 |  |
| test_sample_size_planning | test_mde_zero_groups_is_none (test_sample_size_planning.TestSampleSizePlanning.test_mde_zero_groups_is_none) | PASS | 0.018 |  |
| test_sample_size_planning | test_report_payload_is_planning_not_fact (test_sample_size_planning.TestSampleSizePlanning.test_report_payload_is_planning_not_fact) | PASS | 0.737 |  |
| test_sample_size_planning | test_required_groups_inverse_of_mde (test_sample_size_planning.TestSampleSizePlanning.test_required_groups_inverse_of_mde) | PASS | 0.039 |  |
| test_sample_size_planning | test_scenario_a_blind_groups_below_stability_threshold (test_sample_size_planning.TestSampleSizePlanning.test_scenario_a_blind_groups_below_stability_threshold) | PASS | 0.038 |  |
| test_sample_size_planning | test_scenario_b_meets_stability_threshold (test_sample_size_planning.TestSampleSizePlanning.test_scenario_b_meets_stability_threshold) | PASS | 0.031 |  |
| test_sample_size_planning | test_scenario_c_has_smallest_mde (test_sample_size_planning.TestSampleSizePlanning.test_scenario_c_has_smallest_mde) | PASS | 0.037 |  |
| test_sample_size_planning | test_split_groups_sums_to_total (test_sample_size_planning.TestSampleSizePlanning.test_split_groups_sums_to_total) | PASS | 0.025 |  |
| test_sample_size_planning | test_split_is_group_level_not_pair_level (test_sample_size_planning.TestSampleSizePlanning.test_split_is_group_level_not_pair_level) | PASS | 0.03 |  |
| test_sample_size_planning | test_unjudgeable_sensitivity_monotone (test_sample_size_planning.TestSampleSizePlanning.test_unjudgeable_sensitivity_monotone) | PASS | 0.037 |  |
