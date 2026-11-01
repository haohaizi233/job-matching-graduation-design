# 05 · 标注员 B 独立操作手册

操作者：标注员 B（**真实人类**）。核心纪律：与标注员 A **完全对称且互相隔离**。

## 前置

- [ ] 已阅读 `configs/phase7-preregistered-protocol-v1.json` 标注口径
      （0/1/2 三级；NDCG@10 主指标；不可判定按协议口径处理）；
- [ ] 已完成 `scripts/phase7/annotation_drill.py` 合成演练；
- [ ] 独立判断承诺：不接触标注员 A 的任何中间结果。

## 标注流程

与 `04-annotator-a-manual.md` **相同步骤**，任务与结果目录改为 B：

- 任务：`data/private/annotation/tasks/B/BATCH-###.jsonl`
- 结果：`data/private/annotation/results/B/BATCH-###.jsonl`
- 字段：`pair_id / label / reason? / annotated_at / annotator_id`

任务包对 A/B 随机化呈现顺序（由 `annotation_drill.py` 的任务拆分逻辑保证），
避免顺序效应；B 不得按 A 的顺序「对齐」标注。

## 分歧登记（不由 A/B 自行协商）

- 双人标注完成后由脚本比对产生分歧清单
  （`data/private/annotation/disagreements/BATCH-###.jsonl`）；
- A/B **不得**私下统一意见；分歧一律进入 `06-arbiter-manual.md` 仲裁。

## 禁止事项

同 04 手册：不交流个案、不看模型输出、不代标、不记录 PII。
