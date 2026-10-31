# R2：推荐引擎正确性与索引生命周期审计（实测 + 整改）

- 生成时间：2026-10-31；分支 `fix/phase6-research-integration-hardening`
- 审计对象：`ResearchRetrievalScorer.rank()` / `MatchingService._rank_research()` /
  `RecallIndexCache` / 协作式 deadline
- 回归测试：`tests/phase6/test_ranking_and_cache_contracts.py`（19 用例）
  + 既有 `test_index_invalidation.py`（6 用例）

## 1. 索引缓存生命周期

### 1.1 缓存键（整改后）

```
key = sha256(strategy_id + job_docs_content + config)
config = {
  "retrieval": {"rrf_k": ..., "fusion_id": "rrf"},
  "encoder_tag": "<model_id>@<revision>",   # Embedding 版本；纯词法策略为 lexical_only
  "strategy_version": spec.model_version,
  "scoring_config_version": spec.scoring_config_version,
  "schema": INDEX_SCHEMA_VERSION,
}
```

| 失效场景 | 验证方式 | 结果 |
|---|---|---|
| 相同岗位池 | `test_cache_key_stable_for_identical_inputs` / `test_cache_hit_skips_rebuild` | 命中缓存，不重建 |
| 岗位新增/描述修改 | `test_content_key_changes_on_doc_edit`、`test_index_refresh_after_job_edit` | 新键，重建 |
| 检索配置（rrf_k）变化 | `test_cache_key_includes_retrieval_config`、`test_different_rrf_k_scorers_do_not_share_index` | 新键，各建一次 |
| 编码器版本变化 | `test_cache_key_includes_encoder_tag` | 新键 |
| 策略/评分版本变化 | `test_cache_key_includes_strategy_and_schema_version` | 新键 |
| 索引 schema 变化 | 同上（INDEX_SCHEMA_VERSION 入键） | 新键 |

`encoder_tag` 严格按 `EncoderInfo` 契约取 `model_id/revision`（dataclass 与 dict
双形态兼容），并修复了 `info.get()` 对 dataclass 调用引发 `EncoderInfo has no
attribute 'get'` 的缺陷（回归 `test_encoder_tag_respects_encoderinfo_contract`）。

### 1.2 并发安全

原实现为无锁 check-then-act，同键并发会重复建索引。整改为 `get_or_build` 持锁
（`threading.Lock`）构建：8 线程同键并发实测构建 **1 次**、命中 7 次
（`test_concurrent_get_or_build_builds_once`）。builder 在锁内执行是可接受的串行点
（文档化取舍，见 `RecallIndexCache` docstring）。

### 1.3 容量与泄漏

- LRU 淘汰（默认容量 8）：`test_lru_eviction_respects_capacity` 通过；
- 跨用户泄漏：键含岗位文本内容哈希，不同用户岗位集必然不同键
  （`test_user_data_isolation_via_content_key`）；缓存不存用户/简历数据，仅存索引；
- 内存受控：容量上限 + LRU，无淘汰时最大 8 个索引（R3 实测 10000 语料
  倒排索引 RSS 增量约 47.6MB/索引，8 上限理论最坏约 380MB，需按部署内存预算
  调 `max_entries`）。

## 2. Top-K 与硬约束

| 契约 | 行为 | 验证 |
|---|---|---|
| 被硬约束过滤岗位 | **不进** `results`；单独登记 `filtered_out`（job_id/原因/0.0 占位分），并产生 `hard_filtered_excluded:*` 告警 | `test_hard_filtered_job_not_in_final_results` |
| Top-K 不足 | 只返回合格候选 + `top_k_shortfall:requested=..,returned=..,qualified=..` 告警，不拿过滤项凑数 | `test_top_k_shortfall_declared` |
| top_k=0 / 负数 | 返回空结果（负数按 0 处理） | `test_top_k_zero_returns_empty` / `test_top_k_negative_treated_as_zero` |
| 重复 job_id | 服务层去重保留首条 + `duplicate_job_ids_dropped:*` 告警 | `test_duplicate_job_ids_deduped_with_warning` |
| 同分排序稳定 | score 降序 → 输入顺序（pos 升序） | `test_same_score_stable_order` |
| filtered 行排序 | scorer.rank 全量契约中 filtered 行整体排后且保留原因 | `test_filtered_rows_sorted_after_qualified_in_rank` |
| 未命中召回的岗位 | 全量候选池模式下以 `recall_sem=None`（中性）参与融合；显式截断池模式下跳过并在 `retrieval_truncated` 计数声明 | `ResearchRetrievalScorer.rank` 注释 + 等价性用例 |
| top_k 截断语义 | `top_k` 只在**合格**候选上截断（原实现会把过滤项算进名额） | R2 修改（`matching.py`） |

候选池复杂度：默认全量候选池 = O(N)（N ≤ `max_jobs`=200，服务层批量上限），
1000–10000 条在线推荐必须走分页/分批 + 提高 `max_jobs` 并重做资源预算，
**不是**把 `max_jobs` 调大了事（见 03 报告全链路说明）。

## 3. 超时控制（协作式 deadline）

逐阶段审计：

| 阶段 | deadline 检查 | 说明 |
|---|---|---|
| 构建岗位索引（含编码/倒排） | ✅ 构建前检查 | `rank()` 在 `get_or_build` 前 |
| 加载 Embedding 模型 | ⚠️ 不可中断 | 见下 D6 |
| 批量向量编码 | ✅ 阶段边界检查 | 索引构建内单次批量，边界外不可切分 |
| BM25/TF-IDF/RRF 召回 | ✅ 融合前检查 | |
| Cross-Encoder 推理 | ✅ 推理前检查 | 推理本身不可中断 |
| FeatureFusion | ✅ 每候选检查 | `test_deadline_checked_per_candidate` |
| 结果持久化 | —（服务层外） | reco_store 落库在 deadline 语义外，幂等键去重 |

### 真实缺陷 D6：冷加载与请求 deadline 竞速

BGE 编码器/精排器冷加载（权重读取 + 框架初始化）发生在首个请求 `rank()` 内，
实测本机 30–50s；请求默认 `timeout_ms=30000` 从进服务开始计时，冷加载完成后
的下一处检查点被误判 `INFERENCE_TIMEOUT`（本地复现：`test_missing_artifact_
degrades_with_reason` 在冷进程下 ERROR，栈指向 `_check_deadline`）。

整改：新增 `ResearchRetrievalScorer.warmup()`——部署/预热阶段显式预加载编码器与
精排器，把不可中断的加载时间移出请求 deadline 预算
（回归 `test_warmup_preloads_heavy_resources`）。**不**声称软超时能强制中断
不可中断的底层 PyTorch 推理；deadline 只在协作检查点起作用。

### 真实缺陷 D7：环境条件化测试与 deadline 竞速

`test_missing_artifact_degrades_with_reason` 原实现依赖「本机恰好没有 BGE 权重」
才断言降级；权重存在时走真实推理再 skip，与 30s deadline 竞速导致 ERROR。
整改：制品缺失路径改为确定性模拟（加载边界抛 `FileNotFoundError`，与
`_get_encoder` 的 ServiceError 路径逐字段一致），真实权重推理拆为独立用例
`test_bge_real_model_inference`（缺失时显式 `NOT_RUN`，不以 Mock 冒充）。

## 4. 结论

索引缓存键、并发、LRU、Top-K/硬约束/去重/稳定排序、协作式 deadline 均已
契约化并有回归覆盖；两个真实缺陷（D6/D7）已修复且有失败先行的回归证据。
被过滤岗位不再以零分冒充合格推荐；跨用户无数据泄漏路径。
