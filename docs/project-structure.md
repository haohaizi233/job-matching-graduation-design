# 项目目录结构说明

- 项目：大学生就业岗位画像与简历智能匹配系统的设计与实现
- 项目根目录：`D:\desktop\毕业设计`
- 生成时间：2026-10-28（工程化整理后）
- 目录设计原则：**现有内容优先于示例结构**；不为尚未实现的模块预建空目录与空文件。

---

## 一、最终目录树（实际存在）

```text
毕业设计/
├── .env.example                  环境变量示例（HF_TOKEN / LLM API 密钥 / 论文图表字体路径）
├── .gitignore                    Git 忽略规则（含数据集与训练产物的按目录忽略）
├── environment.yml               Conda 环境主定义（graduation-design，Python 3.11 + torch 2.1.2+cu121）
│
├── data/                         ★ 数据资产根
│   ├── README.md                 数据管理规则（raw 只读、interim/processed/splits 分层）
│   ├── raw/                      原始数据（只读，不入库）
│   │   ├── job-resume-matching/  人岗匹配数据集（Hugging Face 快照）
│   │   │   ├── cv.csv            9,544 条候选人画像，11 列，含 768 维向量
│   │   │   ├── job.csv           1,167 条岗位画像，10 列，含 768 维向量
│   │   │   ├── matches.csv       122,560 条人岗匹配记录，13 列
│   │   │   ├── README.md         HF 数据集卡片（数据字典）
│   │   │   ├── .gitattributes    HF LFS 规则
│   │   │   └── .cache/           HF local_dir 下载元数据
│   │   ├── job-education/        岗位学历解析数据集（Hugging Face 快照）
│   │   │   ├── default/{train,validation,test}/*.csv   197,574 / 45,593 / 22,730 行
│   │   │   ├── annotated/2w_0716_eval.csv              22,730 行人工标注评测集
│   │   │   ├── README.md / .gitattributes / .cache/    HF 卡片、LFS 规则、下载元数据
│   │   └── other/
│   │       └── all_df.csv/       中文招聘岗位风险表（保留原始目录名）
│   │           └── all_df.csv    251,381 行，8 列，UTF-8 带 BOM
│   ├── interim/.gitkeep          中间产物（清洗、抽取、特征工程的半成品）
│   ├── processed/.gitkeep        最终训练输入（特征表、向量库、成对样本）
│   └── splits/.gitkeep           训练/验证/测试切分索引
│
├── docs/                         ★ 文档
│   ├── project-overview.md       项目总览（项目 README 的正身）
│   ├── project-structure.md      本文件：目录结构说明
│   ├── environment-setup.md      环境搭建与维护手册（含故障排查）
│   └── datasets/
│       └── README.md             数据集索引（来源/字段/行数/许可证/清洗状态）
│
├── reports/                      ★ 报告与可回滚记录
│   ├── environment-acceptance.md     环境验收报告（历史实测结论，不再改写）
│   ├── environment-acceptance.json   环境验收结构化结果（历史，不再改写）
│   ├── workspace-reorganization-plan.md   整理前的迁移计划
│   ├── workspace-reorganization.md        实际迁移结果与验证
│   └── workspace-migration-manifest.json  迁移映射 + SHA-256 基线（回滚用）
│
├── scripts/                      ★ 工程脚本
│   ├── hash_datasets.py          流式 SHA-256 计算（1 MB 分块，大文件不占内存）
│   └── verify_data_integrity.py  按迁移清单复核原始数据完整性
│
├── tests/
│   └── environment/              环境验收测试（8 个脚本，104 项检查）
│       ├── test_conda.py               环境隔离与解释器一致性（6 项）
│       ├── test_torch_cuda.py          PyTorch/CUDA 实测 + GPU 矩阵运算（10 项）
│       ├── test_gpu_training.py        GPU 真实训练冒烟（9 项）
│       ├── test_numpy_compat.py        NumPy/PyTorch ABI 兼容（7 项）
│       ├── test_nlp_dependencies.py    AI/NLP 依赖与功能测试（33 项）
│       ├── test_dataset_loading.py     本地数据集验收（25 项）
│       ├── test_e2e_pipeline.py        端到端训练链路（真实数据小样本，6 项）
│       └── test_reproducibility.py     环境可复现性（8 项）
│
└── chinese-skillspan-benchmark/  另一独立 Git 仓库（中文岗位技能跨度抽取基准）
                                  ★ 不属于本毕业设计工程，本次整理未移动、未修改
```

## 二、各主要目录用途

| 目录 | 用途 | 写入规则 |
|---|---|---|
| `data/raw/` | 原始数据集，按数据源一源一目录 | **只读**，永不回写、不改名、不重排 |
| `data/interim/` | 清洗、字段抽取、文本规整的中间结果 | 可自由重算、可删除 |
| `data/processed/` | 可直接喂给模型的最终输入（特征表、向量索引、成对样本） | 由脚本产出，不手改 |
| `data/splits/` | 训练/验证/测试切分索引 | 必须按 `candidate_id` / `job_id` 分组切分 |
| `docs/` | 项目与数据文档 | 与代码同步更新 |
| `reports/` | 验收报告、迁移记录、回滚清单 | 历史报告只增不改 |
| `scripts/` | 可重复执行的工程脚本（哈希、校验、后续数据处理） | 命令行可独立运行 |
| `tests/environment/` | 已通过验收的环境测试 | 只做必要修改，改后必须重跑全部 |
| `chinese-skillspan-benchmark/` | 独立研究项目 | 由其自身仓库管理，本工程不触碰 |

## 三、暂不创建的目录（规划位）

以下目录**当前刻意不建**，避免制造空壳架构。等对应阶段真正开工时再建：

| 规划目录 | 计划用途 | 何时创建 |
|---|---|---|
| `src/job_matching/` | 业务代码包（data / preprocessing / features / models / matching / evaluation） | 特征工程或模型训练开始写业务代码时 |
| `src/job_matching/agents/` | Agent 编排 | Agent 阶段，**不提前生成业务代码** |
| `configs/` | 训练/匹配配置（YAML/TOML） | 第一份配置出现时 |
| `models/` | 训练产出的权重与 checkpoint | 第一次保存权重时（已在 `.gitignore` 预留忽略规则） |
| `experiments/` | 实验记录、指标、曲线 | 第一次实验时（已在 `.gitignore` 预留忽略规则） |
| `backend/` | 后端服务 | 前后端阶段 |
| `frontend/` | 前端工程 | 前后端阶段 |

> `models/`、`experiments/` 的忽略规则已写入 `.gitignore`（含 `!models/README.md` 之类的例外），
> 未来创建时无需再改配置。

## 四、路径约定

1. 新代码一律用 `pathlib.Path` 定位项目资源，避免硬编码字符串拼接。
2. 项目内资源路径**相对项目根**解析；测试中的数据集定位集中在
   `tests/environment/test_dataset_loading.py` 的 `data_path(rel)`，新增数据集时只改那张映射表。
3. 必须保留的外部路径（Conda 环境、CUDA、字体、`CNSS_PAPER_ROOT` 等）走 `.env`，不写死在代码里。
4. Hugging Face 快照目录内的 `.cache/` **必须与数据文件同层移动**，否则下载元数据失效
   （详见 `data/README.md` 第二节）。

## 五、历史文档路径说明

`reports/environment-acceptance.md` 与 `reports/environment-acceptance.json` 是**迁移前**的实测记录，
其中的 `D:\desktop\毕业设计\cv.csv` 等路径是当时的真实位置，按"不修改历史实测结论"的约束原样保留。
新旧路径对照见 `reports/workspace-migration-manifest.json`。
