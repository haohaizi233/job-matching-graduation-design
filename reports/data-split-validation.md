# 第三阶段 · 可信数据划分实测结果

- 生成时间：2026-10-28 20:15:40
- 切分索引：`data/splits/matching/`、`data/splits/education/`
- 所有随机过程使用 `configs/data_pipeline.yaml` 中登记的固定种子，重复执行结果一致。

> **标签与预处理隔离**：StandardScaler / TF-IDF / 词表 / 特征选择器等统计量只能在 Train 上 fit，Validation/Test 只能 transform。预计算 Embedding 由全量数据产生，这一点作为限制单独记录。

## 一、人岗匹配三种协议

### 协议 A：Candidate Cold-start（`candidate_cold`）

- 分组键：`candidate_id`
- 随机种子：`20261028`
- 划分比例：{'test': 0.1, 'train': 0.8, 'validation': 0.1}

| 集合 | 匹配记录 | 候选人数 | 岗位数 | 分组数 | 可排序组(≥2) | 单记录组 | 组大小中位 | 组大小最大 |
|---|---|---|---|---|---|---|---|---|
| train | 98029 | 7617 | 1163 | 7617 | 7565 | 52 | 11.0 | 122 |
| validation | 12270 | 941 | 897 | 941 | 934 | 7 | 11.0 | 62 |
| test | 12261 | 974 | 944 | 974 | 973 | 1 | 11.0 | 83 |

| 集合 | weak_positive | medium_positive | strong_positive |
|---|---|---|---|
| train | 41073 | 56322 | 634 |
| validation | 5019 | 7181 | 70 |
| test | 5058 | 7133 | 70 |

候选人集合交叉：train&test=0, train&validation=0, validation&test=0
岗位集合交叉：train&test=944, train&validation=896, validation&test=773
pair 交叉：train&test=0, train&validation=0, validation&test=0

### 协议 B：Job Cold-start（`job_cold`）

- 分组键：`job_id`
- 随机种子：`20261029`
- 划分比例：{'test': 0.1, 'train': 0.8, 'validation': 0.1}

| 集合 | 匹配记录 | 候选人数 | 岗位数 | 分组数 | 可排序组(≥2) | 单记录组 | 组大小中位 | 组大小最大 |
|---|---|---|---|---|---|---|---|---|
| train | 97887 | 9519 | 952 | 952 | 950 | 2 | 19.5 | 500 |
| validation | 12251 | 6071 | 100 | 100 | 100 | 0 | 17.5 | 500 |
| test | 12422 | 6423 | 112 | 112 | 112 | 0 | 19.5 | 500 |

| 集合 | weak_positive | medium_positive | strong_positive |
|---|---|---|---|
| train | 42460 | 54791 | 636 |
| validation | 3630 | 8557 | 64 |
| test | 5060 | 7288 | 74 |

候选人集合交叉：train&test=6414, train&validation=6063, validation&test=4676
岗位集合交叉：train&test=0, train&validation=0, validation&test=0
pair 交叉：train&test=0, train&validation=0, validation&test=0

### 协议 C：Double Cold-start（`double_cold`）

- 分组键：`['candidate_id', 'job_id']`
- 随机种子：`20261030`
- 划分比例：{'test': 0.1, 'train': 0.8, 'validation': 0.1}
- 分配策略：`eval_first_greedy` —— 阶段 1：candidate_id 按观测边数贪心分配 80/10/10（组完整、边不拆）；阶段 2：job_id 归属由 assignment_strategy 指定。两侧归属不一致的交叉边一律进 excluded，不归入任何集合。eval_first_greedy 是本阶段提出的改进策略：先用 gain/cost 贪心为验证/测试候选人补齐可排序性（每个次要集合带独立的 train 损失预算），再把其余 job 归给边数最多的集合；而 majority_edge 虽保留率最高但验证/测试集为空（见 strategy_comparison）。

| 集合 | 匹配记录 | 候选人数 | 岗位数 | 分组数 | 可排序组(≥2) | 单记录组 | 组大小中位 | 组大小最大 |
|---|---|---|---|---|---|---|---|---|
| train | 68932 | 7217 | 812 | 7217 | 6644 | 573 | 8.0 | 92 |
| validation | 2369 | 908 | 187 | 908 | 739 | 169 | 2.0 | 10 |
| test | 2225 | 920 | 165 | 920 | 717 | 203 | 2.0 | 12 |

