# 数据集结构、规模与质量画像

- **审计日期**：2026-10-28
- **项目**：《大学生就业岗位画像与简历智能匹配系统的设计与实现》
- **审计范围**：`data/raw/` 下 8 个 CSV（`chinese-skillspan-benchmark/` 独立仓库未扫描、未修改）
- **执行方式**：全部结论来自实际执行 `scripts/data_audit/` 下脚本后的计算结果
- **约束遵守**：未改写 `data/raw`、未创建训练集、未训练模型、未下载权重、未联网、未改依赖
- **机器可读明细**：`reports/data-audit/dataset-profile.json`、`reports/data-audit/audit-summary.json`

> 报告中不输出简历全文、联系方式、公司名称与住址原文，只给统计量与长度分布。

---

## 1. 文件清单与规模

| # | 相对路径 | 大小 | 编码 | 行数 | 列数 | 整行重复 |
|---|---|---:|---|---:|---:|---:|
| 1 | `data/raw/job-resume-matching/cv.csv` | 185.0 MB | UTF-8 无 BOM | 9,544 | 11 | 0 |
| 2 | `data/raw/job-resume-matching/job.csv` | 31.4 MB | UTF-8 无 BOM | 1,167 | 10 | 0 |
| 3 | `data/raw/job-resume-matching/matches.csv` | 18.8 MB | UTF-8 无 BOM | 122,560 | 13 | 0 |
| 4 | `data/raw/other/all_df.csv/all_df.csv` | 23.8 MB | **UTF-8 带 BOM** | 251,381 | 8 | **25,433（10.12%）** |
| 5 | `data/raw/job-education/default/train/19w_0701.csv` | 239.0 MB | UTF-8 无 BOM | 197,574 | 9 | 0 |
| 6 | `data/raw/job-education/default/validation/4w_0708.csv` | 57.7 MB | UTF-8 无 BOM | 45,593 | 9 | 0 |
| 7 | `data/raw/job-education/default/test/2w_0716.csv` | 28.9 MB | UTF-8 无 BOM | 22,730 | 9 | 0 |
| 8 | `data/raw/job-education/annotated/2w_0716_eval.csv` | 28.8 MB | UTF-8 无 BOM | 22,730 | 12 | 0 |

**关键观察**

- `job-education` 的 CSV **不在数据源目录顶层**，而是位于 `default/train|validation|test` 与 `annotated` 四个子目录；`other/all_df.csv/` 本身是一个同名子目录，真实文件是 `other/all_df.csv/all_df.csv`。三处路径均已按实际发现结果定位。
- 各数据源目录下存在 `.cache/huggingface/` 下载元数据与 `.gitattributes`（LFS 规则），说明是 Hugging Face 数据集仓库快照；CSV 实体为完整数据，不是 LFS 指针。
- 8 个文件的完整 SHA-256 已写入 `reports/data-audit/audit-summary.json` 的 `data_files` 段（复用 `scripts/hash_datasets.py` 的流式实现）。

---

## 2. 三个主表（`cv.csv` / `job.csv` / `matches.csv`）

### 2.1 `cv.csv` —— 候选人画像表（9,544 行 × 11 列）

| 字段 | 类型 | 缺失 | 唯一值 | 关键统计 |
|---|---|---:|---:|---|
| `candidate_id` | object | 0 | **9,544（唯一主键）** | 无重复 |
| `source_row` | int64 | 0 | 9,544 | 0 ~ 9,543，与行号一一对应 |
| `target_position` | object | 0 | 28 | 长度 10~87，中位 24 |
| `resume_text` | object | 0 | 9,544 | 长度 493~3,000，中位 1,301，均值 1,398 |
| `clean_skills` | object | 0 | 7,971 | 长度 2~1,514，中位 378；20 行长度 ≤3 |
| `clean_skills_json` | object | 0 | 7,971 | 与 `clean_skills` 内容等价的 JSON 形式 |
| `education_text` | object | 0 | 6,645 | 长度 18~959，中位 151 |
| `experience_text` | object | 0 | 9,404 | 长度 161~1,746，中位 547 |
| `years_experience` | float64 | 0 | 16 | 0 ~ 31，均值 5.55，标准差 4.40 |
| `inferred_category` | object | 0 | 6 | IT 8,140 / FINANCE 1,010 / SALES 215 / BUSINESS-DEV 83 / HR 80 / UNKNOWN 16 |
| `embedding` | object | 0 | 9,544 | 字符串化的 768 维向量（详见 `embedding-analysis.md`） |

