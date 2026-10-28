# 第三阶段验收报告

- 生成时间：2026-10-28 20:15:40
- 流水线版本：`phase3-v1`
- 数据版本：`dv-0ce28fa6b560`

## 自动化测试结果

- 测试总数：74，失败 0，错误 0
- 总体结论：**PASS**

| 门禁 | 内容 | 通过/总数 | 结论 |
|---|---|---|---|
| G1 | 原始数据不变 | 3/3 | PASS |
| G2 | 字段约束 | 14/14 | PASS |
| G3 | 目标泄漏防护 | 14/14 | PASS |
| G4 | 切分互斥 | 17/17 | PASS |
| G5 | 结果可复现性 | 10/10 | PASS |
| G6 | 数据可加载 | 9/9 | PASS |
| G7 | 资源约束 | 7/7 | PASS |

## 验收项逐条结论

| 编号 | 验收内容 | 要求 | 结论 | 实际证据 |
|---|---|---|---|---|
| P3-01 | 原始数据完整性 | SHA-256 一致 | PASS | 流水线第 1 步核对 8/8 个原始文件与第二阶段 SHA-256 基线一致；G1 门禁 3/3 通过。 |
| P3-02 | Schema | 关键字段全部验证 | PASS | 7/7 个数据文件通过 Resume/Job/Match/EducationSample Schema 校验（含主键、枚举、取值范围、列集合）；学历 default/annotated 两个列变体分别核对。 |
| P3-03 | 特征泄漏防护 | 禁止字段无法进入对应模型输入 | PASS | G3 门禁 14/14 通过；实际特征矩阵 [122560, 6] 逐列通过白名单检查；派生评分链 10 个字段零命中；间接泄漏扫描（Spearman/R² 重建）硬问题 0 条、分量级提示 2 条（详见下方分级说明）。 |
| P3-04 | Embedding 缓存 | ID 映射和数值一致 | PASS | cv/job 两份 768 维 float32 缓存经 bit 级抽样回比原始 CSV，最大绝对误差 0.0；ID 映射可逆且行号连续；G2 14/14、G6 9/9。 |
| P3-05 | 数据清洗 | 可复现且有异常统计 | PASS | 四张表规范化产物均带异常统计（技能待复核、years_required 标志、education_text 重复判定、标签冲突），输出文件哈希已登记；G5 门禁 10/10 复算一致。 |
| P3-06 | Candidate Cold-start | 候选人集合完全互斥 | PASS | candidate_cold 互斥检查 {'candidate_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}, 'pair_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}}；job_overlap 非互斥（协议允许）={'train&test': 944, 'train&validation': 896, 'validation&test': 773}；同一候选人的全部记录同集合；G4 17/17。 |
| P3-07 | Job Cold-start | 岗位集合完全互斥 | PASS | job_cold 互斥检查 {'job_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}, 'pair_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}}；candidate_overlap 非互斥（协议允许）={'train&test': 6414, 'train&validation': 6063, 'validation&test': 4676}；G4 17/17。 |
| P3-08 | Double Cold-start | 双侧实体互斥且记录覆盖率 | PASS | double_cold 互斥检查 {'candidate_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}, 'job_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}, 'pair_overlap': {'train&test': 0, 'train&validation': 0, 'validation&test': 0}}；原始 122560 条，保留 73526 条（保留率 0.599918），交叉边 49034 条单独落盘为 excluded 索引。 |
| P3-09 | 学历数据切分 | 重复检查与金标准隔离 | PASS | 输入文本/记录键交叉全部为 0（{'train&gold_holdout': 0, 'train&validation': 0, 'validation&gold_holdout': 0} / {'train&gold_holdout': 0, 'train&validation': 0, 'validation&gold_holdout': 0}）；岗位键允许跨集合（{'train&gold_holdout': 0, 'train&validation': 1, 'validation&gold_holdout': 0}），因分组键是输入文本而不判失败；金标准 736 条隔离为 gold_holdout，与开发集输入交叉 0；因原 test ⊂ validation 且伪标签可信度低，未伪造独立 test（已在 manifest 记录理由）。 |
| P3-10 | Matching Baseline | 实际运行并产出指标 | PASS | Random / Embedding Cosine / Skill Jaccard / Position Overlap 四个基线在同一候选集合与口径下完成 2 个子集 × 2 种增益模式评估；示例（candidate_cold/test, embedding_cosine, gain=score）：NDCG@5=0.967769、NDCG@10=0.978857。 |
| P3-11 | Education Baseline | 在合法评估集合上完成测试 | PASS | 规则基线与槽位经验映射基线在开发集（伪标签）与 gold_holdout（人工金标准 736 条）分别评估；金标准 Exact Match=0.48913、Micro-F1=0.70354；未用金标准做任何拟合或调参。 |
| P3-12 | 结果可复现 | 固定配置和种子重复执行一致 | PASS | G5 门禁 10/10（划分 ID、样本计数、特征维度、文件哈希一致）；全流水线重复执行比对：比对 31 个确定性产物（切分索引 / 特征表 / 目标表 / 特征矩阵 / 学历输入与标签 / Embedding 数组与 ID 映射 / manifest 统计量），差异 0 个；Baseline 指标与上次运行逐值一致（剔除时间字段）。 |
| P3-13 | 依赖完整性 | pip check 通过 | PASS | `pip check` 退出码 0：No broken requirements found. |
| P3-14 | 自动化测试 | 核心测试全部 PASS | PASS | tests/data_pipeline 共 74 项，失败 0，错误 0；G1-G7 逐项结论见 reports/data-quality-gates.json。 |