| 集合 | weak_positive | medium_positive | strong_positive |
|---|---|---|---|
| train | 25760 | 42619 | 553 |
| validation | 1368 | 1000 | 1 |
| test | 1153 | 1070 | 2 |

候选人集合交叉：train&test=0, train&validation=0, validation&test=0
岗位集合交叉：train&test=0, train&validation=0, validation&test=0
pair 交叉：train&test=0, train&validation=0, validation&test=0

**未采用的交叉边（excluded）**：49034 条，涉及 9409 个候选人、1088 个岗位；标签分布 {'medium_positive': 25947, 'strong_positive': 218, 'weak_positive': 22869}。

覆盖率：原始 122560 条，保留 73526 条 （保留率 0.599918），排除 49034 条 （丢弃率 0.400082）。

- 参照：两侧独立按 80/10/10 分配的期望保留率仅 **0.66**。
- 两侧独立按 80/10/10 随机分配时期望保留率约 66%（= 0.8² + 0.1² + 0.1²），且验证/测试各只占约 1% 的边。三种策略的实测对比见 strategy_comparison。

## 二、学历数据重新划分

- 分组键：user_hash（规范化输入文本）
- 分组理由：job_id 不是行级唯一键（实测重复 779 行），输入文本也有重复（重复 17072 行，占 7.0%）；按 user_hash 分组可同时保证输入文本与记录键在集合间互斥
- 随机种子：`20261031`

| 集合 | 样本数 | 唯一 job_id | 唯一输入文本 | <学历描述> 覆盖率 | 标签来源 |
|---|---|---|---|---|---|
| train | 180903 | 180866 | 180903 | 0.999972 | {'pseudo_online': 180903} |
| validation | 45226 | 45222 | 45226 | 1.0 | {'pseudo_online': 45226} |
| gold_holdout | 736 | 736 | 702 | 1.0 | {'human_gold': 736} |

### 重复与冲突检查

| 检查项 | 结果 |
|---|---|
| input_groups_with_label_conflict | 374 |
| job_id_duplicated_rows | 779 |
| record_key_duplicated_rows | 0 |
| rows | 243903 |
| rows_in_label_conflict_groups | 812 |
| unique_job_id | 243124 |
| unique_user_hash | 226831 |
| user_hash_duplicated_rows | 17072 |

跨来源输入文本交叉：
| 来源对 | 交叉输入数 |
|---|---|
| annotated_gold&default_train | 0 |
| annotated_gold&default_validation | 702 |
| default_train&default_validation | 2 |

### 互斥性检查

- job_id_overlap：train&gold_holdout=0, train&validation=1, validation&gold_holdout=0
- record_key_overlap：train&gold_holdout=0, train&validation=0, validation&gold_holdout=0
- user_hash_overlap：train&gold_holdout=0, train&validation=0, validation&gold_holdout=0

### 人工金标准隔离

| 项目 | 值 |
|---|---|
| dev_input_hashes_touching_gold_after_removal | 0 |
| dev_rows_removed_due_to_gold_input_overlap | 762 |
| gold_eval_policy | 只做一次性最终评估；规则定义与阈值在开发集上确定后锁定，不对金标准反复调参 |
| gold_input_hashes | 702 |
| gold_label_provenance | human_gold（人工正确结果，736 条） |
| gold_rows | 736 |
| gold_used_for_rule_fitting | False |

### 测试集决策

- 是否构建独立 test：**False**
- 理由：原 default/test 100% 被 default/validation 包含（job_id 22,730/22,730 重合），且其可用标签就是 736 条人工金标准；无法据此构建独立可信测试集。最终独立评估改用 gold_holdout。

### 标签可信度标识

| 来源 | 说明 |
|---|---|
| human_gold | annotated 的 人工正确结果，736 条，可信度标记 high |
| model_new | annotated 的 模型结果-新的，实测含长文本噪声（22 个 '唯一值' 中含 JD 片段），不可用作标签 |
| pseudo_online | default/* 的 assistant，来源为线上旧系统输出，人工复核一致率 45.92%（338/736），可信度标记 low |

### 排除记录

| 排除原因 | 行数 |
|---|---|
| excluded_gold_input_overlap | 762 |
| excluded_input_duplicate | 16276 |
