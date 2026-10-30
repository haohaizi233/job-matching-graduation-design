# 大学生就业岗位画像与简历智能匹配系统的设计与实现

> 本文件是**项目总览**（项目 README 的正身）。
> 项目根目录的 `README.md` 只做入口索引（文档导航 + 本地联调快速开始），不维护状态与测试数；
> Hugging Face 数据集卡片在 `data/raw/job-resume-matching/README.md`，不与项目文档冲突。

---

## 一、项目介绍

面向大学生求职场景，构建「岗位画像 + 简历画像 + 智能匹配」的机器学习系统：

- **岗位画像**：从招聘描述中抽取结构化要求（技能、学历、经验年限、岗位类别）
- **简历画像**：从简历文本中抽取候选人能力特征，并与岗位要求对齐
- **智能匹配**：基于语义相似度、技能重合、岗位/类别/经验/学历六维打分做匹配与排序
- 后续将扩展智能体（Agent）交互；前后端展示已实现（业务 API + Vue 前端联调，见 Phase5-2 与「前后端实现」行）

## 二、当前开发状态（统一阶段状态清单）

> 三个概念严格区分：**已执行的工程任务**（代码与产物存在）、**已通过的实验验收**（自动化测试与实验归档通过）、
> **尚未验证的真实业务有效性**（模型在真实求职语境下的效果，必须靠独立人工评估集验证，见 Phase4-3A）。
>
> **本表是全仓唯一的阶段状态清单**，其他文档（README、project-structure、各架构审计）
> 一律引用本表，不再各自维护完成率/测试数，避免多处口径不一致。
> 测试数为 2026-10-31 Phase5-3 基线轮实测（各阶段原始报告见 `reports/phase5-*/`）；"独立复现"指能否在当前审计环境
> （Python 3.13.2 / numpy 2.2.6 / scikit-learn 1.8.0 / torch 2.12.0+cpu）独立复跑，
> 与项目原训练环境（conda `graduation-design`，Python 3.11 + sklearn 1.5.2 + CUDA）严格区分。

