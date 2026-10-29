# Phase4-3A-2 验收报告（H1 / H2）

> 生成时间：2026-10-29 ｜ 项目：`haohaizi233/job-matching-graduation-design`
> 阶段目标：补齐真实中文简历数据、建立人工双盲标注工作流、准备独立可信可复现的中文人岗匹配 Gold 评估集。
> 纪律声明：本轮**未**生成任何虚假简历 / 人工标签 / 仲裁记录；**未**重新训练模型；**未**进入 Phase4-3B 模型选型。

## 一、结论速览

| 门禁 | 结论 | 核心依据 |
|---|---|---|
| **H1 真实数据接入与标注流程就绪** | **通过（PASS，附声明）** | 收集/授权模板可用；导入+脱敏、岗位审计、配对生成、双盲标注与仲裁、冻结门禁全部可运行；237 项自动化测试全通过；无真实简历/敏感字段泄漏 |
| **H2 真实 Gold 评估集正式冻结** | **BLOCKED（阻断）** | 真实中文简历 0 份、真实配对 0 组、双人人工标注未开始、授权记录未收集、评估集未冻结（`freeze-verification.json` = blocked） |

**H1 附加声明（任务书要求）**：真实数据收集尚未完成——本机没有获得任何真实大学生简历、
授权记录或人工标注。H1 通过的是「流程与工具就绪」，不是「数据就绪」。
H2 在真实人员提供简历、授权与人工标注之前必须保持 BLOCKED。

## 二、真实数据现状（如实统计，合成数据不冒充）

| 指标 | 数量 | 说明 |
|---|---|---|
| 真实中文简历 | **0** 份 | A 类（本人同意）/ B 类（许可公开）均未获得 |
| 英文简历 | 9,544 份 | `data/raw/job-resume-matching/cv.csv`，已隔离，禁止充当中文简历 |
| 合成简历夹具 | 4 份（txt/csv/jsonl/docx 各 1） | 仅验证工具链，`is_synthetic=true`，永不进 Gold |
| 合规中文岗位 JD（准入池 v2） | **150** 条 | job-education（apache-2.0）；`all_df` 已隔离 |
| 真实有效配对 | **0** 组 | 无真实简历则不生成（`real-pair-manifest.json` = blocked_no_real_resumes） |
| 合成测试配对 | 75 组 | `pairs_synthetic_v1.jsonl`，均 `is_synthetic=true` |
| 双人标注完成 | 0 组 | 等待真实配对与标注员 |
| 一致性（Kappa / Weighted Kappa） | not_computable | 无真实双标注样本，如实登记 |

## 三、已处理的重复、污染与授权风险

1. **近似重复（10 处）**：9 处配对级近似重复（0.91–0.97，均在合成配对内）→ 全部隔离不进 Gold；
   1 处岗位级近似重复（`7887069`/`7887495`，Jaccard=0.94）→ 保留 `7887069`、隔离 `7887495`，
   避免同 JD 不同 ID 造成配对重复与指标虚高（`job-candidate-audit.json -> near_duplicate_analysis`）。
2. **历史 Gold 交叉（5 个 job_id：7881740/7891020/7891194/7911845/7926209）**：
   逐条裁决 = `quarantine_from_blind`（保留用于 dev_validation，剔除出最终盲测集）；
   不得作为全新独立盲测样本。
3. **学历训练语料重合（哈希 250 行、近似 255 处，涉及全部 150 条候选 JD）**：
   分任务说明影响，不一概当泄漏——
   - 学历抽取组件：重合岗位非零样本，涉及学历字段输出的评估必须剔除；
   - 人岗匹配排序模型（英文 matches 语料训练）：与中文 JD 无文本重合，无直接文本泄漏
     （英文代理标签是口径限制而非泄漏）；
   - strict-unseen-JD 任务（要求模型完全没见过岗位文本）：当前 strict 可用岗位 = **0**，
     该类任务**不能**使用本岗位池，需另行采集岗位（外部依赖）；
   - 预训练污染：只能声明「未发现已知泄漏」，不声称绝对无泄漏。
4. **`all_df`（251,381 行）**：来源与许可 UNKNOWN → 全量隔离（`quarantine_list`），
   补齐 license + license_evidence 并经准入检查前禁止进入 Gold。
5. **PII**：导入即脱敏掩码（只登记命中类型与数量）；导出走字段白名单 + PII 字段名拦截 +
   文本残留检测三重门禁；真实原文与授权记录只存 `data/private/`（.gitignore 已忽略）。
6. **数据保护**：`.gitignore` 覆盖 `data/private/`、`pairs_real_*.jsonl`、
   `annotation/imports|packets|final_labels.csv|arbitration_filled*.csv`；
   Git 仓库只含 Schema、采集/导入代码、非敏感统计、使用说明、合成夹具、哈希与版本记录。
   本轮未执行任何 push。

## 四、自动化测试真实结果

`python tests/phase4_3a/run_all.py` → **237 项全部通过（PASS=237 FAIL=0 SKIP=0）**：

