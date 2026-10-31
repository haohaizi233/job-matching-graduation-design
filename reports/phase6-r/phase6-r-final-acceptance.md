# Phase6-R 研究推荐引擎质量整改与最终验收报告

- 项目：大学生就业岗位画像与简历智能匹配系统的设计与实现
- 仓库：https://github.com/haohaizi233/job-matching-graduation-design
- 验收基准 commit：`4ff6872`（整改完成点，CI 全绿）；合入 main 合并节点 `dfcb80e`
- 工作分支 `fix/phase6-research-integration-hardening` 已按要求合并进 main 并删除（本地 + 远端），
  远端现存分支仅 `main`（`4ff6872`）
- 报告生成：2026-10-31；本地 Python 3.13.2，CI Python 3.11（Core CI 固定）

## 1. 完成内容（R0–R7）

| 里程碑 | 内容 | 提交 |
|---|---|---|
| R0 | 基线审计（Git SHA / 环境 / 四策略 / 接口 / 覆盖 / 缺陷复现） | `4bce9b7`（00-baseline-audit.md） |
| R1 | Cross-Encoder 实际推理缺陷修复：RerankResult 契约、NumPy `or []` 歧义、长度/NaN 校验、Logits 归一化口径升级（scoring_config_version 升级并保留历史口径解释） | `c8d642a` |
| R2 | 索引缓存键扩展（策略/配置哈希/schema 版本/岗位内容哈希）+ 并发 check-then-act 加锁 + LRU；硬约束过滤项与 Top-K 边界整改（filtered_out 单独登记、top_k_shortfall 告警） | `1a2de43` |
| R3 | BM25 新旧实现真实基准（150/500/1000/5000/10000 语料，独立口径） | `5353b35` |
| R4 | Gold 门禁改为状态驱动：工具链单元测试与真实工作区只读审计解耦，不再硬编码「真实配对必须为 0」 | `3e096c5` |
| R5 | 模型产物来源/许可/泄露/哈希/体积/加载边界审计 + README 与总览分发口径统一 | `ba816e8` |
| R6 | `tests/phase6/run_all.py` 统一运行器（确定性顺序、JSON/Markdown 证据、失败非零退出）+ CI 独立 `phase6-gates` Job | `3005588` |
| R7 | 证据矩阵 + 本验收报告 + CI 验证记录 | `4bce9b7` / `07-ci-validation.md` / 本文件 |
| CI 整改 | 首次真实 CI 执行暴露 2 处真实缺陷并整改（详见 07） | `4ff6872` |

## 2. 修改文件（合并入 main 的 8 + 1 个提交）

- 代码：`src/job_matching/service/research_strategy.py`、`src/job_matching/service/matching.py`
- 测试：`tests/phase6/`（新增 `test_reranker_contract.py`、`test_ranking_and_cache_contracts.py`、`run_all.py`；
  改造 `test_gold_readiness.py`、`test_model_fallback.py`、`test_model_integration.py`、`test_retrieval_equivalence.py`）
- 基准脚本：`scripts/phase6_r/bm25_benchmark.py`
- CI/环境：`.github/workflows/quality-gates.yml`（`phase6-gates` Job + 各后端 Job 补 jieba）、`environment-service.yml`
- 文档：`README.md`（模型分发口径）、`reports/phase6-r/`（00–08 + 本报告）

## 3. 测试数量与结果

| 套件 | 数量 | 本地（3.13，权重齐备） | CI 干净 checkout（3.11） |
|---|---|---|---|
| `tests/phase6/run_all.py` | 81 | PASS=79 FAIL=0 ERROR=0 SKIP=2（SKIP=test_04/05 权重缺失路径本机不可触发） | PASS=79 FAIL=0 ERROR=0 SKIP=2（SKIP=真实 BGE/Reranker 推理显式 NOT_RUN） |
| `tests/core_ci/run_all.py` | 87 | PASS=87 FAIL=0 SKIP=0（226.9s） | core-ci Job ✓（含 Phase5-1R/5-1A/5-1/G0/Core CI） |
| frontend / PG / E2E | — | 本轮合并前由历史报告刷新（`c2c1a8d`） | frontend-ci ✓ / postgres-integration ✓ / browser-e2e ✓ |

- 真实模型业务级推理（BGE 编码器 + BGE-Reranker）在本机**真实执行通过**；
  CI 无 torch/transformers 时显式 `NOT_RUN`，两环境 SKIP 集合互斥互补，未把未执行项计为 PASS。
