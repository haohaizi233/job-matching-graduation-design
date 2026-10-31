# Phase4-3B 测试结果

- 生成时间：2026-10-31T15:35:22
- 运行用例：18，耗时 0.388s
- PASS=18 FAIL=0 ERROR=0 SKIP=0

| 组 | 模块 | 说明 |
|---|---|---|
| P1 | `test_p1_dataset_protocol` | 数据集协议 / 代理标签边界 / Gold 门禁语义 |
| P2 | `test_p2_split_leakage` | 切分互斥 / 文本哈希重叠 / 归一化与负采样泄漏 |
| P3 | `test_p3_model_registry` | 模型登记 / checkpoint 真实存在 / 缺失与不兼容处理 |
| P4 | `test_p4_retrieval_baseline` | TF-IDF / BM25 召回基线行为 |
| P5 | `test_p5_embedding_contract` | TextEncoder 契约：空文本 / 截断 / 批量 / 可复现 |
| P6 | `test_p6_reranker_contract` | 精排契约：批量 / 截断 / 缺模型显式失败 |
| P7 | `test_p7_feature_fusion` | 硬/软约束、可解释明细、权重来源登记 |
| P8 | `test_p8_evaluation_metrics` | 排序指标正确性 / 小样本与空样本 / 指标适用性 |
| P9 | `test_p9_reproducibility` | 同输入同输出 / 固定种子 / 推理不改权重 |
| P10 | `test_p10_privacy_guards` | 日志与导出不落简历原文 / 冻结数据不可修改 |
| P11 | `test_p11_reproducibility_guards` | 仓库根解析可移植 / 行尾与冻结完整性回归护栏 |
| P12 | `test_p12_runtime_guard` | 推理超时契约 / 降级契约 / 统一模型输出信封 |
