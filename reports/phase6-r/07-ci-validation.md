# R6/R7：Phase6 自动化验收 CI 真实验证记录

- 生成时间：2026-10-31；仓库 `haohaizi233/job-matching-graduation-design`
- Workflow：`.github/workflows/quality-gates.yml`（新增独立 Job `phase6-gates`）
- 本记录只登记**远端真实运行结果**（GitHub Actions），本地结果不冒充远端 PASS。

## 1. 远端运行清单

| Run | 触发 commit | 结果 | URL |
|---|---|---|---|
| 41196478479 | `dfcb80e`（Phase6-R 合入 main） | **phase6-gates FAIL**（其余 Job 全绿） | https://github.com/haohaizi233/job-matching-graduation-design/actions/runs/41196478479 |
| 41197215528 | `4ff6872`（缺陷整改） | **全绿**（5 个必需 Job 全部 PASS） | https://github.com/haohaizi233/job-matching-graduation-design/actions/runs/41197215528 |

Run 41197215528 Job 明细：

| Job | 结果 | 说明 |
|---|---|---|
| core-ci (3.11) | ✓ 1m54s | Phase5-1R / 5-1A / 5-1 / G0 / Core CI 五套件 + 完整性自检 |
| phase6-gates | ✓ 43s | `python tests/phase6/run_all.py`：PASS=79 FAIL=0 ERROR=0 SKIP=2（8.786s） |
| frontend-ci | ✓ 24s | 类型检查 + 生产构建 |
| postgres-integration | ✓ 53s | PG 服务集成 |
| browser-e2e | ✓ 1m30s | 真实 Chromium 前后端 E2E |
| artifact-dependent-validation | -（不触发） | 仅 `workflow_dispatch` + 显式输入时运行 |
| model-artifact-compat-manual | -（不触发） | 仅手动触发（历史模型 Legacy 环境专项） |

## 2. 首次真实 CI 执行暴露的两处真实缺陷（已整改）

`phase6-gates` 在 Run 41196478479 首次真实执行即失败（FAIL=2），
失败证据已由 `if: always()` 上传为 `phase6-evidence` artifact。两处均为**真实缺陷**，
不是环境噪声：

### 缺陷 A：API 错误码契约断言错误（被本机 SKIP 长期掩盖）

- 失败用例：`test_model_integration.M1ModelIntegration.test_05_allow_fallback_false_refuses`
- 现象：`AssertionError: 400 != 503`
- 根因：用例断言 `assertEqual(400, r.status_code)`，但 `MODEL_MISSING` 在
  `src/job_matching/service/errors.py` 的 `ERROR_CODES` 登记为 **503**（模型能力缺失
  是服务侧问题，不是请求非法），API 层按登记值返回。断言写错成 400。
- 为什么长期没暴露：本机存在 BGE 权重时该用例走 `skipTest`（200 + 无降级记录），
  **真正执行只发生在权重/依赖缺失环境**（即干净 checkout 的 CI）。这正是
  「以 SKIP 冒充通过」的反面案例：SKIP 本身诚实，但断言从未被运行过。
- 整改：断言改为登记契约（HTTP 503 + `error.code == "MODEL_MISSING"` 显式错误码），
  并在本机用「模拟权重缺失」路径与 CI 双重验证通过（`4ff6872`）。

### 缺陷 B：jieba 分词口径缺失导致检索语义静默漂移

- 失败用例：`test_retrieval_equivalence.M2RetrievalEquivalence.test_empty_query_and_unknown_terms`
- 现象：`Lists differ: [[]] != [[(7, 2.645...), (2, 2.532...)]]`
- 根因：`models/retrieval.tokenize_zh` 统一口径为 jieba 分词（`environment.yml` 已声明
  `jieba==0.42.1`），jieba 缺失时**静默退化为字符切分**。CI 各 Job 的「服务/测试最小集」
  与 `environment-service.yml` 均漏装 jieba，于是干净 checkout 的检索语义与训练/本地
  口径不一致：字符级词元（`y`/`z` 等）命中合成语料，"未登录查询" 有了返回。
- 整改（两层）：
  1. **依赖对齐**：`environment-service.yml` 与 CI 全部后端 Job 补装 `jieba==0.42.1`，
     与训练环境分词口径一致；
  2. **契约测试环境无关**："未登录" 前提改为按**当前分词口径**显式构造查询并断言
     （词元集合与语料不相交），jieba 在/不在两种口径下都必须成立，不再硬编码查询串。

## 3. 本地 3.13 与 CI 3.11 的互补覆盖（不是重复跑）

| 覆盖半区 | 本地（py 3.13，BGE 权重齐备） | CI（py 3.11，干净 checkout 无 torch/transformers） |
|---|---|---|
| 真实 BGE 编码器/Reranker 业务级推理 | **真实执行并 PASS** | 显式 `NOT_RUN`（SKIP=2，注明缺少依赖，不冒充） |
| 权重缺失降级 / 拒绝契约（test_04 / test_05） | `skipTest`（权重在本机存在，失败路径不可触发） | **真实执行并 PASS** |
| 纯工具链/检索/缓存/持久化契约 | PASS | PASS |

两个环境的 SKIP 集合互斥且互补，任何一侧都未把未执行项计入 PASS。

## 4. 门禁承诺（quality-gates.yml `phase6-gates`）

- 干净 checkout 可运行：无本地开发数据库、无真实简历、无 BGE 权重要求；
- 合成夹具全部隔离临时目录，不进入 Gold；
- 每次真实执行并覆盖证据，不复用历史归档结果；
- 测试失败非零退出（真实标红），`if: always()` 上传逐项 JSON/Markdown 证据；
- 真实权重专项由 `model-artifact-compat-manual` 条件化独立 Job 承担（手动触发）。
