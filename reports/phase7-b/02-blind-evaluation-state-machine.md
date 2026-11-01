# Phase7-B / B2：预注册协议状态机与合法盲测解锁

- 时间：2026-11-01（UTC+8）
- 实现：`scripts/phase7/blind_eval_state_machine.py`
- 测试：`tests/phase7/test_blind_eval_state_machine.py`（12 项，全绿）
- 纪律：**未修改** `configs/phase7-preregistered-protocol-v1.json`（预注册锁定，协议级调整须走 amendment 并保留原文件与哈希）；本轮只扩展执行器状态管理，未变更论文评价主指标。

## 1. 状态机

```text
PREREGISTERED → DATA_READY → GOLD_FROZEN → DEV_EVALUATED
    → MODEL_LOCKED → BLIND_UNLOCKED → BLIND_EVALUATED
    → FINAL_ACCEPTED / FINAL_NOT_MET
```

- 不可跳步：每次迁移校验当前状态，`ILLEGAL_TRANSITION` 拒绝；
- 终态不可再迁移；
- 所有迁移记录写入追加式 JSONL 状态日志。

## 2. 可验证迁移设计（非「只检查字段存在」）

### 2.1 哈希链

每条记录含 `seq` / `prev_hash` / `record_hash`（canonical-JSON sha256 链）。
`verify_chain()` 逐条重算：记录被改写、删除、插入 → `CHAIN_TAMPERED`。
已验证：篡改第 2 条记录的证据字段后链校验失败（`test_chain_tamper_detected`）。

### 2.2 证据锚定（伪造 MODEL_LOCKED 无法解锁）

| 锚点 | 校验 |
|---|---|
| 预注册协议 | `protocol_sha256` 必须等于 `configs/phase7-preregistered-protocol-v1.json` **磁盘真实哈希**，并与 `.sha256` 侧车对账 |
| 冻结 Gold | `dataset_hash` 必须等于 GOLD_FROZEN 记录登记的 Gold 清单哈希，且解锁时**重新计算**清单文件哈希（捕捉冻结后漂移） |
| 模型清单 | `selected_model_id` / `model_version` 必须与模型清单文件内部字段一致，清单文件哈希登记并在解锁时复核 |

`MODEL_LOCKED` 必填字段：`selected_model_id / model_version / scoring_config_version /
feature_version / data_version / hyperparameters / selection_reason /
selection_timestamp / protocol_sha256`。

负向证据：`test_forged_lock_record_rejected` 中，攻击者绕过 `lock_model` 手工拼接
一条「字段齐全 + record_hash 自洽」的 MODEL_LOCKED 记录，链校验通过（哈希链本身
不背书内容），但解锁时被 `PROTOCOL_HASH_MISMATCH` 拒绝——**复制伪造 JSON 不能解锁**。

### 2.3 解锁记录

`BLIND_UNLOCKED` 登记：`unlock_id / protocol_hash / model_lock_hash（= 锁定记录
record_hash）/ dataset_hash / unlock_timestamp / evaluator_id / evaluation_run_id`。

### 2.4 盲测纪律

- 解锁前输出盲测指标 → `PREMATURE_BLIND_OUTPUT` / `ILLEGAL_TRANSITION` 拒绝；
- 重复解锁 → `BLIND_ALREADY_UNLOCKED`；重复盲测 → `BLIND_ALREADY_EVALUATED`；
- `evaluation_run_id` 与解锁登记不符 → `EVAL_RUN_MISMATCH`；
- 合法完整状态只允许**一次**正式盲测（`test_full_legal_flow_single_blind`）。

### 2.5 BLOCKED 状态记录口径

`is_blocked_marker()` 与 `verify_preregistration._is_blocked_marker` 一致：
`not_an_experiment_result=true` 且 `status ∈ {BLOCKED, NOT_RUN}` 且无 `results`
才是阻断记录；含真实 `results` 的文件不豁免；BLOCKED 记录不得作为 DEV_EVALUATED 证据。

## 3. 测试矩阵（隔离合成夹具，synthetic_drill=true）

| 要求场景 | 测试 | 结果 |
|---|---|---|
| 未冻结 Gold → 拒绝解锁 | `test_unlock_rejected_without_gold_frozen` | PASS |
| 无模型锁定 → 拒绝解锁 | `test_unlock_rejected_without_model_lock` | PASS |
| 模型版本不符 → 拒绝 | `test_model_version_mismatch_rejected` | PASS |
| 数据哈希不符 → 拒绝 | `test_dataset_hash_mismatch_rejected` | PASS |
| 预注册哈希不符 → 拒绝 | `test_protocol_hash_mismatch_rejected`（字段伪造 + 文件篡改双场景） | PASS |
| 提前输出盲测指标 → 拒绝 | `test_premature_blind_metrics_rejected` | PASS |
| 重复盲测 → 拒绝 | `test_duplicate_blind_rejected`（含重复解锁 / run_id 不符） | PASS |
| 合法完整状态 → 允许一次盲测 | `test_full_legal_flow_single_blind` | PASS |
| BLOCKED 状态文件 → 不误判 | `test_blocked_marker_not_misread` | PASS |
| 真实 Gold 缺失 → 不伪造解锁 | `test_real_gold_missing_no_fake_unlock` | PASS |
| 链篡改检测 | `test_chain_tamper_detected` | PASS |
| 伪造 MODEL_LOCKED → 拒绝 | `test_forged_lock_record_rejected` | PASS |

套件汇总（含 B1/B2 全部）：`PASS=64 FAIL=0 ERROR=0 SKIP=0`，
远端 `phase7-gates` 对应执行见 01 报告（B2 合入后由后续 push 重新验证）。

## 4. 演练 ≠ 真实

所有状态迁移演练均在 tempfile 合成夹具进行并标记 `synthetic_drill=true`，
**不登记为真实 H2 成功**。真实解锁必须由真实人类评估者（evaluator_id 为真人）
在真实 Gold 冻结后执行；Agent 不得代签、代评、伪造解锁记录。

## 5. 残余风险（如实声明）

本机制无数字签名：防护锚点是 Git 提交的协议哈希与冻结数据哈希。若攻击者可
同时篡改全部文件与整条链，需依赖 Git 历史审计与 `.sha256` 侧车复核发现。
建议后续在真实盲测前引入离线签名或公证时间戳（需人工决策，本轮不执行）。
