# Phase4-3A-2 开发前审计报告（preflight-audit）

> 生成时间：2026-10-29 ｜ 作用域：`haohaizi233/job-matching-graduation-design`
> 本报告在开发前完成：核对 Phase4-3A 交付快照与实际文件状态，登记已有能力、待补齐内容与外部依赖。

## 一、工作区与版本管理状态

- 当前分支：`main`；未执行任何 push / 远端操作（本轮 Git 仅限本地审计）。
- Phase4-3A 新增目录仍为**未跟踪**状态（`??`）：`src/job_matching/annotation/`、
  `src/job_matching/independent_eval/`、`scripts/phase4_3a/`、`tests/phase4_3a/`、
  `reports/phase4-3a/`、`data/independent_eval/`、`docs/evaluation/`。
- 历史产物（`reports/education-training/*` 模型验证与实验对比、`scripts/education_training/verify_models.py`）
  存在已修改记录，本轮**不回滚、不覆盖**任何历史结果与模型权重。
- `reports.zip` 为既有打包产物，未改动。

## 二、已有能力盘点（可直接复用）

| 能力 | 位置 | 状态 |
|---|---|---|
| 标注协议 + 操作细则 | `docs/evaluation/phase4-3a-protocol.md`、`annotation-guidelines.md` | 可用（`phase4-3a-annotation-v1`） |
| 配对/标注/仲裁 schema 与校验 | `src/job_matching/annotation/schema.py` | 可用（含模型输出列拒收、unjudgeable 独立状态） |
| PII 检测/脱敏/导出检查 | `src/job_matching/annotation/pii.py` | 可用（邮箱/手机/身份证/座机/微信 + 字段名白名单） |
| 去重（完全/规范化/近似 + 跨语料） | `src/job_matching/annotation/dedup.py` | 可用（shingle 倒排阻塞 + Jaccard） |
| 候选池/配对构建 | `src/job_matching/annotation/pool.py` | 可用（分层采样、难度层配额、固定种子） |
| 标注导入/缺失统计 | `src/job_matching/annotation/importer.py` | 可用 |
| 一致性（一致率/Kappa/Weighted Kappa） | `src/job_matching/annotation/agreement.py` | 可用（样本不足输出 not_computable） |
| 仲裁与最终标签（unjudgeable 保护） | `src/job_matching/annotation/arbitration.py` | 可用 |
| 冻结与 SHA-256 复验 | `src/job_matching/annotation/freeze.py` | 可用（stage=pool/evalset，evalset 有人工标注门禁） |
| 来源授权门禁 | `src/job_matching/annotation/consent.py` | 本轮前已存在（A/B/C 三类来源隔离、拒绝未授权进入 Gold） |
| 简历导入（PDF/DOCX/TXT/CSV/JSONL） | `src/job_matching/annotation/resume_intake.py` | 本轮前已存在（脱敏 + 授权校验 + 稳定随机 resume_id） |
| 评估指标/Bootstrap/Baseline | `src/job_matching/independent_eval/` | 可用 |
| CLI 编排 | `scripts/phase4_3a/{run_all,build_pool,leakage_check,import_annotations,check_agreement,arbitrate,freeze_dataset,run_eval,audit_data}.py` | 可用 |
| 自动化测试 | `tests/phase4_3a/`（P1–P10，共 157 项，全通过） | 可用，本轮只扩展不重写 |

## 三、实际数据状态核对（与 Phase4-3A 快照一致，已实测）

- 中文简历 **0** 份；英文简历 9,544 份（`data/raw/job-resume-matching/cv.csv`，禁止充当中文语料）。
- 中文岗位候选池 **150** 条（`data/independent_eval/pool/job_pool_v1.jsonl`，seed=20261210）。
- 真实待标注配对 **0** 条（`pairs/pairs_v1.jsonl` 为空文件）；合成测试配对 **75** 条（均 `is_synthetic=true`）。
- 泄漏事实（`reports/phase4-3a/leakage-check.json` 实测）：
  - 池内配对级近似重复 **9** 处（相似度 0.90–0.98，均在合成配对池内）；简历级/岗位级同文本不同 ID 均为 0。
  - 与历史 Gold（`data/splits/education/gold_holdout.csv`，736 条）交叉 job_id **5** 个：
    `7881740 / 7891020 / 7891194 / 7911845 / 7926209`。
  - 与学历训练语料（default/train+validation）规范化哈希重合 **250** 行、近似重复 **255** 处。
