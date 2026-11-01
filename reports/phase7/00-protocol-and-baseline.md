# P7-0 研究现状审计与研究协议预注册

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 审计起点 SHA：`fa14c4fb2e37fd12334b647e6d25441c5edc07fc`（origin/main，已 fetch 确认无更新）
- 协议版本：`phase7-eval-protocol-v1`
- 证据产物：
  - `configs/phase7-preregistered-protocol-v1.json` + `.sha256`
  - `reports/phase7/00-preregistration-lock.json`
  - `reports/phase7/sample-size-planning.{json,md}`
  - `reports/phase7/11-phase7-regression.{json,md}`

---

## 一、真实数据现状审计（三级时点并存，不改写历史）

任务书要求严格区分四个概念。本次实测结果：

| 层级 | 含义 | 实测值 | 判定 |
|---|---|---|---|
| `file_exists` | 磁盘存在简历文件 | **1** 个 `.txt`（`data/private/resumes/resumes/<uuid>/<shard>/<sha256>.txt`，780 字节） | 存在 |
| `consent_verified` | 有合法授权记录 | **0** 条（`data/private/consent/` 不存在，仓库内无任何 `consent_records.csv/jsonl`） | **不成立** |
| `intake_accepted` | 已导入 accepted 集 | **0**（`data/independent_eval/resume_pool/resumes.csv` 不存在；`pairs_v1.jsonl` 为空文件） | **不成立** |
| `eligible_for_gold` | 满足 Gold 准入 | **0** | **不成立** |

**结论：那 1 份简历只是业务系统上传存储中的一个文件，不构成「有效真实研究简历」。**
它是 `data/private/resumes/resumes/<租户>/<分片>/<内容哈希>.txt` 形态的应用上传存储，
含手机号/邮箱形态的个人信息（本次只统计了命中计数，未输出原文），且：
无授权记录、未走研究导入流程、未脱敏到研究口径、未进入 accepted 集。

### 三级统计时点并存（不修改旧报告）

| 时点 | real_resumes | real_pairs | 来源 |
|---|---:|---:|---|
| 旧冻结阻断快照 | 0 | 0 | `data/independent_eval/frozen/evalset_v2/freeze_blocked.json` |
| Phase6-R 本地审计 | 1 | 0 | `reports/phase6-r/04-gold-gate-readiness.md` |
| **Phase7 本次实测** | **1（file_exists）/ 0（eligible_for_gold）** | **0** | `reports/phase7/01-data-status.json` |

两个历史数字并不矛盾：它们统计的是不同口径（文件存在 vs 有效准入）。
本轮**不修改**任何历史报告，只在其上追加更细的四级口径。

### 其余门禁状态（实测）

| 项 | 状态 |
|---|---|
| 真实人岗配对 `pairs_real_v*.jsonl` | 0 组 |
| 双人标注文件 `data/private/annotations_raw/annotations_*.csv` | 0 份 |
| 独立标注员 | 0 人 |
| Gold 冻结 `freeze_written` / `freeze_verified` | false / false |
| H2 | **`blocked`** |
| 岗位池 `job_pool_v1.jsonl` | 150 条（可用于候选池，但有下述许可与泄漏限制） |

审计工具：`scripts/phase7/audit_real_data_status.py`（只读，输出无个人信息）。
状态推导与 `tests/phase6/test_gold_readiness.py::audit_gold_workspace_state` 一致：
`real_pairs == 0 → BLOCKED`。

---

## 二、研究协议预注册（在查看盲测结果之前锁定）

### 2.1 预注册为什么必须现在做

主评价指标、数据切分与通过条件一旦在看到 blind_test 结果后修改，任何"提升"都不可信。
本协议在**真实 Gold 尚不存在**时锁定，正是为了避免这种情况。

### 2.2 锁定内容摘要（完整见 `configs/phase7-preregistered-protocol-v1.json`）

| 项 | 锁定值 |
|---|---|
| 评价任务 | 中文简历-岗位相关性排序；评价单位 = (resume_id, job_id) pair；查询组 = `resume_id` |
| 标签体系 | `0 / 1 / 2 / unjudgeable`（`unjudgeable` 独立状态，不是 0） |
| 数据边界 | 组级 70/30：`dev_validation` / `blind_test`；split 种子 `20261215` |
| 训练边界 | E00–E06 不使用任何 Gold 标签训练；E07 需要**独立**合规训练标签，盲测 Gold 严禁入训 |
| **主指标** | **NDCG@10**（唯一，用于选型胜负） |
| 次指标 | NDCG@5、Recall@10、MRR、Precision@5（仅解释性，不决定胜负） |
| 运营指标 | 推理延迟 p50/p95、峰值内存、可解释性覆盖率 |
| Top-K | 5、10 |
| 统计方法 | 配对 Bootstrap，重采样单位 = 查询组，`n_boot=1000`，种子 `20261205`，95% CI |
| tie-breaking | 分数相同按原始行序稳定排序（无随机） |
| 稳定性规则 | 有效查询组 < 20 → `statistical_stability=unstable`，禁止声明显著提升 |
| 通过条件 | G1 数据 / G2 标注 / G3 冻结 / G4 统计（blind ≥20 组）/ G5 效果（ΔNDCG@10 95%CI 下界 > 0） |
| 选型规则 | 只用 `dev_validation`；主判据 NDCG@10；平手依次看 CI 下界 → NDCG@5 → Recall@10 → p95 延迟 → 复杂度更低 |
| 无法计算 | 一律 `not_computable` + `reason`；禁止填 0、禁止用合成/代理标签补足 |
| 修订策略 | blind_test 前可走 amendment（新版本号 + 独立理由）；blind_test 后只能出勘误 |

