# Phase4-3A-2 真实中文数据收集与导入规范

> 配套：[`consent-template.md`](consent-template.md)（授权模板）、
> [`phase4-3a-2-annotation-plan.md`](phase4-3a-2-annotation-plan.md)（标注计划）、
> [`phase4-3a-protocol.md`](phase4-3a-protocol.md)（评估协议）。
> 本规范覆盖模块 A（中文简历接入）与模块 B（校招岗位筛选）的收集、准入、导入与安全要求。

## 一、三类来源严格隔离

| 来源类别 | 含义 | 可否进入人工 Gold | 标识 |
|---|---|---|---|
| `A_consented_individual` | 经本人同意提供的真实大学生简历 | 可（需 `consent_status=granted`） | `is_synthetic=false` |
| `B_licensed_public` | 许可明确允许研究用途的公开简历数据集 | 可（需 `licensed` + license 证据） | `is_synthetic=false` |
| `C_synthetic` | 为测试工具生成的合成简历 | **永不**（仅开发/单元测试） | `is_synthetic=true` |

纪律：

1. 合成简历只能出现在合成测试池（`pairs_synthetic_*.jsonl`）与单元测试夹具中，
   不得冒充真实人工数据，不得计入真实 Gold 数量；
2. 英文简历（`data/raw/job-resume-matching/cv.csv`，9,544 份）**禁止**充当中文就业画像数据；
3. 不抓取需要登录、绕过访问限制或未经授权的大规模个人简历；
4. 未授权真实简历 → `intake_resumes(require_consent=True)` 直接报错（拒绝进入 Gold），
   非 granted 状态 → 进入隔离清单并带原因。

## 二、收集规范（A 类逐条执行）

1. 告知研究目的（见 consent-template 第一节）；
2. 告知处理的数据类别（教育背景/求职意向/技能与经历）；
3. 明确数据仅用于本毕设约定用途；
4. 说明保存方式（本地 `data/private/` 非公开目录）、访问范围（研究者+标注员）与删除方式；
5. 提供授权撤回及删除流程（7 日内删除，冻结版本作废重冻）；
6. 不收集身份证号、家庭住址等无关信息；姓名、联系方式、照片等**非必要不保存**；
7. 关联标识使用随机 `resume_id`（内容哈希+种子派生，`resume_intake.assign_resume_id`），
   **绝不**使用真实姓名做 ID；授权表中人物代号用 `subject_pseudo_id`（禁中文）。

## 三、数据存放与 Git 边界

```
data/private/                      # 不入库（.gitignore 已配置）
  resumes/                         # 简历原文（txt/docx/pdf/csv/jsonl）
  consent/consent_records.csv      # 授权登记（含撤回方式、许可证据路径）
  consent/evidence/                # 许可证据（截图/文件）
  annotations_raw/                 # 标注员原始填写文件
  accepted/resumes_accepted_v2.jsonl  # 导入后脱敏可用记录（仍属真实数据，不入库）
data/independent_eval/             # 入库（仅统计、模板、合成夹具、哈希清单）
```

Git 仓库只保存：数据 Schema、采集与导入代码、不含个人信息的统计、使用说明、
合成测试夹具、非敏感哈希与版本记录。真实简历、授权记录、含个人信息的原始人工标注
不得推送公开仓库（`.gitignore` 按目录/具体文件名忽略，不用通配误伤模板与报告）。

## 四、模块 A：简历导入（支持 PDF / DOCX / TXT / CSV / JSONL）

导入统一走 `src/job_matching/annotation/resume_intake.py`：

- `extract_text`：TXT（utf-8/gbk）、DOCX（zipfile 最小适配器）、PDF（PyMuPDF，缺失时
  **显式报错**不静默跳过）；
- `parse_structured`：CSV / JSONL 结构化行（必须含 `resume_text` 列）；
- `intake_resumes`：批量导入 → PII 脱敏（`pii.scrub_record`）→ 授权门禁（`consent.consent_index`）
  → 重复隔离（同文本不同 ID 保留首条）→ 语言判定（非中文隔离）→ Gold 资格标注。

### 可执行命令

```powershell
# 1) A 类：经本人同意的真实简历（授权记录必须在 data/private/consent/consent_records.csv）
python scripts/phase4_3a_2/intake_resumes.py `
    --source-class A_consented_individual `
    --source-name consented-2026q4 `
    --resumes data/private/resumes `
    --consent data/private/consent/consent_records.csv

# 2) B 类：许可明确的研究用公开数据集（license 与许可证据必须登记）
python scripts/phase4_3a_2/intake_resumes.py `
    --source-class B_licensed_public `
    --source-name public-licensed-v1 `
    --resumes data/private/resumes_public `
    --consent data/private/consent/consent_public.csv

# 3) C 类：合成简历（仅工具测试；产物自动隔离，永不进 Gold）
python scripts/phase4_3a_2/intake_resumes.py `
    --source-class C_synthetic `
    --source-name synthetic-fixture `
    --resumes tests/fixtures/synthetic_resumes.jsonl
