# Phase5-3 / M5 推理契约与模型接口一致性验证报告

- 运行身份：`local-20261031`（隔离临时 sqlite + 合成夹具探针）
- 执行日期：2026-10-31
- 执行环境：Windows 11（10.0.26200）、Python 3.13.2、FastAPI / SQLAlchemy 2.0.45
- 基线提交：`25743f2`（`feat/phase5-3-integration`）
- 纪律：历史 checkpoint 只做**加载实测**，不重训、不转换、不修改；
  测试数据全部为合成夹具；降级绝不伪装成模型输出。

## 1. 验证范围

任务书第七节：模型注册表能力、模型加载错误类型、`allow_fallback` 契约、
降级信息传递（API → 持久化 → 前端）、版本可追踪、评分口径不冒充录用概率。

## 2. 推理契约登记（探针 `scripts/phase5_3/model_serving_probe.py`）

命令：

```powershell
$env:PYTHONPATH="src"
py -3.13 scripts\phase5_3\model_serving_probe.py --out reports\phase5-3\model-serving-probe.json
```

退出码 **0**，登记 **PASS=10 / FAIL=0 / ENV_INCOMPATIBLE=0**（`reports/phase5-3/model-serving-probe.json`）：

| 编号 | 验收项 | 状态 | 实测证据 |
|---|---|---|---|
| MS01 | 注册表能力与声明一致（不存在的模型不冒充） | PASS | `baseline_skill_text_v1=not_a_trained_model/formal:True`；`legacy_match_proxy_v1=research_only_proxy_labels/formal:False`；`chinese_match_future_v1=pending_phase4_3b/formal:False`；`no_such_model → MODEL_MISSING`；`education_normalizer_v1` 未挂载（如实登记"未登记"，非冒充） |
| MS02 | baseline 真实链路 | PASS | `score_type=heuristic_score`、`degradation=None`、警示含 `score_semantics` |
| MS03 | 显式模型缺失 + `allow_fallback=True` → 显式降级 | PASS | `degradation={degraded:true, reason_code:MODEL_MISSING, failure_kind:model_not_registered, requested_model_id:no_such_model, actual_scoring_method:baseline_skill_text_v1}` |
| MS04 | `allow_fallback=False` → 显式错误且不落运行记录 | PASS | HTTP 503 `MODEL_MISSING`，运行记录数 2 → 2（无半成功行） |
| MS05 | 降级快照持久化与回读一致 | PASS | 降级运行 `degradation_info` 回读完整；未降级运行保持 `NULL`（不乐观回填） |
| MS06 | `future_verified` 槽位不冒充 | PASS | HTTP 503 `FUTURE_MODEL_UNAVAILABLE` |
| MS07 | 正式模式门禁 | PASS | `formal=True` + 英文代理模型 → `MODEL_FORMAL_USE_FORBIDDEN`（未过中文正式用途验证不得进正式模式） |
| MS08 | 历史 checkpoint 当前环境真实加载 | PASS | 实测加载 `ridge-double_cold-final-20261028-203750`（只读，未修改未重训） |
| MS09 | 评分口径 | PASS | `formal_evaluation=False`；分数标注"排序参考分，不是录用概率" |
| MS10 | 版本可追踪 | PASS | `profile_version / model_version / scoring_config_version / job_set_snapshot / request_fingerprint` 齐备 |

## 3. 三种运行模式与错误分类（契约现状）

| 模式 | 语义 | 实测行为 |
|---|---|---|
| `baseline` | 启发式排序（非训练模型） | `heuristic_score`，警示 `heuristic_baseline_unvalidated` + `score_semantics` |
| `experimental_model` | 历史模型（英文代理标签 / 研究用途） | `model_raw_score`；`formal=True` 一律拒绝（`MODEL_FORMAL_USE_FORBIDDEN`） |
| `future_verified` | Phase4-3B 后的中文模型预留槽位 | 显式 `FUTURE_MODEL_UNAVAILABLE`，不伪造权重 |

加载错误三分（`model_registry.classify_load_failure`）+ 稳定错误码：

