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


## 一、实验总览


| 模型 | 协议 | 参数量 | 特征数 | 训练耗时(s) | 最优验证指标 | test NDCG@5(score) | test NDCG@5(ordinal) | test Pairwise Acc |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| gradient_boosting | candidate_cold | 3100 | 49 | 3.81 | 0.951459 | 0.989550 | 0.955922 | 0.700872 |
| gradient_boosting | double_cold | 3100 | 49 | 2.21 | 0.979091 | 0.996620 | 0.977758 | 0.619072 |
| gradient_boosting | job_cold | 3100 | 49 | 10.57 | 0.988132 | 0.997347 | 0.988407 | 0.694691 |
| mlp | candidate_cold | 5441 | 49 | 57.14 | 0.937207 | 0.986162 | 0.940522 | 0.665079 |
| mlp | double_cold | 5441 | 49 | 15.14 | 0.975534 | 0.996150 | 0.976617 | 0.601089 |
| mlp | job_cold | 5441 | 49 | 177.22 | 0.989075 | 0.997258 | 0.987247 | 0.691453 |
| ranknet | candidate_cold | 5441 | 49 | 86.54 | 0.953234 | 0.988916 | 0.956469 | 0.692953 |
| ranknet | double_cold | 5441 | 49 | 28.17 | 0.978166 | 0.996486 | 0.979581 | 0.627845 |
| ranknet | job_cold | 5441 | 49 | 98.92 | 0.989273 | 0.997036 | 0.987241 | 0.690486 |
| ridge | candidate_cold | 50 | 49 | 2.61 | 0.933519 | 0.985462 | 0.938592 | 0.657655 |
| ridge | double_cold | 50 | 49 | 1.3 | 0.974577 | 0.996655 | 0.978044 | 0.618138 |
| ridge | job_cold | 50 | 49 | 9.25 | 0.988548 | 0.997401 | 0.987619 | 0.699834 |

## 二、结论要点


- 与第三阶段零训练 Baseline 相比，监督模型在 candidate_cold/test 上最优为 **ranknet**（ordinal NDCG@5 = 0.956469），Position Token Overlap 基线为 0.957500，绝对差 -0.001031，95% CI [-0.006389, 0.004426]，不显著。
- 回归模型（Ridge / GB）与成对排序模型（RankNet）的差异见 `baseline-comparison.md` 与 `ranking-evaluation.md`。
- 全部结论只描述「与原系统代理偏好的一致程度」，不代表真实就业推荐效果。