```

产物：`data/private/accepted/resumes_accepted_<source>.jsonl`（脱敏可用记录）、
`reports/phase4-3a-2/resume-intake-audit.json`（导入审计：数量、隔离原因分布、PII 命中统计）。

## 五、模块 B：校招岗位筛选（复用 Phase4-3A 岗位池）

**不重新采集**：在 `data/independent_eval/pool/job_pool_v1.jsonl`（150 条，seed=20261210）
基础上做准入审计与字段补全，产出 `job_pool_v2.jsonl`（100–200 条合规中文 JD）。

岗位准入字段（缺失显式 `unknown`，**不推断编造**）：
`job_id, job_title, employer_name, job_description, required_skills, preferred_skills,
education_requirement, experience_requirement, employment_type, graduation_cohort, city,
source, source_url, source_license, collection_time, content_hash`。

目标岗位族（优先涵盖，不为凑类别加入无法评估的职位）：
Java 后端 / Python 开发 / Web 前端 / 软件测试 / 数据分析 / 算法与 AI 工程 / 运维与 DevOps /
其他与实际简历方向相关（非技术岗位保留作跨类别负例来源，不占技术族配额）。

### 裁决规则（逐条给出 保留 / 隔离 / 剔除 + 原因）

| 情形 | 裁决 | 原因口径 |
|---|---|---|
| `all_df` 来源（许可 UNKNOWN） | **隔离** | 来源与使用许可未确认前不得进入正式 Gold 池 |
| 与历史 Gold 交叉 job_id（5 个） | **保留但剔除出盲测** | 岗位曾参与 Phase4-2 规则研究，不得作全新独立盲测样本 |
| 与学历训练语料哈希/近似重合 | **保留但剔除出盲测** | 学历抽取模型见过该 JD 文本；仅对"要求模型未见过岗位文本"的盲测任务剔除 |
| 岗位级近似重复 | **保留首条、隔离其余** | 同 JD 不同 ID 会造成配对重复与指标虚高 |
| 配对级近似重复（9 处，均在合成池） | **隔离后进入配对的副本** | 不通过重复简历/岗位机械凑数 |

### 污染风险分任务说明（不得一概而论）

1. **学历抽取模型（教育方向）**：训练语料为 job-education default/train+validation，
   与候选池 JD 文本存在哈希/近似重合 → 该组件在这些 JD 上**不是零样本**，
   涉及其学历字段输出的评估任务须剔除重合岗位；
2. **人岗匹配排序模型（RankNet/GBM/Ridge 等）**：训练语料为英文 matches 语料，
   与中文 JD 无文本重合 → 无直接文本泄漏，但其训练标签为英文代理标签（口径限制另述）；
3. **预训练语料污染**：外部预训练模型语料不可知，只能声明"未发现已知泄漏"，
   不能声称绝对无泄漏。

### 可执行命令

```powershell
# 岗位准入审计 + 裁决 + 字段补全（含 all_df 隔离清单、近似重复/历史 Gold 逐条裁决）
python scripts/phase4_3a_2/build_job_candidates.py

# 可选：对学历训练语料做全量交叉扫描（默认复用缓存结果）
python scripts/phase4_3a_2/build_job_candidates.py --rescan-edu-corpus
```

产物：`data/independent_eval/pool/job_pool_v2.jsonl`、
`reports/phase4-3a-2/source-audit.json`、`reports/phase4-3a-2/job-candidate-audit.json`。

## 六、中文文本与字段完整性检查（导入与配对共用）

- 正文非空、语言判定为 `zh`/`mixed`（英文简历/岗位不得充当中文语料）；
- `content_hash` 由规范化文本 SHA-256 派生，同一文本恒得同一 ID（可复现）；
- 导出前 PII 扫描：文本命中掩码为 `***`，结构化 PII 字段（姓名/手机/邮箱/身份证/住址等）
  一律禁止出现在导出文件（`pii.check_export` 白名单外字段直接报错）。

## 七、当前状态声明

截至本规范建立时：**真实中文简历 0 份**。模块 A/B/C/D/E 的工程链路均可运行并有自动化
测试覆盖；真实数据收集尚未完成，H2（真实 Gold 冻结）保持 BLOCKED，直至取得：
经授权的真实中文简历（目标 30–50 份）、合规中文岗位（已具备 150 条候选）、
真实配对（目标 300–600 组）、双人独立标注与仲裁。
