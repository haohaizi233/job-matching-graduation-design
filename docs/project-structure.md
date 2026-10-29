# 项目目录结构说明

- 项目：大学生就业岗位画像与简历智能匹配系统的设计与实现
- 项目根目录：`D:\desktop\毕业设计`
- 生成时间：2026-10-28（工程化整理后）；**2026-10-29 Phase5-1R 更新**（补记 Phase3–Phase5-1R 实际结构）
- 目录设计原则：**现有内容优先于示例结构**；不为尚未实现的模块预建空目录与空文件。
- 阶段状态/完成率的**唯一口径**在 [`docs/project-overview.md`](project-overview.md) 第二节，本文件不重复维护数字。

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
│   ├── raw/                      原始数据（只读，不入库）：job-resume-matching / job-education / other
│   ├── interim/                  Phase3 中间产物（清洗、抽取、特征工程半成品）
│   ├── processed/                Phase3 最终训练输入（特征表、成对样本）
│   ├── splits/                   训练/验证/测试切分索引（按 candidate_id / job_id 分组）
│   ├── independent_eval/         ★ 独立人工评估资产（Phase4-3A/4-3A-2）
│   │   ├── annotation/           人工标注数据与导入校验记录
│   │   ├── pairs/                简历-岗位配对（v1/v2）
│   │   └── frozen/               冻结评估集（evalset_v1/v2、pool_v1）；未过门禁时只有
│   │                             freeze_blocked.json 阻断记录，真实 Gold 到位前不得出现冻结产物
│   └── private/                  真实简历与原始人工标注（本地私有，公开仓库绝不包含）
│
├── src/job_matching/             ★ 业务代码包
│   ├── core.py / schema.py       基础工具（哈希、规范化）/ CSV 数据表 Schema
│   ├── preprocess_skills.py      技能规范化（别名映射，禁止子串包含）
│   ├── pair_features.py          单 pair 特征
│   ├── metrics_ranking.py        排序指标（NDCG/MRR/Recall，稳定 tie-breaking）
│   ├── policy.py                 特征黑白名单强制（feature_policy.yaml 口径）
│   ├── annotation/               标注工程（抽取、去重、泄漏、导入、一致性、仲裁、
│   │                             PII、盲测保护、Gold 门禁 gold_gate、冻结 freeze、
│   │                             标注完成状态 completion.py）
│   ├── education/                学历规范化模型与规则（Phase4-2）
│   ├── inference/                MatchPredictor 旧模型推理（Phase4-1）
│   ├── training/                 FeatureMap 等训练侧（只读引用）
│   ├── independent_eval/         独立评估指标（evaluate_ranking_human 等）
│   └── service/                  ★ Phase5-1 业务推理服务
│       ├── contracts.py          StudentProfile / JobProfile / CohortRequirement /
│       │                         ExperienceRequirement 契约
│       ├── requirements.py       JD 届别/经验规范化解析层（Phase5-1R F-005/F-006）
│       ├── resume_parser.py / job_parser.py   中文简历与岗位解析
│       ├── explanations.py       学历/经验/届别/技能约束判定与证据
│       ├── matching.py           Baseline / experimental / future 三模式排序与降级
│       ├── model_registry.py     模型登记、惰性加载缓存、错误分类
│       ├── text_extract.py       TXT/DOCX/PDF 抽取（大小/格式/zip 炸弹防护）
│       ├── api.py                FastAPI 应用（请求大小/限流/Request-ID 白名单）
│       ├── errors.py / logging_utils.py      错误码体系（路径脱敏）/ PII 日志脱敏
│
├── configs/                      训练/匹配配置（skills.yaml、feature_policy.yaml 等）
├── models/                       ★ 归档模型权重（Phase4-1 匹配 / Phase4-2 学历，只增不覆盖）
│   ├── matching/{ridge,gradient_boosting,mlp,ranknet}/<协议>/  按 run 目录归档 manifest+权重
│   └── education/{tfidf,charcnn}/                              同上
│
├── scripts/
│   ├── hash_datasets.py / verify_data_integrity.py             流式哈希与完整性复核
│   ├── phase4_3a/               Phase4-3A 流水线（抽取、配对、导入、一致性、检查）
│   ├── phase4_3a_2/             Phase4-3A-2（标注 QA、冻结 CLI、导出、合规）
│   ├── phase5_1/                Phase5-1 辅助（模型兼容性报告等）
│   └── phase5_1r/               Phase5-1R 产物完整性校验（artifact_integrity.py）
│
├── docs/                         ★ 文档
│   ├── project-overview.md       项目总览（项目 README 的正身）+ 统一阶段状态清单
│   ├── project-structure.md      本文件：目录结构说明
│   ├── environment-setup.md      环境搭建与维护手册（含故障排查）
│   ├── evaluation-protocol.md    既有实验评估口径
│   ├── evaluation/               Phase4-3A 协议、标注指南、数据卡
│   ├── architecture/             架构与集成审计（phase5-1-integration-audit.md 等）
│   ├── api/phase5-1-api.md       业务 API 文档（含上线阻断项声明）
│   └── datasets/README.md        数据集索引（来源/字段/行数/许可证/清洗状态）
│
├── reports/                      ★ 报告与可回滚记录（历史报告只增不改）
│   ├── environment-acceptance.* / workspace-*                   环境验收与目录迁移记录
│   ├── data-quality-gates.json                                 Phase3 G1–G7 门禁
│   ├── model-training/ / education-training/                   Phase4-1 / Phase4-2 实验与测试报告
│   ├── phase4-3a/ / phase4-3a-2/                              Phase4-3A / 4-3A-2 阶段报告
│   ├── phase5-1/                                               Phase5-1 集成/演示/测试报告
│   └── phase5-1r/                                              ★ 整改交付（缺陷登记、回归、验收）
│
├── tests/
│   ├── environment/              环境验收测试（8 个脚本，104 项检查）
│   ├── fixtures/                 测试夹具
│   ├── data_pipeline/            Phase3 G1–G7 数据质量门禁（run_all.py）
│   ├── model_training/           Phase4-1 T1–T6（run_all.py）
│   ├── education_training/       Phase4-2 E1–E6（run_all.py）
│   ├── phase4_3a/                Phase4-3A P1–P18（run_all.py）
│   ├── phase5_1/                 Phase5-1 S01–S24（run_all.py）
│   └── phase5_1r/                Phase5-1R R1–R6 整改回归（run_all.py，F-001–F-009）
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
| `data/independent_eval/` | 独立人工评估资产（配对、标注、冻结评估集） | 冻结产物只由冻结 CLI 原子发布；未过门禁只允许 `freeze_blocked.json` |
| `data/private/` | 真实简历与原始人工标注 | **本地私有**，公开仓库绝不包含（`.gitignore` 屏蔽） |
| `models/` | 归档模型权重与 manifest（Phase4-1/4-2） | **只增不覆盖**；同版本冻结/权重拒绝重写 |
| `src/job_matching/` | 业务代码包（数据工程、标注、学历、推理、独立评估、业务服务） | 训练工程与业务服务物理隔离 |
| `docs/` | 项目与数据文档 | 与代码同步更新；阶段状态以 project-overview 为准 |
| `reports/` | 验收报告、迁移记录、回滚清单、各阶段测试报告 | 历史报告只增不改；新一轮结果写各自阶段子目录 |
| `scripts/` | 可重复执行的工程脚本（哈希、校验、各阶段流水线） | 命令行可独立运行 |
| `tests/` | 分阶段自动化测试（每阶段一个 `run_all.py` 入口） | 严禁跳过失败测试或降低既有门禁标准 |
| `chinese-skillspan-benchmark/` | 独立研究项目 | 由其自身仓库管理，本工程不触碰 |

## 三、暂不创建的目录（规划位）

以下目录**当前刻意不建**，避免制造空壳架构。等对应阶段真正开工时再建：

| 规划目录 | 计划用途 | 何时创建 |
|---|---|---|
| `src/job_matching/agents/` | Agent 编排 | Agent 阶段，**不提前生成业务代码** |
| `experiments/` | 实验记录、指标、曲线 | 第一次实验时（已在 `.gitignore` 预留忽略规则） |
| `backend/` | 后端服务 | 前后端阶段 |
| `frontend/` | 前端工程 | 前后端阶段 |

> `models/`、`experiments/` 的忽略规则已写入 `.gitignore`（含 `!models/README.md` 之类的例外），
> 未来创建时无需再改配置。
>
> 历史备注：2026-10-28 版本曾把 `src/job_matching/`、`configs/`、`models/` 列为规划位；
> 三个目录已在 Phase3–Phase5-1 陆续创建并投入使用，本表已同步更新（Phase5-1R，F-008）。

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
