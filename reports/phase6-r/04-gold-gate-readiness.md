# R4：Gold 门禁状态驱动改造（实测就绪审计）

- 生成时间：2026-10-31；分支 `fix/phase6-research-integration-hardening`
- 整改提交：`3e096c5`（R4 - Gold 门禁改为状态驱动审计（只读）+ 工具链测试解耦）
- 代码：`tests/phase6/test_gold_readiness.py`

## 1. 原缺陷

`test_real_data_status_still_blocked()` 硬编码断言：

```python
self.assertEqual(0, real_pairs)
self.assertEqual(0, len(annot_files))
```

这是**当前环境审计**被写成了长期不变的测试要求：真实配对从 0 增长到 100 时，
工具链单元测试会被正常的数据增长打红。测试把「环境状态」与「软件契约」耦合。

## 2. 改造：两类检查解耦

### 第一类：软件工具链稳定单元测试（合成夹具，未来真实 Gold 完成后仍须 PASS）

| 能力 | 用例 |
|---|---|
| 导出盲标注包（盲化 + 可核验） | `test_export_annotation_packets_blind_and_checked` |
| 两个标注员独立性校验 | `test_annotation_import_validation` |
| 标签合法性 / 协议版本一致性 | `test_annotation_import_validation` |
| 仲裁流程 | `test_annotation_import_validation` |
| 合成数据不能进入 Gold | `test_leakage_gate_tooling` |
| PII 脱敏 | `test_pii_detection_and_masking_available` |
| 泄漏检查 | `test_leakage_gate_tooling` |
| 冻结拒绝（无合法真实数据时拒绝冻结） | `test_freeze_gold_blocks_without_real_data` |
| 哈希篡改检测 | `test_freeze_hash_verification_tooling` |
| 进度/断点续标注 | `test_annotation_progress_and_resume_support` |

这些测试全部在 `PHASE4_3A_2_WORKSPACE` 隔离工作区执行，绝不触碰
`data/private` 与 `data/independent_eval/frozen` 的真实对象。

### 第二类：真实工作区状态审计（只读，输出状态而非断言）

`audit_gold_workspace_state(root)` 只读检查真实数据，状态由真实计数**推导**：

| 状态 | 含义 |
|---|---|
| `BLOCKED` | 尚无真实人岗配对（H2 未启动） |
| `READY_FOR_ANNOTATION` | 有真实配对，但双人完整标注未就绪 |
| `READY_FOR_FREEZE` | 真实配对齐备且 ≥2 标注员完整覆盖、分歧已仲裁 |
| `FROZEN_AND_VERIFIED` | 已冻结且哈希校验通过 |
| `INVALID` | 结构不一致（如声称 verified 却无冻结产物） |

一致性断言只校验**状态间逻辑**（如 `FROZEN_AND_VERIFIED` 必须有冻结产物、
`real_pairs==0` 必须为 `BLOCKED`），不再要求计数恒为零。真实配对增长时，
状态自动沿词表推进，工具链测试不受影响。

## 3. 当前真实工作区状态（本次实测，只读）

```json
{
  "status": "BLOCKED",
  "real_resumes": 1,
  "real_pairs": 0,
  "annotation_files": 0,
  "distinct_annotators": 0,
  "covered_pairs": 0,
  "annotations_complete": false,
  "h2_status": "blocked",
  "freeze_written": false,
  "freeze_verified": false
}
```

**H2 = BLOCKED**。真实简历 1 份、真实配对 0、双人标注 0。

## 4. 真实数据纪律（本轮未违反，持续有效）

- 不用合成简历代替真实简历；
- 不把用户反馈冒充人工 Gold（`test_feedback_loop_not_gold` 明确反馈≠Gold）；
- 不把模型预测代替标注；
- 不用单个标注员冒充两人（`distinct_annotators >= 2` 是 `READY_FOR_FREEZE` 硬条件）；
- 不伪造授权文件（consent 校验独立）；
- 配对数量达到 300 **不会**自动冻结——冻结还需要双人完整覆盖 + 仲裁 +
  哈希写入与校验（`freeze_written` / `freeze_verified` 双条件）。

## 5. 结论

Gold 门禁已从「硬编码环境断言」改为「状态驱动审计 + 工具链单元测试解耦」，
真实数据纪律保持零违反。H2 解除需要：真实中文简历授权采集 → 人岗配对 ≥300 →
双人独立标注 + 仲裁 → 冻结哈希校验，本轮**不具备**执行条件，维持 BLOCKED。
