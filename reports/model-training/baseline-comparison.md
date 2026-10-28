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


## 零训练 Baseline 与监督模型对比（指标直接读取第三阶段报告）


基线一致性校验：本地复算每查询 NDCG 与 `reports/baselines/baseline-results.json` 汇总值的最大绝对差——确定性基线（embedding_cosine / skill_jaccard / position_token_overlap）**0.000000496**（< 1e-6 视为口径一致）；random_ranking **0.005076568**，差异来源为第三阶段报告记录多次随机重复的均值、本地复算使用固定单种子，属预期差异，不影响确定性方法之间的比较。


### 协议 candidate_cold / validation

| 方法 | NDCG@5(score) | NDCG@10(score) | NDCG@5(ordinal) | NDCG@10(ordinal) | Pairwise Acc | 来源 |
|---|---:|---:|---:|---:|---:|---|
| random_ranking | 0.958220 | 0.972213 | 0.853227 | 0.892775 | 0.511665 | 第三阶段报告 repeated_stats 均值 |
| embedding_cosine | 0.965956 | 0.977247 | 0.880120 | 0.911782 | 0.582940 | 第三阶段报告 |
| skill_jaccard | 0.972895 | 0.982908 | 0.900984 | 0.931896 | 0.533937 | 第三阶段报告 |
| position_token_overlap | 0.988851 | 0.992933 | 0.957734 | 0.970658 | 0.568013 | 第三阶段报告 |
| **ridge** | 0.984742 | 0.989951 | 0.933519 | 0.951504 | 0.647969 | 本阶段训练 |
| **gradient_boosting** | 0.989186 | 0.992405 | 0.951459 | 0.962028 | 0.688223 | 本阶段训练 |
| **mlp** | 0.985708 | 0.990462 | 0.937207 | 0.953482 | 0.656489 | 本阶段训练 |
| **ranknet** | 0.988734 | 0.992127 | 0.953234 | 0.962594 | 0.689755 | 本阶段训练 |

### 协议 candidate_cold / test

| 方法 | NDCG@5(score) | NDCG@10(score) | NDCG@5(ordinal) | NDCG@10(ordinal) | Pairwise Acc | 来源 |
|---|---:|---:|---:|---:|---:|---|
| random_ranking | 0.957817 | 0.972433 | 0.850377 | 0.893116 | 0.504607 | 第三阶段报告 repeated_stats 均值 |
| embedding_cosine | 0.967769 | 0.978857 | 0.885507 | 0.917631 | 0.584319 | 第三阶段报告 |
| skill_jaccard | 0.973981 | 0.983967 | 0.905417 | 0.934932 | 0.548965 | 第三阶段报告 |
| position_token_overlap | 0.989070 | 0.993119 | 0.957500 | 0.970166 | 0.567734 | 第三阶段报告 |
| **ridge** | 0.985462 | 0.990361 | 0.938592 | 0.953388 | 0.657655 | 本阶段训练 |
| **gradient_boosting** | 0.989550 | 0.992824 | 0.955922 | 0.965210 | 0.700872 | 本阶段训练 |
| **mlp** | 0.986162 | 0.990746 | 0.940522 | 0.954617 | 0.665079 | 本阶段训练 |
| **ranknet** | 0.988916 | 0.992221 | 0.956469 | 0.963777 | 0.692953 | 本阶段训练 |

## 高分基线（Position Token Overlap）问题分析


- **gradient_boosting**：ordinal NDCG@5 = 0.955922，相对 Position Token Overlap 差 -0.001578；95% CI [-0.007003, 0.003478]，不显著；单对推理 0.00000602s。
- **mlp**：ordinal NDCG@5 = 0.940522，相对 Position Token Overlap 差 -0.016978；95% CI [-0.022558, -0.011641]，显著；单对推理 0.00000034s。
- **ranknet**：ordinal NDCG@5 = 0.956469，相对 Position Token Overlap 差 -0.001031；95% CI [-0.006389, 0.004426]，不显著；单对推理 0.00000037s。
- **ridge**：ordinal NDCG@5 = 0.938592，相对 Position Token Overlap 差 -0.018908；95% CI [-0.024422, -0.013308]，显著；单对推理 0.00000008s。

