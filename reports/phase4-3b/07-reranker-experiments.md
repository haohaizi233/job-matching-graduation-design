# 07 精排实验（Phase4-3B / M3-6.3）

- 证据：`reports/phase4-3b/06-retrieval-benchmark.json`（E05/E06）、`08-ablation-study.json`、`10-resource-benchmark.json`、`tests/phase4_3b/test_p6_reranker_contract.py`
- **gold_status：BLOCKED — 合成代理口径，不构成正式性能结论。**

## 1. 精排器登记

| 项 | BGE-Reranker | 词法基线 |
|---|---|---|
| reranker_id | bge_reranker_base | lexical_v1 |
| 模型/来源 | BAAI/bge-reranker-base@2cfc18c9…（MIT） | 项目内字符 n-gram TF-IDF |
| 后端 | transformers SequenceClassification | sklearn |
| 微调 | **否（零样本）** | 否 |
| max_length | 256（显式截断并计数） | 512 |
| 批量推理 | batch_size=8（可配） | 全批 |
| 缺模型行为 | 显式抛 RerankError（local_files_only） | 恒可用 |

纪律落实（任务书 6.3）：优先零样本、不微调（E07 前置未满足）；截断情况记录（实验中 reranker_truncated_pairs=133/批，已入 08 meta）；输入为「简历画像文本 + JD 文本对」；输出为未校准 logits，**不得解释为概率或录用可能性**（RerankResult.note 已声明）。

## 2. 实验结果（合成夹具，75 对 / 8 查询组）

| 配置 | A ndcg@5 | A ndcg@10 | B ndcg@5 | B mrr@5 |
|---|---|---|---|---|
| E05 BGE 召回 + BGE-Reranker | 0.747 | 0.865 | 0.525 | 0.854 |
| E06 完整架构（召回+精排+约束） | 0.782 | 0.884 | 0.575 | 0.938 |
| Full（消融基准） | 0.756 | — | 0.489 | — |
| Full − CrossEncoderReranking | 0.898 | — | 0.498 | — |

## 3. 事实性结论

1. 在本合成代理标签口径下，BGE-Reranker 精排**未带来提升**：消融中移除精排后 Task A ndcg@5 从 0.756 升至 0.898；配对 bootstrap（NDCG@10，查询组为重采样单位）Full −(−CrossEncoder) = −0.088，95% CI [−0.142, −0.036]，8 组中 7 组移除更好。
2. 可能原因（分析，非结论）：difficulty_tier 代理标签偏向技能词重合，Cross-Encoder 的语义相关偏好与该构造信号方向不一致；且 max_length=256 截断了长 JD 尾部。
3. **不据此判定精排无价值**：n_groups=8、代理标签、循环性风险均在；真实 Gold 到位前 E05/E06 的排序质量悬置。与硬约束组合后（E06）MRR 提升，说明约束过滤对 Top-K 命中有效。

## 4. 资源开销（CPU，RTX 2050 机器但未用 GPU）

| 项 | 实测 |
|---|---|
| 模型加载 | 3.44 s |
| 单对打分 | 61.1 ms |
| 批量 16 对 | 333.6 ms（≈20.9 对/s） |
| 截断计数 | 有（truncated_pairs 逐批登记） |

## 5. 未执行登记

- 微调/早停/超参选择：NOT_RUN（无合法监督数据；禁止使用盲测 Gold）。
- 长度截断敏感性实验（max_length 扫描）：NOT_RUN。
- 真实 Gold 上的精排对照：BLOCKED（H2）。
