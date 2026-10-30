# 08 消融实验（Phase4-3B / M5-8.4）

- 证据：`reports/phase4-3b/08-ablation-study.json`、`reports/model-research/runs/phase4-3b-ablation-stats-20261031-042227.json`
- run_id：`phase4-3b-ablation-stats-20261031-042227`；git_commit `cb1f481`；seed 20261031
- 协议：只移除单个组件，其余条件（数据 / 切分 / 召回 Top-K / 权重归一）保持一致。
- **gold_status：BLOCKED — 合成代理口径，不构成正式性能结论。**

## 1. 消融矩阵（Task A / Task B，ndcg@5，mean）

| 配置 | A ndcg@5 | ΔA vs Full | B ndcg@5 | ΔB vs Full | 状态 |
|---|---|---|---|---|---|
| Full（BGE+规则+约束+精排） | 0.756 | — | 0.489 | — | RUN |
| − SemanticEmbedding | 0.783 | +0.026 | 0.505 | +0.015 | RUN |
| − SkillFeatures | 0.756 | 0.000 | 0.485 | −0.005 | RUN |
| − EducationConstraints | 0.765 | +0.009 | 0.506 | +0.017 | RUN |
| − ExperienceConstraints | 0.756 | 0.000 | 0.489 | 0.000 | RUN |
| − IntentFeatures | 0.756 | 0.000 | 0.489 | 0.000 | RUN |
| − CrossEncoderReranking | 0.898 | **+0.142** | 0.498 | +0.009 | RUN |

## 2. 配对差异分析（NDCG@10，重采样单位 = 查询组 resume_id，2000 次 bootstrap）

| 对比（Full − 消融） | 均值差 | 95% CI | 组胜负 (Full好/消融好/平) |
|---|---|---|---|
| vs −SemanticEmbedding | −0.0167 | [−0.0336, −0.0026] | 2 / 3 / 3 |
| vs −SkillFeatures | 0.000 | [0, 0] | 0 / 0 / 8 |
| vs −EducationConstraints | −0.0037 | [−0.0168, +0.0084] | 2 / 3 / 3 |
| vs −ExperienceConstraints | 0.000 | [0, 0] | 0 / 0 / 8 |
| vs −IntentFeatures | 0.000 | [0, 0] | 0 / 0 / 8 |
| vs −CrossEncoderReranking | **−0.0881** | **[−0.1417, −0.0362]** | 1 / 7 / 0 |

## 3. 事实性结论

1. 移除 Cross-Encoder 精排在本口径下**显著方向一致地更好**（7/8 组），是唯一 CI 不跨 0 的对比。
2. SkillFeatures / ExperienceConstraints / IntentFeatures 消融后指标完全不变（8/8 组打平）→ 在该合成夹具上这些组件**未起作用**（夹具规模小、字段区分度低），不是「证明无用」。
3. SemanticEmbedding、EducationConstraints 轻微负贡献（CI 跨 0 或贴近 0），方向不稳定。
4. 统计功效警告（写入 JSON）：n_groups=8，CI 仅方向性参考，**不构成显著性结论**；多随机种子实验 NOT_RUN（确定性夹具 + 无可训练参数，需真实 Gold 与监督数据后执行）。

## 4. 对架构研究的含义（分析，非结论）

- 本阶段证据支持「先做扎实的关键词/规则基线，再叠加语义与精排」的研究路径；
- 精排与语义组件的价值判定**必须**在真实人工 Gold 上重做（H2 解除为前置）；
- 若真实 Gold 上复杂模型仍不敌简单基线，论文按事实报告并分析原因（代理标签构造信号、截断、数据规模）。
