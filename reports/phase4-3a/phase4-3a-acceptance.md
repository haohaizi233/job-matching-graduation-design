# Phase4-3A 阶段验收报告

> 生成时间：2026-10-29T10:22:08 ｜ 协议版本：`phase4-3a-protocol-v1` / `phase4-3a-annotation-v1`

## 一、结论

- **G1 评估工程就绪：通过**（Phase4-3A 工程部分通过，等待人工标注）
- **G2 独立评估数据正式可用：未通过（BLOCKED）**—— 未达到 G2，不得进入 Phase4-3B 最终模型选型
- `annotation_status = pending`
- `blind_evaluation_status = blocked`
- `final_model_selection_status = BLOCKED`

## 二、G1 门禁

| 门禁项 | 结论 | 证据 |
|---|---|---|
| 样本构建脚本正常 | ✅ | 岗位池 150 条；合成配对 75 条；真实配对 0 条 |
| 标注协议明确 | ✅ | docs/evaluation/phase4-3a-protocol.md + annotation-guidelines.md |
| 标注导入及仲裁可用 | ✅ | src/job_matching/annotation/{importer,arbitration}.py + scripts/phase4_3a/{import_annotations,arbitrate}.py |
| 数据清洗和泄漏检查可用 | ✅ | reports/phase4-3a/leakage-check.json |
| 评估程序可运行 | ✅ | src/job_matching/independent_eval/ + scripts/phase4_3a/run_eval.py（合成演示见 data/independent_eval/demo/） |
| 冻结和哈希校验可用 | ✅ | 候选池冻结 stage=pool（frozen/pool_v1/manifest.json 含文件 SHA-256，verify_freeze 可复验）；evalset 冻结状态=blocked：冻结所需文件缺失: final_labels -> D:\desktop\毕业设计\data\independent_eval\annotation\final_labels.csv |
| 自动化测试全部通过 | ✅ | reports/phase4-3a/test-results.json（PASS=157） |
| 真实数据缺口已如实登记 | ✅ | dataset-audit.json -> data_gaps |

## 三、G2 门禁

| 门禁项 | 结论 | 证据 |
|---|---|---|
| 已取得符合授权要求的真实中文求职数据 | ❌ | 当前中文简历 0 份 |
| 人工标注完成并通过质量检查 | ❌ | annotation_status=pending |
| 分歧处理完毕 | ✅ | 未仲裁分歧 0 |
| 验证集与盲测集隔离 | ❌ | 冻结后由 mutual_exclusivity 检查给出 |
| 数据来源及哈希齐全 | ✅ | leakage-check.json -> files |
| 指标可从保存预测复算 | ❌ | run_eval.py --verify 待 Gold 后启用 |
| 没有已知阻断性泄漏 | ❌ | 候选池与原历史 Gold 存在 job_id 交叉（需在评估时登记并降级解释） |
| 样本规模与类别覆盖满足用途 | ❌ | 真实配对 0（缺中文简历） |

## 四、数据与泄漏事实

- 中文简历 0 份（数据缺口）；英文简历 9544 份（禁止充当中国大学生就业画像数据）
- 中文岗位 243124 个唯一 ID，含 JD 正文 286902 行；英文岗位 1167 个
- 岗位候选池 150 条（分层采样 seed=20261210）；合成测试配对 75 条（`is_synthetic=true`，永不进人工真值）
- 泄漏检查：池内完全重复 0，近似重复 9，与历史 Gold 交叉 5 个 job_id，与学历训练语料哈希重合 250
- 预训练污染：预训练语料来源不可知，无法完全排除预训练污染；本报告只能声明『未发现已知泄漏』，不能声称绝对无泄漏

## 五、阻断项与下一阶段前置条件

- [ ] 经授权脱敏的真实中文简历（目标 30–50 份）（当前 0）：G2 阻断：无法建立真实中文简历-岗位人工评估配对
- [ ] 真实中文简历-岗位人工标注（目标 300–600 对）（当前 0）：G2 阻断：blind_evaluation_status=blocked
- [ ] other/all_df 来源与授权说明（当前 UNKNOWN）：补齐前不得进入正式评估集
- [ ] 双人独立标注完成（≥2 名标注员，盲标，`annotation_status=complete`）
- [ ] 分歧样本仲裁完成并保留原始标注
- [ ] 正式评估集冻结（`freeze_dataset.py --stage evalset`）
- [ ] 在 `dev_validation` 上完成选型、在 `blind_test` 上做一次性盲测

## 六、结论纪律

1. 本轮**没有**真实人工 Gold，任何模型性能数值都不成立；
2. 合成测试池结果只证明流水线可运行（`data/independent_eval/demo/`），不是模型结论；
3. 已归档模型训练标签为英文代理标签，其在中文语境下的分数只能作参考；
4. 泄漏检查只能声明『未发现已知泄漏』，不能证明绝对无泄漏。

## 七、文件索引

- 协议：`docs/evaluation/phase4-3a-protocol.md`、`docs/evaluation/annotation-guidelines.md`
- 代码：`src/job_matching/annotation/`、`src/job_matching/independent_eval/`、`scripts/phase4_3a/`、`tests/phase4_3a/`
- 报告：`reports/phase4-3a/`（dataset-audit / leakage-check / annotation-quality / evaluation-readiness / test-results）
- 数据：`data/independent_eval/`（pool / pairs / annotation / frozen / demo）
