# 09 统计显著性分析（Phase4-3B / M5-8.3）

- 证据：`reports/phase4-3b/09-statistical-analysis.json`（由 `scripts/phase4_3b/run_ablation_stats.py` 实测生成，seed=20261031）
- **gold_status：BLOCKED — 合成代理口径，不构成正式性能结论。**

## 1. 方法与口径

| 项 | 设定 |
|---|---|
| 重采样单位 | 查询组（resume_id），与评价单位一致 |
| 方法 | 配对 bootstrap（2000 次），指标 NDCG@10 |
| 显著性水平 | 95% CI |
| 组数 | n_groups=8 |
| 对比 | Full vs 六个单组件消融（详见 08） |

纪律：不把高度相关的人岗 pair 当作独立样本（pair 级 bootstrap 禁用）；组内样本 < 3 或零方差的相关系数记为不可评估（`per_query_corr`），不填 0。

## 2. 结果摘要

| 对比 | 均值差 | 95% CI | 结论（方向性） |
|---|---|---|---|
| Full − (−CrossEncoderReranking) | −0.0881 | [−0.1417, −0.0362] | 移除精排更好（7/8 组），CI 不跨 0 |
| Full − (−SemanticEmbedding) | −0.0167 | [−0.0336, −0.0026] | 移除语义轻微更好（3/8 vs 2/8，3 平） |
| Full − (−EducationConstraints) | −0.0037 | [−0.0168, +0.0084] | CI 跨 0，方向不稳定 |
| Full − (−SkillFeatures / −Experience / −Intent) | 0.000 | [0, 0] | 8/8 组完全打平，组件在该夹具上未起作用 |

## 3. 稳定性与限制

1. **统计功效极低**：n_groups=8，CI 覆盖宽；上述方向性差异不得写成「显著提升/下降」。
2. 多随机种子实验：**NOT_RUN**。原因：当前为确定性合成夹具（8 查询组），检索/规则基线无可训练参数、本身无随机性；多种子设计需在真实 Gold 与监督训练数据（E07）到位后执行。
3. 查询级 Spearman：组内样本不足或零方差的组记 `queries_not_evaluable`，实测数据中此类组已单独计数（见 06 JSON）。
4. Bootstrap 的 CI 建立在代理标签之上；标签噪声与循环性（difficulty_tier 构造信号）无法用统计手段消除。

## 4. 真实 Gold 到位后的统计计划（预登记，防事后挑选）

- 主指标：NDCG@10（graded 人工标签），次指标 NDCG@5 / Recall@5,10 / MRR@5 / Pairwise Accuracy。
- 重采样单位：查询组（resume_id）；组数 <30 时只报点估计 + CI，不做显著性宣称。
- 多随机种子：3–5 seeds（微调/训练类实验），报告 mean±std。
- 效应量：配对均值差 + CI，同时报告组胜负计数。
