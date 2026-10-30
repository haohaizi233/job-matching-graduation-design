# Phase5-3 M1 — GitHub Actions CI 修复报告

> 本次修复的全部结论均来自 2026-10-31 实际执行，命令、退出码与耗时可核对。
> 未删除测试、未降低断言标准、未创建任何伪造 checkpoint。

## 1. 缺陷复现（Inspect → Reproduce）

### 1.1 已知失败

| 项 | 值 |
|---|---|
| 工作流 | `.github/workflows/quality-gates.yml` |
| Run ID | `41108847531` |
| Commit | `cb1f4819` |
| Phase5-1R | 151/151 PASS |
| Phase5-1A | 25 PASS / **1 FAIL** |
| 失败测试 | `tests/phase5_1a/test_a1_a7_gates.py::A4ModelErrorTaxonomy::test_history_checkpoints_untouched` |

### 1.2 本地真实复现

方法：用 `scripts/phase5_1a/verify_fresh_checkout.py` 的 `export_clean_checkout()`
导出「全新 checkout 会拿到的文件」到临时目录（不含 `.git`、不含被 `.gitignore` 忽略的产物），
再在其中执行失败测试。

```
TMP= C:\WINDOWS\TEMP\jm_repro_e0fuu644
COPIED= 1140
FORBIDDEN= []
models exists in clean checkout: False
RETURNCODE= 1
>> test_history_checkpoints_untouched ... FAIL
>> Ran 26 tests in 23.774s
>> FAILED (failures=1)
!! AssertionError: False is not true
```

**与 CI 第 54 次运行完全一致（25 PASS / 1 FAIL）。**

## 2. 根因（Diagnose）

### 缺陷 A（P0-1）：Core CI 依赖 Git 未跟踪的私有目录

```python
# tests/phase5_1a/test_a1_a7_gates.py（修复前）
def test_history_checkpoints_untouched(self):
    # A4 硬约束：本轮不得改动历史权重（models/ 必须保持只读）
    probe = ROOT / "models"
    self.assertTrue(probe.exists())
```

- `.gitignore` 有 `models/**`（仅放行 `models/README.md`），`git ls-files models` 为空；
- 干净 checkout 中 `models/` **必然不存在** → 断言**必然失败**；
- 该项属 **Artifact-dependent（依赖真实产物）**，却被放进要求「全新 checkout 可通过」的 **Core CI**。

### 缺陷 B（P0-2）：断言语义错误

`assertTrue(probe.exists())` 只能证明「目录存在」，**推不出「权重未被修改」**，
即使目录在，也发现不了权重被改动。作为 A4「历史权重不变性」的证据是无效的。

### 缺陷 C（P0-3）：修复 A 后暴露的第二个失败（被 A 掩盖）

按任务书要求「修复后必须继续排查后续步骤」，修复 A 后复跑 `verify_fresh_checkout.py`，
发现 **`core_ci` 套件在干净 checkout 内仍失败**（Run 54 因先失败于 phase5_1a 而未暴露）：

```
=== core_ci status=FAIL rc=1
ERROR: test_clean_export_has_no_forbidden_artifacts
RuntimeError: git ls-files 失败: fatal: not a git repository (or any of the parent directories): .git
ERROR: test_clean_export_contains_portable_suite_sources
RuntimeError: git ls-files 失败: fatal: not a git repository ...
Ran 78 tests in 207.476s
FAILED (errors=2)
```

根因：`tests/core_ci/test_c5_ci_contract.py` 直接调用 `verify_fresh_checkout.tracked_file_list()`，
后者**无条件执行 `git ls-files`**。而「干净 checkout 模拟」的临时目录天然没有 `.git`，
于是契约测试在**恰好需要它的那个环境里**崩溃。

该缺陷在 GitHub runner 上同样会触发：`verify_fresh_checkout.py` 是 Core CI 的一步，
它在临时目录内跑 `core_ci`，临时目录无 `.git` → 该步骤必然 FAIL。

## 3. 修复（Implement）

### 3.1 缺陷 A + B：Core CI 改为「合成夹具自检」，真实权重检查归位 Artifact-dependent

**Core CI（不依赖任何真实产物）**——`tests/phase5_1a/test_a1_a7_gates.py` 新增 4 项
合成自检，替换掉原 `test_history_checkpoints_untouched`：

