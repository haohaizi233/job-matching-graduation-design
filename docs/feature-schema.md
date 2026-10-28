# 特征 Schema 与泄漏防护（第三阶段）

- 代码来源：`src/job_matching/schema.py`（Schema 定义与校验器）、
  `src/job_matching/policy.py`（白名单/黑名单执行）、
  `configs/feature_policy.yaml`（策略配置，唯一事实来源）
- 实测口径：2026-10-28，字段全部来自实际 CSV 表头，未虚构任何数据库字段

本文回答两个问题：**每个字段是什么**、**哪些字段可以进模型输入**。

## 一、Schema 总览

四个 Schema：`Resume` / `Job` / `Match` / `EducationSample`。
每个字段声明：字段名、类型、是否必需、是否可空、取值范围、
是否属于模型输入、是否属于监督标签、是否为派生字段、数据来源。

字段语义标记含义：

- `模型输入`：推理时可用的原始特征（`FieldSpec.is_model_input`）
- `监督标签`：监督目标（`FieldSpec.is_target`）
- `派生`：由其它字段经公式/模型/排序产生（`FieldSpec.is_derived`）
- `来源`：`raw`（原始采集）/ `derived`（派生）/ `human_gold`（人工金标准）/
  `model_output`（模型输出）/ `pseudo_online`（线上旧系统伪标签）

校验器 `schema.validate_frame` 实际执行：必需列、未知列提示、主键唯一性与非空、
数值类型与取值范围、枚举合法性、复合主键组合唯一性。第 2 步对 7 个原始 CSV 全量校验
（分块 20,000 行），结果落盘 `reports/phase3-schema-validation.json`。

### 1. Resume（`cv.csv`，9,544 行 × 11 列）

主键：`candidate_id`

| 字段 | 类型 | 必需 | 可空 | 取值范围 | 模型输入 | 监督标签 | 派生 | 来源 |
|---|---|---|---|---|---|---|---|---|
| candidate_id | object | 是 | 否 | 字符串 ID，唯一 | 否 | 否 | 否 | raw |
| source_row | int64 | 是 | 否 | 0 ~ 9543 | 否 | 否 | 否 | raw |
| target_position | object | 是 | 否 | 28 个唯一值，长度 10~87 | 是 | 否 | 否 | raw |
| resume_text | object | 是 | 否 | 长度 493~3000（上游已截断） | 否 | 否 | 否 | raw |
| clean_skills | object | 是 | 否 | 字符串化的 list[str] | 是 | 否 | 否 | raw |
| clean_skills_json | object | 是 | 否 | 与 clean_skills 等价的 JSON 形式 | 是 | 否 | 否 | raw |
| education_text | object | 是 | 否 | 长度 18~959 | 是 | 否 | 否 | raw |
| experience_text | object | 是 | 否 | 长度 161~1746 | 否 | 否 | 否 | raw |
| years_experience | float64 | 是 | 否 | 0 ~ 31（16 个唯一值，全整数） | 是 | 否 | 否 | raw |
| inferred_category | object | 是 | 否 | INFORMATION-TECHNOLOGY / FINANCE / SALES / BUSINESS-DEVELOPMENT / HR / UNKNOWN | 是 | 否 | 否 | raw |
| embedding | object | 是 | 否 | 字符串化的 768 维 float32 向量 | 否 | 否 | 是 | derived |

### 2. Job（`job.csv`，1,167 行 × 10 列）

主键：`job_id`

| 字段 | 类型 | 必需 | 可空 | 取值范围 | 模型输入 | 监督标签 | 派生 | 来源 |
|---|---|---|---|---|---|---|---|---|
| job_id | int64 | 是 | 否 | 整数主键，唯一 | 否 | 否 | 否 | raw |
| job_title | object | 是 | 否 | 720 个唯一值，长度 10~147 | 是 | 否 | 否 | raw |
| category | object | 是 | 否 | 5 类，接近均匀 | 是 | 否 | 否 | raw |
| job_description | object | 是 | 否 | 长度 167~13639 | 否 | 否 | 否 | raw |
| job_text | object | 是 | 否 | 长度 364~3500（硬截断） | 否 | 否 | 否 | raw |
| clean_skills | object | 是 | 否 | 字符串化的 list[str] | 是 | 否 | 否 | raw |
| clean_skills_json | object | 是 | 否 | JSON 形式 | 是 | 否 | 否 | raw |
| education_text | object | 是 | 否 | 实测与 job_description 逐行相同（1167/1167） | 否 | 否 | 是 | raw |
| years_required | float64 | 是 | 否 | 0 ~ 40（均值 14.30，含 16.95/20.23 等小数） | 否 | 否 | 否 | raw |
| embedding | object | 是 | 否 | 字符串化的 768 维 float32 向量 | 否 | 否 | 是 | derived |

