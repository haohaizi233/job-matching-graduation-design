# 第三阶段 · 数据清洗与特征工程实测记录

- 生成时间：2026-10-28 20:15:40
- 流水线版本：phase3-v1
- 数据版本（由原始文件哈希推导）：`dv-0ce28fa6b560`
- 格式说明：本地缺少 Parquet 引擎（`pyarrow`/`fastparquet` 均未安装），按阶段约束不修改环境，表格产物统一使用 **CSV**，向量用 **NPY**，清单用 **JSON**。

## 1. Schema 校验结果

| 文件 | Schema | 变体 | 行数 | 硬问题 | 结论 | 列集合 |
|---|---|---|---|---|---|---|
| `data/raw/job-resume-matching/cv.csv` | Resume | - | 9544 | 0 | PASS | 一致 |
| `data/raw/job-resume-matching/job.csv` | Job | - | 1167 | 0 | PASS | 一致 |
| `data/raw/job-resume-matching/matches.csv` | Match | - | 122560 | 0 | PASS | 一致 |
| `data/raw/job-education/default/train/19w_0701.csv` | EducationSample | default | 197574 | 0 | PASS | 一致 |
| `data/raw/job-education/default/validation/4w_0708.csv` | EducationSample | default | 45593 | 0 | PASS | 一致 |
| `data/raw/job-education/default/test/2w_0716.csv` | EducationSample | default | 22730 | 0 | PASS | 一致 |
| `data/raw/job-education/annotated/2w_0716_eval.csv` | EducationSample | annotated | 22730 | 0 | PASS | 一致 |

> 「硬问题」= 缺列 / 主键重复 / 越界 / 非法枚举 / 非预期空值；未知列仅作 WARN 提示，不判失败。学历数据分 `default` 与 `annotated` 两个列变体，已分别核对精确列集合。

## 2. 简历数据规范化（cv.csv）

| 项目 | 值 |
|---|---|
| 输入行数 | 9544 |
| 输出行数 | 9544 |
| 主键唯一 | True |
| 技能为空的行 | 20 |
| 技能待复核的行 | 9524 |
| 唯一规范技能数 | 3807 |
| 唯一原始技能数 | 3814 |
| 输出文件 | `data/interim/matching/resume_normalized.csv` |
| 输出 SHA-256 | `bdd16f3295c6f6f8538ad3d15ad4777bf17cbae0308522083f3d8d035532a84c` |

文本 Unicode 规范化（NFKC + 空白折叠）导致内容变化的行数：
| 字段 | 变化行数 |
|---|---|
| education_text | 450 |
| experience_text | 9544 |
| resume_text | 30 |
| target_position | 0 |

工作年限字段检查：
| 标志 | 行数 |
|---|---|
| extreme_high | 28 |
| integer_ok | 8490 |
| zero | 1026 |

## 3. 岗位数据规范化（job.csv）

| 项目 | 值 |
|---|---|
| 输入行数 | 1167 |
| 输出行数 | 1167 |
| `education_text` 与 `job_description` 逐行相同的行数 | 1167 / 1167 |
| 重复判定 | 整列复制（1167/1167 逐行相同） |
| 处置 | 保留原字段 + 打 duplicate 标记 + 禁用为模型输入（不删除） |
| `years_required` 范围 | 0.0 ~ 40.0（均值 14.301） |
| 非整数取值行数 | 15 |
| 语义判定 | 语义不明（0~40、含小数），不得直接当作真实工作年限 |
| 处置 | 保留原值 + 标记异常 + 暂时禁用为模型输入（uncertain_features） |

异常标记分布：
| 标志 | 行数 |
|---|---|
| extreme_high | 140 |
| fractional | 15 |
| integer_ok | 867 |
| zero | 145 |

## 4. 学历样本规范化（job-education）

| 项目 | 行数 |
|---|---|
| annotated_gold | 736 |
| annotated_total | 22730 |
| default_test_total | 22730 |
| default_test_with_gold_label | 736 |
| default_train | 197574 |
| default_validation | 45593 |

- 合并后统一记录表行数：**243903**
- 输出文件：`data/interim/education/education_normalized.csv`
- 输出 SHA-256：`33cbf598913facdd0cfdc7c7efa8b494e96c31ae84c0dcd216171a96e4c86ff0`

