# Phase7-B / B1：Phase7 自动化测试纳入 GitHub Actions 验证报告

- 时间：2026-11-01（UTC+8）
- 工作分支：`feat/phase7b-graduation-delivery`
- 验证 commit：`b34158d`（ci(phase7-b): B1 新增 phase7-gates 门禁 + 运行器执行证据真实身份整改）

## 1. 整改内容

### 1.1 新增 `phase7-gates` Job（`.github/workflows/quality-gates.yml`）

干净 checkout 即可执行，覆盖：

| 验证项 | 落点 |
|---|---|
| 协议预注册与 SHA-256 锁定 | `tests/phase7/test_preregistration.py` |
| 数据规模规划确定性 | `tests/phase7/test_sample_size_planning.py` |
| 盲标注演练（合成夹具，不冒充真人） | `tests/phase7/test_annotation_drill.py` |
| 模型哈希防篡改（`MODEL_ARTIFACT_TAMPERED` 503 契约） | `tests/phase7/test_model_artifact_guard.py` |
| 未授权数据拒绝 / 禁止提前输出正式盲测结果 | `test_preregistration`（`find_premature_blind_outputs` 负向测试） |
| 盲测状态机（拒绝伪造/重复/跳步，合法仅一次） | `tests/phase7/test_blind_eval_state_machine.py`（B2） |
| 运行器身份与报告一致性 | `tests/phase7/test_run_identity.py` |

执行纪律（已写入 Job 步骤并机器校验）：

- 隐私边界检查：干净 checkout 若存在 `data/private/` 即失败；
- 不依赖真实简历 / GPU / BGE 权重 / 本地账号；
- `python tests/phase7/run_all.py` 失败或零测试发现均返回非零退出；
- 运行身份一致性校验：`actual_python_executable == sys.executable`、
  `python_version` 与真实解释器一致、`execution_command` 不含硬编码 `py -3.13`、
  `git_sha != UNKNOWN`、`tests_run > 0`、`exit_code == 0`；
- 报告上传为 Artifact `phase7-evidence`（`if: always()`，失败保留证据）。

### 1.2 执行证据不一致整改（`tests/phase7/run_all.py`）

问题：旧报告 `execution_command` 被硬编码为 `py -3.13 tests/phase7/run_all.py`，
与远端真实解释器（Python 3.11）不一致。

整改后字段一律取自真实进程：

| 字段 | 来源 |
|---|---|
| `python_version` / `python_full_version` / `python_implementation` | `platform` / `sys.version` |
| `actual_python_executable` | `sys.executable` |
| `sys_argv` | `sys.argv` |
| `working_directory` | `os.getcwd()` |
| `execution_command` | `shlex.join([sys.executable, *sys.argv])` |
| `git_sha` | 真实 `git rev-parse HEAD` |
| `started_at` / `finished_at` / `seconds` / `exit_code` | 真实运行时间与退出码 |

零测试发现（模块为空 / `testsRun == 0`）→ `not_ok_reasons` 含
`no_tests_discovered` / `no_modules_matched`，退出码 1。

### 1.3 新增运行器元测试（`tests/phase7/test_run_identity.py`，6 项）

`test_run_identity_actual_interpreter` / `test_run_identity_current_git_sha` /
`test_runner_import_failure_nonzero` / `test_runner_no_tests_discovered_nonzero` /
`test_runner_report_freshness` / `test_report_status_count_consistency`。

## 2. 本地验证（真实执行）

```text
命令：py -3.13 tests/phase7/run_all.py
实际解释器：D:\APP\python 3.13.2\python.exe（Python 3.13.2）
git_sha：1b60d2b42388…（整改后为 b34158d 对应树）
结果：PASS=52 FAIL=0 ERROR=0 SKIP=0 NOT_RUN=0 BLOCKED=0，exit_code=0
（含 B2 状态机测试后为 PASS=64，见 02 报告）
```

报告 `reports/phase7/11-phase7-regression.json` 中
`execution_command = 'D:\APP\python 3.13.2\python.exe' tests/phase7/run_all.py`
（真实进程身份，已核对）。

## 3. 远端验证（真实执行，GitHub Actions）

```text
触发方式：pull_request（PR #1 → main）
Run：41260054652（commit b34158d）
```

| Job | 结果 | 用时 | 证据 |
|---|---|---|---|
| core-ci (3.11) | **pass** | 2m20s | job 124711277231 |
| frontend-ci | **pass** | 18s | job 124711277222 |
| postgres-integration | **pass** | 1m6s | job 124711277148 |
| browser-e2e | **pass** | 1m22s | job 124711277196 |
| phase6-gates | **pass** | 45s | job 124711277168 |
| **phase7-gates** | **pass** | 38s | job 124711277019 |
| artifact-dependent-validation | skipping（workflow_dispatch 限定） | — | **NOT_RUN**（不计 PASS） |
| model-artifact-compat-manual | skipping（workflow_dispatch 限定） | — | **NOT_RUN**（不计 PASS） |

**结论：`phase7-gates` 已在远端 Python 3.11 干净 checkout 真实执行并 SUCCESS**；
两处 manual/dispatch Job 未执行，按纪律登记 NOT_RUN。

## 4. 报告可信性

- 远端 `phase7-evidence` Artifact 登记 CI 环境（Python 3.11）真实执行身份，
  本地报告登记开发环境（Python 3.13）真实执行身份，二者分别登记、不混用；
- JSON / Markdown / Actions 统计一致（`test_report_status_count_consistency` 强制）；
- 历史归档报告一律不采信：`verify_run_freshness` 口径 + 报告每次真实执行覆盖。

## 5. 遗留

- `artifact-dependent-validation` 依赖真实产物，本轮未通过 workflow_dispatch 触发，
  维持 NOT_RUN；B7 收口时按需手动触发登记。
