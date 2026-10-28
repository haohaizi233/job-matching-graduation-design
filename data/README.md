# data/ —— 数据管理规则

本目录是毕业设计《大学生就业岗位画像与简历智能匹配系统的设计与实现》的**数据资产根**。
原始数据只读，处理产物分层落地。

```text
data/
├── README.md        本文件：数据管理规则
├── raw/             原始数据（只读，永不回写）；每个数据集单独一个子目录
│   ├── job-resume-matching/   人岗匹配数据集（HF 快照，含 cv.csv / job.csv / matches.csv）
│   ├── job-education/         岗位→学历抽取数据集（HF 快照，含 default/{train,validation,test} 与 annotated）
│   └── other/
│       └── all_df.csv/        中文招聘岗位风险表（原始目录名与文件名均为 all_df.csv）
├── interim/         中间产物（清洗、抽取、特征工程的中间结果）
├── processed/       最终可用的训练输入（张量、向量库、特征表）
└── splits/          训练/验证/测试切分索引（按 candidate_id / job_id 切分）
```

## 一、原始数据（`data/raw/`）铁律

1. **只读**。任何脚本不得向 `data/raw/` 写入、覆盖、重命名或删除文件。
2. **不改内容**。CSV 的编码、列名、列顺序、数据行一律保持原样；清洗结果写到 `data/interim/`。
3. **一个数据集一个目录**，保留其原始文件组织结构与原始命名，不因命名不美观而改名。
4. **不重复复制**。需要衍生版本时写到 `data/processed/`，不要在 `raw/` 里复制副本。
5. **完整性基线**：`data/raw/` 下所有文件的 SHA-256 记录在
   `reports/workspace-migration-manifest.json`，随时可用
   `scripts/verify_data_integrity.py` 复核。

## 二、Hugging Face 快照目录的特殊性

`data/raw/job-resume-matching/` 与 `data/raw/job-education/` 都是 Hugging Face
`snapshot_download(local_dir=...)` 落地的快照，目录内含：

| 文件/目录 | 作用 | 处置 |
|---|---|---|
| `README.md` | HF 数据集卡片（含 front-matter 与数据字典） | **不要改写**：改动会在下次 `snapshot_download` 时被远端版本静默覆盖 |
| `.gitattributes` | HF 的 LFS 规则 | 随快照一起保留 |
| `.cache/huggingface/download/*.metadata` | 下载元数据（etag/commit/时间戳） | **必须与数据文件保持相对位置不变**，否则 HF 会认为文件丢失并重新下载 |
| `.cache/huggingface/trees/*.json` | 目录树缓存 | 同上 |

因此**迁移这些目录时必须整目录原子移动**，不得只挪 CSV 而留下 `.cache`。
本次整理（2026-10-28）正是按此规则整目录移动，迁移后 `.cache` 相对布局不变，元数据继续有效。

> 说明：`README.md` 是数据集卡片而非项目说明；项目的总览与结构说明放在 `docs/project-overview.md` 与 `docs/project-structure.md`。

## 三、处理产物分层

| 目录 | 写入时机 | 示例 |
|---|---|---|
| `data/interim/` | 清洗、字段抽取、文本规整的中间结果 | 简历分段结果、岗位技能抽取的半成品 JSONL |
| `data/processed/` | 已可直接喂给模型的最终输入 | 特征表 parquet、向量索引、成对训练样本 |
| `data/splits/` | 切分索引 | `train_candidates.txt` / `val_candidates.txt` / `test_candidates.txt` |

切分必须按 `candidate_id`（或 `job_id`）分组切分，**不要按行随机切分**——
`matches.csv` 中同一候选人有多条记录，行级随机会让同一候选人跨集合，导致指标虚高。
依据见 `data/raw/job-resume-matching/README.md` 的 “Recommended Train/Validation/Test Splitting”。

## 四、负样本采样提醒

`matches.csv` **只含正样本**（`weak_positive` / `medium_positive` / `strong_positive`）。
做二分类或成对排序时必须自行采样负例，并把负样本生成结果写到 `data/processed/`，
不要回写 `data/raw/job-resume-matching/matches.csv`。

## 五、数据集索引

数据集的来源、字段、样本量、许可证、清洗状态等元信息统一登记在
[`docs/datasets/README.md`](../docs/datasets/README.md)。新增数据集时必须同步更新该索引。
