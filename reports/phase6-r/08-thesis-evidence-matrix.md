# R7-1：论文证据矩阵（论文章节 ↔ 代码 / 测试 / 实验报告）

- 生成时间：2026-10-31；分支 `fix/phase6-research-integration-hardening`
- 纪律：所有图表使用真实实验数据生成；不得虚构模型效果提升；
  自动化通过 ≠ 真实 Gold 通过（H2 维持 BLOCKED）。

| 论文章节 | 代码证据 | 测试证据 | 实验报告 |
|---|---|---|---|
| 系统总体架构 | `service/api.py` / `business_api.py` / `matching.py` / `reco_store.py` / `model_registry.py`（模块 C/D 真实实现） | `tests/phase5_1`（API 契约 92）、`tests/phase5_2r`（业务闭环 70）、`tests/phase6/test_model_integration.py`（8） | `reports/phase5-3/`（工程闭环）、`reports/phase6-r/00-baseline-audit.md` |
| 简历与岗位画像 | `service/resume_parser.py` / `job_parser.py` / `contracts.py` / `domain/job_rules.py` | `tests/phase5_1r`（151）、`tests/phase6/test_model_integration.py::test_01` | `reports/phase4-3b/`（画像口径）、`docs/feature-schema.md` |
| 智能匹配算法（检索 + 融合） | `models/retrieval.py`（BM25/TF-IDF/BGE + RRF）、`models/fusion.py`（FeatureFusion）、`service/research_strategy.py`（策略执行体） | `tests/phase6/test_retrieval_equivalence.py`（8，Top-K 逐位等价）、`test_reranker_contract.py`（14，排序契约）、`test_ranking_and_cache_contracts.py`（19） | `reports/phase4-3b/` E00–E06、`reports/phase6-r/01-reranker-remediation.md`、`02-retrieval-and-cache-correctness.md` |
| 模型对比（四策略 / 历史模型） | `research_strategy.py` RESEARCH_STRATEGY_SPECS（4 策略）、`model_registry.py`（ridge/gbm/mlp/ranknet 登记）、`inference/predictor.py` | `tests/phase4_3b`（154，含复现性/泄漏防护）、`tests/phase6/test_model_fallback.py`（12）、`test_reranker_contract.py::test_reranker_scoring_version` | `reports/phase4-3b/`（排序指标）、`models/**/metrics.json` + manifest（真实训练产物） |
| 性能优化（BM25 倒排索引） | `models/retrieval.py` BM25Recall（倒排 + 预计算 IDF + Top-K partition） | `tests/phase6/test_retrieval_equivalence.py`（优化前后 Top-K 逐位一致）、`test_ranking_and_cache_contracts.py`（缓存/并发契约） | `reports/phase6-r/03-bm25-benchmark.{json,md}`（150–10000 语料，Warm P50 加速 1.9×–83.9×，真实运行） |
| 系统测试（FastAPI / Vue / PG / E2E） | `service/business_api.py` + `frontend/`（10 视图） | `tests/phase5_1`（92）、`tests/phase5_2`（62，含 PG T7）、`tests/phase5_2r`（70）、`tests/e2e`（E01–E12）、`tests/core_ci`（87） | `reports/phase5-3/e2e-results.*`、`pg-acceptance.json`、`reports/phase6-r/06-phase6-regression.*` |
| 局限性分析与数据门禁 | `annotation/*`（盲标注/仲裁/冻结/PII/泄漏）、`tests/phase6/test_gold_readiness.py`（状态驱动审计） | 工具链 10 项合成夹具测试 + `test_gold_workspace_state_driven_and_consistent` | `reports/phase6-r/04-gold-gate-readiness.md`（H2 = BLOCKED，真实配对 0） |

## 关键图表数据来源（均为真实实验）

| 图表 | 数据源 |
|---|---|
| BM25 新旧延迟/加速比对比图 | `reports/phase6-r/03-bm25-benchmark.json`（逐规模 Build/Cold/Warm P50/P95/QPS/RSS） |
| 精排 Logits 归一化示意图 | `research_strategy._minmax_normalize` 口径 + `test_reranker_contract` 边界数值 |
| 推荐链路时序/架构图 | `matching._rank_research` 阶段 1–4 真实代码路径 |
| 测试覆盖汇总图 | `06-phase6-regression.json` 与各套件 test-results.json 的真实计数 |

## 明确禁止的表述

- 不得把 `score`（排序参考分）表述为录用概率/适配概率；
- 不得用合成代理标签实验声称真实就业匹配有效性（H2 未完成）；
- 不得把「工程测试全绿」等同于「研究复现通过」或「真实有效性通过」；
- Reranker 在合成代理标签上为负贡献（Phase4-3B 观察），不得声称精排带来提升。
