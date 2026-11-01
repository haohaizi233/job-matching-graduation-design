# P7-4 模型选型

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 状态：**`BLOCKED` —— 未选型、未锁定**
- 上游：[`04-real-model-evaluation.md`](04-real-model-evaluation.md)、
  [`05-statistical-analysis.md`](05-statistical-analysis.md)

> **在 `dev_validation` 真实 Gold 出现之前不存在"选定模型"。**
> 任何声称"已选定最佳模型"的表述都是违规结论。

---

## 一、选型规则（预注册锁定，blind_test 前不得更改）

**选型数据**：`dev_validation` **only**（`blind_test` 严禁参与选型或调参）

**主判据**：`NDCG@10` 均值

**平手时按顺序依次比较**：

1. NDCG@10 配对 Bootstrap **95% CI 下界**更高；
2. `NDCG@5` 均值更高；
3. `Recall@10` 均值更高；
4. 推理延迟 **p95** 更低；
5. 实现复杂度更低（更简单者优先）。

**稳定性要求**：`dev_validation` 有效查询组 < 20 时只能给出 **provisional** 选型，
并标记 `statistical_stability="unstable"`。

**禁止**：
- 用 `blind_test` 结果反推或修正选型；
- 因为模型更复杂/更新颖就宣布它更好；
- 为了选出某个模型而修改主指标或切分。

---

## 二、模型锁定记录（模板，当前全部 `BLOCKED`）

| 锁定字段 | 值 | 状态 |
|---|---|---|
| `selected_model_id` | — | **BLOCKED** |
| `model_version` | — | **BLOCKED** |
| `scoring_config_version` | — | **BLOCKED** |
| `feature_version` | — | **BLOCKED** |
| `data_version` | — | **BLOCKED**（Gold 未冻结） |
| `hyperparameters` | — | **BLOCKED** |
| `selection_reason` | — | **BLOCKED** |
| `dev_groups` | 0 | **BLOCKED** |
| `primary_metric_value` | — | `not_computable` |
| `statistical_stability` | — | `not_computable` |
| `locked_at` | — | 未锁定 |

---

## 三、锁定顺序（不可颠倒）

```text
1. 真实 Gold 冻结（G1/G2/G3）        ← 当前 BLOCKED
2. dev_validation 上评测 E00–E06
3. 按本节规则选型，写入第二节锁定表
4. 锁定后**不再**修改任何模型/超参/特征口径
5. 一次性 blind_test（G4/G5）
6. 出具 05 统计分析与最终结论
```

**E07（有条件监督微调）额外约束**：必须有**独立于 Gold** 的合规训练标签才能训练；
blind_test Gold 严禁进入训练集。当前无此标签 → `BLOCKED`。

---

## 四、与业务系统的关系（重要口径）

当前业务系统（`service/research_strategy.py`）提供 4 种实验性中文推荐策略：

| model_id | 组成 | `evaluation_status` |
|---|---|---|
| `zh_research_retrieval_v1` | BM25 + TF-IDF 双路召回 → RRF → FeatureFusion | `research_only_zh` |
| `zh_research_bge_recall_v1` | 三路召回（含 BGE）→ RRF → FeatureFusion | `research_only_zh` |
| `zh_research_rerank_v1` | 双路召回 → Cross-Encoder 精排 → FeatureFusion | `research_only_zh` |
| `zh_research_bge_rerank_v1` | 三路召回 → Cross-Encoder 精排 → FeatureFusion | `research_only_zh` |

这四种**都是实验性**（`_COMMON_LIMITS` 明确写着"在真实人工 Gold（H2）到位前，
全部策略为研究/实验性推荐，不得表述为已验证匹配效果"）。

因此：
- 本报告**不选定**生产模型；
- 现有四种策略的 `evaluation_status` 保持 `research_only_zh`，**不升级**为 `verified`；
- 推荐分 `score` 是排序参考分，**不是录用概率 / 成功率**（`_COMMON_LIMITS` 已声明）。

---

## 五、结论

- **模型选型状态：`BLOCKED`**；
- 未锁定任何 `selected_model_id`，未执行 blind_test；
- 即使未来 Gold 完成，若模型未满足预注册评价标准（G5：ΔNDCG@10 95% CI 下界 > 0），
  仍**不能**自动判定通过，必须如实记录为"未达标"。