**异常与风险**

- `inferred_category` **极度不平衡**：INFORMATION-TECHNOLOGY 占 85.3%，HR 仅 80 条。按类别分层评估时小类样本不足。
- `resume_text` 最大长度被截断在 **3,000 字符**（`job_text` 截断在 3,500），说明上游已做过截断，长简历信息有损。
- `clean_skills` 有 20 行长度 ≤3（近似空），做技能匹配时需单独处理。
- `target_position` 只有 28 个唯一值，粒度很粗，不足以做岗位分类的多分类目标。

### 2.2 `job.csv` —— 岗位画像表（1,167 行 × 10 列）

| 字段 | 类型 | 缺失 | 唯一值 | 关键统计 |
|---|---|---:|---:|---|
| `job_id` | int64 | 0 | **1,167（唯一主键）** | 无重复 |
| `job_title` | object | 0 | 720 | 长度 10~147，中位 33 |
| `category` | object | 0 | 5 | IT 240 / BUSINESS-DEV 239 / FINANCE 236 / SALES 232 / HR 220（**接近均匀**） |
| `job_description` | object | 0 | 1,167 | 长度 167~13,639，中位 3,445 |
| `job_text` | object | 0 | 1,167 | 长度 364~**3,500（硬截断）** |
| `clean_skills` | object | 0 | 1,167 | 长度 58~913，中位 276 |
| `clean_skills_json` | object | 0 | 1,167 | 同上 JSON 形式 |
| `education_text` | object | 0 | 1,167 | 长度分布与 `job_description` **完全一致** |
| `years_required` | float64 | 0 | 56 | 0 ~ 40，均值 14.30，标准差 12.63 |
| `embedding` | object | 0 | 1,167 | 字符串化 768 维向量 |

**异常与风险**

- `education_text` 与 `job_description` 长度统计逐项相同，**疑似整列复制**，需在建模时确认是否重复字段（会造成特征冗余）。
- `years_required` 均值 14.3 年、最大 40 年，明显偏离"岗位要求年限"的常规语义（更像职位序列/职级数值），**不能直接当作经验年限使用**。
- `category`（岗位侧）与 `cv.inferred_category`（候选人侧）的分布差异极大：岗位侧近似均匀、候选人侧 85% 是 IT，会造成 `category_score` 的分布偏斜。

### 2.3 `matches.csv` —— 人岗兼容性记录表（122,560 行 × 13 列）

| 字段 | 类型 | 缺失 | 唯一值 | 关键统计 |
|---|---|---:|---:|---|
| `candidate_id` | object | 0 | 9,532 | 外键 → `cv.candidate_id` |
| `job_id` | int64 | 0 | 1,164 | 外键 → `job.job_id` |
| `final_score` | float64 | 0 | 122,560 | 0.4300 ~ 0.7561，均值 0.5857 |
| `raw_score` | float64 | 0 | 122,557 | 0.3060 ~ 0.6516，均值 0.4359 |
| `label_strength` | object | 0 | 3 | weak 51,150 / medium 70,636 / strong 774 |
| `semantic_score` | float64 | 0 | — | 0.5805 ~ 0.9177，均值 0.7812 |
| `skill_score` | float64 | 0 | — | 0.0000 ~ 0.6170，均值 **0.0581** |
| `position_score` | float64 | 0 | — | 0.0229 ~ 1.0000，均值 0.2656 |
| `category_score` | float64 | 0 | — | 0.0000 ~ 1.0000，均值 0.8847 |
| `experience_score` | float64 | 0 | — | 0.0000 ~ 1.0000，均值 0.6765 |
| `education_score` | float64 | 0 | — | 0.3000 ~ 1.0000，均值 0.8974 |
| `candidate_rank` | int64 | 0 | 122 | 1 ~ 122 |
| `candidate_rank_pct` | float64 | 0 | 6,393 | 0.3832 ~ 1.0，均值 0.9353 |

**关联完整性（已实测）**

