# Phase7 数据采集运营手册（补充件，不替代既有授权协议）

- 版本：`phase7-collection-ops-v1`
- 建立时间：2026-10-31
- **配套关系**：本文件是 [`consent-template.md`](consent-template.md)（`phase4-3a-2-consent-v1`）的
  **运营补充**，授权文本与登记字段**完全沿用** `consent.CONSENT_FIELDS`，不另起一套协议。
  凡与 `consent-template.md` 冲突之处，以 `consent-template.md` 为准。
- 配套：[`phase4-3a-2-data-collection.md`](phase4-3a-2-data-collection.md)、
  [`phase4-3a-2-annotation-plan.md`](phase4-3a-2-annotation-plan.md)、
  [`annotation-guidelines.md`](annotation-guidelines.md)

---

## 一、研究参与者说明（对外话术口径）

对每一位简历提供者，必须先说清三件事，再收简历：

1. **这是什么**：毕业设计研究《大学生就业岗位画像与简历智能匹配系统的设计与实现》的
   人工评估集建设，用来检验"人岗匹配"算法的评估口径是否可靠。
2. **不是什么**：不用于商业招聘、不向任何第三方提供简历、不用于训练对外发布的模型、
   不作为任何录用或淘汰依据。
3. **你会得到什么**：没有直接报酬；研究结论写进毕业论文，且不含任何可识别个人的内容。

参与者须知（随知情同意书一并提供）：

| 项 | 内容 |
|---|---|
| 参与方式 | 自愿提供简历文本（或研究者协助整理为纯文本） |
| 参与时长 | 单次提交；后续如需澄清会再联系 |
| 可获得的结果 | 可索取研究结论摘要 |
| 退出方式 | 见第六节，无需说明理由 |
| 伦理说明 | 本研究为毕业设计，未涉及医疗/未成年人/敏感群体；仍按最小必要原则处理个人信息 |

---

## 二、真实简历授权说明（沿用 consent-template.md）

- 授权文本：`consent-template.md` 第一节（知情同意书模板），逐字使用，不得私自改写条款；
- 授权登记：`consent-template.md` 第二节 CSV 字段，与 `src/job_matching/annotation/consent.py`
  的 `CONSENT_FIELDS` 严格一致；
- **Agent / 研究者不得代签**：授权必须由简历提供者本人确认（线上可留"姓名拼音首字母 + 日期"）。
  任何由 AI、研究者或第三方代为勾选/签署的记录视为无效，直接进入隔离清单。

---

## 三、最小必要字段清单（数据最小化）

**只收**（与匹配判断直接相关）：

| 字段 | 必需 | 说明 |
|---|---|---|
| `resume_text` | 是 | 简历正文（脱敏后进入研究数据） |
| `target_position` | 否 | 目标岗位 |
| `skills` | 否 | 技能清单 |
| `education_level` / `graduation_cohort` | 否 | 学历、毕业届别 |
| `employment_type` / `years_experience` | 否 | 就业类型、年限 |
| `city` / `salary_expectation` | 否 | **独立维度**，不进入相关性真值标签 |

**明确不收**（收到也必须在导入前删除/掩码）：
身份证号、家庭住址、婚姻状况、政治面貌、照片、真实姓名、手机号、个人邮箱、
微信/QQ 号、护照/银行卡号、现/前雇主的具体可识别信息。

> 工具保证：`src/job_matching/annotation/pii.py`（下沉到 `domain/pii_masking`）在导入时
> 自动掩码，`check_export` 在导出标注材料前做全量残留校验；命中只记数量不记原文。

---

## 四、数据脱敏说明

| 步骤 | 时机 | 实现 |
|---|---|---|
| 字段白名单裁剪 | 导入 | `resume_intake.intake_resumes` 只保留白名单字段 |
| PII 掩码 | 导入即脱敏 | `pii.scrub_record`，输出 `***` 掩码，命中数入报告 |
| 随机化 ID | 导入 | `assign_resume_id(content_hash, seed)`，绝不使用真实姓名 |
| 导出残留扫描 | 导出标注包前 | `pii.check_export` + `blind_guard.check_packet_columns` |
| 撤回后清理 | 撤回时 | 见第六节 |

**口径提醒**：掩码 ≠ 不可逆匿名化。公开研究产物必须再过 `check_export` 全量校验，
且**不得**把真实简历、标注原文、同意书上传到公开仓库或 GitHub Actions。

---

## 五、保存、访问权限与保留期限

| 项 | 约定 |
|---|---|
| 存储位置 | `data/private/`（本地、非公开、已在 `.gitignore`） |
| 访问范围 | 研究者本人 + 标注员；标注员只看**去标识化**简历与 JD |
| 备份 | 不做云端备份；如需备份必须加密且同样不入库 |
| 保留期限 | 毕业设计评审结束后 **90 天内删除**，或按参与者要求提前删除 |
| 保留例外 | 无。授权文件、脱敏副本、标注记录、派生统计一并删除 |
| 公开产物 | 只公开聚合统计与哈希清单，不公开任何原文 |

---

## 六、授权撤回与删除流程（可执行）

