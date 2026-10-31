# 06 检索基准（Phase4-3B / M3-6.1-6.2 / 实验矩阵 E00–E06）

- 证据：`reports/phase4-3b/06-retrieval-benchmark.json`、`reports/model-research/runs/phase4-3b-retrieval-matrix-v1-20261031-042117.json`
- run_id：`phase4-3b-retrieval-matrix-v1-20261031-042117`；git_commit `cb1f481`；seed 20261031；device cpu
- **gold_status：BLOCKED — H2 真实人工 Gold 未冻结，本结果不得作为正式性能结论。**

## 1. 评估集与标签（研究口径）

- 数据：`pairs_synthetic_v1.jsonl`（75 对 / 8 简历 / 55 JD，全部合成夹具，不可进 Gold）。
- 标签：`difficulty_tier` 映射为 0/1/2/3 分级代理相关性（`synthetic_fixture_tier_proxy`），**非人工标注**。
- 循环性警告（已写入 JSON meta）：difficulty_tier 由技能/类别重合度分层生成，与技能类基线共享构造信号。
- 两个任务：
  - Task A（组内排序）：候选 = 该简历的观测配对；
  - Task B（全池检索）：候选 = 55 条 JD，相关 = 夹具配对过的岗位。

## 2. E00–E07 结果（mean，K=5/10）

| 实验 | 方法 | A ndcg@5 | A ndcg@10 | B ndcg@5 | B recall@5 | B mrr@5 | 状态 |
|---|---|---|---|---|---|---|---|
| E00 | 规则融合（FeatureFusion） | 0.831 | 0.892 | 0.457 | 0.222 | 0.729 | RUN |
| E00x | 已训练 GB（checkpoint 推理） | 0.851 | 0.902 | 0.606 | 0.308 | 0.875 | RUN |
| E00x | 已训练 MLP | 0.788 | 0.863 | 0.630 | 0.339 | 0.833 | RUN |
| E00x | 已训练 RankNet | 0.738 | 0.867 | 0.562 | 0.267 | 0.854 | RUN |
| E00x | 已训练 Ridge | 0.795 | 0.881 | 0.576 | 0.285 | 0.854 | RUN |
| E01 | TF-IDF char + Cosine | 0.742 | 0.849 | 0.560 | 0.260 | 0.813 | RUN |
| E02 | BM25（k1=1.5,b=0.75，未调参） | 0.807 | 0.893 | 0.536 | 0.262 | 0.713 | RUN |
| E03 | BGE 向量召回 + Cosine | 0.776 | 0.832 | 0.364 | 0.202 | 0.604 | RUN |
| E03 | 哈希 n-gram 向量（离线基线） | 0.715 | 0.825 | 0.330 | 0.164 | 0.629 | RUN |
| E04 | BGE + 规则融合 | 0.829 | 0.889 | 0.516 | 0.253 | 0.754 | RUN |
| E04 | 哈希向量 + 规则融合 | 0.817 | 0.883 | 0.475 | 0.225 | 0.688 | RUN |
| E05 | BGE 召回 + BGE-Reranker 精排 | 0.747 | 0.865 | 0.525 | 0.259 | 0.854 | RUN |
| E06 | 两阶段 + 业务约束（完整架构） | 0.782 | 0.884 | 0.575 | 0.279 | 0.938 | RUN |
| E07 | 合法训练数据微调 | — | — | — | — | — | **NOT_RUN** |

（指标定义见 `src/job_matching/evaluation/retrieval.py`；组过小/全零相关组单独计数。）

## 3. 事实性观察（不作真实性能结论）

1. **传统关键词法并不弱**：BM25 在 Task A 上优于纯 BGE 召回；TF-IDF 在 Task B 上优于 BGE 召回（0.560 vs 0.364 ndcg@5）。中文短 JD + 技能词场景下关键词匹配信号强。
2. 已训练模型（E00x）在 Task B 领先，但其标签即同源代理标签（循环性），且训练语料与岗位池存在重合风险，**不能**据此宣称优于检索基线。
3. Cross-Encoder 精排（E05）在本合成代理口径下未带来提升，消融显示其为负贡献（见 08/09）。
4. E06 完整架构 B mrr@5=0.938 最高，但 ndcg/recall 与 E00x 相当。

## 4. 编码器登记（E03 实现）

`TextEncoder` 契约：批量编码、空文本→零向量计数、截断统计、失败显式抛错、固定 revision、L2 归一化、CPU/GPU 显式声明、同输入同输出。
- BGE：`BAAI/bge-small-zh-v1.5@7999e1d3…`（MIT），dim=512，mean pooling，max_length=256（本实验）。
- 离线基线：确定性字符 n-gram 特征哈希（dim=512），无预训练语义，仅作可执行基线与回归对照。

## 5. 未执行登记

- E07 微调：NOT_RUN（无合法监督训练数据，盲测隔离前置不满足）。
- BM25/RRF 超参数搜索：NOT_RUN（参数为通用默认值，未在本数据上搜索；如调参只允许在开发集进行并登记）。
