# Phase4-3B 验收报告

- 日期：2026-10-31
- 分支：`feat/phase4-3b-model-research`（基线提交：`d7babaa`）
- 测试：`tests/phase4_3b/run_all.py` → **PASS=154 / FAIL=0 / ERROR=0 / SKIP=0**（`test-results.json`）
## 一、总体评级

# **B：工程完成，但部分真实数据与模型验证仍被条件阻断。**

依据：B0–B4 全部完成且门禁通过（154 项测试全绿；14 个历史 run 兼容性复现、E00–E06 可执行原型、消融/统计/资源实测落盘；P11/P12 回归护栏补齐可复现性与推理超时契约）；B5 正式训练与可信实验、B6 正式模型选型因 **H2 真实人工 Gold = BLOCKED** 无法形成正式性能结论。
## 二、里程碑对照

| 里程碑 | 目标 | 状态 | 证据 |
|---|---|---|---|
| B0 模型与数据基线审计 | 成果与风险清晰 | **完成** | `00-research-baseline.md`、`model-registry.json`（43 条）、`05-dataset-protocol.md` |
| B1 历史模型复现 | 可复现部分通过、阻断可追踪 | **完成** | `02`/`03`（14/14 LOADED，matching 12 run 输出逐位一致；阻断项逐条登记） |
| B2 真实中文 Gold 准备 | 工具链通过、H2 如实登记 | **完成（H2 保持 BLOCKED）** | `04-gold-readiness.md`；P1/P10 用合成夹具验证全链路；真实配对 0 |
| B3 中文检索基线 | 可执行模型与指标实现 | **完成** | `06`：E00–E03 RUN；`src/job_matching/models/retrieval.py`、`evaluation/retrieval.py` |
| B4 两阶段匹配原型 | 召回/精排/融合可运行 | **完成** | `06`/`07`：E04–E06 RUN；BGE 编码 + Reranker + 硬/软约束融合 |
| B5 正式训练与可信实验 | 数据满足后真实执行 | **条件阻断** | E07 NOT_RUN；多随机种子 NOT_RUN；真实 Gold 对照 BLOCKED |
| B6 模型选型与集成交付 | 可信对照 + 稳定契约 | **工程交付完成，选型结论条件阻断** | `11`（工程建议）、`12`（集成契约与已验证/未验证清单）、`runtime_guard.py` + P12 |

## 三、门禁结果

| 门禁 | 结果 |
|---|---|
| 全量回归（154 用例） | PASS |
| 切分泄漏三层审计（ID / pair / 文本哈希） | PASS（实体级近似重复 <2% 如实登记，见 `split-text-overlap.json`） |
| checkpoint 真实性（SHA-256 逐个复核） | PASS（43/43） |
| 历史输出复现（COMPARE_HISTORICAL） | matching 逐位一致；education 数值近似（charcnn ≤1.2e-4），决策层 **label flip=0/32 split**（`15`） |
| 冻结不可改 / 合成不进 Gold / 导出脱敏 | PASS |
| 可复现性护栏（仓库根解析 + 行尾/冻结哈希） | PASS（P11，`.gitattributes` 钉死 LF） |
| 推理超时与降级契约 | PASS（P12 + `src/job_matching/models/runtime_guard.py`） |
| 千级/万级岗位池扩展性 + GPU 显存 | RUN（`14`：10000 条池向量 search@10 0.11s；GPU BGE 峰值 84.5MB / 精排峰值 1253.6MB） |
| 真实 H2 | **BLOCKED**（不解除、不代填） |

## 四、关键研究事实（均为合成代理口径，不构成真实推荐结论）

1. 传统关键词基线（TF-IDF/BM25）在中文短 JD 场景强于纯语义召回（B ndcg@5 0.560 vs 0.364）。2. BGE-Reranker 精排在代理标签口径下为负贡献：移除后 A ndcg@5 +0.142，配对 bootstrap 95% CI [0.036, 0.142]（8/8 组）。3. Skill/Experience/Intent 组件消融完全打平（夹具区分度低），不得解释为「组件无用」。4. education 决策层 32/32 split 零翻转，模型推理可复现；`tfidf-final-title` 曾现 3114 处 flip，排查为复现脚本 input_mode 口径缺陷（已修复并重跑归零，见 `15` 边界第 5 条）。5. 以上全部带 `gold_status: BLOCKED` 标记，真实 Gold 到位后必须重做。

## 五、未完成项（逐条，不省略）

| 项 | 状态 | 前置条件 |
|---|---|---|
| H2 真实 Gold（≥300 组授权配对 + 双人标注 + 仲裁 + 冻结） | BLOCKED | 人工数据与授权 |
| E07 合法监督数据微调 | NOT_RUN | 合法训练数据 + 盲测隔离 |
| 真实 Gold 上 E00–E06 正式对照与模型选型结论 | BLOCKED | H2 |
| 多随机种子实验 | NOT_RUN | 真实 Gold + 可训练模型 |
| ~~education 模型决策层一致性比对~~ | **已完成**（`15`） | — |
| ~~千级岗位池扩展性 / GPU 推理 / 显存峰值~~ | **已完成**（`14`） | — |
| ~~推理超时契约与测试~~ | **已完成**（P12 + `runtime_guard.py`） | — |
| 跨旧 sklearn 版本 GB 反序列化 | 本机未复现 | 需 Legacy 环境时再验 |
| double_cold 实体级近似重复（简历 18 / 岗位 2 哈希） | 登记为数据风险 | 新 Gold 按 ≥0.90 相似度隔离 |
| 含数据库的端到端延迟 | NOT_RUN | Phase5-3 集成侧职责边界 |

## 六、产物索引

- 报告：`reports/phase4-3b/00`–`15` + 本文件；结构化结果 `reports/model-research/{runs,manifests}`。
- 代码：`src/job_matching/models/{text_encoder,retrieval,reranker,fusion,runtime_guard}.py`、`src/job_matching/evaluation/retrieval.py`、`scripts/phase4_3b/`。
- 测试：`tests/phase4_3b/`（P1–P12 + run_all.py）。
- 登记：`reports/phase4-3b/model-registry.json`、`model-compatibility-runs.json`。
- 大模型权重不入 Git：以 revision + SHA-256 + 许可证登记（`01-environment-audit.md`）。