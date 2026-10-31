# R0：Phase6-R 基线审计（实际执行结果）

- 审计时间：2026-10-31（UTC+8）
- 分支：`fix/phase6-research-integration-hardening`
- Git HEAD（审计时）：`3e096c53a55c49999c10e4ba8dcb9a99eb4e499a`
  - `3e096c5` test(phase6): R4 - Gold 门禁改为状态驱动审计（只读）+ 工具链测试解耦
  - `c8d642a` fix(research): R1 - Cross-Encoder 精排实际推理缺陷修复 + Logits 融合口径升级
  - 远端 main：`3b4e50b0031d`（`git fetch origin --prune` 后确认未移动）
- 本地解释器：Python 3.13.2（`py -3.13`，本轮唯一具备完整依赖的环境）
- CI 解释器：GitHub Core CI 固定 Python 3.11（跨版本兼容性以 CI 实跑为准）
- 历史模型 Legacy 环境：Python 3.11.18 + torch 2.1.2+cu121 + sklearn 1.5.2
  （见 `models/**/manifest.json` 的 `environment` 字段；不得为统一版本改写历史 checkpoint）

## 1. 可用模型（本机实测）

| 类别 | 内容 | 本机状态 |
|---|---|---|
| 历史人岗匹配 checkpoint | ridge / ranknet / mlp / gradient_boosting × candidate_cold / job_cold / double_cold（含 ablation、smoke） | 权重在库（`models/matching/`） |
| 学历抽取 checkpoint | charcnn 9 变体 + tfidf 7 变体 | 权重在库（`models/education/`） |
| BGE 编码器 | `bge_small_zh_v15` | **可用**（`build_encoder(local_files_only=True)` 实测加载成功，71 tensors） |
| BGE-Reranker | `bge_reranker_base` | **可用**（实测加载成功，201 tensors） |
| 人工 Gold（H2） | `data/independent_eval/pairs/pairs_real_v2.jsonl` | **0 条真实配对**，状态 BLOCKED |

## 2. 四种研究推荐策略（RESEARCH_STRATEGY_SPECS）

| model_id | 召回 | 精排 | scoring_config_version |
|---|---|---|---|
| `zh_research_retrieval_v1` | BM25 + TF-IDF + RRF | 无 | research_scoring_config_v1 |
| `zh_research_bge_recall_v1` | BM25 + TF-IDF + BGE + RRF | 无 | research_scoring_config_v1 |
| `zh_research_rerank_v1` | BM25 + TF-IDF + RRF | CrossEncoder | research_scoring_config_v2 |
| `zh_research_bge_rerank_v1` | BM25 + TF-IDF + BGE + RRF | CrossEncoder | research_scoring_config_v2 |

全部 `evaluation_status=research_only_zh`、`formal_use_allowed=False`、
`score_type=model_raw_score`（排序参考分，禁止录用概率表述）。

## 3. 实际接入接口

- `MatchingService.rank()` → `_rank_experimental()` → `_rank_research()`（loader=`research_retrieval`）；
- `ResearchRetrievalScorer.rank()`：召回 → RRF → FeatureFusion → 业务硬约束 → 稳定 Top-K → `ModelResult` 信封；
- 持久化：`reco_store`（runs.model_version / scoring_config_version / items.explanation_snapshot）；
- 索引缓存：`RecallIndexCache`（进程级 `INDEX_CACHE`，LRU ≤ 8）；
- 降级契约：`DEGRADABLE_CODES = (MODEL_MISSING, MODEL_CORRUPT, MODEL_INAPPLICABLE)`；
  超时 `INFERENCE_TIMEOUT` 永不降级；默认模型槽位未注册一律显式失败。

## 4. 当前测试覆盖（本轮全部实际运行）