| 阶段 | 工程实现 | 自动化测试 | 独立复现 | 真实业务有效性 | 未解决阻断项 |
|---|---|---|---|---|---|
| Conda 环境搭建 | ✅ `graduation-design`（Python 3.11.18 + torch 2.1.2+cu121 + CUDA 12.1 / RTX 2050 4 GB） | ✅ | ⚠ 本机无 conda，训练环境未复建 | — | 无 |
| 环境验收 | ✅ 8 个测试脚本、104 项检查 + `pip check` | ✅ 历史核心项 0 FAIL（`reports/environment-acceptance.md`） | ⚠ 依赖训练环境 | — | `pip check` 在当前共享 Python 环境有三方依赖版本冲突（非项目依赖） |
| 数据集落地与盘点 | ✅ 3 个数据源、8 个 CSV、约 613 MB | ✅ | — | — | 无（索引见 `docs/datasets/README.md`） |
| 工作目录工程化整理 | ✅ | ✅ | — | — | 无（见 `reports/workspace-reorganization.md`） |
| 数据工程（Phase3） | ✅ 产物在 `data/interim/`、`data/processed/`、`data/splits/` | ✅ G1–G7 数据质量门禁 **74/74 PASS**（`reports/data-quality-gates.json`） | ✅ 纯 CPU 可复跑 | ⬜ 未验证 | 无（数据侧） |
| 人岗匹配模型训练与评估（Phase4-1） | ✅ Ridge / GBM / MLP / RankNet 归档权重零改动 | ✅（训练环境）**25/25 PASS**；⚠ 当前审计环境 **20 PASS + T5 5 项 UNVERIFIED** | ⚠ 部分：T5 独立推理依赖 sklearn 1.5.2 反序列化，1.8.0 下 GBM checkpoint 加载失败（见 `docs/architecture/phase5-1-integration-audit.md` R7） | ⬜ 未验证 | 标签为旧评分系统代理标签，非人工真值；GBM checkpoint 跨 sklearn 版本不可加载（登记为 R7，禁止重训修复） |
| 学历要求规范化（Phase4-2） | ✅ 16 组实验 + 1000 次组级 Bootstrap 归档 | ✅ **35/36 PASS**；1 项 `pip check` 为当前共享 Python 环境的三方依赖版本冲突（adalflow/f2），非项目代码缺陷 | ✅ 纯 CPU 可复跑（pip check 除外） | ⬜ 未验证 | 开发集含伪标签噪声；736 条历史 Gold 非全新盲测集；`pip check` 环境依赖冲突（登记） |
| 独立人工评估体系（Phase4-3A） | ✅ 协议、标注工具、泄漏检查、导入、一致性、仲裁、冻结、指标流水线 | ✅ P1–P18 **237/237 PASS**（`reports/phase4-3a/`） | ✅ 纯 CPU 合成夹具可复跑 | ⬜ 等待人工标注 | `annotation_status=pending`；**H2 BLOCKED**（缺真实中文简历与人工 Gold，禁止伪造补齐） |
| Gold 冻结与标注质量门禁（Phase4-3A-2） | ✅ 冻结 CLI（前置/后置双门禁）、标注 QA、独立性检查、仲裁状态机 | ✅ 工程链路由 Phase5-1R R1/R2 覆盖（含 CLI 正向链路） | ✅ 临时隔离工作区可复跑 | ⬜ 等待人工标注 | 同 Phase4-3A：真实 Gold 未到位；无分歧场景已可合法冻结（工程侧不再阻断） |
| 业务推理服务（Phase5-1） | ✅ 中文简历/JD 解析、业务画像、Baseline 排序、可解释结果、FastAPI | ✅ S01–S24 **92/92 PASS**（`reports/phase5-1/`） | ✅ 纯 CPU 合成夹具可复跑 | ⬜ 未验证（分数为启发式/研究分，非录用概率） | 中文人岗匹配模型缺失（`future_verified` 仅预留）；服务默认本地开发、无认证（外网部署为上线阻断项） |
| 工程整改（Phase5-1R） | ✅ F-001–F-009 全部修复 + 二轮审计补漏（姓名 PII 脱敏缺口） | ✅ R1–R6 **151/151 PASS**（`reports/phase5-1r/`） | ✅ 纯 CPU 合成夹具可复跑（`python tests/phase5_1r/run_all.py`） | —（本阶段只做整改，不产生业务结论） | 无 P0/P1 遗留；剩余风险见 `reports/phase5-1r/phase5-1r-acceptance.md` |
| 架构优化与工程质量治理（Phase5-1A） | ✅ 模块化单体分层（domain/infra 抽取 + 兼容 re-export）、类型化配置、模型加载失败三分类、测试运行器可信化、环境三分、最小 CI | ✅ 门禁自检 **26/26 PASS**（A1/A2/A4/A6/A7）+ 全套件回归（`reports/phase5-1a/`） | ✅ 纯 CPU 可复跑（`python tests/phase5_1a/run_all.py`） | —（本阶段只做架构治理，不产生业务结论） | 5 个 GBM checkpoint 跨 sklearn 版本不可加载（`MODEL_ENV_INCOMPATIBLE`，走 Legacy 环境，禁止重训）；`pip check` 环境冲突同上 |
| 业务后端与持久化（Phase5-2） | ✅ 业务 API（认证、学生画像版本化、简历私有存储、岗位管理、推荐快照与反馈闭环）+ SQLAlchemy 持久层 + Alembic 迁移 | ✅ T1–T7 **52 PASS / 0 FAIL / 4 SKIP**（`reports/phase5-2/`） | ✅ 纯 CPU 合成夹具可复跑（PG 集成需 Docker 临时实例） | ⬜ 未验证（分数为排序参考分） | T7 PostgreSQL 集成 3 项 + T6 异常事务 1 项 SKIP（`NOT_RUN`/`ENV_INCOMPATIBLE`）；服务默认本地开发部署 |
| 业务一致性回归（Phase5-2R） | ✅ 岗位画像失效与版本管理、推荐幂等与并发唯一、合成标记、文件生命周期、上传上限、筛选分页语义、快照一致性、API 契约边界 | ✅ R1–R9 **68 PASS / 0 FAIL / 2 SKIP**（`reports/phase5-2r/`） | ✅ 纯 CPU 合成夹具可复跑 | —（本阶段为一致性回归，不产生业务结论） | R9 中 PG 集成 + 契约安全边界 2 项 SKIP；其余无 P0/P1 遗留 |
| CI 与产物完整性治理（Phase5-3） | ✅ M0 基线审计 + M1 GitHub Actions 修复（Core CI 模型检查改合成夹具自检、历史权重检查归位 Artifact-dependent）+ 历史权重完整性基线自检 | ✅ Core CI **79/79 PASS**；六套件合计 **467 PASS / 0 FAIL / 6 SKIP**（`reports/phase5-3/`、`reports/phase5-2/ci/`） | ✅ 纯 CPU 可复跑 | —（本阶段只做工程治理） | CI 修复需推送 GitHub 触发真实 Actions 运行复核 |
| 前后端实现 | ✅ 业务 API 联调 + Vue 3.5 / TypeScript 5.7 / Vite 6 前端 10 页面（登录、工作台、简历、我的画像、岗位、岗位详情、智能匹配、推荐历史、反馈中心、个人设置）：登录态、简历上传解析、画像确认与版本预览、推荐创建/重跑、反馈提交、CSV 导出走真实接口 | ⚠ 前端无独立自动化套件；联调链路由 Phase5-2 / 5-2R 契约与一致性测试覆盖 | ⚠ 需 Node 24 + 本地后端联调 | ⬜ 未验证 | 前端缺独立 e2e 测试；无 HTTPS / 外网部署（上线阻断项） |
| Agent 能力 | ⬜ 未开始 | — | — | — | 不提前造代码 |

