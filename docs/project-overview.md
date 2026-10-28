# 大学生就业岗位画像与简历智能匹配系统的设计与实现

> 本文件是**项目总览**（项目 README 的正身）。
> 项目根目录下不放 README.md —— 那个位置属于 Hugging Face 数据集卡片，已随快照迁到
> `data/raw/job-resume-matching/README.md`，避免与项目文档冲突。

---

## 一、项目介绍

面向大学生求职场景，构建「岗位画像 + 简历画像 + 智能匹配」的机器学习系统：

- **岗位画像**：从招聘描述中抽取结构化要求（技能、学历、经验年限、岗位类别）
- **简历画像**：从简历文本中抽取候选人能力特征，并与岗位要求对齐
- **智能匹配**：基于语义相似度、技能重合、岗位/类别/经验/学历六维打分做匹配与排序
- 后续将扩展智能体（Agent）交互与前后端展示

## 二、当前开发状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| Conda 环境搭建 | ✅ 完成 | `graduation-design`（Python 3.11.18 + torch 2.1.2+cu121 + CUDA 12.1 / RTX 2050 4 GB） |
| 环境验收 | ✅ 完成 | 8 个测试脚本、104 项检查 + `pip check`，核心项 0 FAIL（见 `reports/environment-acceptance.md`） |
| 数据集落地与盘点 | ✅ 完成 | 3 个数据源、8 个 CSV、约 613 MB（643,343,224 字节），索引见 `docs/datasets/README.md` |
| 工作目录工程化整理 | ✅ 完成 | 见 `reports/workspace-reorganization.md` |
| 数据清洗与特征工程 | ⬜ 未开始 | 产物写 `data/interim/`、`data/processed/` |
| 模型训练与评估 | ⬜ 未开始 | — |
| Agent 能力 | ⬜ 未开始 | 不提前造代码 |
| 前后端实现 | ⬜ 未开始 | — |

## 三、快速开始

```powershell
# 1) 激活 Conda 环境（PowerShell）
conda activate graduation-design
# 或者不激活、直接以该环境执行：
$py = "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe"

# 2) 校验原始数据完整性（对照 SHA-256 基线）
& $py "D:\desktop\毕业设计\scripts\verify_data_integrity.py"

# 3) 跑环境验收（8 个脚本）
foreach ($t in 'test_conda','test_torch_cuda','test_gpu_training','test_numpy_compat',
               'test_nlp_dependencies','test_dataset_loading','test_e2e_pipeline','test_reproducibility') {
    & $py "D:\desktop\毕业设计\tests\environment\$t.py"
}

# 4) 依赖完整性
& $py -m pip check
```

## 四、环境启动方法

| 项 | 值 |
|---|---|
| Conda 环境名 | `graduation-design` |
| Python | 3.11.18 |
| PyTorch | 2.1.2+cu121（CUDA 12.1） |
| GPU | NVIDIA GeForce RTX 2050，4 GB 显存 |
| 环境主定义 | `environment.yml`（只列直接依赖，人工维护） |
| 搭建与排错手册 | `docs/environment-setup.md` |

新建机器上复现：

```powershell
conda env create -f environment.yml
```

## 五、数据集存放规则

- 原始数据统一在 `data/raw/`，**一个数据源一个子目录**，保持原始命名与组织结构
- `data/raw/` **只读**：不回写、不覆盖、不改名、不删；清洗产物写 `data/interim/`
- 最终训练输入写 `data/processed/`，切分索引写 `data/splits/`
- 详细规则见 [`data/README.md`](../data/README.md)
- 数据集来源、字段、行数、许可证、清洗状态见 [`docs/datasets/README.md`](datasets/README.md)

| 数据源 | 位置 | 规模 |
|---|---|---|
| 人岗匹配（cv / job / matches） | `data/raw/job-resume-matching/` | 9,544 / 1,167 / 122,560 行 |
| 岗位学历解析（train/val/test/annotated） | `data/raw/job-education/` | 197,574 / 45,593 / 22,730 / 22,730 行 |
| 中文招聘岗位风险表 | `data/raw/other/all_df.csv/` | 251,381 行 |

> ⚠ `matches.csv` **只含正样本**。做二分类/成对排序必须自行采样负例，并按 `candidate_id` 切分。

## 六、环境验收报告位置

| 文件 | 内容 |
|---|---|
| `reports/environment-acceptance.md` | 验收报告（结论、实测数据、风险清单） |
| `reports/environment-acceptance.json` | 同一份结果的结构化版本 |

**注意**：这两份是 2026-10-28 目录整理**之前**的实测记录，其中的旧路径按约束原样保留；
新旧路径对照见 `reports/workspace-migration-manifest.json`。

## 七、测试运行方式

```powershell
$py = "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe"
& $py "D:\desktop\毕业设计\tests\environment\test_dataset_loading.py"
```

| 脚本 | 检查项 | 内容 |
|---|---:|---|
| `test_conda.py` | 6 | 环境隔离与解释器一致性 |
| `test_torch_cuda.py` | 10 | CUDA 初始化、GPU 矩阵运算 |
| `test_gpu_training.py` | 9 | GPU 真实训练冒烟 |
| `test_numpy_compat.py` | 7 | NumPy/PyTorch ABI 兼容 |
| `test_nlp_dependencies.py` | 33 | AI/NLP 依赖与功能 |
| `test_dataset_loading.py` | 25 | 本地数据集读取/结构/关联键 |
| `test_e2e_pipeline.py` | 6 | 数据→张量→CUDA→训练全链路 |
| `test_reproducibility.py` | 8 | 依赖声明与实装一致性 |

合计 **104 项**（另有 `pip check` 1 项）。

## 八、项目目录说明

见 [`docs/project-structure.md`](project-structure.md)。

## 九、主要文档索引

| 文档 | 内容 |
|---|---|
| `docs/project-overview.md` | 本文件：项目总览 |
| `docs/project-structure.md` | 目录结构与路径约定 |
| `docs/environment-setup.md` | 环境搭建、依赖依据、故障排查、维护约定 |
| `docs/datasets/README.md` | 数据集索引 |
| `data/README.md` | 数据管理规则 |
| `reports/workspace-reorganization-plan.md` | 整理前迁移计划 |
| `reports/workspace-reorganization.md` | 整理结果与验证 |
| `reports/workspace-migration-manifest.json` | 迁移映射与 SHA-256 基线（回滚用） |