- `all_df` 来源与许可 UNKNOWN（`docs/datasets/README.md` 登记，本地无 README/许可证证据）。
- 原始语料本地实测存在：`data/raw/job-education/*`（含 train/validation/test/annotated）、
  `data/splits/education/gold_holdout.csv`，可用于交叉检查扫描。

## 四、现有机制安全性审查结论

1. **数据保护 / .gitignore**：现有规则忽略 `data/raw/`、模型权重、日志，但**未**覆盖
   真实简历原文、授权记录、含个人信息的原始人工标注 → 本轮必须补充（见下）。
2. **PII 脱敏**：`pii.scrub_record`/`check_export` 在导入与导出路径已接入（pool.write_pool、
   resume_intake.intake_resumes）；文本脱敏 + 字段名白名单双重拦截，机制保留。
3. **冻结与 SHA-256**：`freeze_dataset` 对文件逐一登记 SHA-256，`verify_freeze` 可复验；
   evalset 冻结带人工标注完成度门禁（未完成显式 BLOCKED，`frozen/evalset_v1/freeze_blocked.json` 为证）。
4. **盲标保护**：schema 已拒收模型输出列（`final_score`/`label_strength`/`candidate_rank` 等）；
   但「标注员视图不得包含抽样难度层/配对来源」「同一标注员冒充两名独立标注员」两项**尚无工程门禁**
   → 本轮新建 `blind_guard.py` 补齐。

## 五、本轮待补齐内容（开发清单）

| 模块 | 待补齐 | 产出 |
|---|---|---|
| A 简历接入 | 数据授权说明 + 收集模板；按来源 A/B/C 隔离的导入审计 CLI | `docs/evaluation/consent-template.md`、`phase4-3a-2-data-collection.md`、`scripts/phase4_3a_2/intake_resumes.py` |
| B 岗位筛选 | 岗位准入字段补全（缺失显式 `unknown`）、来源/许可审计、all_df 隔离清单、9 近似重复 + 5 历史 Gold 交叉逐条裁决、学历语料重合分任务污染说明 | `scripts/phase4_3a_2/build_job_candidates.py` → `source-audit.json`、`job-candidate-audit.json` |
| C 配对生成 | 真实简历×合规岗位配对（10–12 条/简历、六类多样性、固定种子、稳定 pair_id、不重复、训练交叉标记） | `scripts/phase4_3a_2/build_real_pairs.py` → `real-pair-manifest.json` |
| D 双盲标注 | 标注员视图白名单导出（去标识化、无模型预测、无抽样类别）、独立性门禁、一致性与仲裁 QA 流程 | `blind_guard.py`、`export_annotation_packets.py`、`annotation_qa.py`、`phase4-3a-2-annotation-plan.md` |
| E Gold 冻结 | 简历 ID 组级 70/30 切分、盲测保护、来源/许可清单、冻结复验报告 | `gold_gate.py`、`freeze_gold.py` → `freeze-verification.json` |
| F 测试门禁 | 18 项新场景测试（不重写既有 157 项） | `tests/phase4_3a/test_p11`…`test_p18` + JSON/MD 报告 |

## 六、外部依赖（本机无法自行完成）

1. **真实中文大学生简历（30–50 份）**：需本人知情同意或许可明确的研究用公开数据集；
   不抓取需登录/绕过限制的个人简历。缺此则真实配对、双盲标注、Gold 冻结全部阻断。
2. **授权/许可证明材料**：A 类需同意记录（含撤回方式）；B 类需许可证据（license_evidence）。
3. **两名人工标注员 + 一名仲裁员**：真人独立标注，禁止生成式 AI 替代。
4. **`all_df` 来源与许可说明**：补齐前该来源岗位一律隔离，不进 Gold 池。
5. **job-education 具体 HF repo id / 下载日期**：本地无证据（登记为 UNKNOWN），如需精确
   `source_url` 需用户提供。

## 七、保护承诺（本轮纪律）

- 不清空工作区、不覆盖 `reports/phase4-3a/` 与 `reports/education-training/` 历史结果；
- 不修改已验收模型权重（`models/`、`experiments/` 不触碰）；
- 不进入 Phase4-3B 最终模型选型；不重新训练模型；
- 不用生成式 AI 生成任何人工标签 / 简历 / 仲裁结论；无真实人工数据时 G2 保持 BLOCKED；
- Git 只做本地审计与安全忽略规则维护，不自动 push。