- P1–P10 = Phase4-3A 既有 **157** 项（只扩展不重写，全部仍通过，旧门禁未降低）；
- P11–P18 = 本轮新增 **80** 项，覆盖任务书 18 项门禁场景：
  未授权数据拒入 Gold、英文简历不得充中文、合成不得冒充真实、重复 pair_id 拒绝、
  resume_id 跨 dev/blind 拒绝、训练交叉检查、近似重复检查、模型预测不泄给标注员、
  标注员独立性、非法标签与协议混用拒绝、unjudgeable 不强转、仲裁不可静默覆盖、
  PII 不入公开导出、盲测冻结前不得标记通过、冻结后哈希校验、无真实数据 G2=BLOCKED、
  合成不计入真实 Gold、固定种子可复现。

报告：`reports/phase4-3a-2/test-results.json` + `test-results.md`。
期间修正 1 处测试断言口径（互斥检查键名以实现为准），无一跳过、无一降低标准。

## 五、H1 验收明细（PASS）

| 要求 | 状态 | 证据 |
|---|---|---|
| 数据收集和授权流程模板可用 | ✅ | `docs/evaluation/consent-template.md`（`phase4-3a-2-consent-v1`，含撤回/删除流程）、`phase4-3a-2-data-collection.md` |
| 真实简历导入及脱敏工具可运行 | ✅ | `scripts/phase4_3a_2/intake_resumes.py`（PDF/DOCX/TXT/CSV/JSONL；4 种格式实测导入 5 条合成记录，全部正确隔离为 synthetic_not_gold） |
| 岗位筛选及来源审计可运行 | ✅ | `build_job_candidates.py` → `source-audit.json`、`job-candidate-audit.json`、`job_pool_v2.jsonl`（150 条准入） |
| 配对生成流程可运行 | ✅ | `build_real_pairs.py`（固定种子、分层、稳定 pair_id、训练交叉标记、可复现校验；无真实简历时显式 blocked） |
| 双人标注与仲裁流程已集成 | ✅ | `export_annotation_packets.py`、`annotation_qa.py`、`arbitration.py`（unjudgeable_forced 防护保留） |
| 新增自动化测试全部通过 | ✅ | 237/237 |
| 未泄漏真实简历及敏感字段 | ✅ | PII 扫描 0 字段残留；真实数据未入库（`data/private/` 不入库） |

## 六、H2 验收明细（BLOCKED）

| 要求 | 状态 | 阻断原因 |
|---|---|---|
| 数据来源及授权符合准入 | ❌ | 无任何真实简历授权记录 |
| 真实中文简历与 JD 有可评估规模 | ❌ | 简历 0 份（JD 侧 150 条达标） |
| 完成双人独立标注及仲裁 | ❌ | 0 组标注 |
| 分组隔离正确 | ⏸ | 切分逻辑与测试就绪（`gold_gate.check_split_isolation`），无数据可切分 |
| 重复与泄漏风险处理 | ✅ | 已处理（见第三节） |
| 评估集冻结且哈希复验 | ❌ | `freeze_gold.py` 输出 blocked（6 条 reasons） |
| 标注一致性及有效查询组数 | ❌ | not_computable（无真实双标注） |
| dev/blind 使用条件 | ❌ | 依赖以上各项 |

## 七、可执行命令（实际可用）

```bash
# 0. 合成夹具（工具验证用，永不进 Gold）
python scripts/phase4_3a_2/make_synthetic_fixtures.py

# 1. 真实简历导入（A 类：本人同意；授权记录 CSV/JSONL 逐条可核）
python scripts/phase4_3a_2/intake_resumes.py --source-class A_consented_individual \
    --source-name consented-2026q4 --resumes data/private/resumes \
    --consent data/private/consent/consent_records.csv

# 2. 岗位准入与来源审计（all_df 未解隔离前禁止 --allow-all-df）
python scripts/phase4_3a_2/build_job_candidates.py

# 3. 真实配对生成（固定种子 20261212，每份简历 12 条）
python scripts/phase4_3a_2/build_real_pairs.py --seed 20261212 --per-resume 12

# 4. 盲标注材料导出（双人各一份，互不可见）
python scripts/phase4_3a_2/export_annotation_packets.py

# 5. 标注 QA：导入校验 / 独立性 / 一致性 / 仲裁 / 最终标签
python scripts/phase4_3a_2/annotation_qa.py

# 6. 泄漏与重复风险门禁
python scripts/phase4_3a_2/leakage_gate.py

# 7. Gold 冻结 + SHA-256 复验（条件不满足自动 blocked）
python scripts/phase4_3a_2/freeze_gold.py --seed 20261213 --blind-ratio 0.3
python scripts/phase4_3a_2/freeze_gold.py verify \
    --manifest data/independent_eval/frozen/evalset_v2/manifest.json

# 全部自动化测试（157 旧 + 80 新）
python tests/phase4_3a/run_all.py
```

## 八、进入 Phase4-3B 的条件判定

**不满足**。进入 Phase4-3B（最终模型选型）前置条件是 H2 完成：
真实简历 ≥ 30 份（目标 100–200 条 JD × 每简历 10–12 配对 → 300–600 组）、
双人独立标注完成并仲裁、Gold 冻结且哈希复验通过。当前全部依赖外部真实人员参与，
本轮不虚构补齐。数据到齐后按上节命令 1→7 顺序执行即可推进 H2。
