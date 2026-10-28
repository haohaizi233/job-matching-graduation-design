# 工作目录工程化整理 —— 迁移计划（执行前生成）

- 生成时间：2026-10-28
- 项目根目录：`D:\desktop\毕业设计`
- 执行环境：Conda `graduation-design`（Python 3.11.18）
- 计划性质：**先计划、后 dry-run、再执行**；所有迁移均可用 `reports/workspace-migration-manifest.json` 回滚

---

## 一、扫描结论摘要

| 指标 | 实测值 |
|---|---|
| 文件总数 | 4,758 |
| 目录总数 | 428 |
| 总体积 | 1,303.73 MB |
| 是否 Git 仓库（项目根） | **否**（根目录无 `.git`） |
| 嵌套独立 Git 仓库 | `chinese-skillspan-benchmark/`（remote: `github.com/AlfredJamesLi/chinese-skillspan-benchmark`，分支 `main`，工作区 0 处未提交修改） |

### 顶层原始结构

```text
D:\desktop\毕业设计\
├── .cache\                          ← Hugging Face local_dir 下载元数据（跟踪 cv/job/matches/README/.gitattributes）
├── all_df.csv\                      ← 目录，内含同名文件 all_df.csv（23.76 MB）
├── chinese-skillspan-benchmark\     ← 独立 Git 仓库（另一研究项目）
├── docs\                            ← 仅 environment-setup.md
├── job-education\                   ← Hugging Face 数据集快照（自带 .cache\huggingface\、.gitattributes、README.md）
├── reports\                         ← environment-acceptance.{md,json}
├── scripts\                         ← hash_datasets.py
├── tests\environment\               ← 8 个环境验收脚本
├── .env.example
├── .gitattributes                   ← Hugging Face LFS 规则（含 cv.csv/job.csv/matches.csv）
├── .gitignore
├── cv.csv                           (185.03 MB)
├── environment.yml
├── job.csv                          (31.40 MB)
├── matches.csv                      (18.79 MB)
└── README.md                        ← 实为 HF 数据集卡片（非项目 README）
```

### 关键识别结果

