# Phase6 M0 — CI 故障修复与仓库审计报告

> 阶段：M0 ｜ 里程碑目标：远端 CI 修复（core-ci 由 FAIL 转 PASS）
> 生成时间：2026-10-31（UTC+8）

---

## 0. 运行身份（Run Identity）

| 项 | 值 |
|---|---|
| 运行者 | 首席算法架构师 Agent（Phase6 执行） |
| 工作分支 | `feat/phase6-model-integration` |
| 基准提交（`origin/main`） | `e54edc227cec1ac11bc76c15c285c4a54e5dc38c` |
| 执行时本地 HEAD | `21ae6e5d6762d4965648371fca96c0940d210049` |
| Python | 3.11.18（conda env `graduation-design`，与 CI 的 3.11 对齐） |
| 平台 | Windows-10-10.0.26200-SP0 |
| 依赖 | numpy 1.26.4 / pandas 2.2.3 / scikit-learn 1.5.2 / fastapi 0.115.6 / pydantic 2.10.4 / sqlalchemy 2.0.36 / httpx 0.28.1 / pymupdf 1.24.14 / python-docx 1.1.2 / argon2-cffi 23.1.0 |
| 数据版本 | `dv-fd3762f85658`（frozen/pool_v1） |

> 依赖安装口径：按 `.github/workflows/quality-gates.yml` 的 pinned 版本补齐到项目隔离环境，
> 未因本机环境不兼容而修改任何历史基线或测试断言。

---

## 1. 已确认的远端缺陷（复现）

来源：GitHub Actions Run `41183368356`，commit `e54edc227cec`。

| Job | 结果 |
|---|---|
| frontend-ci | PASS |
| browser-e2e | PASS |
| postgres-integration | PASS |
| **core-ci** | **FAIL** |

失败项：`tests/core_ci/test_c4_privacy_security.py::test_gitignore_covers_sensitive_paths`

```text
UnicodeDecodeError:
'utf-8' codec can't decode byte 0xd1 in position 2253
```

### 1.1 原始字节审计

对 `.gitignore` 做逐字节 hexdump，定位到第 2253 字节起的尾部注释行：

```text
2236: 65 61 2f 0a 0a 23 20 50 68 61 73 65 34 2d 33 42   ea/..# Phase4-3B
2252: 20 d1 d0 be bf ca b5 d1 e9 bc c7 c2 bc a3 a8 bd    ...............
2268: e1 b9 b9 bb af ca b5 d1 e9 bd e1 b9 fb a3 a9 b1   ................
2284: d8 d0 eb c8 eb bf e2 0a 21 72 65 70 6f 72 74 73   .........reports
```

该行字节按 **GBK** 解码得到 `研究实验记录（结构化实验结果）必须入库`，按 UTF-8 解码即抛
`invalid continuation byte`。文件其余 2310 字节均为合法 UTF-8。

### 1.2 全仓编码扫描

自研扫描器对 1315 个入库文件做**严格 UTF-8 解码**（不使用 `errors=`）：

```text
SCANNED: 1315
BAD UTF-8 COUNT: 1
  - .gitignore | 'utf-8' codec can't decode byte 0xd1 in position 2253: invalid continuation byte
```

结论：仓库内仅 `.gitignore` 一处编码缺陷，其余关键配置文件（`.gitattributes`、
`.env.example`、`alembic.ini`、`quality-gates.yml`）均为合法 UTF-8。

---

## 2. 根因

1. **编码根因**：`.gitignore` 尾部注释在某次 Windows 侧编辑中以 GBK 写入，
   未经过 UTF-8 校验就入库。
2. **发现滞后根因**：CI 侧此前没有"仓库文本必须严格 UTF-8"的回归门禁，
   只有 `read_text(encoding="utf-8")` 这类**消费侧**解码，因而缺陷表现为消费侧 ERROR
   而不是专门的编码门禁失败。

---

## 3. 修复内容

### 3.1 `.gitignore` 转 UTF-8（保留全部有效规则）

字节级替换 GBK 尾注释为等价 UTF-8，**未增删任何忽略规则**：

```text
bytes: 2323 -> 2342
old rules: 67  new rules: 67
identical rules: True
missing: []   added: []
```

转换后自检：`utf8 ok, CRLF: False`。`.gitignore` 中 `models/**`、`data/raw/`、
`data/private/`、`*.pem`、`*.key` 等敏感规则全部保留。

### 3.2 `.gitattributes` 显式钉死 LF（跨平台 checkout 字节一致）