判定口径：① 绝对提升是否 > Bootstrap 置信区间下界；② 是否以明显更慢的推理与更复杂的模型为代价；③ 若无显著提升，应解释为「模型只学到代理评分系统中已被 position_token_overlap 等简单特征覆盖的部分」，而不是宣称模型无效或有效。


## 相对零训练基线的查询级 Bootstrap 差值区间（test）


| 协议 | 模型 | 对比基线 | 指标 | 均值差 | 95% CI | 显著 |
|---|---|---|---|---:|---|---|
| candidate_cold | ridge | random_ranking | ndcg@5_score | 0.026118 | [0.024233, 0.028053] | 是 |
| candidate_cold | ridge | random_ranking | ndcg@5_ordinal | 0.083139 | [0.074982, 0.091676] | 是 |
| candidate_cold | ridge | random_ranking | pairwise_accuracy | 0.153048 | [0.13833, 0.16774] | 是 |
| candidate_cold | ridge | skill_jaccard | ndcg@5_score | 0.011482 | [0.010058, 0.012924] | 是 |
| candidate_cold | ridge | skill_jaccard | ndcg@5_ordinal | 0.033175 | [0.02746, 0.039217] | 是 |
| candidate_cold | ridge | skill_jaccard | pairwise_accuracy | 0.10869 | [0.098168, 0.119259] | 是 |
| candidate_cold | ridge | position_token_overlap | ndcg@5_score | -0.003608 | [-0.004707, -0.002383] | 是 |
| candidate_cold | ridge | position_token_overlap | ndcg@5_ordinal | -0.018908 | [-0.024422, -0.013308] | 是 |
| candidate_cold | ridge | position_token_overlap | pairwise_accuracy | 0.089921 | [0.079294, 0.100314] | 是 |
| candidate_cold | gradient_boosting | random_ranking | ndcg@5_score | 0.030206 | [0.028352, 0.032054] | 是 |
| candidate_cold | gradient_boosting | random_ranking | ndcg@5_ordinal | 0.100468 | [0.093052, 0.108073] | 是 |
| candidate_cold | gradient_boosting | random_ranking | pairwise_accuracy | 0.196265 | [0.182249, 0.210885] | 是 |
| candidate_cold | gradient_boosting | skill_jaccard | ndcg@5_score | 0.01557 | [0.014164, 0.016983] | 是 |
| candidate_cold | gradient_boosting | skill_jaccard | ndcg@5_ordinal | 0.050504 | [0.045094, 0.056143] | 是 |
| candidate_cold | gradient_boosting | skill_jaccard | pairwise_accuracy | 0.151907 | [0.140378, 0.162832] | 是 |
| candidate_cold | gradient_boosting | position_token_overlap | ndcg@5_score | 0.00048 | [-0.000586, 0.001589] | 否 |
| candidate_cold | gradient_boosting | position_token_overlap | ndcg@5_ordinal | -0.001579 | [-0.007003, 0.003478] | 否 |
| candidate_cold | gradient_boosting | position_token_overlap | pairwise_accuracy | 0.133138 | [0.122551, 0.142951] | 是 |
| candidate_cold | mlp | random_ranking | ndcg@5_score | 0.026818 | [0.02499, 0.028759] | 是 |
| candidate_cold | mlp | random_ranking | ndcg@5_ordinal | 0.085069 | [0.076885, 0.093115] | 是 |
| candidate_cold | mlp | random_ranking | pairwise_accuracy | 0.160472 | [0.145829, 0.176114] | 是 |
| candidate_cold | mlp | skill_jaccard | ndcg@5_score | 0.012182 | [0.010757, 0.013665] | 是 |
| candidate_cold | mlp | skill_jaccard | ndcg@5_ordinal | 0.035105 | [0.029297, 0.041023] | 是 |
| candidate_cold | mlp | skill_jaccard | pairwise_accuracy | 0.116114 | [0.105766, 0.126713] | 是 |
| candidate_cold | mlp | position_token_overlap | ndcg@5_score | -0.002908 | [-0.00395, -0.001672] | 是 |
| candidate_cold | mlp | position_token_overlap | ndcg@5_ordinal | -0.016978 | [-0.022558, -0.011641] | 是 |
| candidate_cold | mlp | position_token_overlap | pairwise_accuracy | 0.097345 | [0.087372, 0.107136] | 是 |
| candidate_cold | ranknet | random_ranking | ndcg@5_score | 0.029572 | [0.02768, 0.031475] | 是 |
| candidate_cold | ranknet | random_ranking | ndcg@5_ordinal | 0.101016 | [0.093438, 0.108939] | 是 |
| candidate_cold | ranknet | random_ranking | pairwise_accuracy | 0.188346 | [0.174462, 0.202646] | 是 |
| candidate_cold | ranknet | skill_jaccard | ndcg@5_score | 0.014935 | [0.013512, 0.016354] | 是 |
| candidate_cold | ranknet | skill_jaccard | ndcg@5_ordinal | 0.051052 | [0.045497, 0.057024] | 是 |
| candidate_cold | ranknet | skill_jaccard | pairwise_accuracy | 0.143988 | [0.132186, 0.155721] | 是 |
| candidate_cold | ranknet | position_token_overlap | ndcg@5_score | -0.000154 | [-0.001245, 0.001084] | 否 |
| candidate_cold | ranknet | position_token_overlap | ndcg@5_ordinal | -0.001031 | [-0.006389, 0.004426] | 否 |
| candidate_cold | ranknet | position_token_overlap | pairwise_accuracy | 0.125219 | [0.114925, 0.135912] | 是 |
| job_cold | ridge | random_ranking | ndcg@5_score | 0.006792 | [0.006397, 0.007224] | 是 |
| job_cold | ridge | random_ranking | ndcg@5_ordinal | 0.02277 | [0.02077, 0.024848] | 是 |
| job_cold | ridge | random_ranking | pairwise_accuracy | 0.199375 | [0.181683, 0.217749] | 是 |
| job_cold | ridge | skill_jaccard | ndcg@5_score | 0.00212 | [0.001843, 0.002373] | 是 |
| job_cold | ridge | skill_jaccard | ndcg@5_ordinal | 0.010145 | [0.008782, 0.011579] | 是 |
| job_cold | ridge | skill_jaccard | pairwise_accuracy | 0.158439 | [0.145827, 0.170927] | 是 |
| job_cold | ridge | position_token_overlap | ndcg@5_score | -0.001173 | [-0.00138, -0.000965] | 是 |
| job_cold | ridge | position_token_overlap | ndcg@5_ordinal | -0.007422 | [-0.008647, -0.00609] | 是 |
| job_cold | ridge | position_token_overlap | pairwise_accuracy | 0.098166 | [0.086837, 0.109968] | 是 |
| job_cold | gradient_boosting | random_ranking | ndcg@5_score | 0.006738 | [0.006362, 0.007147] | 是 |
| job_cold | gradient_boosting | random_ranking | ndcg@5_ordinal | 0.023559 | [0.021547, 0.025587] | 是 |
| job_cold | gradient_boosting | random_ranking | pairwise_accuracy | 0.194232 | [0.176249, 0.211906] | 是 |
| job_cold | gradient_boosting | skill_jaccard | ndcg@5_score | 0.002067 | [0.001768, 0.00233] | 是 |
| job_cold | gradient_boosting | skill_jaccard | ndcg@5_ordinal | 0.010933 | [0.009432, 0.012387] | 是 |
| job_cold | gradient_boosting | skill_jaccard | pairwise_accuracy | 0.153297 | [0.138882, 0.166543] | 是 |
| job_cold | gradient_boosting | position_token_overlap | ndcg@5_score | -0.001227 | [-0.001442, -0.001015] | 是 |
| job_cold | gradient_boosting | position_token_overlap | ndcg@5_ordinal | -0.006634 | [-0.007813, -0.005365] | 是 |
| job_cold | gradient_boosting | position_token_overlap | pairwise_accuracy | 0.093024 | [0.081482, 0.103952] | 是 |
| job_cold | mlp | random_ranking | ndcg@5_score | 0.00665 | [0.00626, 0.007086] | 是 |
| job_cold | mlp | random_ranking | ndcg@5_ordinal | 0.022398 | [0.020451, 0.024452] | 是 |
| job_cold | mlp | random_ranking | pairwise_accuracy | 0.190994 | [0.173677, 0.208506] | 是 |
| job_cold | mlp | skill_jaccard | ndcg@5_score | 0.001978 | [0.001715, 0.002221] | 是 |
| job_cold | mlp | skill_jaccard | ndcg@5_ordinal | 0.009773 | [0.008423, 0.011167] | 是 |
| job_cold | mlp | skill_jaccard | pairwise_accuracy | 0.150058 | [0.137792, 0.161583] | 是 |
| job_cold | mlp | position_token_overlap | ndcg@5_score | -0.001316 | [-0.001536, -0.0011] | 是 |
| job_cold | mlp | position_token_overlap | ndcg@5_ordinal | -0.007794 | [-0.009127, -0.006556] | 是 |
| job_cold | mlp | position_token_overlap | pairwise_accuracy | 0.089785 | [0.079162, 0.100935] | 是 |
| job_cold | ranknet | random_ranking | ndcg@5_score | 0.006427 | [0.006008, 0.006833] | 是 |
| job_cold | ranknet | random_ranking | ndcg@5_ordinal | 0.022392 | [0.020461, 0.02436] | 是 |
| job_cold | ranknet | random_ranking | pairwise_accuracy | 0.190027 | [0.171428, 0.207804] | 是 |
| job_cold | ranknet | skill_jaccard | ndcg@5_score | 0.001756 | [0.001477, 0.002017] | 是 |
| job_cold | ranknet | skill_jaccard | ndcg@5_ordinal | 0.009767 | [0.008344, 0.011162] | 是 |
| job_cold | ranknet | skill_jaccard | pairwise_accuracy | 0.149091 | [0.134801, 0.161424] | 是 |
| job_cold | ranknet | position_token_overlap | ndcg@5_score | -0.001538 | [-0.001787, -0.001282] | 是 |
| job_cold | ranknet | position_token_overlap | ndcg@5_ordinal | -0.0078 | [-0.009111, -0.006488] | 是 |
| job_cold | ranknet | position_token_overlap | pairwise_accuracy | 0.088818 | [0.077678, 0.099864] | 是 |
| double_cold | ridge | random_ranking | ndcg@5_score | 0.005437 | [0.004506, 0.006426] | 是 |
| double_cold | ridge | random_ranking | ndcg@5_ordinal | 0.017144 | [0.011968, 0.022252] | 是 |
| double_cold | ridge | random_ranking | pairwise_accuracy | 0.119736 | [0.083677, 0.157498] | 是 |
| double_cold | ridge | skill_jaccard | ndcg@5_score | 0.001655 | [0.001092, 0.002298] | 是 |
| double_cold | ridge | skill_jaccard | ndcg@5_ordinal | 0.005209 | [0.001725, 0.008492] | 是 |
| double_cold | ridge | skill_jaccard | pairwise_accuracy | 0.084932 | [0.059468, 0.111509] | 是 |
| double_cold | ridge | position_token_overlap | ndcg@5_score | -0.001666 | [-0.00222, -0.001106] | 是 |
| double_cold | ridge | position_token_overlap | ndcg@5_ordinal | -0.014576 | [-0.018359, -0.011109] | 是 |
| double_cold | ridge | position_token_overlap | pairwise_accuracy | 0.070256 | [0.046207, 0.094004] | 是 |
| double_cold | gradient_boosting | random_ranking | ndcg@5_score | 0.005402 | [0.00448, 0.006455] | 是 |
| double_cold | gradient_boosting | random_ranking | ndcg@5_ordinal | 0.016857 | [0.011765, 0.021906] | 是 |
| double_cold | gradient_boosting | random_ranking | pairwise_accuracy | 0.12067 | [0.083044, 0.158604] | 是 |
| double_cold | gradient_boosting | skill_jaccard | ndcg@5_score | 0.001621 | [0.000998, 0.002296] | 是 |
| double_cold | gradient_boosting | skill_jaccard | ndcg@5_ordinal | 0.004923 | [0.001335, 0.008689] | 是 |
| double_cold | gradient_boosting | skill_jaccard | pairwise_accuracy | 0.085866 | [0.058305, 0.113848] | 是 |
| double_cold | gradient_boosting | position_token_overlap | ndcg@5_score | -0.001701 | [-0.002342, -0.0011] | 是 |
| double_cold | gradient_boosting | position_token_overlap | ndcg@5_ordinal | -0.014862 | [-0.018556, -0.011021] | 是 |
| double_cold | gradient_boosting | position_token_overlap | pairwise_accuracy | 0.07119 | [0.04509, 0.096605] | 是 |
| double_cold | mlp | random_ranking | ndcg@5_score | 0.004932 | [0.004002, 0.005941] | 是 |
| double_cold | mlp | random_ranking | ndcg@5_ordinal | 0.015717 | [0.010831, 0.020934] | 是 |
| double_cold | mlp | random_ranking | pairwise_accuracy | 0.102687 | [0.065498, 0.142156] | 是 |
| double_cold | mlp | skill_jaccard | ndcg@5_score | 0.001151 | [0.000618, 0.001766] | 是 |
| double_cold | mlp | skill_jaccard | ndcg@5_ordinal | 0.003782 | [0.001168, 0.006697] | 是 |
| double_cold | mlp | skill_jaccard | pairwise_accuracy | 0.067884 | [0.047894, 0.091152] | 是 |
| double_cold | mlp | position_token_overlap | ndcg@5_score | -0.002171 | [-0.002833, -0.001569] | 是 |
| double_cold | mlp | position_token_overlap | ndcg@5_ordinal | -0.016003 | [-0.019678, -0.012419] | 是 |
| double_cold | mlp | position_token_overlap | pairwise_accuracy | 0.053207 | [0.027774, 0.078221] | 是 |
| double_cold | ranknet | random_ranking | ndcg@5_score | 0.005268 | [0.004318, 0.00626] | 是 |
| double_cold | ranknet | random_ranking | ndcg@5_ordinal | 0.01868 | [0.013926, 0.02378] | 是 |
| double_cold | ranknet | random_ranking | pairwise_accuracy | 0.129442 | [0.093406, 0.167175] | 是 |
| double_cold | ranknet | skill_jaccard | ndcg@5_score | 0.001487 | [0.000968, 0.002086] | 是 |
| double_cold | ranknet | skill_jaccard | ndcg@5_ordinal | 0.006746 | [0.003755, 0.009883] | 是 |
| double_cold | ranknet | skill_jaccard | pairwise_accuracy | 0.094639 | [0.070749, 0.117399] | 是 |
| double_cold | ranknet | position_token_overlap | ndcg@5_score | -0.001835 | [-0.002414, -0.001262] | 是 |
| double_cold | ranknet | position_token_overlap | ndcg@5_ordinal | -0.01304 | [-0.016707, -0.00938] | 是 |
| double_cold | ranknet | position_token_overlap | pairwise_accuracy | 0.079962 | [0.05256, 0.104061] | 是 |