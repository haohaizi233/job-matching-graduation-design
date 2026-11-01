# P7-1 真实中文数据采集与接入审计

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 状态：**BLOCKED（数据不足）**
- 证据产物：
  - `reports/phase7/01-data-status.json`（四级状态，无个人信息）
  - `reports/phase7/sample-size-planning.{json,md}`（规模规划测算）
  - `docs/evaluation/phase7-data-collection-operations.md`（运营材料补充件）
- 复用工具（未重写）：`src/job_matching/annotation/{resume_intake,consent,pii,dedup}.py`、
  `scripts/phase4_3a_2/{intake_resumes,build_job_candidates,build_real_pairs}.py`

---

## 一、当前可用真实数据量（实测）

| 项 | 数量 | 说明 |
|---|---:|---|
| 磁盘存在简历文件（`file_exists`） | 1 | 应用上传存储中的 1 个 `.txt`，含手机号/邮箱形态 PII |
| 有效授权记录（`consent_verified`） | **0** | `data/private/consent/` 不存在 |
| 已导入 accepted 集（`intake_accepted`） | **0** | `data/independent_eval/resume_pool/` 不存在 |
| Gold 准入简历（`eligible_for_gold`） | **0** | 授权与导入均未完成 |
| 真实人岗配对 | **0** | `pairs_v1.jsonl` 为空、`pairs_real_v2.jsonl` 不存在 |
| 独立标注员 | **0** | — |
| 岗位候选池 | 150 | `job_pool_v1.jsonl`（见第四节的许可与泄漏限制） |

### 具体缺口（对照协议门禁）

| 门禁 | 要求 | 现状 | 缺口 |
|---|---|---|---|
| G1-a 有效真实简历 | ≥30（A）/ ≥70（B） | 0 | **缺 30 / 70 份** |
| G1-b 真实人岗配对 | ≥300 | 0 | **缺 300 组** |
| G1-c 授权完整 | 100% granted/licensed | 0 条 | **缺 30 / 70 份授权书** |
| G2-a 独立标注员 | ≥2 人 | 0 | **缺 2 人** |
| G2-b 双人完整覆盖 | 全部配对 | 0 | 依赖 G1-b |
| G3 Gold 冻结 | 写入 + 复验 | false/false | 依赖 G1/G2 |

> **BLOCKED 判定**：在上述缺口补齐前，`H2` 维持 `blocked`，P7-3 / P7-4 不得声称完成。

---

## 二、人工数据收集运营材料（已交付）

任务书要求的 9 项材料，落位如下（**复用**既有 `consent-template.md`，未另起协议）：

| # | 材料 | 落位 | 状态 |
|---|---|---|---|
| 1 | 研究参与者说明 | `phase7-data-collection-operations.md` 第一节 | 完成 |
| 2 | 真实简历授权说明 | `consent-template.md` 第一节（沿用） | 完成 |
| 3 | 最小必要字段清单 | `phase7-data-collection-operations.md` 第三节 | 完成 |
| 4 | 数据脱敏说明 | 同上第四节 + `annotation/pii.py` | 完成 |
| 5 | 保存与访问权限说明 | 同上第五节 | 完成 |
| 6 | 授权撤回和删除流程 | 同上第六节（7 步可执行） | 完成 |
| 7 | 数据保留期限 | 同上第五节（评审后 90 天） | 完成 |
| 8 | 数据来源和使用许可登记 | 同上第七节 Source License Registry | 完成 |
| 9 | 每批数据的验收清单 | 同上第八节（10 项 + 批次记录模板） | 完成 |

**Agent 未代任何人签署授权**；所有授权记录必须由简历提供者本人确认。

---

## 三、样本规划（详细测算见 sample-size-planning.md）

| 方案 | 简历 | 每简历岗位 | 总配对 | dev 组 | blind 组 | 标注员工作量（含仲裁） | blind 统计稳定 |
|---|---:|---:|---:|---:|---:|---:|---|
| A 最低门禁 | 30 | 10 | 300 | 21 | 9 | ~27 小时 | **否** |
| B 合理查询组数 | 70 | 8 | 560 | 49 | 21 | ~53 小时 | 是 |
| C 扩展稳定性 | 120 | 10 | 1200 | 84 | 36 | ~112 小时 | 是 |

- `unjudgeable` 敏感性按 5% / 10% / 20% / 30% 四档测算有效配对与每简历有效候选；
- 去重剔除损失假设 5%；双人分歧率假设 30%（需仲裁）；
- **全部为假设性规划测算**，不是已采集或已标注事实；真实数据到位后必须回填实测值复算；
- 若最终采用 B 或 C，须在标注与盲测**之前**提交版本化协议修订 `phase7-eval-protocol-v2`。

---

## 四、岗位池质量审计（150 条中文 JD）

数据来自 `data/raw/job-education/annotated/2w_0716_eval.csv`（22,671 行）与
`data/raw/job-education/default/test/2w_0716.csv`（22,671 行），
经分层采样（种子 `20261210`）选 150 条；去重剔除 `exact_dup=23,990`、`norm_dup=184`、`near_dup=0`。

### 4.1 逐项检查