原规则为 `* text=auto eol=lf`。实测发现：Windows + `core.autocrlf=true` 下
`.gitattributes` 自身会被 smudge 成 CRLF（`git ls-files --eol` 显示 `i/lf w/crlf`），
即 `text=auto` 在该场景下不足以保证工作区字节一致。

新增显式规则（`text` 而非 `auto`）：

```gitattributes
.gitignore     text eol=lf
.gitattributes text eol=lf
*.ini          text eol=lf
*.cfg          text eol=lf
*.toml         text eol=lf
```

验证：`git check-attr` 现返回 `text: set` + `eol: lf`；`git ls-files --eol`
返回 `i/lf w/lf`。`.gitattributes` 本身原有内容一字未改。

### 3.3 新增编码回归门禁 `C4EncodingIntegrity`

位置：`tests/core_ci/test_c4_privacy_security.py`，在 `tests/core_ci/run_all.py`
注册为 C4 组套件。共 5 项：

| 测试 | 断言 |
|---|---|
| `test_tracked_text_files_are_strict_utf8` | 所有入库文本严格 UTF-8 可解码，**不使用 `errors="ignore"/"replace"`** |
| `test_utf8_decode_errors_are_not_masked_in_gate` | 自检：门禁确实能捕获 GBK 字节，绕过方式可观测 |
| `test_root_config_files_are_utf8_and_lf` | 根配置文件 UTF-8 + 纯 LF + 无 NUL；同时校验 git blob 与工作区 |
| `test_root_config_files_declare_lf_attribute` | `.gitattributes` 必须显式 `text eol=lf`，并用 `git check-attr` 复核 |
| `test_gitignore_sensitive_rules_still_present` | 转码后敏感忽略规则不得丢失 |

可移植性：`test_root_config_files_declare_lf_attribute` 主判定走 `.gitattributes`
**文本内容**，`git check-attr` 仅在 git 工作区内复核；`git` 不可用时按
`filesystem_fallback` 显式登记来源退化，不把退化结果伪装成 git 结果。
（首轮在 `verify_fresh_checkout` 导出的无 git 临时目录中实测 FAIL，已按上述口径修正。）

### 3.4 第二处隐性 CI 缺陷（被前置失败掩盖）

`.gitignore` 修复后继续执行 core-ci 后续步骤时，暴露出**第二个**会失败的步骤：

```text
$ python scripts/phase5_1a/check_artifact_integrity.py \
      --root data/independent_eval --glob '**/manifest*.json' --require-manifest --quiet
artifact-integrity [FAIL] 0/1 OK | 1/1 份 manifest 存在完整性问题
  problems: ['文件缺失: data/independent_eval/pool/job_pool_v1.jsonl', ...]
```

根因：manifest 内登记的是**项目根相对路径**（`data/independent_eval/pool/...`），
而 `--root` 被指到 `data/independent_eval`，路径被解析成
`data/independent_eval/data/independent_eval/...`，必然判为「文件缺失」。
此前该步骤从未真正执行过——core-ci 前置步骤先失败，GitHub Actions 直接 skip 后续步骤。

修复：workflow 两处调用改为以项目根为扫描根，并显式 `--out`：

```yaml
python scripts/phase5_1a/check_artifact_integrity.py \
  --root . --glob 'data/independent_eval/**/manifest*.json' \
  --require-manifest --quiet \
  --out reports/phase5-1a/artifact-integrity.json
```

回归护栏（`tests/core_ci/test_c5_ci_contract.py`，3 项新增）：

| 测试 | 断言 |
|---|---|
| `test_artifact_integrity_invocation_requires_manifest` | 每次调用都必须 `--require-manifest` + `--out` |
| `test_artifact_integrity_root_is_project_root` | `--root` 不得指向 `data/independent_eval` |
| `test_integrity_checker_resolves_project_root_relative_paths` | 功能验证：`--root`=项目根 PASS、`--root`=子目录 FAIL（证明契约真的生效） |

**未采用任何降低断言、`errors="ignore"`、`|| true` 或"只检查报告存在"的绕过方式。**

---

## 4. 实测证据

### 4.1 Core CI 全量（含新增门禁）

```text
=== Core CI 门禁 247.23s | PASS=87 FAIL=0 SKIP=0 | ok=True ===
EXIT=0
```

历史口径对比：

| 时点 | Core CI 结果 |
|---|---|
| Run 41183368356（远端） | 78 PASS / 1 ERROR（`UnicodeDecodeError`） |
| 修复前本地复现 | 82 PASS / 1 FAIL（编码门禁已能捕获） |
| 修复后 | **87 PASS / 0 FAIL / 0 SKIP** |