两个存疑字段的处置（详见 `docs/data-pipeline.md` 第 5.2 节）：

- `years_required`：语义不明，保留原值 + 标记异常 + **禁用为模型输入**（`uncertain_features`）。
- `education_text`：与 `job_description` 整列重复，保留字段 + 打 duplicate 标记 + **禁用为模型输入**。

### 3. Match（`matches.csv`，122,560 行 × 13 列）

复合主键：`(candidate_id, job_id)`；外键：`candidate_id -> Resume`、`job_id -> Job`

| 字段 | 类型 | 取值范围 | 模型输入 | 监督标签 | 派生 | 来源 |
|---|---|---|---|---|---|---|
| candidate_id | object | 9,532 个唯一值 | 否 | 否 | 否 | raw |
| job_id | int64 | 1,164 个唯一值 | 否 | 否 | 否 | raw |
| label_strength | object | weak_positive / medium_positive / strong_positive | 否 | **是** | 是 | derived |
| final_score | float64 | 0.4300 ~ 0.7561 | 否 | 否 | 是 | derived |
| raw_score | float64 | 0.3060 ~ 0.6516 | 否 | 否 | 是 | derived |
| semantic_score | float64 | 0.5805 ~ 0.9177 | 否 | 否 | 是 | derived |
| skill_score | float64 | 0.0000 ~ 0.6170 | 否 | 否 | 是 | derived |
| position_score | float64 | 0.0229 ~ 1.0000 | 否 | 否 | 是 | derived |
| category_score | float64 | 0.0000 ~ 1.0000 | 否 | 否 | 是 | derived |
| experience_score | float64 | 0.0000 ~ 1.0000 | 否 | 否 | 是 | derived |
| education_score | float64 | 0.3000 ~ 1.0000 | 否 | 否 | 是 | derived |
| candidate_rank | int64 | 1 ~ 122（组内 final_score 降序名次） | 否 | **是**（排序任务） | 是 | derived |
| candidate_rank_pct | float64 | 0.3832 ~ 1.0000 | 否 | 否 | 是 | derived |

### 4. EducationSample（job-education，default 三份 9 列 / annotated 12 列）

主键（重建后）：`record_key`；输入同一性：`user_hash`

