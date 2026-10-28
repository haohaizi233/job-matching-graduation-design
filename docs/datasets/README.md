# 数据集索引（Dataset Index）

- 建立时间：2026-10-28
- 项目根目录：`D:\desktop\毕业设计`
- 路径基准：下文「本地路径」均为相对项目根目录
- **编制原则**：只登记实测或有本地证据可核的字段。凡无法从本地文件证实的信息，一律标记为
  `UNKNOWN（本地无证据）`，**不做推测**。

> 行数由 `pandas.read_csv(chunksize=50000)` 分块累加得到（2026-10-28 实测），不按文本行数估算，
> 因此对含换行的多行文本字段也是准确的。字节数为 `os.path.getsize` 实测值。

---

## 总览

| # | 数据集 | 本地路径 | 文件数 | 总大小 | 训练用途 | 清洗状态 |
|---|---|---|---:|---:|---|---|
| 1 | job-resume-matching（人岗匹配） | `data/raw/job-resume-matching/` | 3 个 CSV + HF 元数据 | 235.2 MB | 人岗画像、语义匹配、排序建模 | 已完成（数据卡声明无缺失值，实测一致） |
| 2 | job-education（岗位→学历抽取） | `data/raw/job-education/` | 4 个 CSV + HF 元数据 | 354.5 MB | 岗位学历要求抽取（seq2seq / 对话式） | 已完成（train/validation/test 切分齐备） |
| 3 | all_df.csv（中文招聘岗位风险表） | `data/raw/other/all_df.csv/` | 1 个 CSV | 23.8 MB | 岗位结构化字段、招聘风险/欺诈判别 | **UNKNOWN（本地无证据）** |
| — | chinese-skillspan-benchmark | `chinese-skillspan-benchmark/` | — | ~700 MB | **另一独立研究项目**，不属于本毕业设计数据集 | 不适用 |

---

## 1. job-resume-matching —— 人岗匹配数据集

**本地路径**：`data/raw/job-resume-matching/`

| 文件 | 字节数 | 编码 | 列数 | 行数 |
|---|---:|---|---:|---:|
| `cv.csv` | 194,020,617 | UTF-8（无 BOM） | 11 | **9,544** |
| `job.csv` | 32,930,476 | UTF-8（无 BOM） | 10 | **1,167** |
| `matches.csv` | 19,704,065 | UTF-8（无 BOM） | 13 | **122,560** |
| `README.md` | 9,935 | UTF-8 | — | HF 数据集卡片 |
| `.gitattributes` | 2,639 | UTF-8 | — | HF LFS 规则 |
| `.cache/huggingface/` | ~3 KB | — | — | HF `local_dir` 下载元数据 |

**数据来源**
- 本地证据：目录是 Hugging Face `snapshot_download(local_dir=...)` 快照
  （`.cache/huggingface/download/` 下有 `cv.csv`/`job.csv`/`matches.csv`/`README.md`/`.gitattributes` 五个 `.metadata`）。
- **具体 repo id：UNKNOWN（本地无证据）**。`.metadata` 仅含 etag/sha/时间戳，不含仓库名字符串；
  卡片末尾的 Citation URL 仍是占位符 `https://huggingface.co/datasets/<your-username>/<your-dataset-name>`。
- **下载日期：UNKNOWN（本地无证据）**。
- 本地文件清单与字段结构与该卡片的数据字典逐项一致，可确认「内容与该卡片描述相符」，
  但**不能据此断言仓库名**。此前的 `reports/environment-acceptance.md` 也作同样结论（未联网核对）。

**主要字段**
- `cv.csv`：`candidate_id`、`source_row`、`target_position`、`resume_text`、`clean_skills`、`clean_skills_json`、`education_text`、`experience_text`、`years_experience`、`inferred_category`、`embedding`
- `job.csv`：`job_id`、`job_title`、`category`、`job_description`、`job_text`、`clean_skills`、`clean_skills_json`、`education_text`、`years_required`、`embedding`
- `matches.csv`：`candidate_id`、`job_id`、`final_score`、`raw_score`、`label_strength`、`semantic_score`、`skill_score`、`position_score`、`category_score`、`experience_score`、`education_score`、`candidate_rank`、`candidate_rank_pct`

