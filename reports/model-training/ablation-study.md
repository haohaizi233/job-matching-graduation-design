# 第四阶段 4.1 · 人岗匹配模型训练报告

- 生成时间：2026-10-28 21:02:18
- 数据版本：`dv-0ce28fa6b560`；协议：candidate_cold / job_cold / double_cold
- 排序查询单位：`candidate_id`（为一个候选人对其候选岗位排序）
- 模型选择指标：`ndcg_at_5_ordinal`（只看 validation）

## 评估语义前提（任何指标都必须与本节一起引用）

1. label_strength / candidate_rank / final_score 全部由原评分系统公式派生，本节指标只能衡量预测结果与原系统代理偏好的一致程度，不代表真实录用概率、招聘成功率或用户满意度。
2. Embedding Cosine 与代理标签生成机制直接耦合（semantic_score = 0.5*cosine+0.5），其高 NDCG 不构成独立语义匹配有效性证明。
3. matches.csv 无真实负例，评估只在观测组合内部做组内排序。
4. test 已在第三阶段用于零训练基线比较，本阶段只做方案锁定后的确认评估，不用于调参。
5. RankNet 学习的是原评分系统的代理排序偏好，不是用户真实偏好。


## 特征组消融（整体移除一组高度关联的特征，避免只删一列留下等价信息）


| 消融 | 模型 | 协议 | 移除组 | 特征数 | val NDCG@5(ordinal) | test NDCG@5(ordinal) | test Pairwise Acc |
|---|---|---|---|---:|---:|---:|---:|
| ablation-category | ranknet | candidate_cold | category | 35 | 0.940626 | 0.944520 | 0.665644 |
| ablation-category | ridge | candidate_cold | category | 35 | 0.913187 | 0.916938 | 0.620270 |
| ablation-position | ranknet | candidate_cold | position | 19 | 0.935298 | 0.932346 | 0.577879 |
| ablation-position | ridge | candidate_cold | position | 19 | 0.904357 | 0.904848 | 0.545358 |
| ablation-skill | ranknet | candidate_cold | skill | 45 | 0.978226 | 0.977719 | 0.609605 |
| ablation-skill | ridge | candidate_cold | skill | 45 | 0.972191 | 0.974629 | 0.598357 |

说明：skill/position/category 组的成员见 `configs/training/common.yaml` （skill=技能重合 4 列；position=职位名称词元重合 + 目标职位 one-hot；category=类别一致性 + 双侧类别 one-hot）。experience 组只有 years_experience 一列，移除后无模型可用特征时不单独消融。
