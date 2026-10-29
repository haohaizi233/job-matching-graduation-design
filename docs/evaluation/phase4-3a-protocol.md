# Phase4-3A 独立评估协议（v1）

- 协议版本号：`phase4-3a-protocol-v1`（标注协议版本：`phase4-3a-annotation-v1`）
- 实现：`src/job_matching/annotation/`、`src/job_matching/independent_eval/`、`scripts/phase4_3a/`
- 标注操作细则：[`annotation-guidelines.md`](annotation-guidelines.md)
- 阶段产物与实测结论：`reports/phase4-3a/`

本协议评价的是**模型在真实求职语境下的人岗适配判断能力**，
不是模型对旧评分公式（`final_score` / `label_strength` / `candidate_rank`）的拟合程度。
任何引用本协议结果的报告，必须同时引用「五、结论纪律」。

---

## 〇、三类状态必须分开表述

| 概念 | 含义 | 当前状态 |
|---|---|---|
| 已执行的工程任务 | 代码/脚本/流水线已实现并可运行 | 见 `reports/phase4-3a/phase4-3a-acceptance.md` |
| 已通过的实验验收 | 自动化测试与门禁通过 | 见 `reports/phase4-3a/test-results.json` |
| 尚未验证的真实业务有效性 | 需要真实人工标注（人工Gold）才能声称 | **未验证**（`annotation_status=pending`） |

「工程就绪」≠「模型有效」。任何把工程通过写成模型达到某准确率的表述都属于违规结论。

## 一、评价单位

基本评价单位是 **(一份简历, 一个岗位 JD) 的配对（pair）**。

| 字段 | 说明 | 必填 |
|---|---|---|
| `pair_id` | 配对唯一 ID（`pair-<sha12>`，由 `content_hash` 派生，确定性） | 是 |
| `resume_id` | 简历 ID | 是 |
| `job_id` | 岗位 ID | 是 |
| `resume_source` / `job_source` | 数据来源标识（含子集/文件），必须可追溯 | 是 |
| `resume_text` / `job_text` | 原始文本（导出前必须脱敏，见 `pii.py`） | 是 |
| `job_category` | 岗位类别（注明 `job_category_source` 是否启发式） | 是 |
| `language` | `zh` / `en` / `mixed`，按 CJK 字符占比判定 | 是 |
| `graduation_cohort` | 简历侧毕业届别（可空） | 否 |
| `employment_type` | 就业类型（实习/全职/校招等，可空） | 否 |
| `required_skills` / `preferred_skills` | 岗位必备/加分技能（启发式抽取，仅供标注辅助，**不是真值**） | 否 |
| `education_requirement` | 岗位学历要求（原始表达 + 规范 token） | 否 |
| `experience_requirement` | 岗位经验要求（原始表达 + 规范年限） | 否 |
| `city` / `salary_expectation` | 求职城市 / 薪资期望：**独立维度**，不进入专业能力真值标签 | 否 |
| `difficulty_tier` | 候选池抽样难度层（见三） | 是 |
| `content_hash` | 规范化文本 SHA-256（resume_text + job_text） | 是 |
| `dataset_version` | 数据集版本号（冻结时写入） | 是 |
| `is_synthetic` / `pair_provenance` | 是否合成样本、样本来源组合 | 是 |
| `eligible_for_gold` | 是否允许进入人工真值（合成样本恒为 `false`） | 是 |
| `split` | `dev_validation`（开发选型）/ `blind_test`（最终盲测） | 冻结时分配 |

`content_hash = SHA256(normalize(resume_text) + "\\x1f" + normalize(job_text))`，
`normalize` 为 NFKC + 空白折叠 + 去首尾空白（`job_matching.core.norm_text`），
保证同一文本恒得同一 ID，与历史产物口径一致。

## 二、人工匹配标签

### 2.1 标签取值

| 值 | 含义 |
|---|---|
| `0` | 明显不匹配 |
| `1` | 部分匹配 |
| `2` | 高度匹配 |
| `unjudgeable` | 资料不足或信息自相矛盾，**无法可靠判断** |

`unjudgeable` 是独立状态，**不是** 0。把「缺少信息」判为「不匹配」是违规标注。
`unjudgeable` 不参与 κ 计算，单独统计（见四）。

### 2.2 判定依据（按顺序评估，可多条）

1. **必备技能满足程度**（`required_skills` 与简历技能/项目经历的对应）
2. **岗位职责与实际项目经历的关联**（不是关键词命中数）
3. **资格要求**：学历要求、毕业届别等硬性条件
4. **工作经验要求**：年限与方向
5. **核心技术方向一致性**（方向一致但职责不同 ≠ 高度匹配）

硬性条件（学历/经验/方向）不满足时，`relevance` 上限为 1；
只有 4/5 项依据均无法获得证据时才允许 `unjudgeable`。

