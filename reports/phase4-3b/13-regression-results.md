# 13 回归测试结果（Phase4-3B / 十、测试与质量门禁）

- 证据：`reports/phase4-3b/test-results.json` / `test-results.md`（由 `tests/phase4_3b/run_all.py` 实测生成）
- 运行环境：Python 3.11.18（conda `graduation-design`），2026-10-31
- **总计：154 用例，PASS=154，FAIL=0，ERROR=0，SKIP=0，耗时 88.98s**

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
| P11 | test_p11_reproducibility_guards | 仓库根解析可移植（防串仓）/ 行尾与冻结完整性回归护栏 | 9 |
| P12 | test_p12_runtime_guard | 推理超时契约 / 降级契约 / 统一模型输出信封 | 18 |

（分组用例数以 `test-results.json` 的 records 为准，合计 154。）

## 2. 任务书「至少验证」清单对照

| 要求 | 守护测试 |
|---|---|
| 输入输出类型 | P5/P6（encode 需 list[str]；score 长度一致） |
| 空简历 / 空 JD | P4/P5（空查询→空结果；空文本→零向量并计数） |
| 超长文本 | P5/P6（截断显式计数） |
| 不支持的模型 | P5/P6（build_* 未登记→显式异常） |
| 缺失 checkpoint | P3（NOT_RUN/LOAD_FAILED，绝不虚报 LOADED） |
| 不兼容依赖 | P3/P5/P6（ENV_INCOMPATIBLE 语义；BGE 条件测试显式 SKIP 并写明原因） |
| 推理超时 | **P12（已覆盖）**：软预算超时抛 `InferenceTimeoutError`、协作式 deadline check 可中断长循环、Windows 无 SIGALRM 时如实登记 `soft_poll` |
| NaN/Inf 分数 | P6/P8/P12（finite 断言；`build_result` 拒绝 NaN/Inf） |
| 重复样本 | P1（pair_id 唯一）、P2（pair_index 互斥） |
| 数据泄漏 | P2（ID/pair/文本哈希三层 + IL 规则登记） |
| 冻结数据不可修改 | P10/P11（篡改复验失败 / 拒绝覆盖 / blob 哈希与冻结记录逐字节吻合） |
| 模型输入特征一致性 | P3（n_features/特征名顺序与 schema 一致） |
| 运行结果可复现 | P9/P11（同输入同输出、种子语义、权重只读、仓库根解析可移植） |

## 3. 条件测试的诚实性

- BGE 编码/精排相关用例为**有条件测试**：依赖本地权重（固定 revision、`local_files_only=True`）与 torch/transformers；不可用时显式 `SKIP` 并附原因，绝不伪装无条件 PASS。本轮环境全部真实执行（SKIP=0）。
- 测试不修改任何历史 checkpoint / 冻结数据；P10 的冻结实验全部在临时目录使用显式标记的合成夹具。
- P11 为本轮新增的**回归护栏**：覆盖此前实测发现的两个真实缺陷——研究脚本硬编码 `JM_ROOT` 默认值导致跨检出串仓（D1）、Windows `core.autocrlf` 使冻结哈希复验误报（D2，已由 `.gitattributes` 钉死 LF + `restore_lf_checkout.py` 修复）。
- P12 为本轮新增的**运行期契约**：补齐此前登记的「推理超时未覆盖」缺口（`src/job_matching/models/runtime_guard.py`）。P12 的协作式中断用例已修正一次 flaky 缺陷（循环上限耗时必须显著大于超时预算，否则测不到中断），修正后连跑 5 次全绿。

## 4. 遗留缺口（如实登记）

1. ~~推理超时路径未覆盖~~ → **已覆盖**（P12 + `runtime_guard.py`）。
2. ~~education 模型决策层一致性（label flip 计数）未覆盖~~ → **已执行**，见 `15-education-decision-consistency.md`（16 run / 32 split 全部 label flip=0；发现并修复复现脚本 input_mode 口径缺陷）。
3. 跨版本反序列化（旧 sklearn）无法在当前环境构造，保留登记（见 `02-model-compatibility.md`）。
4. 千级/万级岗位池扩展性与 GPU 推理 → **已执行**，见 `14-resource-scalability.md`。