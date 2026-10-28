# 数据加工流程（第三阶段）

- 流水线版本：`phase3-v1`（`configs/data_pipeline.yaml` -> `pipeline_version`）
- 代码入口：`scripts/data_pipeline/run_all.py`
- 核心实现：`src/job_matching/`
- 配置：`configs/*.yaml`（所有路径、种子、比例、标签映射、批处理限制只从这里取）
- 运行环境：Conda 环境 `graduation-design`（Python 3.11 / NumPy 1.26.4 / pandas 2.2.3）

本文说明**数据从哪里来、经过哪些加工、产出什么、如何重复执行**。
特征能否使用见 `docs/feature-schema.md`，切分与评估口径见 `docs/evaluation-protocol.md`。

## 一、总体原则

1. `data/raw/` 只读。流水线第 1 步先做 SHA-256 基线核对（G1 前置），不一致立即停止。
2. 所有产物带数据版本号 `dv-xxxxxxxxxxxx`，由 8 个原始文件哈希集合推导（内容变则版本变）。
3. 所有随机过程从 `configs/data_pipeline.yaml` 的 `seeds` 取种子，代码中不硬编码。
4. 目标列与输入列**分文件落盘**，只共享关联键。
5. 日志与报告绝不输出简历正文、招聘 JD 原文与联系方式，只记录长度、哈希与计数
   （`configs/data_pipeline.yaml` -> `privacy.forbid_in_logs`）。
6. 任一关键步骤失败立即停止并以非零退出码结束，不继续生成后续产物。

## 二、执行入口

```powershell
conda activate graduation-design
python scripts/data_pipeline/run_all.py            # 全量执行（9 步）
python scripts/data_pipeline/run_all.py --from 5   # 从第 5 步开始
python scripts/data_pipeline/run_all.py --only 6   # 只执行第 6 步
```

- 日志：`reports/phase3-logs/pipeline.log`（UTF-8）
- 每步结果落盘：`reports/phase3-steps/<序号>-<步骤名>.json`
- 失败证据：`reports/phase3-run-failure.json`（含 `failed_step` 与 traceback）

## 三、九个步骤

| # | 步骤 | 实现 | 输入 | 输出 |
|---|---|---|---|---|
| 1 | 原始数据完整性 | `pipeline.step_check_raw_integrity` | `data/raw/**` | 哈希核对结果 + `dataset_version` |
| 2 | Schema 校验 | `pipeline.step_validate_schema` | 7 个原始 CSV | `reports/phase3-schema-validation.json` |
| 3 | 数据规范化 | `preprocess_resume/job/education/risk`、`education_data` | 原始 CSV | `data/interim/**`、`reports/phase3-preprocessing-summary.json` |
| 4 | Embedding 缓存 | `embeddings.build_embedding_cache` | `cv.csv`/`job.csv` 的 embedding 列 | `data/processed/embeddings/**` |
| 5 | 特征构造与泄漏审计 | `pair_features`、`policy` | interim 表 + matches | `data/processed/matching/**`、`data/processed/education/**` |
| 6 | 可信数据切分 | `split_matching`、`education_data` | matches + 规范化学历表 | `data/splits/**`、`reports/phase3-split-summary.json` |
| 7 | 零训练 Baseline | `baseline_ranking`、`baseline_education` | 切分索引 + 特征 + 缓存 | `reports/baselines/baseline-results.json` |
| 8 | 数据质量门禁 G1-G7 | `tests/data_pipeline/run_all.py` | 全部产物 | `reports/data-quality-gates.json` |
| 9 | 报告生成 | `reporting.render_all` | 前 8 步产物 | `reports/*.md` |

步骤 8 内部还会运行 `pip check` 并把证据写入 `reports/dependency-check.json`（验收项 P3-13）。

## 四、输入数据

| 数据集 | 文件 | 角色 |
|---|---|---|
| 人岗匹配 | `data/raw/job-resume-matching/cv.csv` | 简历画像（9,544 行） |
| 人岗匹配 | `data/raw/job-resume-matching/job.csv` | 岗位画像（1,167 行） |
| 人岗匹配 | `data/raw/job-resume-matching/matches.csv` | 匹配记录（122,560 行） |
| 学历 | `data/raw/job-education/default/train/19w_0701.csv` | 伪标注训练池 |
| 学历 | `data/raw/job-education/default/validation/4w_0708.csv` | 伪标注验证池 |
| 学历 | `data/raw/job-education/default/test/2w_0716.csv` | 原 test（实测被 validation 包含，不作测试集） |
| 学历 | `data/raw/job-education/annotated/2w_0716_eval.csv` | 人工金标准（736 条非空） |
| 招聘风险 | `data/raw/other/all_df.csv/all_df.csv` | 仅规范化与元数据登记，本阶段不建模 |

