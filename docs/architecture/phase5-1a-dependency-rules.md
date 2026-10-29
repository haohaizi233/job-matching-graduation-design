# Phase5-1A 依赖规则（硬约束 + 检查方法）

> 这些规则由 `tests/phase5_1a/run_all.py` 自动守卫（A2 组），
> 违反即视为架构回退，CI 会失败。

## 1. 允许/禁止矩阵

| 源 \ 目标 | domain | infra | service | annotation/training/evaluation/independent_eval | 外部重依赖 |
|---|---|---|---|---|---|
| `domain/**` | ✅ | ❌ | ❌ | ❌ | ❌（仅 stdlib） |
| `infra/**` | ✅ | ✅ | ❌ | ❌ | ✅（外部格式库，如 fitz） |
| `service/**` | ✅ | ✅ | ✅ | ❌ | ✅（fastapi/pydantic 仅 api.py） |
| `annotation/**` `training/**` `evaluation/**` `independent_eval/**` | ✅ | ✅ | ❌ | ✅ | ✅（numpy/pandas/torch 允许） |
| `scripts/**` / `tests/**` | ✅ | ✅ | ✅ | ✅ | ✅ |

补充规则：

1. `domain` 不做 IO：不读文件、不读配置、不加载模型、不打日志到文件；
2. `service` 允许依赖 `inference/predictor`、`education/predictor`（模型推理路径），
   但必须经 `ModelRegistry` 的可替换 loader，不得在路由函数内直接 `joblib.load`；
3. 研究层内部依赖不受限（`independent_eval → annotation.freeze` 允许）；
4. 兼容 re-export（`annotation.pool`、`annotation.pii`、`annotation.resume_intake`
   转发 domain/infra 符号）**只允许**为"旧导入路径"服务，不得重新引入新逻辑。

## 2. 单一实现清单（禁止重复实现）

| 规则 | 唯一实现 | 兼容出口（旧路径） |
|---|---|---|
| 技能边界匹配（防子串误伤） | `domain.skills_lexicon.boundary_regex` | `annotation.pool._SKILL_RES`（历史） |
| 启发式技能词表 | `domain.skills_lexicon.SKILL_LEXICON` | `annotation.pool.SKILL_LEXICON` |
| 技能规范名 / 别名 | `preprocess_skills.canonical_skill`（configs/skills.yaml） | — |
| 岗位类别启发式 | `domain.job_rules.classify_job_category` | `annotation.pool.classify_job_category` |
| PII 检测/掩码/导出检查 | `domain.pii_masking` | `annotation.pii` |
| 文档文本抽取 | `infra.documents.extract_text` | `annotation.resume_intake.extract_text` |
| 毕业届别约束解析 | `service.requirements.parse_cohort_requirement` | —（唯一实现，禁止调用方各自解析） |
| 工作经验约束解析（业务口径） | `service.requirements.parse_experience_requirement_detail` | — |
| 工作经验启发式（数据工程口径） | `annotation.pool.parse_experience_requirement` | —（与业务口径**刻意分离**，见下） |

### 两个"经验解析"为什么不合并

- `annotation/pool.parse_experience_requirement`：数据工程抽样分层用，宽松启发式，
  输出 `{raw, years_min, source}`；
- `service.requirements.parse_experience_requirement_detail`：业务资格约束用，
  只从"经验语境子句"解析，区分 `none_required / preference_only / unknown`，
  禁止把项目/实习经历条数等同工作年限。

合并会把两种语义混为一谈，因此保留双实现但**分别命名、分别测试**（R3 组覆盖业务口径）。

## 3. 模型与特征语义冻结

1. 历史 checkpoint（`models/**`）只读：不重训、不改写、不迁移；
2. 训练特征语义由 `training/feature_map.py` + `configs/feature_policy.yaml` 冻结；
   `domain` 层的规范化改动**不得**改变历史 checkpoint 的输入语义；
   需要变更语义时新增版本号（如 `lexicon_v2`）并保留 v1 适配器；
3. 推理特征必须走与训练相同的 `compute_pair_raw_features`，不得在 service 内重写特征。

## 4. 错误语义兼容映射

任务书建议的规范名 ↔ 现有公开错误码（API 消费者可见的是"现有错误码"列）：

| 规范名（内部表述） | 公开错误码 | `detail.failure_kind` | 触发场景 |
|---|---|---|---|
| MODEL_NOT_REGISTERED | `MODEL_MISSING` | `model_not_registered` | model_id 未登记 |
| MODEL_ARTIFACT_MISSING | `MODEL_MISSING` | `artifact_missing` | 权重文件缺失（FileNotFoundError） |
| MODEL_ARTIFACT_CORRUPT | `MODEL_CORRUPT` | `artifact_corrupt_or_load_failed` | 文件损坏 / 加载逻辑失败 |
| MODEL_ENV_INCOMPATIBLE | `MODEL_ENV_INCOMPATIBLE`（新增） | `env_incompatible` | 旧 scikit-learn 反序列化失败、依赖符号缺失、pickle 协议过高 |
| MODEL_INPUT_INAPPLICABLE | `MODEL_INAPPLICABLE` | — | 输入缺字段，无法合法构建特征 |
| MODEL_NOT_VERIFIED | `MODEL_FORMAL_USE_FORBIDDEN` | — | 正式模式拒绝 research_only 模型 |
| （预留槽位） | `FUTURE_MODEL_UNAVAILABLE` | — | future_verified 模式无权重 |
| INFERENCE_TIMEOUT | `INFERENCE_TIMEOUT` | — | 推理超时预算 |

**兼容性说明**：旧错误码一律保留；`MODEL_ENV_INCOMPATIBLE` 是**新增**错误码，
只在"历史 checkpoint 与当前依赖栈不兼容"时出现（此前会被笼统归入 `MODEL_CORRUPT`）。
消费者若只认识 `MODEL_CORRUPT`，可按 `detail.failure_kind` 进一步区分。

**铁律**：旧 scikit-learn 反序列化失败**不得**记为"权重文件缺失"，也不得记为模型业务逻辑失败。

## 5. 隐私口径

| 产物 | 标准 | 允许表述 |
|---|---|---|
| 原始资料（data/private、真实简历） | 无授权记录拒绝进入；导入即掩码 | "已脱敏/已掩码" |
| 公开研究产物（冻结集、报告） | `check_export()` 全量校验后导出 | "已脱敏/已掩码" |
| 任何产物 | — | ❌ 不得声称"已匿名化"（掩码是可逆改写，不等于不可逆匿名化） |

日志展示掩码（`mask_matches`）与不可逆匿名化必须分开表述；
原始资料处理与公开研究产物的隐私标准分别定义（见 `annotation/consent.py` 与
`annotation/pii.py` 文档串）。

## 6. 检查方法

```bash
# 架构守卫 + 门禁自检（A1/A2/A4/A7）
python tests/phase5_1a/run_all.py

# 依赖图实测（生成 reports/phase5-1a/dependency-graph.*）
python scripts/phase5_1a/depgraph.py   # 若不存在，见 reports/phase5-1a/dependency-graph.json

# 运行时重依赖实测
python scripts/phase5_1a/diagnose_model_compat.py
```
