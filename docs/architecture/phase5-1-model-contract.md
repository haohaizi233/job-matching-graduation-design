# Phase5-1 模型契约（Model Contract）

- 生成时间：2026-10-29
- 适用范围：`src/job_matching/service/`（模型注册表、匹配适配层、岗位学历解析）
- 相关文档：`docs/architecture/phase5-1-integration-audit.md`、`docs/api/phase5-1-api.md`
- 配套产物：`reports/phase5-1/model-compatibility.json`（只读加载探测）

> 铁律：本契约只描述**工程可调用性**。任何历史模型分数都不是录用概率；
> Phase5-1 集成通过不代表中文人岗匹配模型效果验收通过。

---

## 1. 模型注册信息（`ModelRegistration`）

每个在业务服务中出现的模型必须登记以下字段（`GET /api/v1/models` 原样返回）：

| 字段 | 含义 | 示例 |
|---|---|---|
| `model_id` | 业务稳定标识 | `legacy_match_proxy_v1` |
| `model_version` | 版本（run 目录名 / 语义版本） | `ridge-double_cold-final-20261028-203750` |
| `task_type` | 任务类型 | `match_ranking` / `education_multilabel` / `heuristic_ranking` |
| `training_data_version` | 训练数据版本与口径 | `dv-english-proxy-labels(phase4-1)` |
| `input_schema_version` | 输入契约版本 | `phase5-1-input-v1` |
| `evaluation_status` | 评估状态（见 §2） | `research_only_proxy_labels` |
| `supported_languages` | 训练/验证语言 | `["en"]` |
| `artifacts` | 权重/清单文件及 sha256 | `[{"path": "...", "sha256": "..."}]` |
| `checksum` | 权重校验和 | `model.pkl:<sha256>` |
| `limitations` | 限制声明（必填，随结果透出） | "代理标签…" |
| `formal_use_allowed` | 派生：是否允许正式模式 | 见 §2 |
| `load_state` / `load_count_total` / `checksum_check` | 运行期状态（仅 status 端点） | |

## 2. 评估状态与正式模式门禁

`evaluation_status` 取值（封闭集合）：

| 取值 | 含义 | `formal_use_allowed` |
|---|---|---|
| `not_a_trained_model` | 启发式/规则，无训练 | 允许（但分数仍是 heuristic_score） |
| `research_only_proxy_labels` | Phase4-1 英文代理标签模型 | 禁止 |
| `research_only_zh` | Phase4-2 中文学历模型（未做正式效果验收） | 禁止 |
| `verified` | Phase4-3B 验证完成后才允许 | 允许 |
| `pending_phase4_3b` | future_verified 预留槽位 | 禁止 |

`formal_use_allowed = evaluation_status ∈ {not_a_trained_model, verified} 且 "zh" ∈ supported_languages`。

正式模式（`options.formal=true`）对不满足上表的模型一律返回
`MODEL_FORMAL_USE_FORBIDDEN`（422），错误 detail 携带 `evaluation_status` 与 `supported_languages`。

## 3. 三种运行模式（`MatchingService.rank`）

| mode | 打分来源 | score_type | 允许正式模式 | 说明 |
|---|---|---|---|---|
| `baseline` | 中文技能覆盖率 + 岗位类别 + 文本相关性（启发式） | `heuristic_score` | 是（但不等于已验证精度） | 不依赖任何归档模型，无 GPU |
| `experimental_model` | Phase4-1 `MatchPredictor`（ridge/GB/mlp/ranknet） | `model_raw_score` | 否 | 仅研究/诊断；必须先过 §4 合法性校验 |
| `future_verified` | Phase4-3B 已验证中文模型 | （预留） | — | 当前返回 `FUTURE_MODEL_UNAVAILABLE`，**不伪称存在** |

`score_type ∈ {heuristic_score, model_raw_score, calibrated_score}`；
`calibrated_score` 只有在真实 Gold 数据支持并完成校准验证后才允许，**本轮全局禁用**。
所有结果均携带 `warnings`（含 `score_semantics:排序参考分，不是录用概率`）。

## 4. 旧模型输入合法性（`LegacyMatchAdapter`）

`experimental_model` 模式在调用 `MatchPredictor.predict_score()` 前，必须能从业务画像**合法构建**
`feature_map.RESUME_FIELDS / JOB_FIELDS` 全部字段：

