# 06 · 仲裁员操作手册

操作者：仲裁员（**真实人类**，不得由标注员 A/B 兼任，不得由 AI 代行）。

## 职责

对 A/B 分歧配对给出**最终标签**，并保证仲裁理由可追溯。

## 仲裁流程

1. 领取分歧清单：`data/private/annotation/disagreements/BATCH-###.jsonl`；
2. 逐一查看配对（R-###, J-###）原始材料（只读）；
3. 独立给出最终标签 0/1/2（或 `unjudgeable` + 理由）；
4. **必须**写仲裁理由（≤80 字），说明采纳 A 或 B 或第三判断的依据；
5. 写入 `data/private/annotation/arbitration/BATCH-###.jsonl`：
   `pair_id / final_label / rationale / arbitrated_at / arbiter_id / label_a / label_b`；
6. 全部仲裁完成后，才允许执行 Gold 冻结流程
   （状态机 `scripts/phase7/blind_eval_state_machine.py` 的 `freeze_gold`）。

## 质量控制

- 每批次抽查 ≥10% 一致项复核（防止双人同错）；
- 仲裁理由缺失的记录视为无效，退回重做；
- 仲裁员不得修改 A/B 的原始标注文件（只读），分歧协商一律留痕。

## 禁止事项

- 查看任何模型输出/排序/分数；
- 与 A/B 就个案达成默契分工；
- 批量复制同一理由；伪造仲裁时间。