| 步骤 | 动作 | 时限 | 责任人 |
|---|---|---|---|
| 1 | 参与者通过约定方式提出撤回（邮件/当面，无需理由） | — | 参与者 |
| 2 | 研究者登记到 `consent-template.md` 第四节撤回记录表 | 当日 | 研究者 |
| 3 | 将该 `consent_status` 改为 `withdrawn` | 当日 | 研究者 |
| 4 | 删除原文、脱敏副本、派生标注记录 | **7 日内** | 研究者 |
| 5 | 若已进入冻结版本：作废该冻结版本并重新冻结（升 `dataset_version`） | 7 日内 | 研究者 |
| 6 | 复查派生产物（预测矩阵、聚合统计）是否可回链；可回链的一并重建 | 7 日内 | 研究者 |
| 7 | 在 `reports/phase7/01-data-intake-audit.md` 追加撤回处理记录 | 完成后 | 研究者 |

撤回不影响撤回前基于授权的处理活动；但**撤回后**不得再新增任何使用。

---

## 七、数据来源与使用许可登记（Source License Registry）

所有进入研究的简历/岗位来源必须在此登记；未登记或许可不明的来源**禁止**进入 Gold。
存放：`data/private/consent/source_license_registry.csv`（不入库），本表只登记**非敏感**摘要。

| 来源 ID | 类别 | 来源描述 | 许可 | 许可证据位置 | 允许用途 | 状态 |
|---|---|---|---|---|---|---|
| SRC-JOB-EDU-001 | B_licensed_public | `data/raw/job-education/`（@wangzihaogithub 发布的岗位学历数据集） | `apache-2.0` | 本地 HF 卡片 front-matter（`docs/datasets/README.md` 第 2 节可核） | 岗位侧候选池、学历抽取训练 | **已核** |
| SRC-JOB-MATCH-001 | B_licensed_public | `data/raw/job-resume-matching/`（英文人岗匹配数据集） | **UNKNOWN** | 卡片 front-matter 写 `mit`，正文写"Please update the dataset license before publishing"，两者矛盾 | 流程验证 / 历史模型研究（不得作为中文真值） | **UNKNOWN，保留阻断** |
| SRC-ALLDF-001 | B_licensed_public | `data/raw/other/all_df.csv` | **UNKNOWN** | 目录内无 README / 元数据 / LICENSE | 岗位资格字段补充 | **UNKNOWN，保留阻断** |
| SRC-A-IND-001 | A_consented_individual | 经本人同意的真实中文大学生简历 | 本人授权（`consent-template.md`） | `data/private/consent/evidence/` | 人工 Gold 评估集 | **未采集（0 份）** |
| SRC-C-SYN-001 | C_synthetic | 合成简历夹具（`tests/fixtures/synthetic_resumes/`） | not_applicable | 脚本生成记录 | 工具链测试 / 演练 | **可用，永不入 Gold** |

登记规则：
1. B 类必须有可核许可证据（LICENSE 文件、数据集卡片 front-matter、发布者声明截图）；
2. 许可矛盾或缺证据一律标 `UNKNOWN`，**不得**自行编造 MIT / Apache-2.0；
3. 每次新增/变更来源都要更新本表并在 `01-data-intake-audit.md` 留痕。

---

## 八、每批数据验收清单（Batch Acceptance Checklist）

一批数据（一份或多份简历）接入时，逐项打勾；任一项不通过 → 整批进入隔离清单，不得混入 Gold。

| # | 验收项 | 检查方式 | 通过标准 |
|---|---|---|---|
| 1 | `consent granted` | `consent.validate_consent_record` | `consent_status ∈ {granted, licensed}`，字段齐全 |
| 2 | `source license` | 第七节登记表 | 许可明确且证据可核；UNKNOWN 一律不通过 |
| 3 | 去标识化 | `pii.scrub_record` + 人工抽查 | 无姓名/手机号/邮箱/身份证残留 |
| 4 | 中文识别 | `pool.detect_language` | `language ∈ {zh, mixed}` |
| 5 | 重复隔离 | `dedup.exact_hash` / `near_duplicate_pairs` | 无完全重复；近重复（Jaccard ≥ 0.90）进隔离 |
| 6 | 字段完整性 | `resume_intake.parse_structured` / 必填校验 | `resume_text` 非空，白名单字段齐全 |
| 7 | 合成标识 | `is_synthetic` 字段 | 真实来源必须 `is_synthetic=false`；合成必须显式声明 |
| 8 | Gold 准入 | `consent.gold_eligibility` | `eligible_for_gold=true` 才可进 accepted |
| 9 | 撤回处理 | 撤回记录表 | 无未处理的撤回请求 |
| 10 | 批次登记 | 本清单 + `01-data-intake-audit.md` | 批次号、数量、哈希清单、验收人、日期齐全 |

批次记录模板：

| 批次号 | 日期 | 来源 ID | 份数 | 接受 | 隔离 | 隔离原因分布 | 验收人 | 备注 |
|---|---|---|---:|---:|---:|---|---|---|
| BATCH-2026Q4-001 | — | SRC-A-IND-001 | 0 | 0 | 0 | — | — | **尚未采集** |

---

## 九、人工依赖清单（当前未满足）

| 依赖 | 数量/规格 | 状态 |
|---|---|---|
| 真实中文简历提供者 | ≥30 份（Scenario A）/ ≥70 份（Scenario B） | **0** |
| 简历授权书签署 | 每份简历 1 份 | **0** |
| 独立标注员 | ≥2 人（不同自然人） | **0** |
| 人工仲裁员 | ≥1 人（非标注员本人） | **0** |
| 岗位池来源许可核实 | 2 个 UNKNOWN 来源 | **待核实** |

以上全部为**人工**任务，Agent 不能代为完成，只能提供材料、工具与状态跟踪。