| 新测试 | 证明的事 |
|---|---|
| `test_history_weights_check_is_artifact_dependent` | 无 `models/` 时检查器返回 `NOT_RUN`（退出码 0），且**绝不判定 PASS**，并留下可核对报告 |
| `test_history_weights_check_never_passes_without_frozen_baseline` | 有 `models/` 但无冻结基线 → `NOT_RUN`（「未与基线比对」≠「未被修改」） |
| `test_history_weights_check_detects_modified_weights` | 建立基线 → 篡改权重 → 必须 `FAIL`；删除基线内文件 → 必须 `FAIL` |
| `test_integrity_checker_is_readonly_on_inputs` | 完整性检查过程**不修改输入文件**（SHA-256 前后一致） |

**Artifact-dependent（依赖真实产物）**——新增
`scripts/phase5_1a/check_history_weights_integrity.py`：

| 状态 | 触发条件 | 退出码 |
|---|---|---|
| `PASS` | 存在 `models/` 与冻结基线，且全部权重哈希一致 | 0 |
| `FAIL` | 存在基线但哈希不一致 / 基线内文件缺失 | 1 |
| `NOT_RUN` | `models/` 缺失，或尚未建立冻结基线 | 0 |
| `ENV_INCOMPATIBLE` | `JM_RUN_ID` 缺失等环境问题 | 2 |

约束：**没有基线就不可能 PASS**（`decide_status()` 强制）；`models/` 全程只读；
不创建伪造 checkpoint、不重训权重、不改写历史产物。

**基线建立**（M1 时点，只读清单，非评估协议）：

```
$ py -3.13 scripts/phase5_1a/check_history_weights_integrity.py --write-baseline
已建立权重完整性基线：configs/history-weights-baseline.json（79 个权重文件）
history-weights-integrity [PASS] scanned=79 baseline=yes changed=0 missing=0 extra=0
  reason: 基线已建立（79 个权重文件）

$ py -3.13 scripts/phase5_1a/check_history_weights_integrity.py
history-weights-integrity [PASS] scanned=79 baseline=yes changed=0 missing=0 extra=0
  reason: 全部权重文件与冻结基线一致
```

基线只登记文件路径 / 大小 / SHA-256，**不含权重内容**，`.gitignore` 的 `models/**` 不影响它。

### 3.2 缺陷 C：文件清单来源显式登记 + 无 git 时受控退化

`scripts/phase5_1a/verify_fresh_checkout.py`：

- 新增 `file_list_source()`，返回 `git` / `filesystem_fallback` / `UNKNOWN`；
- `_git_available()` 探测 git；可用时仍走 `git ls-files -c -o --exclude-standard`（权威口径不变）；
- 无 git 时退化为文件系统枚举，只跳过**非仓库内容**目录
  （`.git`、`chinese-skillspan-benchmark` 独立子仓、`node_modules`、`__pycache__`、
  构建产物、虚拟环境、工具缓存），**不实现 `.gitignore` 语义、不替调用方隐藏任何业务/产物路径**；
- 退化结果**显式登记来源**，绝不伪装成 git 结果。

`tests/core_ci/test_c5_ci_contract.py` 新增
`test_file_list_source_is_explicitly_registered`：来源必须是合法枚举值；
且当来源为 `filesystem_fallback` 时必须确实 `git` 不可用（防止静默降级）。
原 `test_clean_export_has_no_forbidden_artifacts` 断言保持严格（不降低标准），
仅补充了「不在 git 仓库内则无法证明 checkout 洁净」的失败提示。

### 3.3 工作流登记

`.github/workflows/quality-gates.yml`：

- 头部补充 Phase5-3 / M1 修复说明；
- `artifact-dependent-validation` 新增步骤
  `历史权重完整性（Artifact-dependent，缺失即 NOT_RUN）`；
- 证据上传路径补入 `reports/phase5-3/`。

## 4. 验证（Test）

### 4.1 Phase5-1A 门禁自检

```
$ py -3.13 tests/phase5_1a/run_all.py
=== Phase5-1A 门禁自检 25.08s | PASS=29 FAIL=0 SKIP=0 | ok=True ===
```