1. **根目录本身是一个 Hugging Face `local_dir` 数据集快照**：`.gitattributes` 为 LFS 规则并显式列出 `cv.csv`/`job.csv`/`matches.csv`；`.cache\huggingface\download\` 下存在 `cv.csv` / `job.csv` / `matches.csv` / `README.md` / `.gitattributes` 五个 `.metadata` 下载元数据。这 6 项 + `.cache\` 构成一个**原子整体**。
2. **`job-education\` 是第二个 HF 快照**：自带 `.cache\huggingface\`（含 `default/{train,validation,test}` 与 `annotated` 的 `.metadata`）、`.gitattributes`、`README.md`，同样为原子整体。
3. **根目录 `README.md` 不是项目 README**，而是 HF 数据集卡片（含 `license: mit` front-matter 与数据字典），受 `.cache\huggingface\download\README.md.metadata` 跟踪。
4. **`all_df.csv\` 是目录而非文件**，内部仅 1 个 `all_df.csv`，无 HF 缓存，字段为中文招聘岗位/学历/经验/诈骗概率表。
5. **`chinese-skillspan-benchmark\` 是完全独立的 Git 仓库**（含 LICENSE、CITATION.cff、CHANGELOG、自身 `.gitignore`、自身 `requirements-*.txt`），且被根 `.env.example` 作为「另一论文工程」引用（`CNSS_PAPER_ROOT` 等变量）。
6. **8 个数据文件全部被 2 个已通过验收的测试脚本以硬编码绝对路径引用**：
   - `tests\environment\test_dataset_loading.py` → `ROOT = r"D:\desktop\毕业设计"` + 相对名（8 个文件全覆盖）
   - `tests\environment\test_e2e_pipeline.py` → `os.path.join(ROOT, "matches.csv")`
   - `tests\environment\test_reproducibility.py` → 仅读 `environment.yml`，**不涉及数据集路径，无需修改**

---

## 二、变更计划（原路径 → 目标路径）

统一约定：**同一卷（D:）内移动，使用 `Move-Item` 重命名，不产生复制副本；移动前已记录 SHA-256，移动后逐一比对。**

| # | 原路径 | 目标路径 | 大小 | 引用情况 | 风险 | 特殊处理 |
|---|---|---|---|---|---|---|
| M1 | `cv.csv` | `data\raw\job-resume-matching\cv.csv` | 194,020,617 B | `test_dataset_loading.py`、`docs/environment-setup.md`、`README.md`(卡片示例)、`reports/environment-acceptance.*`(历史) | 中 | 与 `.cache`、`README.md`、`.gitattributes` 同批原子迁移 |
| M2 | `job.csv` | `data\raw\job-resume-matching\job.csv` | 32,930,476 B | 同上 | 中 | 同上 |
| M3 | `matches.csv` | `data\raw\job-resume-matching\matches.csv` | 19,704,065 B | `test_dataset_loading.py`、`test_e2e_pipeline.py`、`docs/environment-setup.md` | 中 | 同上 |
| M4 | `README.md` | `data\raw\job-resume-matching\README.md` | 9.7 KB | HF 卡片（受 `.cache` 元数据跟踪） | 中 | 必须与 M1–M3、M6 同处一个 local_dir 根 |
| M5 | `.gitattributes` | `data\raw\job-resume-matching\.gitattributes` | 2.6 KB | HF LFS 规则（受 `.cache` 元数据跟踪） | 中 | 同上 |
| M6 | `.cache\` | `data\raw\job-resume-matching\.cache\` | ~2 KB | HF local_dir 下载元数据 | 中 | 保持与 M1–M5 的相对布局不变，元数据继续有效 |
| M7 | `job-education\`（整目录） | `data\raw\job-education\` | 354.5 MB | `test_dataset_loading.py`（4 个文件）、`docs/environment-setup.md` | 中 | 整目录移动，内部 `.cache` 相对布局不变 |
| M8 | `all_df.csv\`（整目录） | `data\raw\other\all_df.csv\` | 23.76 MB | `test_dataset_loading.py`、`docs/environment-setup.md` | 低 | 整目录移动，保留原始相对路径 `all_df.csv\all_df.csv` |

### 引用同步修改（迁移后立即执行）

| # | 文件 | 修改点 | 性质 |
|---|---|---|---|
| R1 | `tests\environment\test_dataset_loading.py` | 新增 `data_path(rel)` 解析函数（按首个路径段映射到 `data\raw\{job-resume-matching,job-education,other}`），把 `os.path.join(ROOT, rel)` 改为 `data_path(rel)`。**`targets` 字典的 key 与所有 `found[...]` 逻辑名保持不变**，断言与输出格式不变 | 最小改动，不改检查逻辑 |
| R2 | `tests\environment\test_e2e_pipeline.py` | `os.path.join(ROOT, "matches.csv")` → 新路径常量 | 单行 |
| R3 | `docs\environment-setup.md` | 更新数据集路径表格、只读目录清单、示例命令中的旧路径 | 文档 |
| R4 | `.gitignore` | 补充 `data\raw\` 大数据忽略规则（按目录忽略，不用 `*.csv` 通配） | 配置 |

**不需要修改**：`tests\environment\test_reproducibility.py`、`test_conda.py`、`test_gpu_training.py`、`test_nlp_dependencies.py`、`test_numpy_compat.py`、`test_torch_cuda.py`（均不引用数据集路径）。
**禁止修改**：`reports\environment-acceptance.md`、`reports\environment-acceptance.json`（历史实测结论，保留迁移前路径作为历史记录）。

---

## 三、不迁移项及原因（STOP 记录）

| 对象 | 处理 | 原因 |
|---|---|---|
| `chinese-skillspan-benchmark\` | **不移动、不修改** | 独立 Git 仓库（有 GitHub remote、有 LICENSE/CITATION/CHANGELOG），属另一研究项目；根 `.env.example` 将其作为独立论文工程引用；移动会破坏其工作区语义与外部文档引用 |
| `reports\environment-acceptance.*` | **不修改** | 约束「不修改历史实测结论」。其中记录的 `D:\desktop\毕业设计\cv.csv` 等为**迁移前实测路径**，保留原样作为历史证据，由 `reports\workspace-migration-manifest.json` 提供新旧路径映射 |
| `tests\environment\` 8 个脚本 | **不删除、不重写** | 已通过 108 项验收；仅对 2 个脚本做路径解析的最小修改，随后重跑全部验收以证明等价 |
| `environment.yml` | **不修改** | 已含版本约束且 `test_reproducibility.py` 会校验「无本机绝对路径」，无需变更 |
| `.env.example` | **不修改** | 仅含变量名与注释，不含被迁移资源的路径 |
| `docs\datasets\`、`docs\project-*.md` | 新建 | 索引层，不触碰原始数据 |
| `data\interim\`、`data\processed\`、`data\splits\` | 新建（仅 `.gitkeep`） | 后续数据处理产物的约定落点，不预建业务代码 |
| `src\`、`backend\`、`frontend\`、`models\`、`experiments\`、`configs\` | **暂不创建** | 约束「不为尚未实现的业务模块创建大量空文件」「以轻量目录为主」。仅在 `docs\project-structure.md` 中登记为规划位 |

---

## 四、dry-run 检查项

| 检查项 | 结论 |
|---|---|
| 1. 目标路径是否已存在同名文件 | 执行前逐项 `Test-Path` 校验，全部应为 `False`；任一为 `True` 立即中止 |
| 2. Windows 路径大小写冲突 | 目标路径均为新建小写目录，源文件名大小写原样保留，无冲突 |
| 3. 中文路径处理 | 源/目标均在 `D:\desktop\毕业设计`（中文段），使用 .NET/PowerShell 原生 API 与 Python `pathlib`，均按 UTF-16 处理，无编码转换 |
| 4. 是否跨磁盘移动 | **否**，D: → D:，`Move-Item` 为同卷重命名，秒级完成且不产生副本 |
| 5. 目标磁盘空间 | D: 需容纳约 572 MB 迁移数据；因是同卷移动，**不需要额外空间** |
| 6. 是否涉及 Git 跟踪文件 | 项目根**不是** Git 仓库，M1–M8 均不受 Git 跟踪；`chinese-skillspan-benchmark\` 内部文件一律不动 |
| 7. 是否可能破坏运行中的服务/训练任务 | 扫描未发现运行中的训练进程或服务；迁移前再次确认无进程占用这些 CSV |

---

## 五、回滚方案

`reports\workspace-migration-manifest.json` 记录每条迁移的 `source` / `target` / `size` / `sha256` / `status`。回滚方式：

```powershell
# 逐条反向移动（示例）
Move-Item "D:\desktop\毕业设计\data\raw\job-resume-matching\cv.csv" "D:\desktop\毕业设计\cv.csv"
Move-Item "D:\desktop\毕业设计\data\raw\job-education" "D:\desktop\毕业设计\job-education"
Move-Item "D:\desktop\毕业设计\data\raw\other\all_df.csv" "D:\desktop\毕业设计\all_df.csv"
# 测试脚本 R1/R2 的修改可由 git diff 或本文件第二节的描述还原
```

回滚后须重新执行第八阶段完整性验证（哈希比对 + 8 个环境验收脚本）。

---

## 六、执行顺序

1. 写出本计划与空清单 → 2. dry-run 冲突检查 → 3. 记录迁移前 SHA-256 基线 → 4. 建 `data\` 骨架 → 5. 执行 M1–M8 → 6. 执行 R1–R4 → 7. 迁移后哈希比对 → 8. `pip check` → 9. 数据读取验证 → 10. 重跑 8 个环境验收脚本 → 11. 失效路径扫描 → 12. 生成结果报告。