### 2.3 不进入真值标签的维度

求职城市、薪资期望、用户个人偏好、企业风险（`all_df.scam_probability`）等
一律**不得**写入 `relevance` 的判断依据。它们是独立的过滤/偏好维度，
如需评估应单独出指标（`preference_filter` 口径）。

## 三、候选样本池

### 3.1 数据来源与用途限制

| 来源 | 语言 | 用途 | 限制 |
|---|---|---|---|
| `data/raw/job-education/*` | 中文 JD | 岗位侧候选池（有 JD 文本） | Apache-2.0；`default/*` 为线上伪标注 |
| `data/raw/other/all_df.csv` | 中文 | 岗位资格字段补充 | **来源与许可 UNKNOWN**，无 JD 文本 |
| `data/raw/job-resume-matching/*` | **英文** | 流程验证用 | **禁止**充当中国大学生就业画像数据；许可状态不明确 |

**数据缺口（必须显式登记）**：本地**没有**真实中文简历。
英文简历（9,544 条）不得直接当作中文求职语料；任何中文简历-岗位配对
在真实中文简历导入（授权 + 脱敏）之前都无法建立。
合成简历可以建立**单独测试池**（`is_synthetic=true`, `eligible_for_gold=false`），
但不得冒充真实人工评估数据。

### 3.2 规模目标（真实数据优先，禁止凑数）

- 30–50 份**经授权**的中文简历（当前 0 份 → 缺口）
- 100–200 条有效中文招聘 JD（当前可达成）
- 300–600 个待人工评估配对（依赖简历导入）

### 3.3 难度层（抽样必须覆盖）

| `difficulty_tier` | 定义（启发式，基于技能/条件字段） |
|---|---|
| `high_skill_overlap` | 技能重合度高 |
| `medium_skill_overlap` | 技能重合度中等 |
| `same_direction_diff_duties` | 标题/方向接近但技能重合低（职责不同） |
| `hard_requirement_gap` | 学历或经验等硬性条件存在差异 |
| `cross_category_negative` | 明显跨岗位类别 |

困难负样本候选**只是待标注对象**，人工确认前不得赋 0。

### 3.4 抽样与去重

- 固定随机种子（`configs/data_pipeline.yaml -> seeds` 派生，默认 `20261210`），同种子必得同结果；
- 按 `job_category` 分层采样；
- 简历级、岗位级、配对级三级去重：完全重复 → 规范化文本重复 → 近似重复
  （字符 3-gram shingle Jaccard ≥ 0.90 视为近重复）；
- 输出来源与 `content_hash` 清单、抽样策略与覆盖度报告。

## 四、双人独立标注与仲裁

### 4.1 盲标

- ≥2 名标注员独立作答，各自一份 CSV（模板 `annotations_A.csv` / `annotations_B.csv`）；
- 标注界面/文件中**不得**出现待评估模型的预测分数，也**不得**出现另一位标注员的答案；
- 标注记录字段：`annotator_id`、`pair_id`、`relevance`、`confidence`、`reason`、
  `evidence`、`annotation_timestamp`、`protocol_version`；
- `evidence` 必须引用简历/JD 的具体片段（导出时脱敏），`reason` 说明判定依据编号（2.2 的 1–5）；
- `confidence ∈ {high, medium, low}`。

### 4.2 仲裁

- 两人 `relevance` 不同（含 `unjudgeable` vs 0/1/2）→ 进入仲裁；
- 仲裁员给出 `final_relevance` + 理由 + 证据，写入 `arbitration.csv`；
- **保留两份原始标注、仲裁记录与最终标签**，任何环节都不得覆盖原始记录；
- 两人同判 `unjudgeable` → 最终标签 `unjudgeable`，不进入排序指标分母。

### 4.3 导入校验（`annotation/importer.py`）

`pair_id` 存在、标签值合法、`annotator_id` 已登记、同人同样本无冲突重复、
`unjudgeable` 未被强行归类、无模型输出列（`model_score`/`pred_*`/`final_score` 等拒收）、
`annotator_id` 不得是机器标识、全表 `protocol_version` 一致。

## 五、标注一致性分析

对（标注员 A, 标注员 B）在**双方都有可判定标签**的样本上计算：

| 指标 | 说明 |
|---|---|
| 原始一致率 | 一致样本数 / 双方可判定样本数 |
| Cohen's Kappa | 标准公式，期望一致率 = 1 时不可计算 |
| Weighted Kappa | 有序标签 {0,1,2}，线性权重为主，二次权重为辅 |
| 分歧样本统计 | 数量、分歧矩阵、`unjudgeable` 分布 |
| 按岗位类别一致性 | 每类样本量 + 各指标 |