标签 token 统计（多标签，可重复计数）：
| 标签 token | 出现次数 |
|---|---|
| 博士 | 134519 |
| 大专 | 68173 |
| 学历不明 | 3241 |
| 学历不限 | 945 |
| 本科 | 175839 |
| 硕士 | 150412 |

标签规范化状态：
| 状态 | 行数 |
|---|---|
| ok | 243902 |
| oov_token | 1 |

> `oov_token` 表示出现词表外 token（实测如 `大四保研准硕士`），按规范**保留原值并标记待确认**，不强行归并到 6 token 词表。

## 5. 招聘风险数据规范化（all_df.csv）

| 项目 | 值 |
|---|---|
| 输入行数 | 251381 |
| 输出行数 | 251381 |
| 整行重复（标记 is_duplicate，不删除） | 25433 |
| 删除的行数 | 0 |
| 重复占比 | 0.101173 |
| 重复处置 | 整行重复只标记不删除（is_duplicate + duplicate_group_id），原始观测不丢失 |
| 处置 | 本阶段仅规范化与元数据登记，不纳入核心监督训练任务 |

- `scam_probability` 实测唯一取值：[0, 10, 20, 30, 40, 50, 60, 70, 80]
- 是否全部为 10 的倍数：True
- 判定：非人工真值；实测仅 9 个 10 的倍数取值，无任何人工复核列
- 处置：仅登记为上游风险分数，本阶段不作为监督标签使用

## 6. Embedding 工程化缓存

| 侧 | 行数 | 维度 | 类型 | L2 范数 | 全有限 | 零向量 | 重复向量 | 文件 |
|---|---|---|---|---|---|---|---|---|
| cv | 9544 | 768 | float32 | 1.0 ± 2.875339788488418e-08 | True | 0 | 0 | `data/processed/embeddings/cv_embeddings.npy` |
| job | 1167 | 768 | float32 | 1.0 ± 3.121186153975941e-08 | True | 0 | 0 | `data/processed/embeddings/job_embeddings.npy` |

缓存与原始 CSV 的数值一致性校验（bit 级抽样比对）：**通过**

| 侧 | 抽样行数 | 最大绝对误差 | ID 映射可逆 | 维度正确 | 结论 |
|---|---|---|---|---|---|
| cv | 64 | 0.0 | True | True | PASS |
| job | 64 | 0.0 | True | True | PASS |

### 预计算 Embedding 的来源限制（必须随实验结论一并引用）

- 预计算 embedding 的编码模型未知（数据集卡片明确声明未指定），不得仅凭 768 维推断模型。
- 编码输入是 resume_text / job_description 原文还是清洗后文本，未知。
- 单塔（共享编码器）还是双塔（两个编码器），数据不提供判别依据。
- semantic_score = 0.5 * cosine(cv_emb, job_emb) + 0.5（审计以 R²=1.0 证实），故 embedding 经 semantic_score -> raw_score -> final_score -> label_strength 参与了标签生成，属于派生信息链的一环。
- 后续 '冷启动' 实验只能表示下游排序模型未使用这些候选人/岗位做监督训练，不能宣称预训练编码器从未见过相关文本。
- 向量由全量数据产生，其归一化统计不得再用全量数据重复拟合（间接泄漏规则 IL-6）。

## 7. 产物清单

| 文件 | 字节数 |
|---|---|
| `data/interim/matching/job_normalized.csv` | 14315785 |
| `data/interim/matching/resume_normalized.csv` | 49186634 |
| `data/interim/education/education_normalized.csv` | 67164973 |
| `data/interim/risk/risk_normalized.csv` | 54693661 |
| `data/processed/embeddings/cv_embeddings.npy` | 29319296 |
| `data/processed/embeddings/cv_id_map.json` | 399830 |
| `data/processed/embeddings/job_embeddings.npy` | 3585152 |
| `data/processed/embeddings/job_id_map.json` | 47990 |
| `data/processed/embeddings/metadata.json` | 3986 |
| `data/processed/matching/feature_matrix_match_label_strength.npz` | 2942260 |
| `data/processed/matching/feature_schema.json` | 2679 |
| `data/processed/matching/features_pairs.csv` | 138867455 |
| `data/processed/matching/targets_pairs.csv` | 17111252 |
| `data/processed/education/education_inputs.csv` | 30124827 |
| `data/processed/education/education_labels.csv` | 18859649 |