- 修复前 26 项 → 修复后 **29 项**（删除 1 个无效断言，新增 4 个合成自检）；
- 未删除任何其他测试。

### 4.2 Core CI 契约测试

```
$ py -3.13 tests/core_ci/test_c5_ci_contract.py
Ran 16 tests in 1.960s
OK
```

（修复前 15 项 → 新增 `test_file_list_source_is_explicitly_registered` = 16 项）

### 4.3 干净 checkout 可移植性验证（关键验收）

**修复前**：

```
全新 checkout Core CI 验证 | overall=FAIL | 356.03s
[   PASS] export
[   PASS] syntax     [PASS] phase5_1r   [PASS] phase5_1a   [PASS] phase5_1
[   FAIL] core_ci    1
exit_code: 1
```

**修复后**：

```
$ py -3.13 scripts/phase5_1a/verify_fresh_checkout.py
==============================================================================
全新 checkout Core CI 验证 | overall=PASS | 319.98s
==============================================================================
[   PASS] export       干净 checkout 内不含真实数据/权重
[   PASS] syntax       0
[   PASS] phase5_1r    0
[   PASS] phase5_1a    0
[   PASS] phase5_1     0
[   PASS] core_ci      0
-> D:\desktop\毕业设计\reports\phase5-2\ci\fresh-checkout.json
exit_code: 0
```

### 4.4 合成夹具负向验证（证明检查程序真能发现问题）

```
history-weights-integrity [PASS]    scanned=2 baseline=yes   reason: 基线已建立
history-weights-integrity [PASS]    scanned=2 baseline=yes   reason: 全部权重文件与冻结基线一致
history-weights-integrity [FAIL]    scanned=2 changed=1      ! 哈希变化: m1/model.pkl
history-weights-integrity [FAIL]    scanned=1 missing=1      ! 基线内缺失: m1/model.pt
history-weights-integrity [NOT_RUN] scanned=0 baseline=no    reason: models/ 不存在；不计入 PASS
```

**篡改、删除都会被发现；无产物不会被算作通过。**

## 5. 验收条件核对

| 验收条件 | 结果 | 证据 |
|---|---|---|
| 干净 checkout 可以完成 Core CI | ✅ | §4.3 `overall=PASS`，6/6 步骤 PASS，exit 0 |
| 测试失败不能被静默吞掉 | ✅ | `verify_fresh_checkout` 逐步记录 returncode；工作流无 `\|\| true`（C5 断言覆盖） |
| 不依赖 Git 未跟踪的私有目录 | ✅ | Core CI 4 项自检全部使用临时合成夹具；`models/` 只在 Artifact-dependent 出现 |
| 不创建伪造 checkpoint | ✅ | 合成夹具写入 `tempfile.TemporaryDirectory`，内容显式标记 `SYNTHETIC-*`，用后即删 |
| 原有 151 项 Phase5-1R 不回退 | ✅ | 干净 checkout 内 `Ran 151 tests ... OK`；本地亦 151/151 PASS |
| 修复后继续排查后续步骤 | ✅ | 发现并修复缺陷 C（`core_ci` 在无 git 环境崩溃），非只修第一处失败 |

## 6. 未决 / 后续

| 项 | 状态 | 说明 |
|---|---|---|
| GitHub Actions 真实运行 | **NOT_RUN** | 本地无推送权限确认；修复需推送后由 runner 实证，本地以 `verify_fresh_checkout` 等价复现 |
| 真实权重端到端比对 | **NOT_RUN** | 本机有 79 个权重文件且与 M1 基线一致；GitHub runner 无 `models/`，该步骤记 `NOT_RUN`（不计 PASS） |
| Frontend CI / PG Job / E2E Job | **NOT_RUN** | 属 M2/M3/M4，随对应里程碑接入工作流 |

## 7. M1 结论

**M1 状态：PASS**（本地真实证据）

- P0-1 / P0-2 / P0-3 三项缺陷全部修复并有可核对证据；
- Core CI 在干净 checkout 上 6/6 步骤通过；
- 151 项 Phase5-1R、92 项 Phase5-1 无回退；
- 未伪造任何测试结果，未改动历史权重（`configs/history-weights-baseline.json` 只读登记，79 个权重文件哈希一致）。

下一步 → M2（前端真实业务联调）。
