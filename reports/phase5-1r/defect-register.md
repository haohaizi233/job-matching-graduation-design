# Phase5-1R 缺陷登记册（defect-register）

- 基线提交：`0225fcb`（整改代码落地于 `35103e5` / `0eef825`，回归套件落地于 `e78b20a`）
- 本文件依据真实代码与测试证据生成；每条缺陷给出根因、修复位置与回归用例。
- 状态口径：已修复 = 有回归用例锁定且 `python tests/phase5_1r/run_all.py` 全绿（151/151）。

## F-001 Gold 冻结循环门禁

- **现象**：冻结前置检查（precheck）依赖冻结产物（manifest 哈希）才能运行，
  形成"要冻结先通过检查、要检查先有冻结"的循环依赖，工程上无法完成首次冻结。
- **根因**：`annotation/gold_gate.py` 将前置门禁与冻结后置门禁混在同一判定路径。
- **修复**：拆为两阶段门禁（`gold_gate.py` 注释"冻结前置 / 冻结后置两阶段门禁（F-001）"）：
  precheck 只看事实（标注完成、样本量、数据来源），不要求冻结哈希；postcheck 才校验冻结结果。
- **回归**：`test_r1_gold_freeze.R1PreFreezeGate`（`test_precheck_does_not_require_freeze_hash` 等）、
  `R1FreezeCliChain`（`test_positive_chain_engineering_success`、`test_blocked_without_annotations`）。

## F-002 标注完成状态判定不完整

- **现象**：单人标注 / 导入错误行 / 被强制的 unjudgeable 等情形仍可能被计为"标注完成"。
- **根因**：完成状态由调用方各自判断，缺少统一硬性条件集合。
- **修复**：新增 `annotation/completion.py`（"标注完成状态与仲裁状态判定（F-002 / F-003）"），
  五态判定（complete / in_progress / 阻断态），条件含独立性、导入错误、最终标签一对一、unjudgeable 保护。
- **回归**：`test_r2_annotation_quality.R2CompletionStatus`（13 项）、`R2UnjudgeableAndIntegrity`。

## F-003 仲裁状态与越权仲裁

- **现象**：无分歧样本被强制要求仲裁文件；仲裁记录可改写双方已一致的结论（越权仲裁）。
- **根因**：仲裁状态只有二值判定，未区分"无分歧 / 部分仲裁 / 全部仲裁 / 无效仲裁"。
- **修复**：`annotation/completion.py` 仲裁四态判定 + `scripts/phase4_3a_2/annotation_qa.py`
  "标记「越权仲裁」（F-003）"；冻结 CLI 按仲裁状态登记，无分歧不再强制仲裁文件
  （`scripts/phase4_3a_2/freeze_gold.py` 注释）。
- **回归**：`R2ArbitrationStatus`（8 项）、`R2AnnotationCliChain.test_fake_arbitration_cannot_override_agreement`。

## F-004 冻结不可变性不足

- **现象**：冻结只写 manifest，互斥/唯一性检查缺失；同一 dataset_version 可重复冻结；
  写入失败可能留下看似完整的冻结目录。
- **根因**：`annotation/freeze.py` 无内容级硬性检查、无重复冻结拦截、无原子发布。
- **修复**：`freeze.py` 增加互斥/唯一性检查（"不再只写 manifest"）、内容级硬性检查
  （合成配对混入 / 训练数据交叉配对进盲测）、同版本重复冻结拒绝、安全发布（临时目录 + 原子改名）。
- **回归**：`R1FreezeCliChain.test_tamper_detected_on_reverify`、`test_fixture_mode_rejected_in_real_workspace`、
  `test_split_is_resume_group_level`，`R1PostFreezeGate.test_blind_protection_requires_freeze`。

## F-005 毕业届别约束"见值即 satisfied"