**已知标签类型**
- `label_strength` 三档（实测分布）：`medium_positive` 70,636 / `weak_positive` 51,150 / `strong_positive` 774
- `cv.inferred_category`、`job.category`：`INFORMATION-TECHNOLOGY`、`BUSINESS-DEVELOPMENT`、`FINANCE`、`SALES`、`HR`（`cv` 另有 `UNKNOWN` 16 条）

**关联键完整性（实测）**：`matches.csv` 的 9,532 个 `candidate_id` 100% 命中 `cv.csv`；1,164 个 `job_id` 100% 命中 `job.csv`。

**训练用途**：候选人/岗位画像、语义检索、Learning-to-Rank、混合匹配模型、二分类（需自行采样负例）。

**许可证**：卡片 front-matter 写 `license: mit`，但卡片正文 “License” 一节明确写着
*“Please update the dataset license before publishing.”* —— **两者不一致，实际授权状态
以 UNKNOWN 处理**，使用前须向数据提供方确认。

**数据清洗状态**：已完成。卡片声明全列无缺失，实测前 2000 行空值合计 0，与声明一致。
`embedding` 为字符串化的 768 维向量，需 `ast.literal_eval` + `np.array(..., dtype=np.float32)` 还原（实测维度 (768,)）。

**使用限制**
- `matches.csv` **只含正样本**。做二分类或成对排序必须自行采样负例，并按 `candidate_id` 切分，
  否则同一候选人跨集合会高估性能（卡片 “Recommended Train/Validation/Test Splitting” 明确要求）。
- 卡片声明：embedding 的生成模型未知；覆盖的岗位类别有限；不得把模型分数当作最终录用决策。

---

## 2. job-education —— 岗位学历解析数据集

**本地路径**：`data/raw/job-education/`

| 文件 | 字节数 | 编码 | 列数 | 行数 |
|---|---:|---|---:|---:|
| `default/train/19w_0701.csv` | 250,645,425 | UTF-8（无 BOM） | 9 | **197,574** |
| `default/validation/4w_0708.csv` | 60,517,865 | UTF-8（无 BOM） | 9 | **45,593** |
| `default/test/2w_0716.csv` | 30,340,189 | UTF-8（无 BOM） | 9 | **22,730** |
| `annotated/2w_0716_eval.csv` | 30,251,826 | UTF-8（无 BOM） | 12 | **22,730** |
| `README.md` / `.gitattributes` / `.cache/huggingface/` | ~5 KB | — | — | HF 数据集卡片 + LFS 规则 + 下载元数据 |

**数据来源**（本地 README 有明确声明）
- 卡片标题：*Job Educational Parser Dataset*（招聘领域的岗位与学历要求数据集）
- 创建者：**@wangzihaogithub**（README 末句 “由 @wangzihaogithub 创建。”）
- 任务：`text-generation`；语言：`zh`；规模标签：`100K<n<1M`
- 本地同样为 HF `snapshot_download(local_dir=...)` 快照（`.cache/huggingface/download/` 下有 6 个 `.metadata`）
- **具体 repo id：UNKNOWN（本地无证据）**；**下载日期：UNKNOWN（本地无证据）**

**主要字段**
- 三个 `default/*` 切分字段相同（9 列）：
  `job_id`、`system`、`user`、`assistant`、`id`、`user_short`、`ai`、`diff`、`user_short2`
  - `user`：职位描述；`assistant`：要求的学历（如 `博士、硕士、本科`，从高到低）
- `annotated/2w_0716_eval.csv`（12 列）：
  `job_id`、`user`、`assistant`、`线上学历-旧的`、`id`、`user_short`、`模型结果-新的`、`diff`、
  `人工正确结果`、`【线上学历-旧的】是否正确`、`【模型结果-新的】是否正确`、`是否英文岗位`
  - 该文件是**人工标注评测集**，含新旧模型对比与人工正确结果，可直接用于评测指标计算

