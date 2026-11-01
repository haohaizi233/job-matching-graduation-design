# 07 · 数据撤回与删除操作流程

操作者：数据管理员（真人）。提供者**随时**可撤回，无需理由。

## 触发

提供者口头/书面提出撤回（记录时间、渠道、编号）。

## 流程（T+0 当日启动，T+3 日内完成）

1. **登记撤回请求**：`data/private/consent/withdrawal-log.jsonl`
   （`resume_id / requested_at / channel / handled_by`）；
2. **停止使用**：立即把该简历对应配对标记 `withdrawn`，后续标注/评测任务剔除；
   已进入标注任务但未完成的，任务作废重发；
3. **删除数据**（逐项执行并登记）：
   - [ ] `data/private/resumes/` 对应文件删除；
   - [ ] `data/private/pairs/` 对应配对删除或匿名化剔除；
   - [ ] `data/private/annotation/` 对应标注记录删除；
   - [ ] 同意书扫描件删除（consent-log 保留「已撤回+删除时间」的**元记录**，
         不保留内容）；
4. **冻结数据影响评估**：若该简历已进入 Gold 冻结清单：
   - Gold 需**重新冻结**并重新走状态机（`GOLD_FROZEN` 之后的记录不得复用）；
   - 在批次报告中登记「撤回导致 Gold 版本变更」；
5. **哈希复核**：运行 `py -3.13 scripts/phase7/audit_real_data_status.py`
   确认 `intake_accepted` / `eligible_for_gold` 计数下降；
6. **完成登记**：`withdrawal-log.jsonl` 补记 `deleted_at / deleted_by /
   verified_by`（两人核对：执行者 + 复核者）。

## 禁止事项

- 「先用完这批再删」；删除不登记；登记不删除；
- 撤回后继续在论文/答辩中引用可识别片段（匿名聚合统计可在论文说明口径后保留，
  须在撤回说明中告知提供者）。
