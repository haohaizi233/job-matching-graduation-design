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
| **mlp** | 0.985695 | 0.990457 | 0.937135 | 0.953435 | 0.656505 | 本阶段训练 |
| **ranknet** | 0.988493 | 0.992037 | 0.952779 | 0.962441 | 0.682722 | 本阶段训练 |

### 协议 candidate_cold / test

| 方法 | NDCG@5(score) | NDCG@10(score) | NDCG@5(ordinal) | NDCG@10(ordinal) | Pairwise Acc | 来源 |
|---|---:|---:|---:|---:|---:|---|
| random_ranking | 0.957817 | 0.972433 | 0.850377 | 0.893116 | 0.504607 | 第三阶段报告 repeated_stats 均值 |
| embedding_cosine | 0.967769 | 0.978857 | 0.885507 | 0.917631 | 0.584319 | 第三阶段报告 |
| skill_jaccard | 0.973981 | 0.983967 | 0.905417 | 0.934932 | 0.548965 | 第三阶段报告 |
| position_token_overlap | 0.989070 | 0.993119 | 0.957500 | 0.970166 | 0.567734 | 第三阶段报告 |
| **ridge** | 0.985467 | 0.990364 | 0.938592 | 0.953388 | 0.657666 | 本阶段训练 |
| **gradient_boosting** | 0.989550 | 0.992824 | 0.955922 | 0.965210 | 0.700872 | 本阶段训练 |
| **mlp** | 0.986171 | 0.990745 | 0.940632 | 0.954636 | 0.664849 | 本阶段训练 |
| **ranknet** | 0.988496 | 0.992166 | 0.955752 | 0.963915 | 0.689253 | 本阶段训练 |

## 高分基线（Position Token Overlap）问题分析


- **gradient_boosting**：ordinal NDCG@5 = 0.955922，相对 Position Token Overlap 差 -0.001578；95% CI [-0.007003, 0.003478]，不显著；单对推理 0.00000943s。
- **mlp**：ordinal NDCG@5 = 0.940632，相对 Position Token Overlap 差 -0.016868；95% CI [-0.02249, -0.011614]，显著；单对推理 0.00000014s。
- **ranknet**：ordinal NDCG@5 = 0.955752，相对 Position Token Overlap 差 -0.001748；95% CI [-0.007037, 0.003547]，不显著；单对推理 0.00000015s。
- **ridge**：ordinal NDCG@5 = 0.938592，相对 Position Token Overlap 差 -0.018908；95% CI [-0.024422, -0.013308]，显著；单对推理 0.00000003s。

判定口径：① 绝对提升是否 > Bootstrap 置信区间下界；② 是否以明显更慢的推理与更复杂的模型为代价；③ 若无显著提升，应解释为「模型只学到代理评分系统中已被 position_token_overlap 等简单特征覆盖的部分」，而不是宣称模型无效或有效。


## 相对零训练基线的查询级 Bootstrap 差值区间（test）