**不可计算的显式标记**：单人标注、无重叠样本、某类别样本量 < 5、
标签分布退化（期望一致率 = 1）时，输出 `status="not_computable"` 与 `reason`，
**禁止**填充 0 或任何虚假一致性数值。

## 六、评估指标（`independent_eval/metrics.py`）

统一口径（与 `metrics_ranking.evaluate_ranking` 完全一致的组内排序与 tie-breaking：
分数相同按原始行序稳定排序）：

| 指标 | 定义 |
|---|---|
| Precision@5 | top-5 中 `relevance ≥ 1` 的比例；分母 = `min(5, 组内候选数)` |
| Recall@10 | top-10 命中的相关项数 / 该组相关项总数（`relevance ≥ 1`） |
| NDCG@5 / NDCG@10 | 增益 = 有序相关性 {0,1,2}，折损 `1/log2(rank+1)` |
| MRR | 首个 `relevance ≥ 1` 项的倒数排名（在 top-10 内） |
| 有效查询组数量 | `queries_total` / `queries_size_ge_2` / `queries_evaluated` / `queries_skipped` |

口径细则：

- **查询组 = 一份简历**（`resume_id`），组内候选 = 该简历配对到的岗位；
- `min_group_size_for_ranking = 2`（沿用 `configs/matching_splits.yaml`）；
- `unjudgeable` **不计入**增益、不计入相关项、不计入分母（在组内排序时跳过并计数）；
- 相关性阈值 = `relevance ≥ 1`（`2` 为高相关，`1` 为部分相关）；
- 候选池构成必须随指标一起报告（每个查询组的候选来源与难度层构成）；
- 组内候选数不足 K 时按实际组大小截断，分母见上。

## 七、统计推断（配对 Bootstrap）

- 重采样单位 = **查询组（简历）**，绝不把同一简历的多个 pair 当独立样本；
- 同一次 Bootstrap 中，所有模型使用**完全相同**的重采样组（固定种子，
  实现复用 `evaluation/statistical_tests.bootstrap_diff`，其确定性保证同种子同组）；
- 默认 `n_boot=1000`，种子默认 `20261205`；
- 输出模型 − 基线的均值差、95% 置信区间、原始指标与有效组数；
- **有效查询组 < 20 时**必须报告 `statistical_stability="unstable"`，
  不得声明「显著优于 Baseline」。

## 八、基线与模型适用性

| 方法 | 是否可直接用于真实中文 JD 评估 | 说明 |
|---|---|---|
| 关键词/技能重合 Baseline | 是 | `required_skills` × 简历技能 Jaccard |
| TF-IDF Cosine Baseline | 是 | 字符 + 词 n-gram，评估集内拟合 IDF |
| Embedding Cosine | **否** | 预计算 embedding 仅覆盖英文数据集，编码器未知 |
| Ridge / GBDT / MLP / RankNet | **有条件** | 特征只依赖白名单原始字段，可前向计算；但训练标签为英文代理标签、技能规范化词表为英文，结果只作参考，**不得**作为中文真实适配结论 |

不允许为了让某个模型参加对比而制造不可获得的线上输入；
特征无法从真实 pair 原始字段重建的模型，登记为 `applicable=false` 并显式报错。

## 九、模型选型与冻结

- **开发选型只允许使用 `dev_validation`**；`blind_test` 单独冻结，禁止反复调参；
- 最终生产模型的选型结论标记为 **BLOCKED**，直到：
  1) 取得经授权的真实中文简历与 JD；2) 双人标注完成并通过一致性检查；
  3) 验证集与盲测集隔离；4) 无阻断性泄漏。
- 不得依据历史伪标签 NDCG 宣布最终生产模型。

### 冻结规范（`annotation/freeze.py`）

冻结必须生成：数据集版本号、标签协议版本号、样本数量、来源统计、标签分布、
互斥检查结果（pair 唯一、split 隔离、无重复）、文件 SHA-256、冻结时间、
数据来源与人工标注责任记录。冻结后禁止静默修改；修改必须升版本号。

## 十、结论纪律

1. 任何指标必须标注标签来源（人工 Gold / 伪标签 / 合成）。
2. 无真实人工 Gold 时，`annotation_status=pending`、`blind_evaluation_status=blocked`，
   **禁止**输出正式性能数值。
3. 泄漏检查只能证明「未发现已知泄漏」；预训练语料来源不可知，
   **不能**宣称绝对无泄漏。
4. 合成样本、英文简历、伪标签不得混入中文人工真值。
5. 失败测试与不可计算指标必须如实呈现，禁止隐藏或降标准。

## 十一、版本

| 版本 | 日期 | 变更 |
|---|---|---|
| phase4-3a-protocol-v1 | 2026-10-29 | 首版：评价单位、三级标签 + unjudgeable、双人标注与仲裁、一致性口径、指标与 Bootstrap、适用性登记、冻结规范 |