### 2.3 防篡改机制（已实现并有负向测试）

1. **哈希锁定**：`configs/phase7-preregistered-protocol-v1.sha256` 登记协议文件 SHA-256；
2. **测试钉死哈希**：`tests/phase7/test_preregistration.py::PINNED_SHA256` 常量钉死同一哈希，
   修改协议而不更新常量会使 CI 失败——事后改口径**必然留下可见 diff**；
3. **不变式校验**：`scripts/phase7/verify_preregistration.py` 校验主指标、切分、通过条件、
   选型规则、`not_computable` 口径等关键字段仍在位；
4. **盲测产物前置检查**：`find_premature_blind_outputs()` 扫描 `reports/phase7/04-real-model-evaluation.json`
   等盲测结果路径，一旦提前存在即 FAIL；
5. **负向测试**：`test_verify_script_detects_tampering` 把主指标偷偷改成 `Precision@5`，
   校验必须判 FAIL（实测通过）。

当前锁定哈希：`7112e151e2553f52bf16530ab717ad2bf4278b3660b97dfbfd252b2b95eb65f5`

---

## 三、基线与模型适用性（沿用 phase4-3a-protocol-v1 第八节，不新造）

| 编号 | 模型 | 无真实 Gold 时可否直接用于中文 JD 评估 | 说明 |
|---|---|---|---|
| E00 | 规则 Baseline（技能 Jaccard） | 是 | 当前线上规则口径 |
| E01 | TF-IDF + Cosine | 是 | 评估集内拟合 IDF |
| E02 | BM25 | 是 | 复用 `models/retrieval.py` 倒排索引实现 |
| E03 | BGE Embedding 余弦 | 是（需权重） | 缺权重显式 `MODEL_MISSING`，不回退随机分 |
| E04 | Embedding + 结构化特征融合 | 是 | 融合权重人工设定，非训练得到 |
| E05 | BM25/TF-IDF + Cross-Encoder | 是 | 合成代理标签上曾观察到负贡献，必须如实保留 |
| E06 | 完整融合推荐策略（`zh_research_*_v1` 四种） | 是 | 复用 `RESEARCH_STRATEGY_SPECS` |
| E07 | 有条件监督微调 | **否** | 需独立合规训练标签；当前 `BLOCKED` |

历史 Ridge / GBM / MLP / RankNet 的训练标签为**英文代理标签**、技能词表为英文，
按协议第八节只能作参考，**不得**作为中文真实适配结论。

---

## 四、样本规模规划（300–600 配对的查询组稳定性重算）

任务书指出的风险被实测计算证实。完整测算见 `reports/phase7/sample-size-planning.{json,md}`，
由 `scripts/phase7/sample_size_planning.py` 确定性生成（有 12 项单元测试锁定口径）。

| 方案 | 真实简历 | 每简历岗位 | 总配对 | dev 组 | blind 组 | blind MDE | blind 统计稳定 |
|---|---:|---:|---:|---:|---:|---:|---|
| **A 最低门禁** | 30 | 10 | 300 | 21 | **9** | 0.1868 | **否** |
| **B 合理查询组数** | 70 | 8 | 560 | 49 | **21** | 0.1223 | 是 |
| **C 扩展稳定性** | 120 | 10 | 1200 | 84 | **36** | 0.0934 | 是 |

**核心结论**：
- 300 配对只覆盖 30 个查询组，盲测组数 9 **远低于**协议要求的 20，无法支撑稳定统计结论；
- 要让盲测有效查询组 ≥ 20，需要至少 **67 个独立查询组**（`ceil(20/0.30)`），
  按每简历 8–12 岗位计约 **536–804 个配对**——已经超出原 300–600 上限；
- 若目标是 blind MDE ≤ 0.10（NDCG@10），需要约 **107 个独立查询组 / 1200 配对**（Scenario C）。

`unjudgeable` 敏感性（假设 5%/10%/20%/30%）、去重损失（假设 5%）、
标注工作量（含仲裁）等规划测算均已输出，全部标记 `ASSUMPTION`，
**不是已采集或已标注事实**，真实数据到位后必须用实测值回填复算。

> **协议修订要求**：若采纳 Scenario B/C，则须在标注与盲测**之前**提交版本化协议修订
> （`phase7-eval-protocol-v2`），说明修订理由与结果无关；不得事后为凑规模降低门禁。

---

## 五、本轮结论

| 项 | 结论 |
|---|---|
| 真实数据可用量 | 有效真实简历 **0**、真实配对 **0**、标注员 **0** |
| H2 | **`blocked`**（维持） |
| 协议预注册 | **完成并锁定**（含防篡改与负向测试） |
| 样本规划 | **完成**（Scenario A/B/C + 敏感性 + MDE） |
| P7-3 / P7-4 | **BLOCKED**（不具备合法真实数据） |

纪律遵守：本轮未伪造任何真实简历、授权记录或人工标注；未修改历史 checkpoint 与冻结结果；
未读取任何 blind_test 指标；未降低既有 H2 门禁。