| 特征字段 | 业务来源 | 缺失处理 |
|---|---|---|
| `target_position_norm` | `student.employment_intention`（必须非空） | 缺 -> `MODEL_INAPPLICABLE` |
| `job_title_norm` | `job.job_title`（必须非空） | 缺 -> `MODEL_INAPPLICABLE` |
| `skills_canonical_json` | 双方技能规范名列表 | 可为空列表（触发 `both_skills_empty`） |
| `inferred_category` / `category` | `annotation/pool.classify_job_category` 规则映射 | 映射为 5/6 英文枚举，未知落 `__OOV__` |
| `years_experience` | 业务画像不采集 -> **显式 NaN** | 由 FeatureMap 按 train 均值填充（既有合法行为） |

`MODEL_INAPPLICABLE`（422）的 detail 列出 `missing_fields` 与 `required_fields`。
**禁止**用读取目标值、伪造旧评分、构造虚假 embedding 的方式填充任何缺失特征
（`assert_no_forbidden_keys` + `policy.check_feature_columns` 双重强制，
禁用字段：`final_score / raw_score / semantic_score / skill_score / position_score /
category_score / experience_score / education_score / candidate_rank / candidate_rank_pct /
label_strength / label_ordinal`，命中 -> `LEAKAGE_GUARD`）。

## 5. 加载与降级

1. 模型只在**首次使用或缓存失效**时加载（`ModelRegistry.load` 惰性缓存，
   `load_count / cache_hits / load_events` 可审计）；
2. 权重/清单缺失或加载异常 -> `MODEL_MISSING`（503），**绝不伪造输出**；
3. `options.allow_fallback=true`（默认）时，`experimental_model` 的 `MODEL_MISSING`
   **透明降级 baseline**，结果 `warnings` 含 `degraded_to_baseline:MODEL_MISSING:<model_id>`，
   `score_type` 同步降为 `heuristic_score`；
4. `allow_fallback=false` 时显式返回错误，由调用方决定；
5. 岗位学历解析：模型不可用 -> **明确标识的规则模式**（`mode=rules_only` / `source=rule`），
   不生成任何 `model_*` 字段；模型可用 -> `mode=model+rule_fallback`，记录 `model_version`、
   `expression_seen_in_train`（表达式是否出现在训练槽位词表）、`confidence`（含义随结果返回）；
6. `confidence` 一律附 `confidence_meaning`："模型分数在预测标签上的均值，未经校准，不是真实正确概率"
   （画像字段的 `confidence` 同理："抽取/归一化启发式置信度，不是技能掌握概率"）。

## 6. 归档模型兼容性实测（2026-10-29，只读探测）

`python scripts/phase5_1/model_compatibility_report.py` -> `reports/phase5-1/model-compatibility.json`：

| 家族 | 目录数 | 可加载 | 问题 | 说明 |
|---|---|---|---|---|
| matching: ridge | 8 | 8 | 0 | 可加载；sklearn 1.8.0 加载 1.5.2 权重带 `InconsistentVersionWarning`，建议按 `environment.yml`（sklearn 1.5.2）运行 |
| matching: mlp / ranknet（torch） | 10 | 10 | 0 | CPU 加载与推理正常 |
| matching: gradient_boosting | 5 | 0 | 5 | **pickle 不兼容**：`AttributeError: __pyx_unpickle_CyHalfSquaredError`，checkpoint 为 sklearn 1.5.2 训练，当前解释器 sklearn 1.8.0 无法反序列化 |
| education: tfidf / charcnn | 17 | 17 | 0 | 加载与批量推理正常，`expression_seen_in_train` 可用 |

对业务服务的影响：`gradient_boosting` 任一 run 走 `experimental_model` 时 -> `MODEL_MISSING`
（或 `allow_fallback` 透明降级 baseline）；该问题**不通过重训练/覆盖 checkpoint 修复**，
正确做法是按 `environment.yml` 使用 scikit-learn 1.5.2 环境（见验收报告已知限制）。

## 7. 未来模型（future_verified）接入约定

Phase4-3B 验证完成的中文模型接入时必须：

1. 在 `ModelRegistry` 注册 `evaluation_status="verified"`、`supported_languages=["zh"]`、
   完整 `artifacts + checksum` 与 `limitations`；
2. 提供与 §4 同构的输入合法性校验（或声明自己的 `input_schema_version`）；
3. 复用 `build_match_result` 解释链路（四态技能结论 + 人工复核标记）；
4. 若宣称 `calibrated_score`，必须附 Gold 校准验证报告，否则只能返回 `model_raw_score`。

本轮**不创建**任何上述模型，不伪称存在已验证中文模型。