## 数据泄漏验证摘要

### 任务 `match_label_strength`

- 允许特征（白名单）：`target_position_norm`, `years_experience`, `inferred_category`, `cv_skills_canonical_json`, `job_title_norm`, `job_category`, `job_skills_canonical_json`, `skill_jaccard`, `skill_overlap_ratio_cv`, `skill_overlap_ratio_job`, `position_token_overlap`, `category_match`, `both_skills_empty`
- 禁止字段（黑名单）：`semantic_score`, `skill_score`, `position_score`, `category_score`, `experience_score`, `education_score`, `raw_score`, `final_score`, `candidate_rank`, `candidate_rank_pct`
- 监督目标：`label_strength`；派生目标：`label_ordinal`
- 评估元数据（不进特征）：`candidate_id`, `job_id`, `split`, `protocol`, `final_score`, `candidate_rank`
- 待定特征（默认禁止，需显式 opt-in）：`embedding`, `years_required`, `education_text`

### 任务 `match_ranking`

- 允许特征（白名单）：`target_position_norm`, `years_experience`, `inferred_category`, `cv_skills_canonical_json`, `job_title_norm`, `job_category`, `job_skills_canonical_json`, `skill_jaccard`, `skill_overlap_ratio_cv`, `skill_overlap_ratio_job`, `position_token_overlap`, `category_match`, `both_skills_empty`
- 禁止字段（黑名单）：`semantic_score`, `skill_score`, `position_score`, `category_score`, `experience_score`, `education_score`, `raw_score`, `final_score`, `candidate_rank`, `candidate_rank_pct`
- 监督目标：`candidate_rank`；派生目标：
- 评估元数据（不进特征）：`candidate_id`, `job_id`, `split`, `protocol`
- 待定特征（默认禁止，需显式 opt-in）：`embedding`

### 任务 `edu_label_multilabel`

- 允许特征（白名单）：`user_norm`, `job_title_norm`, `slot_education_norm`, `slot_present`, `user_len`
- 禁止字段（黑名单）：`assistant`, `ai`, `diff`, `线上学历-旧的`, `模型结果-新的`, `人工正确结果`, `【线上学历-旧的】是否正确`, `【模型结果-新的】是否正确`, `label_tokens`, `label_multi_hot`, `label_provenance`
- 监督目标：`label_tokens`；派生目标：`label_multi_hot`
- 评估元数据（不进特征）：`record_key`, `user_hash`, `job_id`, `source_split`, `is_gold`, `label_status`, `label_confidence`
- 待定特征（默认禁止，需显式 opt-in）：`user_short`

