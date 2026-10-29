# Phase5-1A 重构总结（refactoring-summary）

- 基线：`0225fcb`；日期：2026-10-29
- 策略：渐进式重构，小步可回滚；每批完成后跑回归；不重训模型、不改历史 checkpoint。

## Batch A：测试基础设施整改（P0，先行门禁）

**改动**：`tests/phase5_1r/run_all.py` 重写分组与报告逻辑（详见 `docs/architecture/adr/0004`）。

- 分组唯一来源 = `TEST_MODULES` 注册表（按加载模块归属），类名与分组解耦；
- 0 项测试 / 未知分组 → 退出码 2（"无测试但 PASS"被杜绝）；
- 部分组运行写 `test-results-<GROUP>.json`，仅全量运行更新正式报告；
- 聚合一致性断言（`sum(groups)==totals`、全部记录分组合法）+ 环境/commit 元信息。

**验证**：R5 独立运行 20 项、R6 独立运行 23 项、全量 151 项、`run_all.py R9` 退出码 2；
R9/R? 错误分组消失。Batch A 通过后才开始 Batch B。

## Batch B：共用规则抽取与依赖方向

**新增模块**（纯规则下沉，旧导入路径保留 re-export 兼容）：

| 新模块 | 承载 | 兼容出口 |
|---|---|---|
| `domain/skills_lexicon.py` | 技能词表 + 边界匹配（防 Java/JavaScript、C/C++、Spring/Spring Boot 子串误伤） | `annotation.pool.SKILL_LEXICON` 等 |
| `domain/job_rules.py` | `classify_job_category`、偏好段落、语言判定、职位词元化 | `annotation.pool.classify_job_category` |
| `domain/pii_masking.py` | PII 检测/掩码/导出检查（含姓名键值对） | `annotation.pii` |
| `infra/documents.py` | PDF/DOCX/TXT 文本抽取 | `annotation.resume_intake.extract_text` |

**迁移顺序**：先建 domain/infra → 迁移 1 个调用点（`service/skills_normalize`）并测试 →
迁移其余 5 个（`matching`/`job_parser`/`resume_parser`/`logging_utils`/`text_extract`）→
`pair_features`、`independent_eval/baselines` 改用 `domain.job_rules`。

**语义冻结**：规范名/别名仍由 `preprocess_skills.canonical_skill`（configs/skills.yaml）承担；
历史 checkpoint 输入特征语义不变（`training/feature_map.py` + `configs/feature_policy.yaml`）。

**验证**：`tests/phase5_1a` A2 组 9 项（依赖方向守卫 + 共用规则单一实现 + 兼容层）+
Phase5-1R 151 项 + Phase5-1 92 项全绿；隔离进程探针 `HEAVY=`（pandas 不再被业务 API 加载）。

## Batch C：应用服务与 API

**改动**：

- `service/settings.py`（新增）：类型化配置（API 环境、请求/上传/文本上限、批量岗位上限、
  推理时间预算、模型目录、日志级别、研究模型开关、Baseline 降级开关、部署安全要求），
  环境变量 `JM_*` 可覆盖，`to_config_dict()` 保留旧 config 键输出；
- `service/model_registry.py`：`classify_load_failure()` 三分类
  （env_incompatible / artifact_corrupt_or_load_failed / artifact_missing），
  可注入 `loader_impl`（测试替换接缝），保留惰性加载与缓存语义；
- `service/errors.py`：新增 `MODEL_ENV_INCOMPATIBLE`（HTTP 503），旧错误码全保留；
- `service/api.py` / `text_extract.py`：请求边界与 Base64 预检顺序（F-007 语义保留并集中常量）。

**兼容性**：API 请求/响应结构、错误码、CLI 参数与退出码均无变化（见 compatibility-matrix.md）。

## Batch D：环境、冻结完整性、CI 与文档

- **环境三分**：`environment.yml`（历史训练环境，冻结不动）、
  `environment-service.yml`（Serving）、`environment-legacy-model.yml`（旧 checkpoint 兼容）、
  `requirements-test.txt`（测试附加）；
- **模型兼容诊断**：`scripts/phase5_1a/diagnose_model_compat.py` →
  `reports/phase5-1a/model-compatibility.{json,md}`（22 loaded / 15 版本漂移警告 / 5 env_incompatible）；
- **冻结完整性补缺**：`scripts/phase5_1a/check_artifact_integrity.py`
  （manifest 规范化摘要、清单外文件、路径歧义；明确哈希 ≠ 签名防篡改）；
- **历史基线保护**：`tests/model_training/run_all.py` 改为
  "只有全量且全通过才更新基线报告 `model-tests.json`，否则写 `model-tests-run-*.json` 诊断"
  + 注册表分组（消除与 P0 同源的类名分组脆弱性）；
- **CI**：`.github/workflows/quality-gates.yml`（纯 Python：语法/导入检查、
  Phase5-1R 151、Phase5-1A 26、Phase5-1 92、Phase4-3A 237、数据闸门 74、
  隐私与冻结完整性、模型兼容登记（允许失败但必须登记）、报告一致性检查；
  训练完整性/GPU 复现为独立手动工作流）；
- **文档**：`docs/architecture/phase5-1a-{current-state,target-state,dependency-rules}.md`、
  `docs/architecture/adr/0001–0004`、`reports/phase5-1a/*`、`reports/phase5-1r/*`（验收闭环）。

## 回滚性

各批改动相互独立：Batch A 仅动 `tests/phase5_1r/run_all.py`；
Batch B 新增 domain/infra 并保留旧导入路径（re-export 可随时反向）；
Batch C 保留旧配置键与旧错误码；Batch D 只新增文件。
任一批可单独 `git checkout` 回退而不影响其它批。
