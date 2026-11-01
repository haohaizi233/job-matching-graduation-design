# 第四阶段 4.1 · 人岗匹配模型训练报告

- 生成时间：2026-11-01 18:30:28
- 数据版本：`dv-0ce28fa6b560`；协议：candidate_cold / job_cold / double_cold
- 排序查询单位：`candidate_id`（为一个候选人对其候选岗位排序）
- 模型选择指标：`ndcg_at_5_ordinal`（只看 validation）

## 评估语义前提（任何指标都必须与本节一起引用）

1. label_strength / candidate_rank / final_score 全部由原评分系统公式派生，本节指标只能衡量预测结果与原系统代理偏好的一致程度，不代表真实录用概率、招聘成功率或用户满意度。
2. Embedding Cosine 与代理标签生成机制直接耦合（semantic_score = 0.5*cosine+0.5），其高 NDCG 不构成独立语义匹配有效性证明。
3. matches.csv 无真实负例，评估只在观测组合内部做组内排序。
4. test 已在第三阶段用于零训练基线比较，本阶段只做方案锁定后的确认评估，不用于调参。
5. RankNet 学习的是原评分系统的代理排序偏好，不是用户真实偏好。


## 一、实验总览


| 模型 | 协议 | 参数量 | 特征数 | 训练耗时(s) | 最优验证指标 | test NDCG@5(score) | test NDCG@5(ordinal) | test Pairwise Acc |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| gradient_boosting | candidate_cold | 3100 | 49 | 6.19 | 0.951459 | 0.989550 | 0.955922 | 0.700872 |
| gradient_boosting | double_cold | 3100 | 49 | 4.83 | 0.979091 | 0.996620 | 0.977758 | 0.619072 |
| gradient_boosting | job_cold | 3100 | 49 | 10.98 | 0.988132 | 0.997347 | 0.988407 | 0.694691 |
| mlp | candidate_cold | 5441 | 49 | 34.25 | 0.937135 | 0.986171 | 0.940632 | 0.664849 |
| mlp | double_cold | 5441 | 49 | 13.7 | 0.975648 | 0.996591 | 0.978496 | 0.616559 |
| mlp | job_cold | 5441 | 49 | 128.49 | 0.989047 | 0.997241 | 0.987217 | 0.691233 |
| ranknet | candidate_cold | 5441 | 49 | 39.22 | 0.952779 | 0.988496 | 0.955752 | 0.689253 |
| ranknet | double_cold | 5441 | 49 | 14.61 | 0.977806 | 0.996676 | 0.980261 | 0.627911 |
| ranknet | job_cold | 5441 | 49 | 49.98 | 0.989179 | 0.997073 | 0.987535 | 0.691461 |
| ridge | candidate_cold | 50 | 49 | 1.72 | 0.933519 | 0.985467 | 0.938592 | 0.657666 |
| ridge | double_cold | 50 | 49 | 0.94 | 0.974577 | 0.996655 | 0.978044 | 0.618138 |
| ridge | job_cold | 50 | 49 | 6.91 | 0.988548 | 0.997401 | 0.987619 | 0.699834 |

## 二、结论要点


- 与第三阶段零训练 Baseline 相比，监督模型在 candidate_cold/test 上最优为 **gradient_boosting**（ordinal NDCG@5 = 0.955922），Position Token Overlap 基线为 0.957500，绝对差 -0.001578，95% CI [-0.007003, 0.003478]，不显著。
- 回归模型（Ridge / GB）与成对排序模型（RankNet）的差异见 `baseline-comparison.md` 与 `ranking-evaluation.md`。
- 全部结论只描述「与原系统代理偏好的一致程度」，不代表真实就业推荐效果。