> **H2 口径提示**：Phase5-1R 通过只代表冻结/标注/推理软件流程在工程夹具下可正确运行，
> **不代表 Phase4-3A 的真实 Gold H2 通过**。H2 维持 BLOCKED，直到真实中文简历、
> 人工标签与合法盲测集真正完成。

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

本地业务 API + 前端联调的启动命令（uvicorn 业务服务、演示数据种子、`npm run dev`、各阶段测试入口）
见根目录 [`README.md`](../README.md) 的「快速开始（本地联调）」。

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
| `docs/evaluation-protocol.md` | 人岗匹配/学历规范化既有实验评估口径 |
| `docs/evaluation/phase4-3a-protocol.md` | Phase4-3A 独立人工评估协议（评价单位、标签、双人标注、指标、Bootstrap） |
| `docs/evaluation/annotation-guidelines.md` | 人工标注操作指南 |
| `docs/api/phase5-1-api.md` | Phase5-1 推理服务 API（研究口径，无认证） |
| `docs/datasets/README.md` | 数据集索引 |
| `data/README.md` | 数据管理规则 |
| `reports/workspace-reorganization-plan.md` | 整理前迁移计划 |
| `reports/workspace-reorganization.md` | 整理结果与验证 |
| `reports/workspace-migration-manifest.json` | 迁移映射与 SHA-256 基线（回滚用） |
| `reports/phase4-3a/phase4-3a-acceptance.md` | Phase4-3A 阶段验收（G1/G2 门禁） |
| `reports/phase5-2/test-results.md` | Phase5-2 业务后端端到端测试（T1–T7） |
| `reports/phase5-2r/test-results.md` | Phase5-2R 业务一致性回归（R1–R9） |
| `reports/phase5-2/ci/core-ci-test-results.md` | Core CI 可移植门禁（C2–C5） |
| `reports/phase5-3/00-baseline-audit.md` | Phase5-3 M0 基线审计（真实执行记录） |
| `reports/phase5-3/01-ci-remediation.md` | Phase5-3 M1 GitHub Actions CI 修复 |
