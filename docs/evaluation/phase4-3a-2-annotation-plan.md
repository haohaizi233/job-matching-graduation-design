# Phase4-3A-2 双人盲标注与 Gold 冻结执行计划

> 配套：[`annotation-guidelines.md`](annotation-guidelines.md)（标注操作细则，唯一填写依据）、
> [`phase4-3a-protocol.md`](phase4-3a-protocol.md)（评估协议）、
> [`phase4-3a-2-data-collection.md`](phase4-3a-2-data-collection.md)（数据收集）。
> 本计划说明标注分配、盲标保护、一致性、仲裁与 Gold 冻结的执行流程与命令。

## 一、标注对象与规模

- 标注单位：`(去标识化简历, 岗位 JD)` 配对（`pair_id` 稳定、内容哈希派生）；
- 规模目标：300–600 个真实配对（每份简历 10–12 条），覆盖六类抽样多样性
  （专业方向明显相关 / 技能高度相似 / 技能部分相似 / 技术方向相近但职责不同 /
  存在重要资格差异 / 明显不相关）；
- 抽样难度层只是**分层元数据**，不是标签；候选配对不带任何相关性判断
  （`label_status=unlabeled`），人工确认前不得视为 0/1/2 任何值。

## 二、标注分配与盲标保护

每个真实配对由**两名人工标注员**独立评估（`annotator_A` / `annotator_B`，匿名工号）。

标注员**看到**：

1. 去标识化简历（真实姓名/联系方式/身份证/住址已在导入时掩码为 `***`）；
2. 岗位 JD 与结构化辅助字段（必备/加分技能、学历与经验要求等）；
3. 统一评分规则（annotation-guidelines.md）；
4. 可引用的匹配证据（`evidence` 栏引用原文片段，个人信息用 `***`）。

标注员**看不到**（工程门禁强制）：

1. 模型预测结果与旧评分（`final_score` / `label_strength` / `candidate_rank` /
   `semantic_score` 等，`schema.MODEL_OUTPUT_COLUMNS` 全量拒收）；
2. 抽样难度层与预期匹配类别（`difficulty_tier` / `pair_provenance` / `difficulty_factors`）；
3. 切分与 Gold 资格（`split` / `eligible_for_gold` / `is_synthetic`）；
4. 另一位标注员的答案（各自独立标注文件，互不可见）。

实现：`blind_guard.build_annotation_view`（白名单视图）+
`blind_guard.check_packet_columns`（列名门禁）+ `pii.check_export`（PII 残留检查），
违规直接报错拒绝导出，不静默降级。

**独立性门禁**（`blind_guard.check_annotator_independence`）：

- 两份标注不得使用同一 `annotator_id`（一人冒充两人直接拒收）；
- 全部共同样本记录逐字镜像（标签/置信度/理由/证据/时间戳全同）视为同一人重复提交，
  不计为独立双标注。

## 三、标注等级（与协议一致）

| 值 | 含义 |
|---|---|
| `0` | 明显不匹配 |
| `1` | 部分匹配 |
| `2` | 高度匹配 |
| `unjudgeable` | 证据不足或信息矛盾，无法可靠判断（**独立状态，不是 0**） |

每条记录必须保留：`reason`（依据编号+一句话）、`evidence`（原文片段）、
`annotation_timestamp`、`protocol_version`（`phase4-3a-annotation-v1`）、标注员匿名 ID。
判定依据顺序：1 必备技能 → 2 职责-经历关联 → 3 资格（学历/届别）→ 4 经验年限与方向 →
5 核心技术方向一致性；硬性条件不满足时 `relevance` 上限为 1。

## 四、一致性评估

`annotation_qa.py` 自动计算并写入 `reports/phase4-3a-2/agreement-results.json`：

- 原始一致率、Cohen's Kappa、Weighted Cohen's Kappa（线性/二次）；
- 各岗位类别一致率、分歧比例、仲裁数量、`unjudgeable` 单独统计；
- 可判定样本 < 5 或单人标注时输出 `not_computable` + 原因，**不填充任何数值**。

