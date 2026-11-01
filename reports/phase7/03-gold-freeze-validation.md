# P7-3 Gold 冻结验证

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 状态：**`BLOCKED` —— 不具备执行条件，本轮不冻结**
- 门禁状态：`status=BLOCKED` / `h2_status=blocked` / `freeze_written=false` / `freeze_verified=false`

---

## 一、为什么本轮不能冻结

`scripts/phase4_3a_2/freeze_gold.py` 的冻结前置条件（`gold_gate.evaluate_precheck`）
在当前工作区**全部不满足**：

| 前置条件 | 要求 | 实测 | 结果 |
|---|---|---|---|
| `real_resumes` | ≥ 30 | **0** | **FAIL** |
| `real_pairs` | ≥ 300 | **0** | **FAIL** |
| `consent_complete` | 全部 granted/licensed | 0 条授权记录 | **FAIL** |
| `dual_annotation_complete` | ≥2 标注员完整覆盖 | 0 标注文件 / 0 标注员 | **FAIL** |
| `source_license_ok` | 来源许可可核 | 2 个来源 `UNKNOWN` | **FAIL** |
| `split_isolation_ok` | 组级隔离 | 无数据可切 | **FAIL** |
| `annotator_independence_ok` | 独立性通过 | 无标注可查 | NOT_RUN |
| `arbitration_status` | 分歧已仲裁 | 无分歧对象 | NOT_RUN |
| `synthetic_pairs_included` | = 0 | 0 | PASS |
| `unjudgeable_forced` | = 0 | 0 | PASS |
| `blocking_findings` | = 0 | 0 | PASS |

冻结工具本身已验证可用（`tests/phase6/test_gold_readiness.py` 合成夹具用例
`test_freeze_gold_blocks_without_real_data` / `test_freeze_hash_verification_tooling` 通过），
`scripts/phase7/annotation_drill.py` 的 `freeze_refused_without_real_data` 演练也确认：
**无合法真实数据时工具会拒绝冻结**，不会伪造 Gold。

> **纪律**：数据不足时不降低门禁、不用合成样本补足、不改写旧的 `freeze_blocked.json`。
> 本轮**不执行** `freeze_gold.py`，也**不生成**任何冻结 manifest。

---

## 二、冻结产物登记项（预留，待 G1/G2 通过后填写）

按协议第九节，冻结时必须登记：

| 登记项 | 当前值 |
|---|---|
| 数据版本 `dataset_version` | **BLOCKED** |
| 数据哈希（pairs / annotations / arbitration 逐文件 SHA-256） | **BLOCKED** |
| 标注协议版本 | `phase4-3a-annotation-v1`（已锁定） |
| 双人标注统计（覆盖数、分布、`unjudgeable` 占比） | **BLOCKED** |
| 仲裁统计（分歧数、仲裁数、未决数） | **BLOCKED** |
| 来源与授权审计（consent 通过数、来源许可） | **BLOCKED**（0 条授权 / 2 个 UNKNOWN 许可） |
| 查询组数量（dev / blind） | **BLOCKED** |
| 切分结果（组级 70/30，种子 `20261215`） | **BLOCKED** |
| 泄漏检测（组间隔离 / 重复 / 历史 Gold / 模型输出 / PII） | **BLOCKED** |
| 冻结时间 | **BLOCKED** |

---

## 三、CLI 兼容性检查（预检，未实际冻结）

| 命令 | 兼容性 | 说明 |
|---|---|---|
| `py -3.13 scripts/phase4_3a_2/freeze_gold.py` | 兼容 | argparse 签名实测：`action` 位置参数 + `--manifest/--seed/--blind-ratio/--min-real-pairs/--job-isolated/--fixture-mode` |
| `py -3.13 scripts/phase4_3a_2/freeze_gold.py verify --manifest data/independent_eval/frozen/evalset_v2/manifest.json` | 兼容 | `verify` 作为 `action` 传入；当前无 manifest，运行会显式报缺失（预期行为） |
| `py -3.13 scripts/phase4_3a_2/annotation_qa.py` | 兼容 | 当前输出 `annotation_status=pending` / `agreement_status=not_computable`（如实） |
| `py -3.13 scripts/phase4_3a_2/leakage_gate.py` | 兼容 | 当前无阻断发现（无真实配对可查） |

---

## 四、`unjudgeable` 与不可计算项处理（预置规则）

| 情形 | 处理 |
|---|---|
| 样本不足 / 单人标注 / 无重叠样本 | `status="not_computable"` + `reason`，**禁止填 0** |
| 某岗位类别样本量 < 5 | 该类别的分类别一致性指标 `not_computable` |
| 标签分布退化（期望一致率 = 1） | Cohen's Kappa `not_computable` |
| 双人同判 `unjudgeable` | 最终标签 `unjudgeable`，**不进入排序指标分母** |
| 一方 `unjudgeable` 一方数值 | 视为分歧，必须人工仲裁 |

---

## 五、结论

- **Gold 冻结：`BLOCKED`**，本轮不执行、不伪造、不降门槛；
- 工具链与门禁已就绪并有负向测试保护，解除阻断的唯一路径是补齐
  「≥30 份经授权真实中文简历 → ≥300 真实配对 → 双人独立标注 + 人工仲裁」；
- **冻结完成 ≠ 模型效果通过**：即使未来冻结成功，`blind_test` 仍须在模型与超参锁定后
  才能执行独立评价（见 `06-model-selection.md` 的锁定顺序）。
