# 工作目录工程化整理 —— 实际迁移结果与验证

- 执行日期：2026-10-28
- 项目根目录：`D:\desktop\毕业设计`
- 计划文件：`reports/workspace-reorganization-plan.md`（执行前生成）
- 回滚清单：`reports/workspace-migration-manifest.json`
- 执行方式：同一卷（D:）内 `Move-Item` 重命名，**零复制、零内容改写、零删除**

---

## 一、整理前后对比

| 指标 | 整理前 | 整理后 | 变化 |
|---|---:|---:|---:|
| 文件总数 | 4,758 | 4,768 | +10（新增文档与脚本，见第五节） |
| 目录总数 | 428 | 436 | +8（`data/` 及其 7 个子目录） |
| 总体积 | 1,303.73 MB | 1,303.80 MB | +0.07 MB（仅新增小文档，无数据副本） |
| 根目录散落文件 | 8 个 | **3 个** | 仅剩 `.env.example` / `.gitignore` / `environment.yml` |
| 根目录数据集 | 3 个 CSV + 2 个数据集目录 | **0** | 全部归入 `data/raw/` |
| 是否 Git 仓库（项目根） | 否 | 否 | 未执行任何 Git 操作 |

### 整理前的主要混乱问题

1. **根目录本身是 Hugging Face `local_dir` 快照**，与项目工程文件（`environment.yml`、`.gitignore`、`docs/`、`tests/`）混在一层，两类资产无法分辨。
2. **根目录 `README.md` 是 HF 数据集卡片**，不是项目 README；项目缺少总览文档。
3. **CSV 与代码/文档混放**：`cv.csv` 185 MB、`job.csv` 31 MB、`matches.csv` 19 MB 直接躺在根目录。
4. **一个目录叫 `all_df.csv`**，内含同名文件 `all_df.csv`，目录名带扩展名，语义混乱，且与其它数据源无隔离。
5. **两个 Hugging Face 快照的 `.cache` 元数据散落**（根目录一份、`job-education/` 一份），容易被误删。
6. **缺少数据集索引**：数据来源、许可证、行数、清洗状态无处可查。
7. **测试硬编码绝对路径** `ROOT = r"D:\desktop\毕业设计"` + 裸文件名，数据一挪就断。
8. **`.gitignore` 未覆盖大型数据集**（只忽略了 `.cache/`），一旦 `git init` 会把 600+ MB CSV 收进仓库。
9. **`chinese-skillspan-benchmark/` 独立 Git 仓库与本工程并列**，容易被误当作本项目的一部分。
10. **无完整性基线**：迁移前没有任何 SHA-256 记录可用于校验数据未被改动。

---

## 二、实际执行的迁移（8 条，全部成功）

