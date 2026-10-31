# 04 Gold 准备度（Phase4-3B / M2 / H2 门禁）

- 证据：`data/independent_eval/` 实测状态、`tests/phase4-3b`（P1/P10）、`data/independent_eval/frozen/*/freeze_blocked.json`
- 结论先行：**真实 H2 = BLOCKED，本轮不解除、不代填。**

## 1. 最新工作区实测状态（2026-10-31，非采信旧结论）

| 项 | 实测值 |
|---|---|
| 真实中文简历配对（pairs_real_v2.jsonl） | **0 行** |
| 历史配对（pairs_v1.jsonl） | 0 行 |
| 合成夹具（pairs_synthetic_v1.jsonl） | 75 行，全部 `is_synthetic=True`、`eligible_for_gold=False` |
| 双人标注模板（annotations_A/B.csv） | 各 75 行（**空白模板**，非已标注数据） |
| 分歧仲裁记录（arbitration.csv） | 0 行 |
| 人工最终标签（final_labels.csv） | **0 行** |
| 正式 Gold 冻结 | **未冻结**（evalset_v1/v2 均为 freeze_blocked.json，无 manifest.json） |
| 岗位池冻结（pool_v1/manifest.json） | 已冻结且 `verify_freeze` 复验通过（岗位池 ≠ Gold） |
| 门禁阈值 H2_MIN_REAL_PAIRS | 300 组真实配对 |

## 2. 工具链状态（复用 Phase4-3A-2，未另起协议）

`scripts/phase4_3a_2/` 的 intake / build_job_candidates / build_real_pairs / export_annotation_packets / annotation_qa / leakage_gate / freeze_gold 均在位；本轮以 `tests/phase4_3b` P1/P10 用**明确标记的合成夹具**验证整条链路：

| 验证项 | 结果 |
|---|---|
| 合成记录被判 `is_real_gold_record=False`（不可进 Gold） | PASS |
| EvalSet.require_gold() 在无 Gold/标注未完成时抛 GoldUnavailableError | PASS |
| freeze_dataset 拒绝合成配对进入 evalset（内容级硬检查） | PASS |
| freeze_dataset 拒绝 annotation_status≠complete / 缺责任记录 | PASS |
| 冻结后篡改被 verify_freeze 检出 | PASS |
| 拒绝覆盖已冻结产物、拒绝同 dataset_version 重复冻结 | PASS |
| 标注信息（PII）脱敏与导出白名单拦截 | PASS |

## 3. H2 阻断原因（逐条）

1. 无合法授权的真实中文简历（真实配对 0，远低于 300 组门禁）。
2. 无双人独立标注记录（模板存在但未填写）。
3. 无仲裁记录、无 final_labels.csv 内容 → freeze 在 `final_labels` 文件缺失处直接拒绝（evalset_v1 阻断原因原文记录于 freeze_blocked.json）。
4. 岗位池虽有约 150 条准入中文 JD（pool_v1/v2），但历史审计指出其与学历训练语料存在重合，**不得直接宣称为 strict-unseen 测试集**。
5. 授权、独立性（两位真实标注员）、完整性、质量与隔离五项准入条件均未满足数量之外的部分。

## 4. 人工所需完成事项（工具已备好，等人操作）

1. 取得书面授权的真实中文简历来源（授权依据留档；原文不入 Git）。
2. 通过 `intake_resumes.py` 导入并过 PII 脱敏。
3. `build_job_candidates.py` / `build_real_pairs.py` 生成配对，`leakage_gate.py` 过泄漏门禁（含近重复隔离）。
4. `export_annotation_packets.py` 导出盲评包 → **两位相互独立**标注员在不看模型分数的条件下标注（允许 unjudgeable）。
5. `annotation_qa.py` 核验一致性（Cohen's Kappa），分歧经仲裁流程记录。
6. 满足 ≥300 组且授权/独立性/完整性/质量/隔离全部通过后，`freeze_gold.py` 冻结并生成 manifest。

## 5. 边界声明

- 合成夹具只用于工具链测试与方法开发，**不得**进入 Gold、**不得**支撑正式性能结论。
- 模型输出不代替人工标注；不得由代理标签自动制造「真实 Gold」。
- 以上任一条件未满足，H2 保持 BLOCKED，报告中所有基于合成夹具的指标均带 `gold_status: BLOCKED` 标记。
