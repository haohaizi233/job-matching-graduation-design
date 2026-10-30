# 13 回归测试结果（Phase4-3B / 十、测试与质量门禁）

- 证据：`reports/phase4-3b/test-results.json` / `test-results.md`（由 `tests/phase4_3b/run_all.py` 实测生成）
- 运行环境：Python 3.11.18（conda `graduation-design`），2026-10-31
- **总计：127 用例，PASS=127，FAIL=0，ERROR=0，SKIP=0，耗时 74.7s**

## 1. 测试组与覆盖

| 组 | 模块 | 覆盖 | 用例数 |
|---|---|---|---|
| P1 | test_p1_dataset_protocol | 数据集协议 / 代理标签边界 / Gold 门禁语义 | 8 |
| P2 | test_p2_split_leakage | 切分互斥 / 文本哈希重叠 / 归一化与负采样泄漏 / 哈希完整性 | 17 |
| P3 | test_p3_model_registry | 模型登记 / checkpoint 真实存在 / 缺失与损坏处理 | 12 |
| P4 | test_p4_retrieval_baseline | TF-IDF / BM25 / 向量召回 / RRF 融合行为 | 12 |
| P5 | test_p5_embedding_contract | TextEncoder：空文本 / 截断 / 批量 / 失败处理 / 缓存 / 可复现 | 14 |
| P6 | test_p6_reranker_contract | 精排契约：批量 / 截断 / 缺模型显式失败 / 权重只读 | 9 |
| P7 | test_p7_feature_fusion | 硬/软约束、可解释明细、权重来源、非法权重拒绝 | 16 |
| P8 | test_p8_evaluation_metrics | NDCG/MRR/Recall/Precision 正确性、空/小样本、指标适用性 | 18 |
| P9 | test_p9_reproducibility | 同输入同输出 / 固定配置 / 推理不改权重 | 7 |
| P10 | test_p10_privacy_guards | PII 脱敏 / 导出白名单 / 冻结不可改 / 合成不进 Gold | 14 |

（分组用例数以 `test-results.json` 的 records 为准，合计 127。）

## 2. 任务书「至少验证」清单对照

| 要求 | 守护测试 |
|---|---|
| 输入输出类型 | P5/P6（encode 需 list[str]；score 长度一致） |
| 空简历 / 空 JD | P4/P5（空查询→空结果；空文本→零向量并计数） |
| 超长文本 | P5/P6（截断显式计数） |
| 不支持的模型 | P5/P6（build_* 未登记→显式异常） |
| 缺失 checkpoint | P3（NOT_RUN/LOAD_FAILED，绝不虚报 LOADED） |
| 不兼容依赖 | P3/P5/P6（ENV_INCOMPATIBLE 语义；BGE 条件测试显式 SKIP 并写明原因） |
| 推理超时 | 登记为**未覆盖**（本轮无长任务场景），在验收表登记 |
| NaN/Inf 分数 | P6/P8（finite 断言；指标对不可评估记 NaN 而非 0） |
| 重复样本 | P1（pair_id 唯一）、P2（pair_index 互斥） |
| 数据泄漏 | P2（ID/pair/文本哈希三层 + IL 规则登记） |
| 冻结数据不可修改 | P10（篡改复验失败 / 拒绝覆盖 / 拒绝重复 dataset_version） |
| 模型输入特征一致性 | P3（n_features/特征名顺序与 schema 一致） |
| 运行结果可复现 | P9（同输入同输出、种子语义、权重只读） |

## 3. 条件测试的诚实性

- BGE 编码/精排相关用例为**有条件测试**：依赖本地权重（固定 revision、`local_files_only=True`）与 torch/transformers；不可用时显式 `SKIP` 并附原因，绝不伪装无条件 PASS。本轮环境全部真实执行（SKIP=0）。
- 测试不修改任何历史 checkpoint / 冻结数据；P10 的冻结实验全部在临时目录使用显式标记的合成夹具。

## 4. 遗留缺口（如实登记）

1. 推理超时路径未覆盖（无超时契约实现）。
2. education 模型决策层一致性（label flip 计数）未覆盖 → 02 报告登记 NOT_RUN。
3. 跨版本反序列化（旧 sklearn）无法在当前环境构造，保留登记。
