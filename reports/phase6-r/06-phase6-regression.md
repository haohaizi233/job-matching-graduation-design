# Phase6 统一回归结果

- 生成时间：2026-10-31T22:51:52
- 解释器：Python 3.13.2 / win32（本地 3.13；GitHub Core CI 固定 3.11，跨版本兼容性需另行验证）
- 运行用例：81，耗时 48.794s
- PASS=79 FAIL=0 ERROR=0 SKIP=2
- 结论：全部通过

## 运行模块（确定性顺序）

- `test_gold_readiness`
- `test_index_invalidation`
- `test_model_fallback`
- `test_model_integration`
- `test_ranking_and_cache_contracts`
- `test_recommendation_persistence`
- `test_reranker_contract`
- `test_retrieval_equivalence`

## 逐项结果

| 模块 | 用例 | 状态 | 耗时(ms) | 说明 |
|---|---|---|---|---|
| test_gold_readiness | test_annotation_import_validation (test_gold_readiness.M3GoldReadiness.test_annotation_import_validation) | PASS | 1122.272 |  |
| test_gold_readiness | test_annotation_progress_and_resume_support (test_gold_readiness.M3GoldReadiness.test_annotation_progress_and_resume_support) | PASS | 3.709 |  |
| test_gold_readiness | test_export_annotation_packets_blind_and_checked (test_gold_readiness.M3GoldReadiness.test_export_annotation_packets_blind_and_checked) | PASS | 437.571 |  |
| test_gold_readiness | test_freeze_gold_blocks_without_real_data (test_gold_readiness.M3GoldReadiness.test_freeze_gold_blocks_without_real_data) | PASS | 480.546 |  |
| test_gold_readiness | test_freeze_hash_verification_tooling (test_gold_readiness.M3GoldReadiness.test_freeze_hash_verification_tooling) | PASS | 3.299 |  |
| test_gold_readiness | test_gold_workspace_state_driven_and_consistent (test_gold_readiness.M3GoldReadiness.test_gold_workspace_state_driven_and_consistent) | PASS | 101.628 |  |
| test_gold_readiness | test_leakage_gate_tooling (test_gold_readiness.M3GoldReadiness.test_leakage_gate_tooling) | PASS | 390.181 |  |
| test_gold_readiness | test_pii_detection_and_masking_available (test_gold_readiness.M3GoldReadiness.test_pii_detection_and_masking_available) | PASS | 0.089 |  |
| test_index_invalidation | test_cache_hit_skips_rebuild (test_index_invalidation.M2IndexInvalidation.test_cache_hit_skips_rebuild) | PASS | 0.374 |  |
| test_index_invalidation | test_content_key_changes_on_doc_edit (test_index_invalidation.M2IndexInvalidation.test_content_key_changes_on_doc_edit) | PASS | 0.388 |  |
| test_index_invalidation | test_index_refresh_after_job_edit (test_index_invalidation.M2IndexInvalidation.test_index_refresh_after_job_edit) | PASS | 3551.616 |  |
| test_index_invalidation | test_invalidate_specific_and_all (test_index_invalidation.M2IndexInvalidation.test_invalidate_specific_and_all) | PASS | 0.061 |  |
| test_index_invalidation | test_lru_eviction_respects_capacity (test_index_invalidation.M2IndexInvalidation.test_lru_eviction_respects_capacity) | PASS | 0.047 |  |
| test_index_invalidation | test_user_data_isolation_via_content_key (test_index_invalidation.M2IndexInvalidation.test_user_data_isolation_via_content_key) | PASS | 0.093 |  |
| test_model_fallback | test_bge_missing_raises_model_missing (test_model_fallback.M2ModelFallback.test_bge_missing_raises_model_missing) | PASS | 0.43 |  |
| test_model_fallback | test_bge_real_model_inference (test_model_fallback.M2ModelFallback.test_bge_real_model_inference) | PASS | 24697.133 |  |
| test_model_fallback | test_empty_job_list_rejected (test_model_fallback.M2ModelFallback.test_empty_job_list_rejected) | PASS | 14.348 |  |
| test_model_fallback | test_empty_text_rejected_not_random_score (test_model_fallback.M2ModelFallback.test_empty_text_rejected_not_random_score) | PASS | 0.342 |  |
| test_model_fallback | test_explicit_model_id_missing_can_degrade (test_model_fallback.M2ModelFallback.test_explicit_model_id_missing_can_degrade) | PASS | 1.707 |  |
| test_model_fallback | test_fusion_score_nan_refused (test_model_fallback.M2ModelFallback.test_fusion_score_nan_refused) | PASS | 0.238 |  |
| test_model_fallback | test_missing_artifact_degrades_with_reason (test_model_fallback.M2ModelFallback.test_missing_artifact_degrades_with_reason) | PASS | 0.898 |  |
| test_model_fallback | test_missing_artifact_refuses_without_fallback (test_model_fallback.M2ModelFallback.test_missing_artifact_refuses_without_fallback) | PASS | 0.443 |  |
| test_model_fallback | test_rerank_disabled_by_default (test_model_fallback.M2ModelFallback.test_rerank_disabled_by_default) | PASS | 4.722 |  |
| test_model_fallback | test_reranker_missing_raises_model_missing (test_model_fallback.M2ModelFallback.test_reranker_missing_raises_model_missing) | PASS | 4.406 |  |
| test_model_fallback | test_timeout_never_degrades (test_model_fallback.M2ModelFallback.test_timeout_never_degrades) | PASS | 0.498 |  |
| test_model_fallback | test_unregistered_default_slot_fails_explicitly (test_model_fallback.M2ModelFallback.test_unregistered_default_slot_fails_explicitly) | PASS | 0.288 |  |
| test_model_integration | test_01_profile_confirmed_and_jobs_parsed (test_model_integration.M1ModelIntegration.test_01_profile_confirmed_and_jobs_parsed) | PASS | 519.94 |  |
| test_model_integration | test_02_research_strategy_really_called (test_model_integration.M1ModelIntegration.test_02_research_strategy_really_called) | PASS | 560.625 |  |
| test_model_integration | test_03_research_differs_from_baseline (test_model_integration.M1ModelIntegration.test_03_research_differs_from_baseline) | PASS | 499.066 |  |
| test_model_integration | test_04_model_missing_degrades_explicitly (test_model_integration.M1ModelIntegration.test_04_model_missing_degrades_explicitly) | SKIP | 622.741 | BGE 权重在本机存在，降级路径未触发（登记 SKIP，不计 PASS） |
| test_model_integration | test_05_allow_fallback_false_refuses (test_model_integration.M1ModelIntegration.test_05_allow_fallback_false_refuses) | SKIP | 521.631 | BGE 权重在本机存在，失败路径未触发（登记 SKIP，不计 PASS） |
| test_model_integration | test_06_formal_mode_rejected (test_model_integration.M1ModelIntegration.test_06_formal_mode_rejected) | PASS | 0.333 |  |
| test_model_integration | test_07_user_isolation (test_model_integration.M1ModelIntegration.test_07_user_isolation) | PASS | 915.365 |  |
| test_model_integration | test_08_deterministic_same_input (test_model_integration.M1ModelIntegration.test_08_deterministic_same_input) | PASS | 6.574 |  |
| test_ranking_and_cache_contracts | test_cache_key_includes_encoder_tag (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_includes_encoder_tag) | PASS | 0.153 |  |
| test_ranking_and_cache_contracts | test_cache_key_includes_retrieval_config (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_includes_retrieval_config) | PASS | 0.064 |  |
| test_ranking_and_cache_contracts | test_cache_key_includes_strategy_and_schema_version (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_includes_strategy_and_schema_version) | PASS | 0.068 |  |
| test_ranking_and_cache_contracts | test_cache_key_stable_for_identical_inputs (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_stable_for_identical_inputs) | PASS | 0.086 |  |
| test_ranking_and_cache_contracts | test_concurrent_get_or_build_builds_once (test_ranking_and_cache_contracts.R2CacheKeyContract.test_concurrent_get_or_build_builds_once) | PASS | 56.626 |  |
| test_ranking_and_cache_contracts | test_different_rrf_k_scorers_do_not_share_index (test_ranking_and_cache_contracts.R2CacheKeyContract.test_different_rrf_k_scorers_do_not_share_index) | PASS | 9.427 |  |
| test_ranking_and_cache_contracts | test_encoder_tag_dict_form_supported (test_ranking_and_cache_contracts.R2CacheKeyContract.test_encoder_tag_dict_form_supported) | PASS | 0.127 |  |
| test_ranking_and_cache_contracts | test_encoder_tag_respects_encoderinfo_contract (test_ranking_and_cache_contracts.R2CacheKeyContract.test_encoder_tag_respects_encoderinfo_contract) | PASS | 0.143 |  |
| test_ranking_and_cache_contracts | test_deadline_checked_before_index_build (test_ranking_and_cache_contracts.R2DeadlineContract.test_deadline_checked_before_index_build) | PASS | 0.376 |  |
| test_ranking_and_cache_contracts | test_deadline_checked_per_candidate (test_ranking_and_cache_contracts.R2DeadlineContract.test_deadline_checked_per_candidate) | PASS | 3.064 |  |
| test_ranking_and_cache_contracts | test_warmup_preloads_heavy_resources (test_ranking_and_cache_contracts.R2DeadlineContract.test_warmup_preloads_heavy_resources) | PASS | 5.943 |  |
| test_ranking_and_cache_contracts | test_duplicate_job_ids_deduped_with_warning (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_duplicate_job_ids_deduped_with_warning) | PASS | 4.451 |  |
| test_ranking_and_cache_contracts | test_filtered_rows_sorted_after_qualified_in_rank (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_filtered_rows_sorted_after_qualified_in_rank) | PASS | 3.002 |  |
| test_ranking_and_cache_contracts | test_hard_filtered_job_not_in_final_results (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_hard_filtered_job_not_in_final_results) | PASS | 2.658 |  |
| test_ranking_and_cache_contracts | test_same_score_stable_order (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_same_score_stable_order) | PASS | 3.945 |  |
| test_ranking_and_cache_contracts | test_top_k_negative_treated_as_zero (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_top_k_negative_treated_as_zero) | PASS | 4.554 |  |
| test_ranking_and_cache_contracts | test_top_k_shortfall_declared (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_top_k_shortfall_declared) | PASS | 4.405 |  |
| test_ranking_and_cache_contracts | test_top_k_zero_returns_empty (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_top_k_zero_returns_empty) | PASS | 4.217 |  |
| test_recommendation_persistence | test_explanation_replayable_from_history (test_recommendation_persistence.M5RecommendationPersistence.test_explanation_replayable_from_history) | PASS | 505.36 |  |
| test_recommendation_persistence | test_feedback_loop_not_gold (test_recommendation_persistence.M5RecommendationPersistence.test_feedback_loop_not_gold) | PASS | 538.247 |  |
| test_recommendation_persistence | test_idempotency_key_semantic_conflict (test_recommendation_persistence.M5RecommendationPersistence.test_idempotency_key_semantic_conflict) | PASS | 505.698 |  |
| test_recommendation_persistence | test_job_update_produces_distinct_run (test_recommendation_persistence.M5RecommendationPersistence.test_job_update_produces_distinct_run) | PASS | 581.127 |  |
| test_recommendation_persistence | test_model_version_persisted_in_db (test_recommendation_persistence.M5RecommendationPersistence.test_model_version_persisted_in_db) | PASS | 444.166 |  |
| test_recommendation_persistence | test_profile_change_produces_distinct_run (test_recommendation_persistence.M5RecommendationPersistence.test_profile_change_produces_distinct_run) | PASS | 596.177 |  |
| test_recommendation_persistence | test_repeat_request_naturally_deduped (test_recommendation_persistence.M5RecommendationPersistence.test_repeat_request_naturally_deduped) | PASS | 498.055 |  |
| test_reranker_contract | test_reranker_equal_logits (test_reranker_contract.RerankerContract.test_reranker_equal_logits) | PASS | 5.182 |  |
| test_reranker_contract | test_reranker_inference_exception_is_corrupt (test_reranker_contract.RerankerContract.test_reranker_inference_exception_is_corrupt) | PASS | 2.513 |  |
| test_reranker_contract | test_reranker_length_mismatch (test_reranker_contract.RerankerContract.test_reranker_length_mismatch) | PASS | 2.407 |  |
| test_reranker_contract | test_reranker_mixed_signs_strictly_monotonic (test_reranker_contract.RerankerContract.test_reranker_mixed_signs_strictly_monotonic) | PASS | 4.302 |  |
| test_reranker_contract | test_reranker_negative_logits (test_reranker_contract.RerankerContract.test_reranker_negative_logits) | PASS | 3.104 |  |
| test_reranker_contract | test_reranker_none_scores (test_reranker_contract.RerankerContract.test_reranker_none_scores) | PASS | 2.448 |  |
| test_reranker_contract | test_reranker_nonfinite_scores (test_reranker_contract.RerankerContract.test_reranker_nonfinite_scores) | PASS | 4.393 |  |
| test_reranker_contract | test_reranker_numpy_scores (test_reranker_contract.RerankerContract.test_reranker_numpy_scores) | PASS | 2.786 |  |
| test_reranker_contract | test_reranker_numpy_scores_order_preserved (test_reranker_contract.RerankerContract.test_reranker_numpy_scores_order_preserved) | PASS | 2.953 |  |
| test_reranker_contract | test_reranker_real_model_inference (test_reranker_contract.RerankerContract.test_reranker_real_model_inference) | PASS | 3788.279 |  |
| test_reranker_contract | test_reranker_scoring_version (test_reranker_contract.RerankerContract.test_reranker_scoring_version) | PASS | 0.045 |  |
| test_reranker_contract | test_reranker_stable_order_same_input (test_reranker_contract.RerankerContract.test_reranker_stable_order_same_input) | PASS | 5.188 |  |
| test_reranker_contract | test_reranker_top50_boundary (test_reranker_contract.RerankerContract.test_reranker_top50_boundary) | PASS | 239.702 |  |
| test_reranker_contract | test_reranker_zero_logits (test_reranker_contract.RerankerContract.test_reranker_zero_logits) | PASS | 5.073 |  |
| test_retrieval_equivalence | test_empty_corpus (test_retrieval_equivalence.M2RetrievalEquivalence.test_empty_corpus) | PASS | 0.292 |  |
| test_retrieval_equivalence | test_empty_query_and_unknown_terms (test_retrieval_equivalence.M2RetrievalEquivalence.test_empty_query_and_unknown_terms) | PASS | 7.202 |  |
| test_retrieval_equivalence | test_medium_pool_exact_match (test_retrieval_equivalence.M2RetrievalEquivalence.test_medium_pool_exact_match) | PASS | 585.952 |  |
| test_retrieval_equivalence | test_only_positive_scores_returned (test_retrieval_equivalence.M2RetrievalEquivalence.test_only_positive_scores_returned) | PASS | 21.301 |  |
| test_retrieval_equivalence | test_repeated_query_terms_accumulate (test_retrieval_equivalence.M2RetrievalEquivalence.test_repeated_query_terms_accumulate) | PASS | 23.873 |  |
| test_retrieval_equivalence | test_small_pool_exact_match (test_retrieval_equivalence.M2RetrievalEquivalence.test_small_pool_exact_match) | PASS | 61.278 |  |
| test_retrieval_equivalence | test_tie_breaking_stable_by_doc_id (test_retrieval_equivalence.M2RetrievalEquivalence.test_tie_breaking_stable_by_doc_id) | PASS | 0.77 |  |
| test_retrieval_equivalence | test_topk_variants (test_retrieval_equivalence.M2RetrievalEquivalence.test_topk_variants) | PASS | 296.271 |  |