| 套件 | 用例数 | 结果 | 耗时 |
|---|---|---|---|
| tests/phase6/run_all.py | 80 | PASS=78 FAIL=0 ERROR=0 SKIP=2 | 147.6s |
| tests/phase4_3b/run_all.py | 154 | PASS=154 | 187.5s |
| tests/core_ci/run_all.py | 87 | PASS=87 | 276.0s |
| tests/phase5_1/run_all.py | 92 | PASS=92 | 11.9s |
| tests/phase5_1r/run_all.py | 151 | PASS=151 | 89.6s |
| tests/phase5_1a/run_all.py | 29 | PASS=29 | 23.8s |
| tests/phase5_2 / phase5_2r | 见 06 报告 | 运行中登记 | — |

SKIP 说明（不计 PASS）：`test_model_integration` 的 04/05 为「BGE 权重缺失才触发」的
条件化路径，本机权重存在故登记 SKIP；真实权重专项（BGE 编码器 + BGE-Reranker
业务级推理）本机均真实执行并通过。

## 5. CI 状态

- `.github/workflows/quality-gates.yml`：core-ci / frontend-ci / postgres-integration /
  browser-e2e / artifact-dependent-validation / model-artifact-compat-manual 六 Job；
- **Phase6 测试此前未接入任何 CI Job**（R6 待办）；
- 远端 main HEAD `3b4e50b` 对应的 Actions 结果不作为本轮任何 PASS 证据；
  本轮分支推送后以真实 Run URL 为准（见 07）。

## 6. 已发现缺陷（复现条件明确）

| # | 缺陷 | 复现 | 状态 |
|---|---|---|---|
| D1 | 精排消费端 `list(getattr(rr,"scores",[]) or [])` 对多元素 ndarray 触发布尔歧义，被误判 MODEL_CORRUPT | 真实 Cross-Encoder 返回 np.ndarray scores（≥2 元素） | R1 已修复（c8d642a），回归 `test_reranker_numpy_scores` |
| D2 | Logits 融合 `score/max_score` 在全负/零/混合 logits 下静默跳过或越界 | 注入负 logits / 最大 logit=0 | R1 已修复（min-max 归一化 + scoring v2） |
| D3 | 硬约束过滤岗位以 score=0 混入最终推荐结果 | 岗位学历要求高于学生学历 | R2 已修复（filtered_out 单独登记），回归 `test_hard_filtered_job_not_in_final_results` |
| D4 | 索引缓存键不含检索配置/编码器版本，且存在 check-then-act 并发竞态 | 不同 rrf_k 共用缓存；8 线程同键并发 | R2 已修复（键扩展 + 持锁构建），回归 `test_different_rrf_k_scorers_do_not_share_index` 等 |
| D5 | Gold 门禁测试硬编码真实数据必须为零 | 真实配对从 0 增至 >0 即 FAIL | R4 已修复（3e096c5，状态驱动） |
| D6 | BGE 冷加载（实测 30–50s）发生在首个请求内，默认 30s deadline 后被误判 INFERENCE_TIMEOUT | 无预热 + 默认 timeout_ms=30000 + 冷进程调 BGE 策略 | R2 已修复（`warmup()` 预热接口 + 文档），回归 `test_warmup_preloads_heavy_resources` |
| D7 | `test_missing_artifact_degrades_with_reason` 依赖本机权重缺失才断言，且冷加载与 deadline 竞速致 ERROR | 上述 D6 环境下直接 ERROR | R2 已修复（确定性模拟制品缺失 + 真实推理独立用例） |
| D8 | README 称 `models/` 默认不入库，与 433 个跟踪文件的现状矛盾 | `git ls-files models` 计数 | R5 整改（口径同步，见 05） |

## 7. 未完成事项（本基线时点）

- R3 基准：已完成（`reports/phase6-r/03-bm25-benchmark.{json,md}`，150–10000 语料实测）；
- R5 模型产物分发审计与 README 口径同步；
- R6 Phase6 CI Job 接入 + 干净 checkout 验证；
- R7 论文证据矩阵与最终验收报告；
- H2 真实人工 Gold：**BLOCKED**（真实简历 1 份、真实配对 0、标注文件 0），
  本轮不得以任何合成/反馈/模型预测冒充。