**已知标签类型**
- 输出为学历要求串（`博士`/`硕士`/`本科`/`大专` 等，从高到低排列）
- `annotated` 集另含布尔判定列 `【线上学历-旧的】是否正确`、`【模型结果-新的】是否正确`

**训练用途**：岗位描述 → 学历要求的抽取/生成（可作 seq2seq 或对话式微调）；
`annotated/2w_0716_eval.csv` 作为人工评测基准。

**许可证**：卡片 front-matter 声明 **`license: apache-2.0`**（本地文件可核）。

**数据清洗状态**：已完成。train/validation/test 三个切分齐备，`user`/`assistant` 实测无空值、
文本长度正常。**注意字段含换行，不要用文本编辑器打开，请用 pandas 读取。**

---

## 3. all_df.csv —— 中文招聘岗位风险表

**本地路径**：`data/raw/other/all_df.csv/all_df.csv`
（保留原始目录结构：外层目录名与内层文件名均为 `all_df.csv`）

| 文件 | 字节数 | 编码 | 列数 | 行数 |
|---|---:|---|---:|---:|
| `all_df.csv` | 24,912,302 | **UTF-8 带 BOM** | 8 | **251,381** |

**主要字段**：`job_name`、`company_name`、`job_salary`、`work_experience`、`educational_requirements`、
`company_address`、`job_type`、`scam_probability`

**已知标签类型**：`scam_probability` 为招聘风险/欺诈概率（连续值）。取值范围与标注方式
**UNKNOWN（本地无证据）** —— 目录内无 README、无元数据、无 `.gitattributes`。

**数据来源**：**UNKNOWN（本地无证据）**。
**许可证**：**UNKNOWN（本地无证据）**。
**下载日期**：**UNKNOWN（本地无证据）**。
**数据清洗状态**：**UNKNOWN（本地无证据）**；实测仅确认 8 列齐全、前 2000 行无空值、可被 `utf-8-sig` 完整解码。

**训练用途**：中文招聘岗位结构化字段（岗位名、公司、薪资、经验、**学历要求**、地址、类型），
与本设计的「岗位画像 + 学历要求」方向直接相关；`scam_probability` 可用于招聘风险判别子任务。
**使用前须先补齐来源与授权说明。**

---

## 4. 其他（不计入本项目数据集）

### chinese-skillspan-benchmark

- 路径：`chinese-skillspan-benchmark/`（项目根目录，**2026-10-28 整理时未迁移**）
- 性质：**完全独立的 Git 仓库**（remote `github.com/AlfredJamesLi/chinese-skillspan-benchmark`，
  含自己的 `LICENSE`、`CITATION.cff`、`CHANGELOG.md`、`requirements-*.txt`、`.gitignore`）
- 与本项目的关系：另一研究项目（中文岗位技能跨度抽取基准）；根 `.env.example` 中
  `CNSS_PAPER_ROOT` / `CNSS_CN_FONT` 等变量即为其论文图表工程预留
- **不纳入本毕业设计的数据集管理与统计**，其内部数据由该仓库自己的 `docs/`、`DATA_AVAILABILITY.md` 管理

---

## 完整性基线

所有原始数据文件的 SHA-256 见 `reports/workspace-migration-manifest.json`，
可用下面命令随时复核：

```powershell
$py = "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe"
& $py "D:\desktop\毕业设计\scripts\verify_data_integrity.py"
```

## 维护约定

1. 新增数据集必须在本文件登记，未知项写 `UNKNOWN（本地无证据）`，不要猜。
2. 原始数据只读；清洗产物写 `data/interim/`，最终输入写 `data/processed/`（见 `data/README.md`）。
3. 行数/字段变更必须重新实测并更新本文件，同时更新 SHA-256 基线。
