# Phase6 统一回归结果

- 生成时间：2026-10-31T19:15:29
- 解释器：Python 3.13.2 / win32（本地 3.13；GitHub Core CI 固定 3.11，跨版本兼容性需另行验证）
- 运行用例：81，耗时 36.93s
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
| test_gold_readiness | test_annotation_import_validation (test_gold_readiness.M3GoldReadiness.test_annotation_import_validation) | PASS | 1262.151 |  |
| test_gold_readiness | test_annotation_progress_and_resume_support (test_gold_readiness.M3GoldReadiness.test_annotation_progress_and_resume_support) | PASS | 1.669 |  |
| test_gold_readiness | test_export_annotation_packets_blind_and_checked (test_gold_readiness.M3GoldReadiness.test_export_annotation_packets_blind_and_checked) | PASS | 288.219 |  |
| test_gold_readiness | test_freeze_gold_blocks_without_real_data (test_gold_readiness.M3GoldReadiness.test_freeze_gold_blocks_without_real_data) | PASS | 248.649 |  |
| test_gold_readiness | test_freeze_hash_verification_tooling (test_gold_readiness.M3GoldReadiness.test_freeze_hash_verification_tooling) | PASS | 1.143 |  |
| test_gold_readiness | test_gold_workspace_state_driven_and_consistent (test_gold_readiness.M3GoldReadiness.test_gold_workspace_state_driven_and_consistent) | PASS | 37.579 |  |
| test_gold_readiness | test_leakage_gate_tooling (test_gold_readiness.M3GoldReadiness.test_leakage_gate_tooling) | PASS | 251.864 |  |
| test_gold_readiness | test_pii_detection_and_masking_available (test_gold_readiness.M3GoldReadiness.test_pii_detection_and_masking_available) | PASS | 0.037 |  |
| test_index_invalidation | test_cache_hit_skips_rebuild (test_index_invalidation.M2IndexInvalidation.test_cache_hit_skips_rebuild) | PASS | 0.187 |  |
| test_index_invalidation | test_content_key_changes_on_doc_edit (test_index_invalidation.M2IndexInvalidation.test_content_key_changes_on_doc_edit) | PASS | 0.11 |  |
| test_index_invalidation | test_index_refresh_after_job_edit (test_index_invalidation.M2IndexInvalidation.test_index_refresh_after_job_edit) | PASS | 2414.502 |  |
| test_index_invalidation | test_invalidate_specific_and_all (test_index_invalidation.M2IndexInvalidation.test_invalidate_specific_and_all) | PASS | 0.056 |  |
| test_index_invalidation | test_lru_eviction_respects_capacity (test_index_invalidation.M2IndexInvalidation.test_lru_eviction_respects_capacity) | PASS | 0.039 |  |
| test_index_invalidation | test_user_data_isolation_via_content_key (test_index_invalidation.M2IndexInvalidation.test_user_data_isolation_via_content_key) | PASS | 0.085 |  |
| test_model_fallback | test_bge_missing_raises_model_missing (test_model_fallback.M2ModelFallback.test_bge_missing_raises_model_missing) | PASS | 0.385 |  |
| test_model_fallback | test_bge_real_model_inference (test_model_fallback.M2ModelFallback.test_bge_real_model_inference) | PASS | 17438.254 |  |
| test_model_fallback | test_empty_job_list_rejected (test_model_fallback.M2ModelFallback.test_empty_job_list_rejected) | PASS | 16.292 |  |
| test_model_fallback | test_empty_text_rejected_not_random_score (test_model_fallback.M2ModelFallback.test_empty_text_rejected_not_random_score) | PASS | 0.313 |  |
| test_model_fallback | test_explicit_model_id_missing_can_degrade (test_model_fallback.M2ModelFallback.test_explicit_model_id_missing_can_degrade) | PASS | 1.759 |  |
| test_model_fallback | test_fusion_score_nan_refused (test_model_fallback.M2ModelFallback.test_fusion_score_nan_refused) | PASS | 0.244 |  |
| test_model_fallback | test_missing_artifact_degrades_with_reason (test_model_fallback.M2ModelFallback.test_missing_artifact_degrades_with_reason) | PASS | 0.943 |  |
| test_model_fallback | test_missing_artifact_refuses_without_fallback (test_model_fallback.M2ModelFallback.test_missing_artifact_refuses_without_fallback) | PASS | 0.413 |  |
| test_model_fallback | test_rerank_disabled_by_default (test_model_fallback.M2ModelFallback.test_rerank_disabled_by_default) | PASS | 4.973 |  |
| test_model_fallback | test_reranker_missing_raises_model_missing (test_model_fallback.M2ModelFallback.test_reranker_missing_raises_model_missing) | PASS | 4.895 |  |
| test_model_fallback | test_timeout_never_degrades (test_model_fallback.M2ModelFallback.test_timeout_never_degrades) | PASS | 0.533 |  |
| test_model_fallback | test_unregistered_default_slot_fails_explicitly (test_model_fallback.M2ModelFallback.test_unregistered_default_slot_fails_explicitly) | PASS | 0.331 |  |
| test_model_integration | test_01_profile_confirmed_and_jobs_parsed (test_model_integration.M1ModelIntegration.test_01_profile_confirmed_and_jobs_parsed) | PASS | 427.671 |  |
| test_model_integration | test_02_research_strategy_really_called (test_model_integration.M1ModelIntegration.test_02_research_strategy_really_called) | PASS | 479.09 |  |
| test_model_integration | test_03_research_differs_from_baseline (test_model_integration.M1ModelIntegration.test_03_research_differs_from_baseline) | PASS | 400.962 |  |
| test_model_integration | test_04_model_missing_degrades_explicitly (test_model_integration.M1ModelIntegration.test_04_model_missing_degrades_explicitly) | SKIP | 527.793 | BGE 权重在本机存在，降级路径未触发（登记 SKIP，不计 PASS） |
| test_model_integration | test_05_allow_fallback_false_refuses (test_model_integration.M1ModelIntegration.test_05_allow_fallback_false_refuses) | SKIP | 436.359 | BGE 权重在本机存在，失败路径未触发（登记 SKIP，不计 PASS） |
| test_model_integration | test_06_formal_mode_rejected (test_model_integration.M1ModelIntegration.test_06_formal_mode_rejected) | PASS | 0.274 |  |
| test_model_integration | test_07_user_isolation (test_model_integration.M1ModelIntegration.test_07_user_isolation) | PASS | 777.189 |  |
| test_model_integration | test_08_deterministic_same_input (test_model_integration.M1ModelIntegration.test_08_deterministic_same_input) | PASS | 7.815 |  |
| test_ranking_and_cache_contracts | test_cache_key_includes_encoder_tag (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_includes_encoder_tag) | PASS | 0.159 |  |
| test_ranking_and_cache_contracts | test_cache_key_includes_retrieval_config (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_includes_retrieval_config) | PASS | 0.062 |  |
| test_ranking_and_cache_contracts | test_cache_key_includes_strategy_and_schema_version (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_includes_strategy_and_schema_version) | PASS | 0.071 |  |
| test_ranking_and_cache_contracts | test_cache_key_stable_for_identical_inputs (test_ranking_and_cache_contracts.R2CacheKeyContract.test_cache_key_stable_for_identical_inputs) | PASS | 0.071 |  |
| test_ranking_and_cache_contracts | test_concurrent_get_or_build_builds_once (test_ranking_and_cache_contracts.R2CacheKeyContract.test_concurrent_get_or_build_builds_once) | PASS | 55.469 |  |
| test_ranking_and_cache_contracts | test_different_rrf_k_scorers_do_not_share_index (test_ranking_and_cache_contracts.R2CacheKeyContract.test_different_rrf_k_scorers_do_not_share_index) | PASS | 5.722 |  |
| test_ranking_and_cache_contracts | test_encoder_tag_dict_form_supported (test_ranking_and_cache_contracts.R2CacheKeyContract.test_encoder_tag_dict_form_supported) | PASS | 0.072 |  |
| test_ranking_and_cache_contracts | test_encoder_tag_respects_encoderinfo_contract (test_ranking_and_cache_contracts.R2CacheKeyContract.test_encoder_tag_respects_encoderinfo_contract) | PASS | 0.047 |  |
| test_ranking_and_cache_contracts | test_deadline_checked_before_index_build (test_ranking_and_cache_contracts.R2DeadlineContract.test_deadline_checked_before_index_build) | PASS | 0.201 |  |
| test_ranking_and_cache_contracts | test_deadline_checked_per_candidate (test_ranking_and_cache_contracts.R2DeadlineContract.test_deadline_checked_per_candidate) | PASS | 2.31 |  |
| test_ranking_and_cache_contracts | test_warmup_preloads_heavy_resources (test_ranking_and_cache_contracts.R2DeadlineContract.test_warmup_preloads_heavy_resources) | PASS | 3.846 |  |
| test_ranking_and_cache_contracts | test_duplicate_job_ids_deduped_with_warning (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_duplicate_job_ids_deduped_with_warning) | PASS | 2.423 |  |
| test_ranking_and_cache_contracts | test_filtered_rows_sorted_after_qualified_in_rank (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_filtered_rows_sorted_after_qualified_in_rank) | PASS | 2.399 |  |
| test_ranking_and_cache_contracts | test_hard_filtered_job_not_in_final_results (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_hard_filtered_job_not_in_final_results) | PASS | 2.591 |  |
| test_ranking_and_cache_contracts | test_same_score_stable_order (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_same_score_stable_order) | PASS | 2.485 |  |
| test_ranking_and_cache_contracts | test_top_k_negative_treated_as_zero (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_top_k_negative_treated_as_zero) | PASS | 2.13 |  |
| test_ranking_and_cache_contracts | test_top_k_shortfall_declared (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_top_k_shortfall_declared) | PASS | 2.323 |  |
| test_ranking_and_cache_contracts | test_top_k_zero_returns_empty (test_ranking_and_cache_contracts.R2TopKAndHardConstraint.test_top_k_zero_returns_empty) | PASS | 2.141 |  |
| test_recommendation_persistence | test_explanation_replayable_from_history (test_recommendation_persistence.M5RecommendationPersistence.test_explanation_replayable_from_history) | PASS | 712.595 |  |
| test_recommendation_persistence | test_feedback_loop_not_gold (test_recommendation_persistence.M5RecommendationPersistence.test_feedback_loop_not_gold) | PASS | 410.254 |  |
| test_recommendation_persistence | test_idempotency_key_semantic_conflict (test_recommendation_persistence.M5RecommendationPersistence.test_idempotency_key_semantic_conflict) | PASS | 411.74 |  |
| test_recommendation_persistence | test_job_update_produces_distinct_run (test_recommendation_persistence.M5RecommendationPersistence.test_job_update_produces_distinct_run) | PASS | 443.826 |  |
| test_recommendation_persistence | test_model_version_persisted_in_db (test_recommendation_persistence.M5RecommendationPersistence.test_model_version_persisted_in_db) | PASS | 342.591 |  |
| test_recommendation_persistence | test_profile_change_produces_distinct_run (test_recommendation_persistence.M5RecommendationPersistence.test_profile_change_produces_distinct_run) | PASS | 510.855 |  |
| test_recommendation_persistence | test_repeat_request_naturally_deduped (test_recommendation_persistence.M5RecommendationPersistence.test_repeat_request_naturally_deduped) | PASS | 408.505 |  |
| test_reranker_contract | test_reranker_equal_logits (test_reranker_contract.RerankerContract.test_reranker_equal_logits) | PASS | 3.048 |  |
| test_reranker_contract | test_reranker_inference_exception_is_corrupt (test_reranker_contract.RerankerContract.test_reranker_inference_exception_is_corrupt) | PASS | 2.433 |  |
| test_reranker_contract | test_reranker_length_mismatch (test_reranker_contract.RerankerContract.test_reranker_length_mismatch) | PASS | 2.358 |  |
| test_reranker_contract | test_reranker_mixed_signs_strictly_monotonic (test_reranker_contract.RerankerContract.test_reranker_mixed_signs_strictly_monotonic) | PASS | 3.159 |  |
| test_reranker_contract | test_reranker_negative_logits (test_reranker_contract.RerankerContract.test_reranker_negative_logits) | PASS | 3.239 |  |
| test_reranker_contract | test_reranker_none_scores (test_reranker_contract.RerankerContract.test_reranker_none_scores) | PASS | 3.113 |  |
| test_reranker_contract | test_reranker_nonfinite_scores (test_reranker_contract.RerankerContract.test_reranker_nonfinite_scores) | PASS | 5.059 |  |
| test_reranker_contract | test_reranker_numpy_scores (test_reranker_contract.RerankerContract.test_reranker_numpy_scores) | PASS | 2.939 |  |
| test_reranker_contract | test_reranker_numpy_scores_order_preserved (test_reranker_contract.RerankerContract.test_reranker_numpy_scores_order_preserved) | PASS | 3.215 |  |
| test_reranker_contract | test_reranker_real_model_inference (test_reranker_contract.RerankerContract.test_reranker_real_model_inference) | PASS | 3253.248 |  |
| test_reranker_contract | test_reranker_scoring_version (test_reranker_contract.RerankerContract.test_reranker_scoring_version) | PASS | 0.041 |  |
| test_reranker_contract | test_reranker_stable_order_same_input (test_reranker_contract.RerankerContract.test_reranker_stable_order_same_input) | PASS | 5.395 |  |
| test_reranker_contract | test_reranker_top50_boundary (test_reranker_contract.RerankerContract.test_reranker_top50_boundary) | PASS | 224.737 |  |
| test_reranker_contract | test_reranker_zero_logits (test_reranker_contract.RerankerContract.test_reranker_zero_logits) | PASS | 3.523 |  |
| test_retrieval_equivalence | test_empty_corpus (test_retrieval_equivalence.M2RetrievalEquivalence.test_empty_corpus) | PASS | 0.193 |  |
| test_retrieval_equivalence | test_empty_query_and_unknown_terms (test_retrieval_equivalence.M2RetrievalEquivalence.test_empty_query_and_unknown_terms) | PASS | 3.212 |  |
| test_retrieval_equivalence | test_medium_pool_exact_match (test_retrieval_equivalence.M2RetrievalEquivalence.test_medium_pool_exact_match) | PASS | 399.84 |  |
| test_retrieval_equivalence | test_only_positive_scores_returned (test_retrieval_equivalence.M2RetrievalEquivalence.test_only_positive_scores_returned) | PASS | 11.099 |  |
| test_retrieval_equivalence | test_repeated_query_terms_accumulate (test_retrieval_equivalence.M2RetrievalEquivalence.test_repeated_query_terms_accumulate) | PASS | 16.94 |  |
| test_retrieval_equivalence | test_small_pool_exact_match (test_retrieval_equivalence.M2RetrievalEquivalence.test_small_pool_exact_match) | PASS | 48.706 |  |
| test_retrieval_equivalence | test_tie_breaking_stable_by_doc_id (test_retrieval_equivalence.M2RetrievalEquivalence.test_tie_breaking_stable_by_doc_id) | PASS | 0.796 |  |
| test_retrieval_equivalence | test_topk_variants (test_retrieval_equivalence.M2RetrievalEquivalence.test_topk_variants) | PASS | 188.04 |  |