`MODEL_MISSING`（权重/清单缺失）/ `MODEL_CORRUPT`（损坏）/ `MODEL_ENV_INCOMPATIBLE`
（旧依赖栈不兼容，禁止重训掩盖）/ `MODEL_INAPPLICABLE`（输入无法合法构建特征）。

`allow_fallback` 契约（`matching.py`）：

- 可降级：`MODEL_MISSING` / `MODEL_CORRUPT` / `MODEL_INAPPLICABLE` 且 `allow_fallback=True`；
- **模型未注册**只在调用方**显式指定** `model_id` 时才按策略降级；默认模型槽位未注册
  属于部署配置错误，一律显式失败（防止线上长期静默降级成启发式分）；
- 永不降级：正式模式门禁、future 槽位、推理超时、目标泄漏护栏、请求非法。

## 4. 降级信息持久化（Phase5-3 / M5 新增）

**问题**：降级此前只体现在 `warnings` 里，历史运行无法结构化追溯"这次到底用没用模型"。

**改动**：

- 迁移 `alembic/versions/d7e8f9a0b1c2_reco_degradation_info.py`：
  `recommendation_runs` 增加 `degradation_info`（JSON，可空；PG 侧 JSONB 变体）；
- `reco_store.py`：运行创建时写入 `degradation_info`，运行详情回读；
  `result_summary.degradation` 透出（只加不减，未降级保持 `NULL`）；
- `frontend/src/api/types.ts` + `MatchingView.vue`："是否发生降级"由硬编码"否"
  改为读取真实降级快照，降级时显示原因码与请求模型；
- 回归断言：`tests/phase5_2/test_t6_failures.py` 新增降级可追溯断言
  （`result_summary.degradation` + 运行记录 `degradation_info` + 未降级不回填）。

## 5. 测试证据汇总

| 测试套件 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| M5 探针（MS01–MS10） | `py -3.13 scripts\phase5_3\model_serving_probe.py` | **10 PASS / 0 FAIL** | 0 |
| Phase5-1（S01–S24，含 S13–S16 模型契约） | `py -3.13 tests\phase5_1\run_all.py` | **92 PASS / 0 FAIL** | 0 |
| Phase5-2（T1–T8，含 T6 降级断言） | `py -3.13 tests\phase5_2\run_all.py` | **61 PASS / 0 FAIL / 1 SKIP** | 0 |
| 历史权重完整性 | `scripts/phase5_1a/check_history_weights_integrity.py` | **PASS**（79 文件与冻结基线一致） | 0 |

注：Phase5-2 唯一 SKIP 为依赖外部故障注入条件的事务用例（历史口径，`NOT_RUN`）。

## 6. 版本与口径可追踪性

- `RecommendationRun` 持久化：`profile_version` / `profile_content_hash` /
  `model_version` / `scoring_config_version` / `job_set_snapshot` /
  `request_fingerprint` / `request_semantic_hash` / `degradation_info`；
- 口径约束：`heuristic_score` / `model_raw_score` 均在 API 与前端标注
  "排序参考分，不是录用概率"；`formal_evaluation` 恒为 `false`；
  `evaluation_status` 区分 `not_a_trained_model` / `research_only_proxy_labels`。

## 7. 遗留与边界（如实登记）

| 项 | 状态 | 说明 |
|---|---|---|
| `education_normalizer_v1` 未挂载业务注册表 | NOT_RUN | 业务服务默认 `education_run_dir=None`；研究侧注册表可挂载，不冒充业务可用 |
| `chinese_match_future_v1`（中文匹配模型） | BLOCKED | 等 Phase4-3B（依赖 H2 真实 Gold），不伪造权重 |
| 真实中文场景有效性 | 未验证 | 代理标签模型 + 启发式基线均未经中文 Gold 验证（见 `08-real-evaluation-readiness.md`） |
| 历史权重完整性 | PASS（哈希自检） | 可发现非预期改动，**不等于**可信签名防篡改（`history-weights-integrity.json` 已注明） |

## 8. 结论

**M5 推理契约一致性：PASS**。三模式契约、错误分类、`allow_fallback` 语义、
降级可追溯（API + 持久化 + 前端）、版本追踪、评分口径全部实测通过；
历史模型产物未做任何修改；模型有效性结论不冒充（详见 08 报告）。
