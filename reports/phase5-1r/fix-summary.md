# Phase5-1R 整改修复总结（fix-summary）

> 缺陷逐条根因见 `defect-register.md`；验收结论见 `phase5-1r-acceptance.md`。
> 本文件只陈述真实执行结果，不编造验收信息。

## 1. 修复前仓库版本与工作区状态

- 整改前基线：`35103e5`（服务层）之前；整改代码落地提交：
  - `35103e5` feat(service)：契约/错误模型重构 + `service/requirements.py`（F-005/F-006/F-007/F-009）
  - `0eef825` feat(annotation)：金标冻结与标注质控（F-001/F-002/F-003/F-004 + 姓名 PII 补漏）
  - `e78b20a` test(phase5-1r)：R1–R6 回归套件、产物完整性校验、测试报告
- 验收审计基线（本轮 Phase5-1A）：`0225fcb91a17feec486afb81ae4de3d0e44b342d`。

## 2. F-001 至 F-009 各项根因

见 `reports/phase5-1r/defect-register.md`（每条含现象 / 根因 / 修复位置 / 回归用例）。

## 3. 实际修改文件与关键代码

| 文件 | 关键改动 |
|---|---|
| `src/job_matching/annotation/gold_gate.py` | 冻结前置/后置两阶段门禁（F-001） |
| `src/job_matching/annotation/completion.py`（新增） | 完成状态五态 + 仲裁四态判定（F-002/F-003） |
| `src/job_matching/annotation/freeze.py` | 互斥/唯一性检查、内容级硬性检查、重复冻结拒绝、安全发布（F-004） |
| `src/job_matching/annotation/pii.py` | 姓名键值对脱敏（二轮审计补漏） |
| `scripts/phase4_3a_2/annotation_qa.py` | 越权仲裁标记、完成状态联动（F-002/F-003） |
| `scripts/phase4_3a_2/freeze_gold.py` | 仲裁状态登记、无分歧不强制仲裁文件（F-003/F-004） |
| `src/job_matching/service/requirements.py`（新增） | 届别/经验规范化纯规则（F-005/F-006） |
| `src/job_matching/service/contracts.py` | 届别约束规范化（F-005） |
| `src/job_matching/service/explanations.py` | 届别真正比较；先特殊状态后缺失值（F-005/F-006） |
| `src/job_matching/service/job_parser.py` | 届别/经验解析接入（F-005/F-006） |
| `src/job_matching/service/api.py` | 请求边界上限、Base64 预检顺序、回环默认、限流/请求跟踪（F-007） |
| `src/job_matching/service/text_extract.py` | 解码后大小先于解析检查、临时目录清理（F-007） |
| `src/job_matching/service/errors.py` | 错误详情脱敏本地路径（F-007） |
| `src/job_matching/independent_eval/metrics.py` | 入口统一物化输入（F-009） |

## 4. 新增测试及对应缺陷编号

`tests/phase5_1r/`（151 项，`TEST_MODULES` 注册表分组）：

| 组 | 模块 | 项数 | 覆盖缺陷 |
|---|---|---:|---|
| R1 | test_r1_gold_freeze | 15 | F-001、F-003、F-004 |
| R2 | test_r2_annotation_quality | 33 | F-002、F-003 |
| R3 | test_r3_business_constraints | 39 | F-005、F-006 |
| R4 | test_r4_api_boundary | 21 | F-007 |
| R5 | test_r5_metrics_input | 20 | F-009 |
| R6 | test_r6_e2e_chains | 23 | F-007/F-008 联动 + 链路 B/C |

## 5. 三条端到端正向链路真实执行结果

`python tests/phase5_1r/run_all.py`（2026-10-29 复跑，86.05s）：

| 链路 | 状态 | 通过/总数 | 说明 |
|---|---|---|---|
| chain_a_gold_freeze_engineering | PASS | 15/15 | 冻结工程模拟，**不构成真实 H2 PASS** |
| chain_b_resume_job_recommendation | PASS | 8/8 | 简历→画像→排序→解释，合成夹具 |
| chain_c_model_error_and_degradation | PASS | 15/15 | 模型错误分类与降级语义 |

摘要落盘：`reports/phase5-1r/positive-flow-validation.json`。

## 6. 各历史测试套件执行结果（2026-10-29 复跑）

| 套件 | 命令 | 结果 |
|---|---|---|
| Phase4-3A | `python tests/phase4_3a/run_all.py` | **237/237 PASS** |
| Phase5-1 | `python tests/phase5_1/run_all.py` | **92/92 PASS** |
| Phase5-1R | `python tests/phase5_1r/run_all.py` | **151/151 PASS** |
| 数据管线 | `python tests/data_pipeline/run_all.py` | 74/74（前轮记录，G1–G7） |
| 模型训练 | `python tests/model_training/run_all.py` | 20/21；T5 setUpClass ERROR = 旧 sklearn checkpoint 环境不兼容（§9） |
| 学历训练 | `python tests/education_training/run_all.py` | 35/36；仅 `pip check` 失败（共享解释器三方包冲突） |

## 7. 数据及模型权重完整性校验结果

- `python scripts/phase5_1r/artifact_integrity.py`：`reports/phase5-1r/artifact-integrity.json`
  对 `data/raw/**`、`models/**`、`data/independent_eval/frozen/**` 与历史评估报告逐文件 SHA-256 登记；
- `python scripts/phase5_1a/check_artifact_integrity.py`：`reports/phase5-1a/artifact-integrity.json`
  补齐 manifest 规范化摘要 / 清单外文件 / 路径歧义三类检查；
- 历史 checkpoint（`models/**`）零改动：本轮无重训、无转换、无改写。

## 8. R1–R6 六道门禁状态

全部 PASS（151/151，无 FAIL/ERROR/SKIP；聚合一致性断言全绿）。
链路 A 为工程模拟，H2 维持 **BLOCKED**（真实中文简历、双人 Gold 标签与合法盲测集未到位）。

## 9. 剩余风险与未解决事项

1. 旧 scikit-learn checkpoint（5 个 gradient_boosting）在当前环境不可反序列化，
   需 Legacy 兼容环境；15 个权重带版本漂移警告（详见 `reports/phase5-1a/model-compatibility.md`）。
2. 共享解释器 `pip check` 三方依赖冲突（非项目依赖）。
3. 冻结完整性为普通哈希自检，不等于可信签名防篡改。

## 10. Git 未提交修改清单

见 `reports/phase5-1a/phase5-1a-acceptance.md` §工作区清单（含建议提交信息）。
