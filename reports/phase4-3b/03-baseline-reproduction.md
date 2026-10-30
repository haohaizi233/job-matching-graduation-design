# 03 基线复现（Phase4-3B / M1-4.3）

- 证据：`reports/phase4-3b/model-compatibility-runs.json`、`reports/phase4-3b/06-retrieval-benchmark.json`
- 纪律：四种行为严格分开登记（见 02 报告行为分类表）。

## 1. 已执行的复现行为

| 行为 | 对象 | 结果 |
|---|---|---|
| 重新运行评估（REEVALUATE） | 12 个 matching run 的历史预测文件 | RUN，n_pairs_table=122,560 |
| 加载既有 checkpoint 推理（LOAD+PREDICT） | 14 个 run（matching 12 + education 2） | RUN，输出结构符合契约 |
| 与历史输出比对（COMPARE_HISTORICAL） | 同上 | matching 逐位一致；education 数值近似（见 02） |
| 重新训练（RETRAIN） | — | **NOT_RUN**（本轮不执行，历史权重不改写） |
| 从零训练复现（REPRODUCE_FROM_SCRATCH） | — | **NOT_RUN** |

## 2. 复现结论（可复现部分）

1. matching 四模型（Ridge / GB / MLP / RankNet）在三协议下的 checkpoint 加载、前向推理与历史预测**逐位一致**，模型工程产物可复现。
2. education 两模型加载与推理正常；tfidf 概率与历史差 ≤2.9e-8，charcnn ≤1.3e-4。
3. 历史评估指标可由历史预测文件重算得到（REEVALUATE 不训练不推理）。

## 3. 阻断项（如实登记）

| 项 | 状态 | 原因 |
|---|---|---|
| education 决策层一致性比对 | NOT_RUN | 本轮只比对了概率矩阵，未登记 label flip 计数 |
| RETRAIN / FROM_SCRATCH | NOT_RUN | 任务书纪律：不以重训练掩盖问题；且无新监督数据 |
| 真实 Gold 上的基线复评 | BLOCKED | H2 未完成，真实人工标注 0 组 |
| E07 微调 | NOT_RUN | 前置条件（合法监督数据 + 盲测隔离）不满足 |

## 4. 传统检索基线复现（新增，可执行）

E00–E06 在合成夹具（75 对 / 8 简历 / 55 JD）上全部 RUN，覆盖 TF-IDF、BM25、BGE 向量召回、规则融合、Cross-Encoder、约束融合；指标与口径见 `06-retrieval-benchmark.json` 与 `06-retrieval-benchmark.md`。E07 NOT_RUN。