| 字段 | 类型 | 必需 | 可空 | 取值范围 | 模型输入 | 监督标签 | 派生 | 来源 |
|---|---|---|---|---|---|---|---|---|
| job_id | object | 是 | 否 | 非严格唯一（train 中 43 个重复） | 否 | 否 | 否 | raw |
| system | object | 否 | 否 | 常量「从岗位中提取学历」（仅 default/*） | 否 | 否 | 否 | raw |
| user | object | 是 | 否 | `<岗位名称>…<岗位描述>…<学历描述>…` | 是 | 否 | 否 | raw |
| assistant | object | 是 | 是 | 6 token 组合串；test/annotated 缺 96.76% | 否 | **是**（伪标签） | 否 | pseudo_online |
| id | object | 是 | 是 | train 中 12 缺失、11 重复 | 否 | 否 | 否 | raw |
| user_short | object | 是 | 是 | 来源与生成方式未知 | 否 | 否 | 是 | derived |
| ai | object | 否 | 是 | 另一路模型输出 | 否 | 否 | 是 | model_output |
| diff | object | 是 | 是 | ai == assistant 的布尔标记，直接泄漏标签 | 否 | 否 | 是 | derived |
| user_short2 | object | 否 | 是 | 实测整列全空（100% NaN） | 否 | 否 | 是 | derived |
| 线上学历-旧的 | object | 否 | 是 | 旧线上系统输出（仅 annotated） | 否 | 否 | 是 | model_output |
| 模型结果-新的 | object | 否 | 是 | 新模型输出，实测含长文本噪声（仅 annotated） | 否 | 否 | 是 | model_output |
| 人工正确结果 | object | 否 | 是 | 736 条非空 | 否 | **是**（金标准） | 否 | human_gold |
| 【线上学历-旧的】是否正确 | object | 否 | 是 | 人工判定（仅 annotated） | 否 | 否 | 是 | human_gold |
| 【模型结果-新的】是否正确 | object | 否 | 是 | 人工判定（仅 annotated） | 否 | 否 | 是 | human_gold |
| 是否英文岗位 | float64 | 否 | 是 | 仅 33 行为 1 | 否 | 否 | 否 | human_gold |

## 二、目标泄漏的来源（为什么必须隔离）

第二阶段已反推原系统评分链（`reports/data-audit/label-formula.json`，R²=1.0 证实）：

```text
semantic_score = 0.5 * cosine(cv_emb, job_emb) + 0.5
raw_score      = 0.25*semantic + 0.35*skill + 0.20*position
               + 0.10*category + 0.05*experience + 0.05*education
final_score    = 0.7 * raw_score + 0.3 * candidate_rank_pct
label_strength = f(final_score)      # <0.58 weak / [0.58,0.68) medium / >=0.68 strong
candidate_rank = g(final_score)      # 组内排序
```

`candidate_rank` 又由 `final_score` 得到，因此这 **10 个字段**
（`semantic_score`/`skill_score`/`position_score`/`category_score`/`experience_score`/
`education_score`/`raw_score`/`final_score`/`candidate_rank`/`candidate_rank_pct`）
是派生结果或监督目标本身，**不得进入以 `label_strength` / `candidate_rank` 为目标的模型输入**。

注意：这是**按任务定义的隔离**，不是删除数据。这些字段仍然保留在 `targets_pairs.csv`
与原始 CSV 中，用于事后相关性分析与评估元数据。

## 三、任务级白名单 / 黑名单（`configs/feature_policy.yaml`）

### 任务 `match_label_strength`（匹配强度三分类）

- **允许特征（白名单）**：
  `target_position_norm`, `years_experience`, `inferred_category`, `cv_skills_canonical_json`,
  `job_title_norm`, `job_category`, `job_skills_canonical_json`,
  `skill_jaccard`, `skill_overlap_ratio_cv`, `skill_overlap_ratio_job`,
  `position_token_overlap`, `category_match`, `both_skills_empty`
- **禁止特征（黑名单）**：派生评分链 10 个字段（见上）
- **监督目标**：`label_strength`；派生目标：`label_ordinal`
- **评估元数据（不进特征）**：`candidate_id`, `job_id`, `split`, `protocol`, `final_score`, `candidate_rank`
- **待定特征（默认禁止，需显式 `allow_uncertain=True` 并在报告标注风险）**：
  - `embedding`：预计算向量经 `semantic_score` 参与了标签生成，属派生信息链一环
  - `years_required`：语义不明
  - `education_text`：与 `job_description` 整列重复

### 任务 `match_ranking`（Learning-to-Rank）

- 白名单同上；黑名单同上
- **监督目标**：`candidate_rank`；相关性列（只用于算指标，不是特征）：`final_score`, `label_strength`
- **特例登记**：`embedding_cosine_baseline` 允许使用 `embedding`，
  但必须在报告中声明它与代理标签生成机制直接耦合（`baseline_feature_exception`）

### 任务 `edu_label_multilabel`（学历多标签）

- **允许特征**：`user_norm`, `job_title_norm`, `slot_education_norm`, `slot_present`, `user_len`
- **禁止特征**：`assistant`, `ai`, `diff`, `线上学历-旧的`, `模型结果-新的`, `人工正确结果`,
  `【线上学历-旧的】是否正确`, `【模型结果-新的】是否正确`, `label_tokens`, `label_multi_hot`, `label_provenance`
- **监督目标**：`label_tokens`；派生目标：`label_multi_hot`
- **评估元数据**：`record_key`, `user_hash`, `job_id`, `source_split`, `is_gold`, `label_status`, `label_confidence`
- **待定特征**：`user_short`（来源与生成方式未知）

### 任务 `risk_screening`（招聘风险，本阶段不建模）

- 目标列为空；`scam_probability` 禁止作为真值（实测仅 9 个 10 的倍数取值）；
- `job_type`（含义未给出）、`job_salary`（存在 4,597,500 极端离群值）登记为待定。

### 全局禁令

任何任务都不得把 `candidate_id` / `job_id` / `source_row` / `id` / `record_key` / `split` / `protocol`
当作语义特征（数值型 ID 无语义，且会造成实体记忆式泄漏）。

## 四、间接泄漏防护（`indirect_leakage_rules`）

即使派生评分没有直接进入输入，只要**编码、归一化或特征构造间接使用了这些字段**，同样视为泄漏：

| 编号 | 规则 |
|---|---|
| IL-1 | StandardScaler / MinMaxScaler / 任何统计归一化参数只能在 train 上 fit |
| IL-2 | TF-IDF / 词表 / 特征选择器只能在 train 上 fit |
| IL-3 | 禁止用 `final_score`/`raw_score` 分位数构造分箱、难负例权重或样本权重 |
| IL-4 | 禁止用 `candidate_rank`/`candidate_rank_pct` 做特征分桶、目标编码或 group prior |
| IL-5 | 禁止把 `label_strength` 编码进任何输入列（含 one-hot 拼接、目标编码、聚类 ID） |
| IL-6 | 预计算 embedding 由全量数据产生，其归一化统计不得再用全量数据重复拟合 |

`policy.detect_indirect_leakage` 会用两种检测扫描实际特征矩阵：

1. 单列与禁止字段的 |Spearman| ≥ 0.999（近乎确定的单调关系）；
2. 全部特征线性重建禁止字段的 R² ≥ 0.999。

严重度分级：能重建 `final_score`/`candidate_rank`/`candidate_rank_pct`/`label_strength`
（目标或其直接决定量）判为**硬泄漏**，流水线立即失败；与原公式**中间分量**
（`semantic_score` … `raw_score`）一致判为**提示级（warn）**，必须查明构造来源并写入报告。

实测结果（`reports/phase3-feature-build.json`）：硬泄漏 0 条；
提示级 2 条，均为 `category_match` 与 `category_score` 一致——`category_match` 由
`cv.inferred_category` 与 `job.category` 两个**原始字段**独立构造，未读取任何派生评分列，
说明原系统的 `category_score` 本身就是「类别是否相同」的二值指示，属复刻原公式分量而非目标泄漏。

## 五、物理隔离与自动化防护

| 任务 | 输入文件 | 目标文件 | 共享键 |
|---|---|---|---|
| 匹配 | `data/processed/matching/features_pairs.csv` | `data/processed/matching/targets_pairs.csv` | `pair_index`, `candidate_id`, `job_id` |
| 学历 | `data/processed/education/education_inputs.csv` | `data/processed/education/education_labels.csv` | `record_key` |

自动化防护（`tests/data_pipeline/test_g3_leakage_guard.py`，G3 门禁）：

1. 静态扫描：`configs/feature_policy.yaml` 的黑名单不得出现在任何任务白名单中；
2. 动态扫描：实际写出的 `features_pairs.csv` / `education_inputs.csv` 列集合逐列核对；
3. 矩阵扫描：`feature_matrix_match_label_strength.npz` 的 `feature_names` 逐列核对
   （`policy.assert_tensor_features` 同时核对特征名数量与矩阵最后一维）；
4. 间接泄漏扫描：如上；
5. 目标隔离：`targets_pairs.csv` / `education_labels.csv` 不得被任何特征加载路径读入输入矩阵。

> 维护提示：新增特征时必须先在 `configs/feature_policy.yaml` 登记，
> 否则 `policy.check_feature_columns` 会以「不在任务白名单内」直接抛 `LeakageError`。
