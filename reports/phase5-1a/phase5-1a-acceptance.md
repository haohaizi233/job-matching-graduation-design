# Phase5-1A 验收报告（phase5-1a-acceptance.md）

- 验收日期：2026-10-29
- 基线提交：`0225fcb91a17feec486afb81ae4de3d0e44b342d`（HEAD，未移动）
- 证据目录：`reports/phase5-1a/`（本文件、architecture-audit、refactoring-summary、
  compatibility-matrix、dependency-graph、runtime-deps、model-compatibility、
  artifact-integrity、test-results）
- 阶段状态以 `docs/project-overview.md` 的阶段表为唯一清单（已同步 Phase5-1A 行）。
- **H2 维持 BLOCKED**：本轮为架构治理，不产生业务结论，不触碰真实简历与私人授权记录。

## 一、A1–A7 门禁结论

| 门禁 | 结论 | 关键证据 |
|---|---|---|
| A1 测试可信性 | **通过** | R5 独立 20 项、R6 独立 23 项、全量 151 项准确分入 R1–R6；R9/R? 分组消失；`run_all.py R9` 退出码 2；0 项测试退出码 2；部分组运行写 `test-results-R5/R6.json` 不覆盖全量报告；聚合一致性断言全绿（`reports/phase5-1r/test-results.json` `consistency` 字段） |
| A2 架构边界 | **通过** | `service/** → annotation/**` 跨层边 **0**（`reports/phase5-1a/dependency-graph.md` 实测）；隔离进程导入 `service.api` 输出 `HEAVY=`（pandas/torch/sklearn 不加载）；domain 纯规则守卫 9 项（`tests/phase5_1a` A2 组） |
| A3 接口兼容 | **通过** | Phase5-1 92/92 PASS（含 S19–S22 API 契约）；旧错误码全保留、仅新增 `MODEL_ENV_INCOMPATIBLE`；旧导入路径（`annotation.pool/pii/resume_intake`）re-export 兼容且有守卫测试；CLI 参数与退出码语义不变（`reports/phase5-1a/compatibility-matrix.md`） |
| A4 模型兼容 | **通过** | `classify_load_failure()` 三分类（env_incompatible / artifact_corrupt / artifact_missing）；5 个 GBM checkpoint 登记为 `env_incompatible`（历史环境 py3.11.18/sklearn1.5.2）；15 个权重版本漂移警告；`models/**` 零改动（SHA-256 登记 `reports/phase5-1r/artifact-integrity.json`）；未重训、未转换、未改写 |
| A5 数据安全 | **通过** | 姓名键值对 PII 脱敏（`domain/pii_masking.name_kv`）；导出前 `check_export()` 强校验；掩码≠匿名化口径全仓统一；Gold 阻断与冻结不可变性 R1/R2 全绿；冻结完整性自检 1/1 OK（`reports/phase5-1a/artifact-integrity.json`，含"哈希≠签名防篡改"能力边界声明） |
| A6 测试回归 | **通过（含登记的不可执行项）** | 237/237、92/92、151/151、74/74 全绿；**无新增回归失败**；不可执行项如实登记：T5 独立推理（旧 sklearn checkpoint 环境不兼容）、`pip check`（共享解释器三方包冲突）；历史基线报告 `reports/model-training/model-tests.json` 受保护不被覆盖 |
| A7 文档交付 | **通过** | 现状/目标/依赖规则三份架构文档 + ADR 0001–0004 + 架构审计/重构总结/兼容性矩阵 + Phase5-1R 验收三件套（acceptance/defect-register/fix-summary）均与代码一致；`docs/project-overview.md` 为唯一阶段状态清单 |

门禁自检可执行证据：`python tests/phase5_1a/run_all.py` → **26/26 PASS**
（A1 4 项、A2 9 项、A4 6 项、A6 3 项、A7 4 项，`reports/phase5-1a/test-results.json`）。

## 二、任务书十问

### 1. 优化前后的依赖图有什么区别？

- **前**：`service/matching|job_parser|skills_normalize → annotation.pool`，
  `service/resume_parser|logging_utils|job_parser|skills_normalize → annotation.pii`，
  `service/text_extract → annotation.resume_intake`，共 6 处业务→研究跨层边；
  `import job_matching.service.api` 实测加载 numpy + **pandas**（pandas 全部来自 `annotation.pool` 链）。
- **后**：上述边全部消失；纯规则下沉 `domain/{skills_lexicon,job_rules,pii_masking}`，
  文档抽取下沉 `infra/documents`，研究层 re-export 保持旧路径可用；
  `service.api` 隔离进程探针 `HEAVY=`（空）。