- `candidate_id`、`job_id` 在主表中**均为唯一主键**，无重复。
- `matches` 中的 9,532 个 `candidate_id` **100% 命中** `cv.csv`；1,164 个 `job_id` **100% 命中** `job.csv`；**0 个孤儿键**。
- `cv.csv` 有 **12 个候选人从未出现在 `matches.csv`**；`job.csv` 有 **3 个岗位从未出现**。
- `(candidate_id, job_id)` 组合 **122,560 个全部唯一**，无重复组合，因此**不存在标签冲突**。
- 观测组合只占全交叉积（9,544 × 1,167 = 11,137,848）的 **1.10%**。

**度分布**

| 指标 | min | p25 | 中位 | p75 | max | 均值 |
|---|---:|---:|---:|---:|---:|---:|
| 每个候选人的岗位数 | 1 | 7 | 11 | 18 | 122 | 12.86 |
| 每个岗位的候选人数 | 1 | 9 | 19 | 122.25 | 500 | 105.29 |

候选人度分布长尾（1~122），岗位度分布更长尾（1~500）。60 个候选人只对应 1 个岗位，这些组**无法做组内排序评估**。

---

## 3. 学历解析数据（`job-education/`）

| 文件 | 行数 | 主键 `job_id` | 输入 `user` 中位长度 | `assistant` 缺失 |
|---|---:|---:|---:|---:|
| `default/train/19w_0701.csv` | 197,574 | 197,531 唯一 | 324 | **0** |
| `default/validation/4w_0708.csv` | 45,593 | 45,593 唯一 | 342 | **0** |
| `default/test/2w_0716.csv` | 22,730 | 22,730 唯一 | 348 | **21,994（96.76%）** |
| `annotated/2w_0716_eval.csv` | 22,730 | 22,730 唯一 | 348 | `人工正确结果` 缺 **21,994** |

**字段结构**（9 列 / 12 列）

- `system`：常量 `"从岗位中提取学历"`（唯一值 1）
- `user`：`<岗位名称>…</岗位名称><岗位描述>…</岗位描述><学历描述>…</学历描述>` 三段 XML-like 拼接；`<岗位名称>` 覆盖率 99.98%、`<岗位描述>` 99.999%、**`<学历描述>` 99.997%**
- `assistant`：学历标签短串（如 `博士、硕士、本科`）
- `user_short`：精简版输入（缺失极少）
- `ai`：另一路模型输出（见下）
- `diff`：`ai == assistant` 的布尔标记（train 中 `True` 191,814 行 = 97.09%，与 `ai`/`assistant` 逐行一致率 97.09% 吻合）
- `user_short2`：**整列全空**（24 个文件×行集合全部 NaN），可直接忽略
- `id`：train 中有 12 个缺失、11 行重复；val/test 中唯一

**`annotated/2w_0716_eval.csv` 额外列**

| 列 | 非空行数 | 含义 |
|---|---:|---|
| `线上学历-旧的` | 22,730 | 旧线上系统输出 |
| `模型结果-新的` | 22,730 | 新模型输出 |
| `人工正确结果` | **736** | 人工复核金标准 |
| `【线上学历-旧的】是否正确` | 736 | 人工判定（True 338 / False 398） |
| `【模型结果-新的】是否正确` | 736 | 人工判定（True 300 / False 436） |
| `是否英文岗位` | 33 | 仅 33 行标记为 1 |

**缺失值总览**

| 文件 | 有缺失的列 |
|---|---|
| train | `id`(12)、`user_short`(22)、`diff`(12)、`user_short2`(100%) |
| validation | `user_short`(5)、`user_short2`(100%) |
| test | `assistant`(96.76%)、`user_short`(1)、`user_short2`(100%) |
| annotated | `assistant`(96.76%)、`user_short`(1)、`人工正确结果`(96.76%)、两个正确性判定列(96.76%)、`是否英文岗位`(99.86%)、`user_short2`(100%) |

**切分包含关系（重要）**

| 对 | `job_id` 重叠 | `user` 文本重叠 | 是否子集 |
|---|---:|---:|---|
| train ∩ validation | 0 | 1 | 否 |
| train ∩ test | 0 | 1 | 否 |
| **validation ∩ test** | **22,730（100% of test）** | **21,433（100% of test）** | **test ⊂ validation** |

**内部重复**：`user` 文本在 train/val/test 内分别有 6.50% / 6.05% / 5.71% 的重复行。

---

## 4. 中文招聘风险数据（`other/all_df.csv/all_df.csv`）

251,381 行 × 8 列，UTF-8 带 BOM，**整行重复 25,433 行（10.12%）**。