- 全部逐项证据：`reports/phase6-r/06-phase6-regression.json` / `.md`（每次真实执行覆盖，不复用归档）。

## 4. 真实性能数据（R3，非估算）

本机实测（Python 3.13.2 / numpy 2.2.6；预热 3 次不计入；建索引与热查询分列口径）：

| 语料规模 | 朴素 Warm P50 | 倒排 Warm P50 | 加速比 | 等价性 |
|---|---|---|---|---|
| 150 | 0.434 ms | 0.227 ms | 1.9× | 逐位一致 |
| 1 000 | 1.258 ms | 0.082 ms | 15.3× | 逐位一致 |
| 5 000 | 7.750 ms | 0.168 ms | 46.1× | 逐位一致 |
| 10 000 | 12.082 ms | 0.144 ms | **83.9×** | 逐位一致 |

- 10000 语料 QPS：67 → 6417；建索引侧两者同量级（10000：2066 ms vs 1879 ms），不与查询口径混用。
- 完整表（Build/Cold/Warm P50/P95/QPS/RSS）：`reports/phase6-r/03-bm25-benchmark.json` / `.md`。
- 业务层默认岗位上限 200，1000–10000 在线规模属算法侧基准，不冒充业务 API 吞吐（口径见 03 报告）。

## 5. CI Run URL

- 合入 main 首跑（暴露 2 缺陷）：https://github.com/haohaizi233/job-matching-graduation-design/actions/runs/41196478479
- 整改后全绿（验收依据）：https://github.com/haohaizi233/job-matching-graduation-design/actions/runs/41197215528

## 6. H2 状态

**BLOCKED**（真实人工 Gold 未完成）：

- 真实简历/岗位人工双标注配对 = 0，标注包未导出，冻结/仲裁未启动；
- 工具链（盲标注包导出、双标注员独立性、仲裁、PII、泄漏、冻结、哈希校验）全部测试通过，
  且已与真实状态审计解耦（R4）：真实数据增长不会打红工具链测试；
- 真实工作区审计只读输出状态（BLOCKED / READY_FOR_ANNOTATION / READY_FOR_FREEZE /
  FROZEN_AND_VERIFIED / INVALID），不写回、不覆盖；
- 纪律保持：不以合成简历/用户反馈/模型预测冒充人工 Gold，不因配对数达标自动冻结。

## 7. 遗留问题

1. **H2 真实人工 Gold 未启动**——真实就业匹配有效性无证据，整体不得表述为"已验证匹配效果"。
2. **模型产物许可未登记**：训练数据与模型分发许可需补齐后才可公开再分发（`05-model-artifact-audit.md`）。
3. **体积策略未执行**：smoke/ablation 变体与大词表迁 Git LFS / Release 的方案已列出，
   涉及历史变更，须批准后执行（本轮未动 Git 历史、未 force-push）。
4. **真实权重专项 CI 为 NOT_RUN**：CI 无 torch/transformers；真实推理目前由本机执行 +
   `model-artifact-compat-manual` 手动 Job 覆盖。
5. **软超时为协作式 deadline**：无法强制中断底层 PyTorch 推理，已在 `02-retrieval-and-cache-correctness.md`
   登记为已知边界。
6. **双 Python 口径长期存在**：本地 3.13 / CI 3.11 / 历史模型 Legacy 环境，未擅自统一历史依赖锁定。

## 8. 最终评级

| 维度 | 结论 | 依据 |
|---|---|---|
| **工程通过** | ✅ 通过 | 代码/接口/测试/CI 全绿（Run 41197215528）；Phase6 81 + Core CI 87 用例真实执行 |
| **研究复现通过** | ✅ 通过（有边界） | BM25 新旧等价性逐位一致 + 真实基准可复现（脚本入库）；R1 精排契约修复有回归；历史 checkpoint 未改写，Legacy 环境独立 |
| **真实就业匹配有效性** | ❌ 未通过 | H2 BLOCKED：无人工 Gold，禁止任何"真实有效性"结论 |

**整体评级：B（有条件通过）** —— 依据验收标准第 10 节：H2 仍 BLOCKED，评级上限为 B。
升 A 的唯一路径是完成独立双人标注 + 仲裁的真实人工 Gold 评价并冻结核验。