- 证据：`reports/phase5-1a/dependency-graph.{json,md}`（AST 实测）、`runtime-deps.json`、
  图对比见 `reports/phase5-1a/architecture-audit.md` §3/§4。

### 2. 哪些模块职责发生变化？

| 模块 | 变化 |
|---|---|
| `annotation/pool.py` | 只保留研究数据工程（数据源/配对/清单/合成样本）；词表、岗位类别、职位词元化移交 `domain`（re-export 兼容） |
| `annotation/pii.py` | PII 检测/掩码/导出检查移交 `domain/pii_masking`，自身为薄兼容层 |
| `annotation/resume_intake.py` | 文本抽取移交 `infra/documents`，保留授权/导入职责 |
| `pair_features.py` | `title_tokens` 移交 `domain/job_rules`（re-export） |
| `service/model_registry.py` | 新增加载失败分类职责（`classify_load_failure`）与可注入 `loader_impl` |
| `service/settings.py`（新） | 承接散落常量的类型化配置 |
| `tests/phase5_1r/run_all.py`、`tests/model_training/run_all.py` | 分组改注册表驱动；报告写入增加基线保护语义 |

### 3. 哪些重复实现被消除？

1. 技能边界匹配：`annotation/pool._SKILL_RES` + `service/skills_normalize._boundary_regex`
   两份 → `domain.skills_lexicon.boundary_regex` 一份（守卫测试断言两处 pattern 一致）；
2. 启发式技能词表：`annotation/pool.SKILL_LEXICON` + service 侧副本 → `domain.skills_lexicon.SKILL_LEXICON`；
3. 岗位类别/偏好段落/语言判定/职位词元化：pool 与 service/pair_features 各一份 → `domain/job_rules`；
4. PII 检测掩码：service 直接依赖研究层实现 → `domain/pii_masking` 单一实现（`pii.mask_matches is mask_matches`）；
5. 文档抽取：`annotation/resume_intake` 内嵌实现 → `infra/documents` 单一实现。
   规范名/别名仍为 `preprocess_skills.canonical_skill` 唯一入口（Java≠JavaScript、C≠C++、
   Spring≠Spring Boot，铁律测试锁定）。**刻意保留的双实现**：数据工程口径
   `annotation/pool.parse_experience_requirement` vs 业务口径
   `service/requirements.parse_experience_requirement_detail`（语义不同，见依赖规则 §2）。

### 4. 哪些跨层依赖被移除？

- `service/** → annotation/**`：6 处全部移除（静态实测 0 边 + A2 守卫测试长期锁定）；
- `service/text_extract → annotation.resume_intake` → `infra/documents`；
- `independent_eval/baselines → annotation.pool`（岗位类别）→ `domain.job_rules`；
- `pair_features → annotation.pool`（词元化）→ `domain.job_rules`。
- 保留（允许）：研究层内部 `independent_eval.dataset → annotation.freeze`；
  研究层 → domain 的正向依赖。

### 5. 哪些API和CLI保持完全兼容？

- HTTP：Phase5-1 全部端点的请求/响应结构、错误信封、错误码（新增码仅 `MODEL_ENV_INCOMPATIBLE`）、
  请求上限语义、配置键输出——见 `reports/phase5-1a/compatibility-matrix.md` §1；
- CLI：`freeze_gold.py`（precheck/freeze/verify）、`annotation_qa.py`、各 `tests/**/run_all.py`
  参数与退出码语义——见同文件 §2（运行器新增退出码 2 属缺陷修复：原先"0 测试也 PASS"）；
- Python 导入路径：`annotation.pool/pii/resume_intake` 旧符号可用，且与新实现为同一对象。

### 6. 哪些历史模型仍受环境限制？

- **5 个** `matching/gradient_boosting/*` checkpoint：当前环境
  （py3.13 / sklearn 1.8.0）反序列化失败
  `AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError'`，
  分类 `env_incompatible` → `MODEL_ENV_INCOMPATIBLE`；需
  `environment-legacy-model.yml`（py3.11 / sklearn 1.5.2）加载；**禁止重训修复**；
- **15 个**（education/tfidf + matching/ridge）：可加载但 `InconsistentVersionWarning`，
  输出不保证与训练时逐位一致，正式口径数值需 Legacy 环境复核；
- **22 个**（charcnn/mlp/ranknet 等）当前环境可加载。
- 明细：`reports/phase5-1a/model-compatibility.md`（逐模型）。

### 7. 哪些问题被证明不值得现在重构？