质量目标：Weighted Kappa ≥ 0.60 为**初步目标**，不是通过线；严禁为追求阈值修改标签。
一致性不足时的处理顺序：

1. 分析是指南歧义、题目本身不可判断，还是标注员理解差异；
2. 修订 `annotation-guidelines.md` 并**升版本号**保存历史版本；
3. 按新指南**重新独立标注**受影响样本；不一致结果全部保留、如实公开。

## 五、仲裁

- 只仲裁两人 `relevance` 不一致的样本（含 `unjudgeable` vs 0/1/2）；
- 仲裁表保留：原始两份标签、双方理由与证据、仲裁结论、仲裁依据、仲裁时间、
  仲裁协议版本（`arbitration.export_arbitration_sheet` 导出即含 `_relevance_a/_reason_a` 等列）；
- 仲裁员独立看原文，可参考双方理由，**不得取平均**；
- `unjudgeable` 保护：双方均判 `unjudgeable` 且无仲裁时，最终标签必须是 `unjudgeable`；
  任何强行归入数值标签的记录会被 `importer.check_unjudgeable_not_forced` 标记并阻断冻结；
- 原始标注**永久保留**，仲裁不得覆盖（`arbitration.build_final_labels` 生成最终标签时
  携带 `annotator_a_relevance` / `annotator_b_relevance` 两列）。

## 六、执行命令（按顺序）

```powershell
# 1) 导出双人盲标注材料（去标识化、白名单、PII 检查）
python scripts/phase4_3a_2/export_annotation_packets.py

# 2) 标注员独立填写 data/private/annotations_raw/annotations_annotator_{A,B}.csv
#    （字段与填写要求见 annotation-guidelines.md；互不可见对方文件）

# 3) 导入校验 + 独立性 + 一致性 + 仲裁 + 最终标签
python scripts/phase4_3a_2/annotation_qa.py

# 4) 有分歧时：仲裁员填 data/private/annotations_raw/arbitration_filled.csv
#    （待仲裁表由步骤 3 自动生成，含双方原始标签与理由），再重跑步骤 3

# 5) 泄漏与重复风险复核
python scripts/phase4_3a_2/leakage_gate.py

# 6) Gold 冻结（简历组级 70/30 + SHA-256 复验）
python scripts/phase4_3a_2/freeze_gold.py
python scripts/phase4_3a_2/freeze_gold.py verify `
    --manifest data/independent_eval/frozen/evalset_v2/manifest.json
```

## 七、切分与盲测保护（冻结协议）

- 按 **resume_id 组级**划分：`dev_validation` 70% / `blind_test` 30%（seed=20261213），
  同一简历的配对绝不跨集合（`gold_gate.check_split_isolation` 强制）；
- 岗位盲测不合格（历史 Gold 交叉/近似重复）的配对不进 blind_test；
  若其简历被分入 blind_test，该配对整体排除（`quarantined_out`，记录原因）；
- 本次切分**只按简历隔离**，不得称为岗位冷启动或双冷启动；如需岗位冷启动/双冷启动，
  必须按 `job_id` 严格隔离另行建立协议（`freeze_gold.py --job-isolated` 预留）；
- 盲测保护：在模型、特征、参数冻结前，不得用 blind_test 调参/选算法/反复查看指标/
  替换不利样本/删除低分模型的评估记录；最终盲测只执行一次
  （`gold_gate.check_blind_status` 在冻结复验完成前拒绝任何「盲测通过」标记）。

## 八、当前状态（如实登记）

- 真实中文简历 **0** 份 → 标注对象 0 组 → 双人标注 **未开始**；
- 标注材料导出、导入校验、一致性、仲裁、冻结链路已实现并有 18 项新增自动化测试覆盖；
- 在取得经授权真实简历并完成双人独立标注 + 仲裁前，H2（Gold 正式冻结）保持 **BLOCKED**；
  严禁用生成式 AI 生成简历、标签或仲裁结论充数。