| # | 原路径 | 目标路径 | 文件数 | 字节数 | 结果 |
|---|---|---|---:|---:|---|
| M1 | `cv.csv` | `data\raw\job-resume-matching\cv.csv` | 1 | 194,020,617 | ✅ |
| M2 | `job.csv` | `data\raw\job-resume-matching\job.csv` | 1 | 32,930,476 | ✅ |
| M3 | `matches.csv` | `data\raw\job-resume-matching\matches.csv` | 1 | 19,704,065 | ✅ |
| M4 | `README.md` | `data\raw\job-resume-matching\README.md` | 1 | 9,935 | ✅ |
| M5 | `.gitattributes` | `data\raw\job-resume-matching\.gitattributes` | 1 | 2,639 | ✅ |
| M6 | `.cache\` | `data\raw\job-resume-matching\.cache\` | 8 | 3,193 | ✅ |
| M7 | `job-education\` | `data\raw\job-education\` | 15 | 371,760,362 | ✅ |
| M8 | `all_df.csv\` | `data\raw\other\all_df.csv\` | 1 | 24,912,302 | ✅ |
| | **合计** | | **29** | **643,343,224** | 0 失败 / 0 覆盖 |

**实际移动的文件数量：29 个文件（含 2 个整目录的递归内容），全部为同卷重命名。**

### dry-run 结果（执行前）

| 检查项 | 结果 |
|---|---|
| 目标路径是否已存在同名文件 | 10 个目标全部 `False`（无冲突） |
| 源文件是否存在 | 8 个源全部 `True` |
| Windows 大小写冲突 | 无（源文件名大小写原样保留） |
| 中文路径 | 源/目标均在 `D:\desktop\毕业设计` 内，PowerShell/.NET 与 Python `pathlib` 均按 UTF-16 处理，无编码转换 |
| 跨磁盘移动 | **否**（D: → D:），不产生复制副本 |
| 磁盘空间 | D: 可用 33.04 GB；同卷移动不需要额外空间 |
| Git 跟踪冲突 | 项目根非 Git 仓库，M1–M8 均不受跟踪；`chinese-skillspan-benchmark/` 内部文件一律未动 |
| 运行中任务占用 | `cv.csv`/`job.csv`/`matches.csv` 逐一 `File.Open(ReadWrite, None)` 探测，**均未被占用** |

---

## 三、未移动的文件及原因

| 对象 | 处理 | 原因 |
|---|---|---|
| `chinese-skillspan-benchmark\` | **未移动、未修改** | 完全独立的 Git 仓库（`remote: github.com/AlfredJamesLi/chinese-skillspan-benchmark`，分支 `main`，工作区 0 处未提交修改），含自己的 `LICENSE`/`CITATION.cff`/`CHANGELOG.md`。属另一研究项目，根 `.env.example` 中 `CNSS_PAPER_ROOT` 等变量即为其论文工程预留。移动会破坏仓库语义与外部引用 |
| `reports\environment-acceptance.md` | **未修改** | 历史实测结论。其中 `D:\desktop\毕业设计\cv.csv` 等为**迁移前**真实位置，按"不修改历史实测结论"约束原样保留 |
| `reports\environment-acceptance.json` | **未修改** | 同上（`datasets[].path` 记录的是迁移前路径） |
| `environment.yml` | **未修改** | 不含数据集路径；`test_reproducibility.py` 还会校验其中不得出现本机绝对路径 |
| `.env.example` | **未修改** | 仅含环境变量名与注释，不含被迁移资源的路径 |
| `tests\environment\test_conda.py`、`test_gpu_training.py`、`test_nlp_dependencies.py`、`test_numpy_compat.py`、`test_reproducibility.py`、`test_torch_cuda.py` | **未修改** | 不引用任何数据集路径 |
| `docs\environment-setup.md` 第 11 节「本次搭建验证记录」 | **未改写** | 属历史记录；仅更新第 6.5 节示例命令、第 7 节路径表、第 10 节只读目录清单 |

---

## 四、配置文件修改清单

| 文件 | 修改内容 | 验证 |
|---|---|---|
| `tests\environment\test_dataset_loading.py` | 新增 `DATA_HOME` / `_DATA_PARENT` / `data_path(rel)` 解析层，把 `os.path.join(ROOT, rel)` 改为 `data_path(rel)`。**`targets` 的 key、`found[...]` 逻辑名、断言与输出格式全部保持不变** | 重跑 **25 项 / FAIL=0**（与历史报告逐脚本项数一致） |
| `tests\environment\test_e2e_pipeline.py` | 单行：`os.path.join(ROOT, "matches.csv")` → `os.path.join(ROOT, "data", "raw", "job-resume-matching", "matches.csv")` | 重跑 **6 项 / FAIL=0** |
| `docs\environment-setup.md` | 6.5 示例命令路径；第 7 节数据集表加 `data\raw\` 前缀并补路径说明；第 4 条只读声明加迁移注记；第 10 节第 5 条只读目录清单更新 | 全文检索无指向旧位置的失效数据集路径 |
| `.gitignore` | 新增数据集与训练产物忽略规则（**按目录忽略，不用 `*.csv`/`*.json` 通配**）：`data/raw/`、`data/{interim,processed,splits}/*`（保留 `.gitkeep`）、`models/**`、`experiments/**`、`*.safetensors`、`*.bin` | `data/README.md` 与 `.gitkeep` 仍可入库；`environment.yml`、`reports/*.json`、`docs/**` 均不受影响 |

**新增文件（10 个，均为文档/脚本，不含数据副本）**

| 文件 | 作用 |
|---|---|
| `docs/project-overview.md` | 项目总览（项目 README 的正身） |
| `docs/project-structure.md` | 最终目录结构说明 |
| `docs/datasets/README.md` | 数据集索引 |
| `data/README.md` | 数据管理规则 |
| `data/interim/.gitkeep`、`data/processed/.gitkeep`、`data/splits/.gitkeep` | 目录占位 |
| `reports/workspace-reorganization-plan.md` | 迁移计划（执行前生成） |
| `reports/workspace-migration-manifest.json` | 迁移映射 + SHA-256 基线（回滚用） |
| `scripts/verify_data_integrity.py` | 按清单复核数据完整性 |
| `reports/workspace-reorganization.md` | 本文件 |

**关于根目录 README 的说明**：原根目录 `README.md` 实为 Hugging Face 数据集卡片，受
`.cache/huggingface/download/README.md.metadata` 跟踪，本地改写会在下次 `snapshot_download` 时被远端静默覆盖，
因此**未改写、未重命名**，而是随快照迁到 `data/raw/job-resume-matching/README.md`；
项目文档改放 `docs/project-overview.md`（此为用户选定方案）。

---

## 五、完整性验证结果

### 5.1 文件完整性

| 检查 | 结果 |
|---|---|
| 原始数据文件数量 | 迁移前 27 个（哈希基线覆盖）→ 迁移后 29 个登记文件，**数量一致**（+2 为 HF 快照的 `README.md` 与 `.gitattributes`，基线未覆盖，见下） |
| 原始数据文件大小 | 29 个文件字节数逐一比对，**全部一致** |
| 迁移后 SHA-256 | **27/27 与迁移前基线逐字节一致，0 处不一致** |
| 无基线的 2 个文件 | `data\raw\job-resume-matching\README.md`（9,935 B）与 `.gitattributes`（2,639 B）。迁移前基线未纳入它们；因是**同卷 `Move-Item` 元数据重命名、不重写内容**，迁移后 SHA-256 即当前权威值，已登记入清单：`5f0bece4…` / `8112ea19…` |
| 是否存在迁移失败或覆盖 | **无**。8 条迁移全部成功；dry-run 已确认目标无同名文件，不存在覆盖 |
| 意外新增的大型数据副本 | **无**。`scripts/verify_data_integrity.py` 会扫描 `data/raw/` 下未登记文件，结果 0 个 |

`scripts/verify_data_integrity.py` 实测输出：

```text
清单: D:\desktop\毕业设计\reports\workspace-migration-manifest.json
登记文件 29 个, 已校验 29 个
问题 0 项:
结论: PASS —— 全部原始数据文件与基线一致，无未登记副本
```

### 5.2 环境完整性

```text
conda run -n graduation-design python -m pip check
→ No broken requirements found.   （退出码 0）
```

环境未因整理而损坏。

### 5.3 数据读取

| 数据 | 结果 |
|---|---|
| 简历数据 `cv.csv` | ✅ 可读，**9,544 行** / 11 列，`candidate_id` 在 |
| 岗位数据 `job.csv` | ✅ 可读，**1,167 行** / 10 列，`job_id` 在 |
| 匹配标签 `matches.csv` | ✅ 可读，**122,560 行** / 13 列，`label_strength` 三档分布与迁移前完全相同 |
| `other/all_df.csv/all_df.csv` | ✅ 可读（UTF-8 带 BOM），**251,381 行** / 8 列 |
| `job-education` 4 个 CSV | ✅ 可读，**197,574 / 45,593 / 22,730 / 22,730 行** |
| 主要关联字段 | ✅ `matches.candidate_id` 9,532 个 100% 命中 `cv.csv`；`matches.job_id` 1,164 个 100% 命中 `job.csv` |
| 迁移前可读的 CSV | ✅ 迁移后全部仍可读（8/8） |

> 行数为迁移后用 `pandas.read_csv(chunksize=50000)` 分块实测，与迁移前一致；
> `all_df` 与 `job-education` 的精确行数是本次新增的可靠统计（此前文档只有估算值）。

### 5.4 测试完整性

8 个环境验收脚本**全部重跑**，逐脚本项数与历史报告完全一致：

| 脚本 | 项数 | FAIL | 说明 |
|---|---:|---:|---|
| `test_conda.py` | 6 | 0 | 环境隔离、解释器一致性 |
| `test_torch_cuda.py` | 10 | 0 | CUDA 初始化、GPU 矩阵乘 512²/1024² |
| `test_gpu_training.py` | 9 | 0 | 40 步真实训练冒烟，Loss 1.3893→0.7258 |
| `test_numpy_compat.py` | 7 | 0 | NumPy/PyTorch ABI 双向转换 |
| `test_nlp_dependencies.py` | 33 | 0 | 17 个组件 import + 功能测试 |
| `test_dataset_loading.py` | 25 | 0 | 8 个数据文件读取/编码/表头/空值/关联键 |
| `test_e2e_pipeline.py` | 6 | 0 | CSV→特征→CUDA→MLP→AdamW 20 步 |
| `test_reproducibility.py` | 8 | 0 | 依赖声明与实装逐项一致（含 1 项**既存** WARN） |
| **合计** | **104** | **0** | 另有 `pip check` 1 项 PASS |

**关于「108 项」的说明**：任务描述提到 108 项检查。按 `reports/environment-acceptance.json` 中
逐脚本 `items` 字段累加为 **104 项**（6+10+9+7+33+25+6+8），加上 `pip check` 为 **105 项**。
本次重跑的逐脚本项数与历史报告**逐项一致**，差异只在总数口径，未丢失任何检查项。

**关于 `test_reproducibility.py` 的 WARN**：该项提示 `chinese-skillspan-benchmark/` 内的
`requirements-train.txt` 等冻结配方与 `environment.yml` 有 4 处版本差异。这是**整理前就存在的既存告警**
（历史报告第 10 项即记为「PASS（1 项 WARN）」），非本次整理引入，且属跨项目差异，本次不处理。

**副作用说明**：`test_nlp_dependencies.py` 会在系统临时目录写 `gd_accept_st.safetensors` 做读写测试，
`test_gpu_training.py` / `test_e2e_pipeline.py` 会占用少量显存做真实训练冒烟。均为只读原始数据、
可重复执行的测试，无网络下载、无耗时训练。**未执行任何需要联网或大模型下载的检查。**

### 5.5 引用完整性

对 `**/*.{py,md,yml,yaml,toml,json,bat,ps1,sh,ipynb,txt}` 全量检索旧路径：

- ✅ **Python 代码中 0 处失效引用**。所有数据集定位集中在 `test_dataset_loading.py` 的
  `_DATA_PARENT` 映射表与 `test_e2e_pipeline.py` 的单行路径常量，均已指向新位置。
- ✅ `docs/environment-setup.md` 已更新为新路径。
- ⚠ 仍出现旧路径的位置**全部是应当保留的历史/说明性文本**：
  - `reports/environment-acceptance.md` / `.json` —— 迁移前实测记录（约束要求不改写）
  - `reports/workspace-reorganization-plan.md` / `workspace-migration-manifest.json` —— 记录原路径以支持回滚
  - `docs/project-structure.md` 第五节、`reports/workspace-reorganization-plan.md` 第二节 —— 显式说明历史路径由来
- ✅ 原有流程仍可正常执行：8 个测试脚本、`scripts/hash_datasets.py`、`scripts/verify_data_integrity.py` 全部实测可运行。

---

## 六、最终目录树

```text
毕业设计/
├── .env.example            环境变量示例
├── .gitignore              Git 忽略规则（含数据集/训练产物按目录忽略）
├── environment.yml         Conda 环境主定义（graduation-design）
├── data/
│   ├── README.md           数据管理规则
│   ├── raw/
│   │   ├── job-resume-matching/   cv.csv / job.csv / matches.csv + HF 卡片与缓存
│   │   ├── job-education/         default/{train,validation,test} + annotated + HF 卡片与缓存
│   │   └── other/all_df.csv/      all_df.csv
│   ├── interim/            中间产物
│   ├── processed/          最终训练输入
│   └── splits/             切分索引
├── docs/
│   ├── project-overview.md     项目总览
│   ├── project-structure.md    目录结构说明
│   ├── environment-setup.md    环境搭建与排错手册
│   └── datasets/README.md      数据集索引
├── reports/
│   ├── environment-acceptance.{md,json}      环境验收（历史，未改写）
│   ├── workspace-reorganization-plan.md      迁移计划
│   ├── workspace-reorganization.md           本文件
│   └── workspace-migration-manifest.json     回滚清单 + SHA-256 基线
├── scripts/
│   ├── hash_datasets.py            流式 SHA-256
│   └── verify_data_integrity.py    完整性复核
├── tests/environment/              8 个验收脚本（104 项）
└── chinese-skillspan-benchmark/    独立 Git 仓库，未迁移未修改
```

---

## 七、回滚方法

```powershell
# 1) 反向移动（M8 → M1 顺序）
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\other\all_df.csv" -Destination "D:\desktop\毕业设计\all_df.csv"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-education"    -Destination "D:\desktop\毕业设计\job-education"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-resume-matching\cv.csv" -Destination "D:\desktop\毕业设计\cv.csv"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-resume-matching\job.csv" -Destination "D:\desktop\毕业设计\job.csv"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-resume-matching\matches.csv" -Destination "D:\desktop\毕业设计\matches.csv"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-resume-matching\README.md" -Destination "D:\desktop\毕业设计\README.md"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-resume-matching\.gitattributes" -Destination "D:\desktop\毕业设计\.gitattributes"
Move-Item -LiteralPath "D:\desktop\毕业设计\data\raw\job-resume-matching\.cache" -Destination "D:\desktop\毕业设计\.cache"

# 2) 还原测试脚本（R1/R2）：见 workspace-reorganization-plan.md 第二节的修改点描述
# 3) 重新校验
& "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe" "D:\desktop\毕业设计\scripts\hash_datasets.py" "D:\desktop\毕业设计\cv.csv" "D:\desktop\毕业设计\job.csv" "D:\desktop\毕业设计\matches.csv"
```

> ⚠ 回滚后 `.gitignore` 中的 `data/raw/` 等规则会失效（数据已不在该处），请一并还原 `.gitignore`。

---

## 八、结论

- **原始数据完整**：29 个登记文件、643,343,224 字节全部在位，27 个有基线的文件 SHA-256 逐字节一致，0 处不一致，0 覆盖，0 失败，0 未登记副本。
- **Conda 环境正常**：`pip check` 无损坏依赖。
- **测试全部通过**：104 项检查 FAIL=0，逐脚本项数与历史验收报告一致。
- **引用全部有效**：Python 代码中无失效数据集路径，原有流程可正常执行。
- **历史结论未被改写**：`reports/environment-acceptance.*` 原样保留，新旧路径由迁移清单提供映射。