| 协议 | 模型 | 对比基线 | 指标 | 均值差 | 95% CI | 显著 |
|---|---|---|---|---:|---|---|
| candidate_cold | ridge | random_ranking | ndcg@5_score | 0.026123 | [0.024237, 0.028062] | 是 |
| candidate_cold | ridge | random_ranking | ndcg@5_ordinal | 0.083139 | [0.074982, 0.091676] | 是 |
| candidate_cold | ridge | random_ranking | pairwise_accuracy | 0.15306 | [0.13833, 0.167763] | 是 |
| candidate_cold | ridge | skill_jaccard | ndcg@5_score | 0.011486 | [0.010058, 0.012924] | 是 |
| candidate_cold | ridge | skill_jaccard | ndcg@5_ordinal | 0.033175 | [0.02746, 0.039217] | 是 |
| candidate_cold | ridge | skill_jaccard | pairwise_accuracy | 0.108701 | [0.098169, 0.119259] | 是 |
| candidate_cold | ridge | position_token_overlap | ndcg@5_score | -0.003603 | [-0.004699, -0.002375] | 是 |
| candidate_cold | ridge | position_token_overlap | ndcg@5_ordinal | -0.018908 | [-0.024422, -0.013308] | 是 |
| candidate_cold | ridge | position_token_overlap | pairwise_accuracy | 0.089932 | [0.079294, 0.100314] | 是 |
| candidate_cold | gradient_boosting | random_ranking | ndcg@5_score | 0.030206 | [0.028352, 0.032054] | 是 |
| candidate_cold | gradient_boosting | random_ranking | ndcg@5_ordinal | 0.100468 | [0.093052, 0.108073] | 是 |
| candidate_cold | gradient_boosting | random_ranking | pairwise_accuracy | 0.196265 | [0.182249, 0.210885] | 是 |
| candidate_cold | gradient_boosting | skill_jaccard | ndcg@5_score | 0.01557 | [0.014164, 0.016983] | 是 |
| candidate_cold | gradient_boosting | skill_jaccard | ndcg@5_ordinal | 0.050504 | [0.045094, 0.056143] | 是 |
| candidate_cold | gradient_boosting | skill_jaccard | pairwise_accuracy | 0.151907 | [0.140378, 0.162832] | 是 |
| candidate_cold | gradient_boosting | position_token_overlap | ndcg@5_score | 0.00048 | [-0.000586, 0.001589] | 否 |
| candidate_cold | gradient_boosting | position_token_overlap | ndcg@5_ordinal | -0.001579 | [-0.007003, 0.003478] | 否 |
| candidate_cold | gradient_boosting | position_token_overlap | pairwise_accuracy | 0.133138 | [0.122551, 0.142951] | 是 |
| candidate_cold | mlp | random_ranking | ndcg@5_score | 0.026827 | [0.025, 0.028779] | 是 |
| candidate_cold | mlp | random_ranking | ndcg@5_ordinal | 0.085179 | [0.077081, 0.093185] | 是 |
| candidate_cold | mlp | random_ranking | pairwise_accuracy | 0.160242 | [0.145636, 0.175764] | 是 |
| candidate_cold | mlp | skill_jaccard | ndcg@5_score | 0.01219 | [0.010784, 0.013667] | 是 |
| candidate_cold | mlp | skill_jaccard | ndcg@5_ordinal | 0.035215 | [0.029432, 0.041036] | 是 |
| candidate_cold | mlp | skill_jaccard | pairwise_accuracy | 0.115884 | [0.10557, 0.126292] | 是 |
| candidate_cold | mlp | position_token_overlap | ndcg@5_score | -0.002899 | [-0.003945, -0.001665] | 是 |
| candidate_cold | mlp | position_token_overlap | ndcg@5_ordinal | -0.016868 | [-0.02249, -0.011614] | 是 |
| candidate_cold | mlp | position_token_overlap | pairwise_accuracy | 0.097115 | [0.087074, 0.106882] | 是 |
| candidate_cold | ranknet | random_ranking | ndcg@5_score | 0.029152 | [0.027309, 0.031038] | 是 |
| candidate_cold | ranknet | random_ranking | ndcg@5_ordinal | 0.100299 | [0.092926, 0.108406] | 是 |
| candidate_cold | ranknet | random_ranking | pairwise_accuracy | 0.184646 | [0.17109, 0.199407] | 是 |
| candidate_cold | ranknet | skill_jaccard | ndcg@5_score | 0.014516 | [0.013063, 0.015925] | 是 |
| candidate_cold | ranknet | skill_jaccard | ndcg@5_ordinal | 0.050335 | [0.044752, 0.056058] | 是 |
| candidate_cold | ranknet | skill_jaccard | pairwise_accuracy | 0.140288 | [0.128661, 0.152948] | 是 |
| candidate_cold | ranknet | position_token_overlap | ndcg@5_score | -0.000574 | [-0.001679, 0.00059] | 否 |
| candidate_cold | ranknet | position_token_overlap | ndcg@5_ordinal | -0.001748 | [-0.007037, 0.003547] | 否 |
| candidate_cold | ranknet | position_token_overlap | pairwise_accuracy | 0.121519 | [0.110742, 0.132295] | 是 |
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
| job_cold | mlp | random_ranking | ndcg@5_score | 0.006632 | [0.006244, 0.007073] | 是 |
| job_cold | mlp | random_ranking | ndcg@5_ordinal | 0.022368 | [0.020431, 0.024427] | 是 |
| job_cold | mlp | random_ranking | pairwise_accuracy | 0.190774 | [0.173247, 0.208128] | 是 |
| job_cold | mlp | skill_jaccard | ndcg@5_score | 0.00196 | [0.001694, 0.0022] | 是 |
| job_cold | mlp | skill_jaccard | ndcg@5_ordinal | 0.009743 | [0.008439, 0.011113] | 是 |
| job_cold | mlp | skill_jaccard | pairwise_accuracy | 0.149838 | [0.137723, 0.161478] | 是 |
| job_cold | mlp | position_token_overlap | ndcg@5_score | -0.001333 | [-0.001557, -0.001115] | 是 |
| job_cold | mlp | position_token_overlap | ndcg@5_ordinal | -0.007824 | [-0.009162, -0.006593] | 是 |
| job_cold | mlp | position_token_overlap | pairwise_accuracy | 0.089566 | [0.078933, 0.100938] | 是 |
| job_cold | ranknet | random_ranking | ndcg@5_score | 0.006464 | [0.006071, 0.006884] | 是 |
| job_cold | ranknet | random_ranking | ndcg@5_ordinal | 0.022687 | [0.020675, 0.024703] | 是 |
| job_cold | ranknet | random_ranking | pairwise_accuracy | 0.191002 | [0.173244, 0.208508] | 是 |
| job_cold | ranknet | skill_jaccard | ndcg@5_score | 0.001793 | [0.001535, 0.002052] | 是 |
| job_cold | ranknet | skill_jaccard | ndcg@5_ordinal | 0.010061 | [0.008645, 0.011481] | 是 |
| job_cold | ranknet | skill_jaccard | pairwise_accuracy | 0.150067 | [0.136877, 0.162619] | 是 |
| job_cold | ranknet | position_token_overlap | ndcg@5_score | -0.001501 | [-0.001733, -0.001259] | 是 |
| job_cold | ranknet | position_token_overlap | ndcg@5_ordinal | -0.007506 | [-0.008838, -0.006203] | 是 |
| job_cold | ranknet | position_token_overlap | pairwise_accuracy | 0.089794 | [0.078298, 0.100627] | 是 |
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
| double_cold | mlp | random_ranking | ndcg@5_score | 0.005373 | [0.004451, 0.006386] | 是 |
| double_cold | mlp | random_ranking | ndcg@5_ordinal | 0.017595 | [0.012721, 0.022804] | 是 |
| double_cold | mlp | random_ranking | pairwise_accuracy | 0.118156 | [0.083079, 0.156511] | 是 |
| double_cold | mlp | skill_jaccard | ndcg@5_score | 0.001591 | [0.001083, 0.002155] | 是 |
| double_cold | mlp | skill_jaccard | ndcg@5_ordinal | 0.005661 | [0.002837, 0.008604] | 是 |
| double_cold | mlp | skill_jaccard | pairwise_accuracy | 0.083353 | [0.061027, 0.106595] | 是 |
| double_cold | mlp | position_token_overlap | ndcg@5_score | -0.001731 | [-0.002227, -0.001202] | 是 |
| double_cold | mlp | position_token_overlap | ndcg@5_ordinal | -0.014125 | [-0.017553, -0.01091] | 是 |
| double_cold | mlp | position_token_overlap | pairwise_accuracy | 0.068676 | [0.044328, 0.093538] | 是 |
| double_cold | ranknet | random_ranking | ndcg@5_score | 0.005459 | [0.004559, 0.006464] | 是 |
| double_cold | ranknet | random_ranking | ndcg@5_ordinal | 0.019361 | [0.014702, 0.024313] | 是 |
| double_cold | ranknet | random_ranking | pairwise_accuracy | 0.129509 | [0.093584, 0.168144] | 是 |
| double_cold | ranknet | skill_jaccard | ndcg@5_score | 0.001677 | [0.001188, 0.002278] | 是 |
| double_cold | ranknet | skill_jaccard | ndcg@5_ordinal | 0.007426 | [0.00462, 0.01057] | 是 |
| double_cold | ranknet | skill_jaccard | pairwise_accuracy | 0.094705 | [0.071705, 0.118645] | 是 |
| double_cold | ranknet | position_token_overlap | ndcg@5_score | -0.001645 | [-0.002189, -0.001125] | 是 |
| double_cold | ranknet | position_token_overlap | ndcg@5_ordinal | -0.012359 | [-0.015975, -0.008665] | 是 |
| double_cold | ranknet | position_token_overlap | pairwise_accuracy | 0.080029 | [0.054013, 0.104017] | 是 |