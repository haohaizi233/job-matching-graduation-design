# P7-4 真实中文模型对比实验

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 状态：**`BLOCKED` —— 实验未执行，无任何性能数值**
- 结构化状态记录：[`04-real-model-evaluation.json`](04-real-model-evaluation.json)
  （`not_an_experiment_result=true`，`results=[]`）

> **本报告不含任何模型效果数值**。在真实人工 Gold 到位前，任何"准确率 / NDCG / 提升"
> 都只能来自合成代理标签或英文代理标签，均**不得**写入本报告。

---

## 一、模型矩阵（复用既有实现，禁止重造算法）

| 编号 | 模型 | 实现位置 | 需训练标签 | 当前状态 |
|---|---|---|---|---|
| E00 | 规则 Baseline（`required_skills` × 简历技能 Jaccard） | `independent_eval/baselines.py` | 否 | NOT_RUN |
| E01 | TF-IDF + Cosine（字符 + 词 n-gram，评估集内拟合 IDF） | `independent_eval/baselines.py` | 否 | NOT_RUN |
| E02 | BM25 | `models/retrieval.py`（倒排索引实现） | 否 | NOT_RUN |
| E03 | BGE Embedding 余弦 | `models/text_encoder.py` | 否 | NOT_RUN |
| E04 | Embedding + 结构化特征融合 | `models/fusion.py`（FeatureFusion） | 否 | NOT_RUN |
| E05 | BM25/TF-IDF + Cross-Encoder 精排 | `models/reranker.py` | 否 | NOT_RUN |
| E06 | 完整融合推荐策略 | `service/research_strategy.py::RESEARCH_STRATEGY_SPECS`（4 种 `zh_research_*_v1`） | 否 | NOT_RUN |
| E07 | 有条件监督微调 | — | **是** | **BLOCKED**（无独立合规训练标签） |

历史 Ridge / GBM / MLP / RankNet 的训练标签为英文代理标签、技能词表为英文，
按协议第八节登记为 `applicable=false`（不可作为中文真实适配结论），
**不进入**本次主对比矩阵。

### 适用性登记（协议第八节）

| 方法 | 无真实 Gold 时可否用于真实中文 JD 评估 |
|---|---|
| 关键词/技能重合 Baseline | 是 |
| TF-IDF Cosine | 是 |
| Embedding Cosine | 是（权重在位时） |
| Ridge / GBDT / MLP / RankNet | **有条件**（仅参考，不得作中文结论） |

不允许为了让某个模型参加对比而制造不可获得的线上输入；特征无法从真实 pair
原始字段重建的模型登记 `applicable=false` 并显式报错。

---

## 二、开发集选型指标（`dev_validation`）

| 类别 | 指标 | 角色 |
|---|---|---|
| **主指标** | **NDCG@10** | 唯一胜负判据 |
| 次指标 | NDCG@5、Recall@10、MRR、Precision@5 | 解释性，不决定胜负 |
| 稳定性 | 查询级稳定性（组级方差 / Bootstrap CI 宽度） | 选型 tie-breaker |
| 运营 | 推理延迟 p50 / p95 | 选型 tie-breaker |
| 资源 | 峰值内存 / 显存 | 参考 |
| 可解释性 | 解释覆盖率（能否给出可核验的匹配依据） | 参考 |

**当前全部指标状态：`not_computable`**，原因：`无真实 Gold 查询组（0 组）`。

---

## 三、统计分析口径（预注册，见 05-statistical-analysis.md）

- 重采样单位 = **查询组（`resume_id`）**，绝不把同一简历的多个 pair 当独立样本；
- 同一次 Bootstrap 中所有模型使用**完全相同**的重采样组；
- `n_boot = 1000`，种子 `20261205`，95% 置信区间；
- 有效查询组 < 20 → `statistical_stability="unstable"`，禁止声明显著提升；
- 若复杂模型低于 BM25，**必须保留结果并分析原因**，不得因为模型复杂就宣布它更好。

---

## 四、模型锁定与 blind_test 顺序（不可颠倒）

```text
dev_validation 评测全部模型
        ↓
按预注册选型规则选出 selected_model_id（06-model-selection.md）
        ↓
锁定：selected_model_id / model_version / scoring_config_version /
      feature_version / data_version / hyperparameters / selection_reason
        ↓
（此时才允许）一次性 blind_test 独立评价
        ↓
报告 05 统计分析 → 最终结论
```

**在锁定完成前读取 blind_test 指标属于违规**，`scripts/phase7/verify_preregistration.py`
的 `find_premature_blind_outputs()` 会在 CI 中拦截提前产出的盲测结果文件。

---

## 五、当前结论

| 项 | 结论 |
|---|---|
| 是否能判断哪个模型更好 | **不能**（无真实 Gold） |
| 是否存在可重复的提升 | **无法评估** |
| 是否达到预注册验收标准 | **未达到**（G1–G4 全部 BLOCKED） |
| 能否作为已验证研究模型 | **不能**（全部策略仍为 `research_only_zh` / `research_only_proxy_labels`） |

**如实记录**：即使未来 Gold 到位，如果模型实际效果不满足预注册标准，
必须如实记录为"未达标"，**不得**自动升级为通过，**不得**通过删除低质量样本提高指标。