### 4.2 core-ci job 全步骤（本地等价执行）

| 步骤 | 退出码 | 结果 |
|---|---:|---|
| `python -m compileall -q src scripts tests` | 0 | PASS |
| `tests/phase5_1r/run_all.py` | 0 | PASS=151 FAIL=0 SKIP=0 |
| `tests/phase5_1a/run_all.py` | 0 | PASS=29 FAIL=0 SKIP=0 |
| `tests/phase5_1/run_all.py` | 0 | PASS=92 FAIL=0 SKIP=0 |
| `tests/data_pipeline/test_g0_synth_data_quality.py` | 0 | PASS |
| `tests/core_ci/run_all.py` | 0 | PASS=87 FAIL=0 SKIP=0 |
| `check_artifact_integrity.py`（修复后调用） | 0 | PASS 1/1 OK |
| `scripts/phase5_1a/verify_fresh_checkout.py` | 0 | overall=PASS（export/syntax/phase5_1r/phase5_1a/phase5_1/core_ci 全 PASS） |

SKIP / BLOCKED / NOT_RUN 计数：**0**，本阶段无任何一项被记为 PASS 但未实跑。

---

## 5. 并发干扰登记（重要）

本轮执行过程中检测到**同一工作树 / 同一分支上存在并发提交活动**，与本 Agent 的
改动交错。已发生的事实：

| 提交 | 内容 | 归属 |
|---|---|---|
| `fd3faf8` / `97bafba` | 本 Agent 的 M0 编码门禁改动被一并提交 | 本 Agent 的工作 |
| `5c80803` | `.gitignore` 放开 `models/**` 白名单 + 弱化 C4 安全门禁 + 本 Agent 的 `.gitignore` UTF-8 修复 | **非本 Agent 决策** |
| `7cb7bf6` / `a7b2615` / `f1c0ade` / `21ae6e5` | 433 个训练产物（含 20.7MB / 19MB 词表权重）入库 | **非本 Agent 决策** |

### 5.1 未决决策（已按指示 defer，不擅自处理）

`5c80803` 将 C4 门禁的 `test_models_and_raw_data_untracked`（断言 `models/` 一律不入库）
改为 `test_raw_and_private_data_untracked_model_artifacts_whitelisted`
（允许 `.pt`/`.pth`/`.pkl`/`.npz`/`.npy` 等入库），并同步调整 C5 干净 checkout 口径。

**本 Agent 未采纳也未回滚该决策**，按用户指示 defer，登记为待决事项
（详见 `09-blockers-and-next-actions.md`）。需要指出的事实：

- 该改动与 Phase5-2 既有文档口径冲突（原文：`models/**` 被 .gitignore 忽略、
  Git 不跟踪，干净 checkout 中必然不存在）；
- 该改动属于对**已通过质量门禁的断言放宽**，与本轮「保留全部已通过的质量门禁」的约束存在张力；
- `data/raw/`、`data/private/`、`.env` 的禁令未被触碰。

### 5.2 隔离决策

用户选择「就在主工作树继续」，因此本 Agent 继续在
`D:\desktop\毕业设计` 的 `feat/phase6-model-integration` 上工作，
并在每个里程碑完成后立即提交，降低交错提交造成的丢失风险。

---

## 6. 结论

| 检查项 | 结论 |
|---|---|
| `.gitignore` 有效忽略规则完整保留 | PASS（67/67 规则一致） |
| 文件统一转为 UTF-8 | PASS（全仓 1315 文件严格 UTF-8） |
| 未用 `errors="ignore"` / 降低断言绕过 | PASS |
| Windows / Linux checkout 行为一致 | PASS（`.gitattributes` 显式 `text eol=lf`，blob 与工作区均 LF） |
| 其余关键配置文件编码体检 | PASS（仅 `.gitignore` 一处缺陷） |
| 编码回归门禁 | PASS（`C4EncodingIntegrity` 5 项） |
| `.gitattributes` LF 规范保持 | PASS（并显式化） |
| 修复后完整 Core CI | PASS（87/87） |
| 隐性第二缺陷（artifact-integrity 调用契约） | 已修复并加 3 项回归护栏 |

**M0 状态：PASS（工程口径）。** 远端 GitHub Actions 的真实绿灯验证需在分支推送后进行
（本地无推送权限时登记为 NOT_RUN，不计入 PASS）。
