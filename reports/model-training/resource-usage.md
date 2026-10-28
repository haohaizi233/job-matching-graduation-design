# 第四阶段 4.1 · 人岗匹配模型训练报告

- 生成时间：2026-10-28 21:05:09
- 数据版本：`dv-0ce28fa6b560`；协议：candidate_cold / job_cold / double_cold
- 排序查询单位：`candidate_id`（为一个候选人对其候选岗位排序）
- 模型选择指标：`ndcg_at_5_ordinal`（只看 validation）

## 评估语义前提（任何指标都必须与本节一起引用）

1. label_strength / candidate_rank / final_score 全部由原评分系统公式派生，本节指标只能衡量预测结果与原系统代理偏好的一致程度，不代表真实录用概率、招聘成功率或用户满意度。
2. Embedding Cosine 与代理标签生成机制直接耦合（semantic_score = 0.5*cosine+0.5），其高 NDCG 不构成独立语义匹配有效性证明。
3. matches.csv 无真实负例，评估只在观测组合内部做组内排序。
4. test 已在第三阶段用于零训练基线比较，本阶段只做方案锁定后的确认评估，不用于调参。
5. RankNet 学习的是原评分系统的代理排序偏好，不是用户真实偏好。


## 训练与推理资源占用


| 模型 | 协议 | 训练耗时(s) | 参数量 | 特征数 | 产物体积(KB) | 设备 | 推理单对耗时(s) |
|---|---|---:|---:|---:|---:|---|---:|
| gradient_boosting | candidate_cold | 3.81 | 3100 | 49 | 527.8 | cpu | 0.00000602 |
| gradient_boosting | double_cold | 2.21 | 3100 | 49 | 419.8 | cpu | 0.00000647 |
| gradient_boosting | job_cold | 10.57 | 3100 | 49 | 529.4 | cpu | 0.00001193 |
| mlp | candidate_cold | 57.14 | 5441 | 49 | 252.3 | cuda | 0.00000034 |
| mlp | double_cold | 15.14 | 5441 | 49 | 170.7 | cuda | 0.00000094 |
| mlp | job_cold | 177.22 | 5441 | 49 | 258.4 | cuda | 0.00000053 |
| ranknet | candidate_cold | 86.54 | 5441 | 49 | 260.2 | cuda | 0.00000037 |
| ranknet | double_cold | 28.17 | 5441 | 49 | 174.8 | cuda | 0.00000096 |
| ranknet | job_cold | 98.92 | 5441 | 49 | 267.1 | cuda | 0.00000038 |
| ridge | candidate_cold | 2.61 | 50 | 49 | 127.0 | cpu | 0.00000008 |
| ridge | double_cold | 1.3 | 50 | 49 | 47.2 | cpu | 0.00000000 |
| ridge | job_cold | 9.25 | 50 | 49 | 133.0 | cpu | 0.00000009 |

说明：RTX 2050（4GB）训练 MLP / RankNet；Ridge / GradientBoosting 使用 CPU（sklearn）。模型规模按 4GB 显存约束选择轻量结构，未为占满显存而扩大网络。表中设备列为实际计算设备；部分历史 run 记录（reports/model-training/runs/*.json）中的 `device` 字段记录的是解析出的 torch 设备，对 sklearn 模型不适用。