见 `docs/architecture/phase5-1a-current-state.md` §4：
① `service/` 重命名为 `application/` 并引入用例类（迁移风险 > 收益）；
② 为每个函数建 Protocol/Port（与复杂度不匹配，仅保留 Services 容器 + ModelRegistry 接缝）；
③ FastAPI Lifespan 重写生命周期（现有惰性缓存已被 R6 链路 C 锁定）；
④ 合并两种"经验解析"（语义刻意不同）；
⑤ 迁移 pytest（现有 unittest 稳定）；
⑥ 重训/转换旧 checkpoint（禁止改动历史训练成果）。

### 8. A1–A7各自是否通过？

见 §一：7 项全部通过（A6 附 2 项已登记的"无法执行"）。

### 9. 全部测试真实执行结果是什么？

2026-10-29 实测（命令均为仓库根目录执行）：

| 命令 | 结果 | 落盘证据 |
|---|---|---|
| `python tests/phase5_1r/run_all.py` | **151/151 PASS**（86.05s，R1 15/R2 33/R3 39/R4 21/R5 20/R6 23） | `reports/phase5-1r/test-results.json` |
| `python tests/phase5_1r/run_all.py R5` | 20/20 PASS | `test-results-R5.json` |
| `python tests/phase5_1r/run_all.py R6` | 23/23 PASS | `test-results-R6.json` |
| `python tests/phase5_1r/run_all.py R9` | 退出码 2（未知分组拒绝） | — |
| `python tests/phase5_1a/run_all.py` | **26/26 PASS**（3.8s） | `reports/phase5-1a/test-results.json` |
| `python tests/phase4_3a/run_all.py` | **237/237 PASS**（1.04s） | `reports/phase4-3a/test-results.json` |
| `python tests/phase5_1/run_all.py` | **92/92 PASS**（5.74s） | `reports/phase5-1/test-results.json` |
| `python tests/data_pipeline/run_all.py` | **74/74 PASS**（G1–G7，52.5s） | `reports/data-quality-gates.json` |
| `python tests/model_training/run_all.py` | 20 PASS / 1 ERROR（T5 setUpClass = 旧 sklearn 反序列化失败，`env_incompatible`，非业务失败） | `reports/model-training/model-tests-run-20261029-143259.json`（诊断）；基线 `model-tests.json` 保持训练环境 25/25 归档不动 |
| `python tests/education_training/run_all.py` | 35/36（仅 `pip check` 失败：共享解释器三方包冲突，非项目依赖） | `reports/education-training/education-tests.json` |
| `python scripts/phase5_1a/check_artifact_integrity.py` | 1/1 OK | `reports/phase5-1a/artifact-integrity.json` |
| `python scripts/phase5_1a/diagnose_model_compat.py` | 22 loaded / 15 版本警告 / 5 env_incompatible | `reports/phase5-1a/model-compatibility.json` |

FAIL / ERROR / SKIP 分别统计，无 SKIP 被计为通过；"无法加载外部权重"一律登记为
环境不兼容，不表述为业务逻辑通过。

### 10. 工作区有哪些修改和未提交文件？

**已按批次提交并推送至 `origin/main`（应用户要求），提交清单：**

| 提交 | 内容 |
|---|---|
| `1e86a77` | 测试运行器可信化（注册表分组/0 测试报错/基线报告保护）+ Phase5-1A 门禁自检 + R5/R6 分组报告 |
| `375e532` | 纯规则下沉 domain/infra，移除 service→annotation 跨层依赖 |
| `42f22d3` | 类型化配置与模型加载失败三分类 |
| `482bcff` | 环境三分、模型兼容诊断与最小 CI 质量门禁 |
| `0eb9210` | 架构文档、ADR 与阶段状态同步 |
| （本提交） | 验收报告、证据文件与各套件复跑记录 |

覆盖文件：`src/job_matching/` 22 个（domain/infra 新增 6 个 + 调用点迁移与兼容层）、
`tests/` 4 个、`scripts/phase5_1a/` 3 个、`docs/` 8 个、`reports/` 23 个、
`environment-*.yml` / `requirements-test.txt` / `.github/workflows/quality-gates.yml`。

**刻意不入库**：`.tmp_*` 临时残留 13 个（`_batch_b_*`、`_depgraph*`、`_runtime_deps_probe`、
`_edu_out*`、`_mt_out`、`_p43a_out`、`_p51_out`、`_smoke_freeze`、`_taskbook`），
为调试残留，可人工清理。

## 三、遗留与边界

1. H2 维持 **BLOCKED**（真实中文简历、双人 Gold、合法盲测集未到位）；
2. 5 个 GBM checkpoint 待 Legacy 环境复核（历史指标数值暂不引用）；
3. `pip check` 三方包冲突属环境问题；
4. 服务默认本地开发、无认证：未经网关与认证不得公网部署（配置强制声明）；
5. 冻结完整性为哈希自检，不等于防恶意篡改。