目标字段与输入的物理隔离：匹配任务 `features_pairs.csv` / `targets_pairs.csv`、学历任务 `education_inputs.csv` / `education_labels.csv` 分文件落盘，仅共享关联键（`candidate_id`/`job_id`/`record_key`）。

### 间接泄漏扫描（特征重建派生字段检测）

严重度分级规则：能重建 `final_score` / `candidate_rank` / `candidate_rank_pct` （目标或其直接决定量）判为**硬泄漏**；与原公式**中间分量**（`semantic_score` … `raw_score`）一致判为**提示级**，必须查明构造来源并在报告中说明。

| 参考字段 | 级别 | 特征 | 检测 | 数值 | 严重度 |
|---|---|---|---|---|---|
| category_score | component | category_match | NEAR_DETERMINISTIC_MONOTONIC | 1.0 | warn |
| category_score | component | - | LINEAR_RECONSTRUCTION | 1.0 | warn |

来源核查：`category_match` 由 `cv.inferred_category` 与 `job.category` 两个**原始字段**独立构造（`src/job_matching/pair_features.py`），未读取任何派生评分列；它与 `category_score` 数值完全一致，说明原系统的 `category_score` 本身就是「类别是否相同」的二值指示。这是对原公式一个分量的复刻，**不构成目标泄漏**，但说明该特征只提供原公式 0.10 权重那一部分信息，已如实登记。

## 风险与剩余问题

### 阻断性问题

- 无。未发现目标泄漏、切分交叉或核心数据异常。

### 非阻断性问题（限制实验解释力，必须随结论一并引用）

- **匹配标签是代理标签**：`label_strength`/`candidate_rank`/`final_score` 均由原系统评分公式派生（非真实投递或录用结果），排序指标只能解释为「与原系统代理偏好的一致程度」，不代表真实录用概率或用户满意度。
- **Embedding Cosine 基线与代理标签机制耦合**：`semantic_score = 0.5*cosine+0.5` 已被审计以 R²=1.0 证实，而 semantic_score 占 raw_score 0.25 权重。该基线的高 NDCG 不构成独立的语义匹配有效性证明。
- **预计算 Embedding 来源未知**：「冷启动」仅表示下游排序模型未用这些候选人/岗位监督训练，不能宣称预训练编码器从未见过相关文本。
- **匹配数据无真实负例**：matches.csv 全部为 *_positive 观测记录，本阶段不做负采样，评估只在观测组合内部做组内排序。
- **学历伪标签可信度低**：default/* 的 assistant 为线上旧系统输出，人工复核一致率 45.92%（338/736），只能作低置信开发信号。
- **学历无独立可信测试集**：原 default/test 100% 被 default/validation 包含，最终独立评估改用 gold_holdout（736 条人工金标准），只做一次性评估。
- **学历任务范围受限**：`<学历描述>` 是上游已抽取的短槽位，本数据只能支撑「学历要求表达的规范化/多标签归一」，不是端到端 JD 学历抽取。
- **Double Cold-start 稀疏性**：双侧互斥必然丢弃交叉边，保留率与可排序组数见 reports/data-split-validation.md，评估时必须按保留率解释。
- **格式限制**：本地缺少 Parquet 引擎（pyarrow/fastparquet 未安装），按约束不修改环境，表格产物使用 CSV（已在 manifest 记录）。

## 阶段验收结论

**B. 有条件通过**

数据加工、可信切分与零训练 Baseline 全部可用，但代理标签与学历伪标签的可信度限制仍然存在，具备正式模型训练条件时必须沿用本报告的评估协议与限制说明。

判定依据：上表全部核心验收项均为 PASS，且 G1-G7 自动化门禁全部通过；但匹配标签为原评分系统派生的代理标签、学历伪标签可信度低且无独立可信测试集，因此按验收规则判定为「有条件通过」，不判定为「完全通过」。