## 五、规范化（步骤 3）

### 5.1 简历 `preprocess_resume.normalize_resume`

- 主键 `candidate_id` 唯一性校验；
- 文本字段 NFKC + 空白折叠 + 去首尾空白（不改写正文语义）；
- 技能解析见 5.3；
- `years_experience` 类型与语义检查（实测 0~31、全为整数）；
- 输出 `data/interim/matching/resume_normalized.csv`。

### 5.2 岗位 `preprocess_job.normalize_job`

第二阶段遗留的两个问题的处置（依据实测，不臆断）：

| 问题 | 实测证据 | 处置 |
|---|---|---|
| `years_required` 最大 40、均值 14.3，含 16.95/20.23 等小数 | `years_required_flag` 统计：`integer_ok`/`fractional`/`zero`/`extreme_high` 分档 | **保留原值 + 标记异常 + 暂时禁用为模型输入**（进入 `uncertain_features`），不得当作真实工作年限 |
| `education_text` 疑似与 `job_description` 重复 | 逐行规范化后比较：1167/1167 完全相同 | **不删除**；保留字段并写 `education_text_dup_of_job_description` 标记，禁用为模型输入 |

### 5.3 技能规范化 `preprocess_skills.canonicalize_skills`

铁律：**禁止子串包含判断**。Java 与 JavaScript、C 与 C++、R 与 Rust 必须保持独立
（`configs/skills.yaml` -> `must_remain_distinct` 由测试断言）。

只做三件事：

1. 形式规范化：NFKC -> casefold -> 空白折叠 -> 去首尾标点（保留 `c++`/`c#`/`node.js` 等符号）；
2. 显式别名表精确映射（`configs/skills.yaml` -> `aliases`，人工确认过的等价表达）；
3. 无法确认的保留规范化后的原值并标记 `needs_review`，绝不强行归并。

每行同时保留 `skills_raw_json`（原值）、`skills_canonical_json`（规范名）、
`skills_mapping_json`（原值 -> 规范名）、`skills_unmapped_json`（待复核），映射关系可逆可审计。

### 5.4 学历 `education_data.build_education_table`

- 解析 `user` 的三段结构 `<岗位名称>…<岗位描述>…<学历描述>…`；
- 标签按 `configs/education_labels.yaml` 规范成 6 token 多热向量；
  无法映射的 token 保留原值并置 `label_status=oov_token`，不强行归并；
- 记录级主键 `record_key` = "rk" + sha256(job_id, user_hash, source_split)，
  `user_hash` = 规范化输入文本哈希（原文不落盘，保护隐私）；
- 合并 default/train、default/validation 与 annotated 金标准，金标准打 `is_gold=1`、
  `label_provenance=human_gold`，伪标签打 `pseudo_online`（可信度 low）。

### 5.5 风险表 `preprocess_risk.normalize_risk`

只做规范化与元数据登记（重复组、离群值标记），`scam_probability` 不是人工真值，
本阶段不纳入任何监督训练任务。

## 六、Embedding 缓存（步骤 4）

```text
data/processed/embeddings/
├── cv_embeddings.npy      # (9544, 768) float32
├── job_embeddings.npy     # (1167, 768) float32
├── cv_id_map.json         # id_to_row / row_to_id 双向可逆
├── job_id_map.json
└── metadata.json          # 哈希、范数统计、限制声明
```

- 从 `cv.csv`/`job.csv` 的 `embedding` 字符串列解析还原，不修改原始向量、不调用在线 API、
  不重新归一化（沿用原始 L2 归一化状态）；
- 校验：dtype float32、维度 768、全有限、ID 唯一、行数与映射一致；
- 一致性验证 `verify_embedding_cache`：随机抽 64 行与原始 CSV **逐元素 bit 级比对**，
  最大绝对误差必须为 0，否则流水线报错停止；
- `candidate_id`/`job_id` 的整数形式**不得**作为模型特征（ID 映射只用于定位向量行）。

> **限制**：预计算 Embedding 的编码模型未知，且它经 `semantic_score` 参与了标签生成。
> 后续「冷启动」只能表示下游排序模型未用这些实体做监督训练，不能宣称预训练编码器
> 从未见过相关文本（详见 `data/processed/embeddings/metadata.json` -> `limitations`）。

