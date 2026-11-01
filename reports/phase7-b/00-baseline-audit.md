# Phase7-B 基线审计（B0）

- 审计时间：2026-11-01（UTC+8）
- 审计人：Cursor Agent（Phase7-B 交付收口工作流）
- 纪律：本报告只登记**本轮真实执行**取得的事实；已知基线数值仅作对照，不冒充本轮结果。

## 1. 真实 HEAD

| 项 | 值 |
|---|---|
| 本地 HEAD（`git rev-parse HEAD`） | `efcb2375f1408d42fa5aa911caf95b42acb01207` |
| `origin/main`（`git fetch origin --prune` 后） | `efcb2375f1408d42fa5aa911caf95b42acb01207` |
| 是否一致 | 一致（工作区干净，无未提交改动） |
| HEAD 提交 | `efcb237 merge: Phase7 Gold 冻结与真实模型评估（P7-0/1/2 + P7-3/4/5/6）合入 main` |

## 2. 当前分支

| 项 | 值 |
|---|---|
| 审计时所在分支 | `main`（审计后立即建立工作分支） |
| 本轮工作分支 | `feat/phase7b-graduation-delivery`（新建，基于 `efcb237`） |
| 其他分支 | 无（feat/phase7-gold-evaluation、docs/phase7-graduation-delivery 已于 Phase7-A 收口时合并删除） |
| Worktree | 仅主 worktree `D:\desktop\毕业设计`（trackB worktree 已移除） |

## 3. Python 实际解释器

| 项 | 值 |
|---|---|
| 本地首选解释器 | `py -3.13` → `D:\APP\python 3.13.2\python.exe`（Python 3.13.2） |
| `pip check` | 5 项**与本项目无关**的第三方包版本冲突（adalflow / f2 要求的 pytest-asyncio、click、cryptography、httpx、rich 版本不符），不影响本项目依赖 |
| 项目关键依赖（py -3.13 实测） | numpy 2.2.6 / scikit-learn 1.8.0 / joblib 可用 / torch 2.12.0+cpu 可用 |
| CI 解释器 | GitHub Actions `ubuntu-latest` + Python **3.11**（`core-ci` 等 job） |
| 其他本机环境 | miniconda `graduation-design` 环境（历史回归曾用）；miniconda base 无 numpy，**不可**用于跑测试 |
| 风险登记 | 本地 3.13 + numpy 2.2.6 与 CI 3.11 + numpy 1.26.4 存在版本差异，跨版本兼容性以远端 CI 为准 |

## 4. Phase7 测试数量（本轮真实执行）

```text
命令：py -3.13 tests/phase7/run_all.py
结果：PASS=46 FAIL=0 ERROR=0 SKIP=0 NOT_RUN=0 BLOCKED=0（0.614s，退出码 0）
测试模块（4）：test_preregistration / test_sample_size_planning /
              test_annotation_drill / test_model_artifact_guard
报告：reports/phase7/11-phase7-regression.{json,md}
```

与已知基线（PASS=46）一致。

## 5. GitHub Actions 状态（本轮真实查询 `gh`）

| 项 | 值 |
|---|---|
| 最新运行 | Run `41257939608`（workflow `quality-gates`，push 到 main，commit `efcb237`） |
| 结论 | **success** |
| 已执行 Job | `core-ci (3.11)` ✓ / `frontend-ci` ✓ / `postgres-integration` ✓ / `browser-e2e` ✓ / `phase6-gates` ✓ |
| 未执行 Job | `model-artifact-compat-manual`、`artifact-dependent-validation`（workflow_dispatch 限定）→ 按纪律登记 **NOT_RUN**，不计 PASS |
| **缺失门禁** | **无独立 `phase7-gates` Job**——`tests/phase7/run_all.py` 从未在远端干净 checkout 执行过 |
| 历史 | Run `41196478479` 曾 failure（Phase6-R 合并时），其后两次运行 success |

## 6. Gold 状态

| 项 | 值 |
|---|---|
| 真实 Gold 有效简历 | **0** |
| 人工标注配对 | **0** |
| H2（真实中文人岗匹配有效性） | **BLOCKED** |
| 业务上传文件 | 1 个（`file_exists=1`），但 `consent_verified=0 / intake_accepted=0 / eligible_for_gold=0`，**不等于**授权研究简历 |
| 盲测 | 模型正式独立评价 **NOT_RUN**；`reports/phase7/04-real-model-evaluation.json` 为 BLOCKED 状态记录（`not_an_experiment_result=true`） |

## 7. 论文资料完成度

| 项 | 状态 |
|---|---|
| `docs/thesis/` | **不存在**（outline、七章正文、evidence-index、limitations、figures、tables 全缺） |
| 现有可依托证据 | `reports/phase6-r/08-thesis-evidence-matrix.md`、各阶段 reports、BM25 实测 JSON、CI/E2E/PG 报告 |
| 结论 | 论文研究材料目录完成度 **0%**，为 Phase7-B 主要交付缺口 |

## 8. 系统交付完成度

| 项 | 状态 |
|---|---|
| 后端 / 前端 / 数据库 | Phase5 系列已完成并通过 core-ci / frontend-ci / postgres-integration / browser-e2e |
| `README.md` / `docs/project-overview.md` / `docs/project-structure.md` | 存在（阶段状态待与 Phase7-B 真实交付对齐） |
| `docs/delivery/` | **不存在**（quick-start / demo-script / deployment-checklist / test-guide / troubleshooting / feature-acceptance / final-delivery-manifest 全缺） |
| 可复现演示 | 未按干净机器标准验证 |
| 结论 | 系统本体可运行，交付文档完成度不足 |

## 9. 模型分发许可状态

| 项 | 状态 |
|---|---|
| Git 跟踪的权重 | `models/**/*.pt` / `*.pkl` / `*.npz` **已公开**（education charcnn/tfidf、matching ridge/ranknet 等，数百个文件） |
| `models/LICENSE-MODELS.md` | 存在（`models-license-v1`），如实登记：匹配模型训练数据许可 **UNKNOWN**（卡片声明与正文矛盾）、教育数据 `apache-2.0`、模型分发许可全部 **UNKNOWN**、仓库根 **无 LICENSE** |
| 结论 | **文件已公开**与**许可未核实**并存；不得以声明文件替代真实许可证据；分发整改为 Phase7-B B4 专项 |

## 10. 仍需人工决定的事项

1. **许可证选择**：仓库根 LICENSE 与各模型族分发许可需作者/导师决定，Agent 不得擅自指定。
2. **已公开权重的处置**：是否转私有仓库 / Git LFS / Release 迁移 / 保持现状并披露风险——均需用户批准（注意：迁移不消除既有公开历史）。
3. **真实简历招募**：提供者招募、知情同意签署、标注员 A/B 与仲裁员必须为真实人类，Agent 不得代签/代标。
4. **Python 版本统一**：本地 3.13 vs CI 3.11 是否统一（本轮以双环境实测登记，不强行统一）。
5. **论文格式规范**：如学校有论文模板/章节规范，需提供后调整 `docs/thesis/` 结构。
6. **H2 是否纳入答辩口径**：Gold 未到位时，答辩须按「工程通过 + 真实效果未验证」口径表述。

---

**结论**：仓库与远端一致（`efcb237`），本地 py -3.13 复跑 Phase7 46/46 全绿，远端 CI 除缺 `phase7-gates` 外全绿；Gold 为 0、H2 BLOCKED；论文与交付文档为最大缺口；模型许可 UNKNOWN 需人工决策。