| 字段 | 类型 | 缺失 | 唯一值 | 关键统计 |
|---|---|---:|---:|---|
| `job_name` | object | 0 | 106,326 | 长度 1~59，中位 7；11,814 行长度 ≤3 |
| `company_name` | object | 0 | 116,734 | 长度 1~80，中位 5；31,932 行长度 ≤3 |
| `job_salary` | float64 | 0 | 1,282 | **450 ~ 4,597,500**，均值 22,195，中位 8,500 |
| `work_experience` | object | 0 | 4 | `1-5年` 165,323 / `无需经验` 51,030 / `5-10年` 31,201 / `10年以上` 3,827 |
| `educational_requirements` | object | 0 | 4 | `大专及以下` 129,657 / `本科` 112,932 / `硕士` 8,019 / `博士` 773 |
| `company_address` | object | 0 | 7,128 | 长度 2~22，中位 9 |
| `job_type` | int64 | 0 | 7 | 0~6，均值 3.98（**编码含义未在数据中给出**） |
| `scam_probability` | int64 | 0 | **9** | 0~80，见第 5 节 |

**异常与风险**

- `job_salary` 最大值 4,597,500 元/月，p99 = 375,000，**存在极端离群值**；p25 = p5 = 4,500，疑似有下限截断。
- `job_name` / `company_name` 有大量超短串（≤3 字符 11,814 / 31,932 行），多为占位或截断值。
- 该表**没有 `candidate_id` / `job_id`**，与主匹配数据集没有可靠连接键。

---

## 5. `scam_probability` 字段来源判断

**已证实事实**

- 取值域为整数百分数 0~100，但**实际只有 9 个不同取值**：`0, 10, 20, 30, 40, 50, 60, 70, 80`。
- **100% 是 10 的整数倍**，`is_integer_valued = True`。
- 分布：0 → 121,561（48.4%）、10 → 45,580、30 → 36,670、20 → 27,842、40 → 8,976、50 → 7,476、60 → 2,127、70 → 819、80 → 330。
- 表中**不存在**布尔真值列、人工复核结论列、标注来源列或标注者信息。
- 与 `job_salary` 的 Pearson 相关仅 **0.065**。

**实验支持的推断**

- 取值离散、严格落在 10 的倍数网格上、且无任何人工真值列，**强烈提示它是某个风险评分模型/规则输出后再做粗粒度量化的分数**，不是人工核实的诈骗概率。

**无法从数据确定**

- 生成该分数的模型/规则/人工流程未知。
- 分数的校准含义未知（40 是否代表 40% 诈骗概率无法验证）。

**结论**：`scam_probability` **不能作为监督学习的真值标签**。它可作为**弱监督/远监督信号**用于可演示的风险打分模块，但必须在论文与报告中明确标注为"上游风险分数"而非"人工标注诈骗真值"。本阶段不与主匹配数据集合并。

---

## 6. 数据质量总评

| 维度 | 结论 | 证据 |
|---|---|---|
| 可读性 | ✅ 8/8 文件可读 | 逐文件 `pd.read_csv` 成功 |
| 结构有效性 | ✅ 表头与字段类型符合预期 | 主键唯一、外键 100% 命中 |
| 缺失情况 | ⚠️ 局部严重 | test/annotated 的标签列缺 96.76%；`user_short2` 整列全空 |
| 重复情况 | ⚠️ 风险表重复严重 | `all_df.csv` 整行重复 10.12% |
| 主键与关联 | ✅ 无孤儿键、无重复组合 | `(candidate_id, job_id)` 122,560 全唯一 |
| 数值合理性 | ⚠️ 有离群 | `job_salary` 最大 4.6M；`years_required` 最大 40 |
| 文本完整性 | ⚠️ 上游已截断 | `resume_text` ≤3,000、`job_text` ≤3,500 |
| 标签可用性 | ⚠️ 见 `matching-label-analysis.md` | 标签为公式派生，非人工/真实结果 |

**必须在建模前解决的问题**（按优先级）

1. `all_df.csv` 整行去重（25,433 行）。
2. `job-education` 重新切分（test ⊂ validation）。
3. `matches.csv` 无真实负例，需设计负采样方案。
4. 明确 `job-education` 标签是伪标签还是只用 736 条人工金标准。
5. 剔除目标泄漏字段（见 `matching-label-analysis.md` 第 4 节）。
6. 确认 `job.csv` 的 `education_text` 是否为 `job_description` 的冗余副本。