## 七、特征与目标的物理隔离（步骤 5）

| 产物 | 内容 |
|---|---|
| `data/processed/matching/features_pairs.csv` | pair 键 + 白名单特征（无任何派生评分） |
| `data/processed/matching/targets_pairs.csv` | `label_strength` / `label_ordinal` / 代理相关性元数据 |
| `data/processed/matching/feature_matrix_match_label_strength.npz` | 数值特征矩阵 `[122560, 6]` + 特征名 |
| `data/processed/matching/feature_schema.json` | 实际特征 Schema 与黑名单登记 |
| `data/processed/education/education_inputs.csv` | 输入侧（`record_key` 关联） |
| `data/processed/education/education_labels.csv` | 标签侧（`record_key` 关联） |

构建完成后立即执行 `policy.audit_feature_set`：

- 静态检查：列名不得命中黑名单 / ID 列 / 目标列 / 白名单之外的列；
- 动态检查：实际写出的 DataFrame 与特征矩阵逐列核对；
- 间接泄漏：检查特征能否近乎确定地重建 `final_score` / `candidate_rank` 等禁止字段
  （Spearman ≥ 0.999 或线性重建 R² ≥ 0.999）。

## 八、产物目录与格式

```text
data/interim/
├── matching/resume_normalized.csv
├── matching/job_normalized.csv
├── education/education_normalized.csv
└── risk/risk_normalized.csv

data/processed/
├── embeddings/          # NPY + JSON
├── matching/            # CSV + NPZ + JSON
└── education/           # CSV

data/splits/
├── matching/{candidate_cold,job_cold,double_cold}/{train,validation,test,excluded}.csv + manifest.json
└── education/{train,validation,gold_holdout,excluded}.csv + manifest.json
```

格式选择说明：本地实测 `pyarrow` / `fastparquet` 均未安装，按阶段约束不擅自安装依赖，
因此表格产物统一用 **CSV**（固定 `%.10g` 浮点格式、`\n` 换行、UTF-8 无 BOM，保证哈希可复现），
向量用 **NPY**，索引/清单用 **JSON**。该限制已写入 `configs/data_pipeline.yaml` -> `formats.parquet_note`
与各 manifest。

## 九、可复现性

1. **确定性**：`assign_groups`、`build_double_cold`、`build_education_splits` 全部由种子驱动的
   确定性算法实现（同分平局用固定规则打破），同配置同种子必得同结果。
2. **取证脚本**：

   ```powershell
   python scripts/data_pipeline/rerun_consistency.py snapshot   # 记录产物指纹
   python scripts/data_pipeline/run_all.py                      # 重复执行
   python scripts/data_pipeline/rerun_consistency.py compare    # 比对并落盘结论
   ```

   比对对象是确定性产物（切分索引、特征表、目标表、特征矩阵、学历输入/标签、
   Embedding 数组与 ID 映射、manifest 统计量）与 Baseline 指标数值；
   `created_at`/`seconds` 等时间字段在比对前剔除。
   结论写入 `reports/phase3-reproducibility-rerun.json`。
3. **浮点容差**：Baseline 指标不要求跨硬件逐位一致，指标数值保留 6 位小数，
   涉及浮点求和的比较在测试中使用合理容差（G5）。

## 十、隐私与合规

- 简历正文（`resume_text`/`experience_text`/`education_text`）、招聘 JD 原文（`job_description`/`job_text`）、
  学历输入原文（`user`）不写入日志与报告；
- 学历表只落盘 `user_hash`（规范化文本哈希）与槽位摘要，不落盘原文；
- 报告中的样例一律为计数、长度分布、哈希与字段名。

## 十一、常见问题

- **流水线能否重复执行？** 可以。产物会被同名覆盖，但内容由确定性算法生成，
  `rerun_consistency.py compare` 可证明逐值一致。每步产物自带 SHA-256 登记。
- **为什么日志里中文乱码？** 控制台代码页与 UTF-8 不一致时 `Tee-Object` 会乱码，
  但 `reports/phase3-logs/pipeline.log` 是 UTF-8 写入，内容正确。
- **可以只跑某一步吗？** 可以，`--only N` / `--from N`；但步骤间存在依赖
  （3 -> 4 -> 5 -> 6 -> 7），跳过前置步骤会读到旧产物，请确认产物时间戳。
