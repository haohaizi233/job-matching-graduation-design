# 05 数据集协议与泄漏审计（Phase4-3B / M4-7.2）

- 证据：`data/splits/matching/*/manifest.json`、`data/processed/matching/feature_schema.json`、`reports/phase4-3b/split-text-overlap.json`（测试实测生成）、`tests/phase4_3b/test_p2_split_leakage.py`

## 1. 切分协议（沿用既有 phase3-v1，不重写历史基线）

| 协议 | group_key | train | validation | test | excluded（保留） |
|---|---|---|---|---|---|
| candidate_cold | candidate_id | 98,029 | 12,270 | 12,261 | 0 |
| job_cold | job_id | 97,887 | 12,251 | 12,422 | 0 |
| double_cold | candidate_id + job_id | 68,932 | 2,369 | 2,225 | 49,034 |

seed=20261028，比例 0.8/0.1/0.1；manifest 逐文件登记 SHA-256（本轮复核全部一致）。

## 2. 任务书 7.2 检查点逐项结论

| 检查点 | 方法 | 结果 |
|---|---|---|
| resume_id 重叠 | candidate_id 集合交集 | 三协议按各自 group_key 互斥，交集=0 |
| job_id 重叠 | job_id 集合交集 | job_cold/double_cold 交集=0；candidate_cold **允许** job 重叠（train&test=944，协议设计如此，已在 manifest 登记） |
| 文本哈希重叠 | pair 级（画像+岗位文本 SHA-256） | double_cold 跨子集交集=**0**（严格通过） |
| 近似重复 | 实体级画像文本哈希 | double_cold train/test：候选 8 个、岗位 2 个重复哈希（<2% 测试实体）→ **如实登记为数据风险**，新 Gold 必须 `quarantine_near_duplicates` 隔离 |
| 特征标准化泄漏 | IL-1/IL-2/IL-6 规则登记 + 测试守护 | 规则登记于 feature_schema.json，测试断言存在且要求 train-only fit |
| 负样本采样泄漏 | 负例由观察配对外构造，禁止用 final_score 分位数构造难负例（IL-3） | 规则登记；matching 训练管线无独立负采样器（pairwise 模型用组内序），无额外泄漏面 |
| 标注信息泄漏 | 目标列物理分离 + 黑名单扫描 | features_pairs.csv 不含 label_strength/final_score/candidate_rank 等；policy.check_feature_columns 通过 |
| 训练时使用测试集决策 | 切分 manifest + 训练脚本口径 | 历史训练以 validation 做选择（selection_metric 登记于 run manifest）；未发现 test 参与决策 |

## 3. 特征白名单/黑名单（IL 规则，摘自 feature_schema.json）

- 禁止列：`semantic_score / skill_score / position_score / category_score / experience_score / education_score / raw_score / final_score / candidate_rank / candidate_rank_pct` 及 ID 类列。
- IL-1 标准化统计只在 train 上 fit；IL-2 TF-IDF/词表只在 train 上 fit；IL-3 禁止用 final_score 分位数构造分箱/难负例/样本权重；IL-4 禁止用 candidate_rank 做目标编码；IL-5 禁止把 label_strength 编码进输入列；IL-6 预计算 embedding 的归一化统计不得用全量数据重复拟合。

## 4. 评价口径纪律

- 查询组 = 一份简历（candidate_id），组内候选 = 该简历的岗位配对。
- 相关性标签必须显式给出来源；组内候选不足 K 按实际组大小截断；tie-breaking 固定为输入顺序稳定排序。
- 只有正例/全零相关/组过小的组单独计数（`queries_skipped`），不强行输出误导性指标（P8 测试守护）。

## 5. 遗留风险（如实登记）

1. 实体级近似重复（上表第 4 行）：phase3-v1 切分冻结不改；新 Gold 构建时按相似度 ≥0.90 隔离。
2. matching 标签为 final_score 派生代理标签，语义类特征与标签存在构造耦合；报告中一律以「代理偏好一致度」表述。
3. 合成夹具 difficulty_tier 与技能类特征共享构造信号（循环性），见 06 报告 circularity_warning。