| 检查项 | 结论 | 证据 |
|---|---|---|
| 来源许可 | **部分通过** | `job-education` = `apache-2.0`（卡片 front-matter 可核）；`all_df.csv` = **UNKNOWN** |
| 原文完整性 | 通过 | 59 行空描述已跳过，其余 22,671 行保留 |
| 重复与近似重复 | 通过 | 三级去重已执行，`near_dup=0` |
| 岗位类别覆盖 | **不均衡** | IT 88 / OTHER 19 / MARKETING-OPS 15 / HR 12 / FINANCE 8 / SALES 8 |
| 学历要求 | 可用 | `education_requirement` 原始表达 + 规范 token |
| 技能要求 | 可用 | `required_skills` / `preferred_skills`（启发式，仅供标注辅助） |
| 招聘时效性 | **UNKNOWN（本地无证据）** | 数据集无发布时间字段 |
| 可评估性 | 部分 | 仅 IT 类样本量足以支撑分类别一致性分析；FINANCE/SALES 各 8 条 < 5×2，分类别指标应报 `not_computable` |

PII 扫描（只记计数）：`email 40 / landline 58 / mobile_cn 9 / qq_wechat_id 1015`——
岗位联系方式在导入时已按 `pii.py` 掩码，但**电话/微信命中量较大**，
导出标注包前必须再次过 `check_export`。

### 4.2 任务相关泄漏：必须按子任务分别结论（不得一概宣称无泄漏）

| 子任务 | 是否存在泄漏 | 说明 |
|---|---|---|
| **学历要求抽取** | **存在文本泄漏** | 岗位池 JD 来自 `job-education` 语料，正是学历抽取模型（tfidf / charcnn）的训练与评测语料。同一 JD 对该子任务属于**已见文本**。用这些 JD 去评价学历抽取，会高估泛化能力 |
| **人岗相关性排序（中文人工 Gold）** | **不存在标签泄漏，但存在文本分布偏熟悉** | 人工相关性标签是全新标注，与学历抽取标签不同源；但 JD 文本本身对模型是"熟悉分布"。属于**输入侧已见**而非标签泄漏，须如实披露 |
| **英文代理标签历史模型** | **不同源** | Ridge/GBM/MLP/RankNet 训练标签来自 `job-resume-matching`（英文），与中文 JD 岗位池不构成同源标签泄漏；但不得据此宣称"无泄漏" |

处理要求：
1. 论文与报告中，凡引用岗位池结果，必须标注 `job_pool_overlap_with_education_corpus=true`；
2. `leakage_gate.flag_training_overlap` 应把这批 `job_id` 登记为训练重合候选；
3. 学历抽取子任务的评价必须改用**不在训练语料中的 JD**，或明确标注"仅流程验证，不代表泛化"。

### 4.3 历史 Gold 污染

`pool_manifest_v1.json` 记录 `historical_gold_in_source = 736`——源语料中含 736 条历史人工标注记录。
这些记录**不得**当作本项目的人工 Gold（口径不同、标注者不明、无法双人复核），
必须在 `leakage_gate` 中作为"历史 Gold 污染"项登记并隔离。

---

## 五、数据接入验收（当前实测结果）

按 `phase7-data-collection-operations.md` 第八节 10 项清单，对"当前唯一一份简历文件"执行：

| # | 验收项 | 结果 | 原因 |
|---|---|---|---|
| 1 | consent granted | **FAIL** | 无授权记录 |
| 2 | source license | **FAIL** | 来源未登记 |
| 3 | 去标识化 | **FAIL** | 原文含手机号/邮箱形态 PII，未脱敏 |
| 4 | 中文识别 | PASS | CJK 占比 0.386，`zh_or_mixed` |
| 5 | 重复隔离 | NOT_RUN | 未进入导入流程 |
| 6 | 字段完整性 | NOT_RUN | 未进入导入流程 |
| 7 | 合成标识 | **UNKNOWN** | 无法确认是否合成 |
| 8 | Gold 准入 | **FAIL** | 1–3 不通过 |
| 9 | 撤回处理 | NOT_APPLICABLE | 无授权即无撤回 |
| 10 | 批次登记 | **FAIL** | 无批次记录 |

**结论：该文件不得进入 Gold，也不得作为研究样本使用。**
处理建议（需真人决定）：若它是某位同学授权提交的简历，应补签授权并按流程重新导入；
若无授权来源，应立即删除（见撤回与删除流程第六节）。

---

## 六、结论

- 当前**可用真实数据数量：有效简历 0 / 岗位 150（带许可与泄漏限制）/ 真实配对 0**；
- H2 **维持 BLOCKED**，缺口为：有效简历 30–70 份、授权书 30–70 份、真实配对 300+ 组、
  独立标注员 2 人、仲裁员 1 人、2 个数据源许可核实；
- 数据采集是**人工运营任务**，Agent 本轮已交付全部可执行材料、工具与状态跟踪，
  但不能代替真人提供简历、签署授权或进行标注。

### 纪律遵守

不伪造真实简历、不伪造授权记录、不访问未授权简历库、不把合成数据当人工真值、
不把业务用户反馈冒充人工标签、不在公开仓库上传真实简历或同意书。