- **现象**：学生 2027 届 + 岗位仅限 2026 届，旧逻辑误判 `satisfied`。
- **根因**：届别约束只要有值即判满足，未真正比较届别。
- **修复**：`service/requirements.py`（新增）+ `service/contracts.py`
  "规范化毕业届别约束（F-005）"+ `service/explanations.py`
  "真正比较届别，而非见值即 satisfied"；支持仅限某届/多届/区间/及以后/应届/往届/不限，
  旧契约 `graduation_cohort` 字段回退仍正确比较。
- **回归**：`R3CohortConstraint`（13 项，含 `test_2027_rejects_only_2026` 历史缺陷复现）。

## F-006 经验判断顺序错误

- **现象**：`none_required + years_min=None` 被提前判为 `requirement_unclear`；
  "学历不限"被误读为经验不限。
- **根因**：缺失值分支先于语义明确的特殊状态返回。
- **修复**：`service/explanations.py`"先处理语义明确的特殊状态，再处理缺失值"、
  `service/job_parser.py`（F-006 注释）、`service/requirements.py`
  `parse_experience_requirement_detail`（只从经验语境子句解析，
  区分 `none_required / preference_only / unknown`）。
- **回归**：`R3ExperienceConstraint`（`test_none_required_not_confused_with_unknown` 等）。

## F-007 API 边界与安全加固缺失

- **现象**：请求体/上传大小无硬上限；Base64 先解码后检查可耗尽内存；
  错误响应泄漏本机绝对路径；默认监听地址不安全。
- **根因**：请求边界与安全常量分散且顺序错误。
- **修复**：`service/api.py`（请求边界上限、Base64 "先查长度、再解码、再查字节数"、
  开发环境默认回环绑定、限流与请求跟踪）、`service/text_extract.py`
  （解码后大小在解析前检查、临时目录可靠清理）、`service/errors.py`
  （"本地绝对路径不得进入错误响应"）。
- **回归**：`R4UploadLimits`（9 项）、`R4ErrorHygiene`（4 项）、`R4RequestTracking`（5 项）、
  `R4DeploymentScope`。

## F-008 阶段文档与目录不一致

- **现象**：`docs/project-structure.md` 目录表遗漏已投入使用的目录。
- **根因**：文档随阶段演进未同步。
- **修复**：文档同步（`docs/project-structure.md` 注记"F-008"）。
- **回归**：文档一致性检查（A7 门禁，人工 + CI 报告一致性检查）。

## F-009 独立评估输入被生成器二次消费

- **现象**：`evaluate_ranking_human` 传入生成器时，二次 `list()` 只能得到空序列，
  评估结果不可复现。
- **根因**：入口未统一物化输入。
- **修复**：`independent_eval/metrics.py`"入口统一物化输入（Phase5-1R F-009）"。
- **回归**：`test_r5_metrics_input.R9GeneratorMaterialization`
  （`test_generator_of_relevance_not_consumed_twice` 历史缺陷复现）等 20 项。

## F-010（二轮审计补漏）姓名 PII 脱敏缺口

- **现象**：「姓名：张三」形式的原文姓名未被脱敏即进入日志/证据。
- **根因**：PII 模式集只覆盖号码/邮箱/住址，未覆盖姓名键值对。
- **修复**：`annotation/pii.py` 增加姓名键值对模式（现下沉 `domain/pii_masking.py` 的
  `name_kv` 模式），导出检查将姓名字段列为违规字段。
- **回归**：`tests/phase5_1a` `A2SharedRules.test_pii_mask_is_not_anonymization`、
  `tests/phase5_1r/test_r6_e2e_chains.ChainBResumeToRanking.test_no_pii_in_response_or_logs`。

## 未修复 / 暂不实施

| 项 | 说明 |
|---|---|
| 共享解释器 `pip check` 三方包冲突 | 非项目依赖（adalflow/f2/grpcio-tools 等），属环境问题；登记为已知限制 |
| 旧 scikit-learn checkpoint 在 Serving 环境反序列化失败 | 环境不兼容（见 `reports/phase5-1a/model-compatibility.md`）；禁止重训，走 Legacy 兼容环境 |
