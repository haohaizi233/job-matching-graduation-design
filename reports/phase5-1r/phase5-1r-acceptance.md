# Phase5-1R 整改验收报告（phase5-1r-acceptance.md）

- 验收日期：2026-10-29
- 验收基线提交：`0225fcb91a17feec486afb81ae4de3d0e44b342d`
- 执行命令：`python tests/phase5_1r/run_all.py`（纯 CPU、纯合成夹具、可复跑）
- 证据文件：`reports/phase5-1r/test-results.json` / `test-results.md` /
  `positive-flow-validation.json` / `artifact-integrity.json`
- 缺陷与修复明细：`defect-register.md` / `fix-summary.md`

## 1. 验收结论

**通过（工程整改维度）**：F-001–F-009 全部修复并有回归用例锁定；
二轮审计补漏（姓名 PII 脱敏缺口）已修复。R1–R6 共 **151/151 PASS**，
0 FAIL / 0 ERROR / 0 SKIP。

**本阶段不产生业务结论**：三条端到端链路使用纯合成工程夹具，
只证明软件流程可运行；真实中文简历、双人 Gold 标签与合法盲测集未到位，
**H2 维持 BLOCKED**（`positive-flow-validation.json` 中 `real_h2_status` 字段明确登记）。

## 2. 门禁状态（R1–R6）

| 门禁 | 覆盖缺陷 | 项数 | 结果 |
|---|---|---:|---|
| R1 Gold 冻结循环门禁 | F-001、F-003、F-004 | 15 | PASS |
| R2 标注独立性 / 仲裁 / 完成状态 | F-002、F-003 | 33 | PASS |
| R3 毕业届别 / 工作经验约束 | F-005、F-006 | 39 | PASS |
| R4 API 边界与安全加固 | F-007 | 21 | PASS |
| R5 独立评估输入物化 | F-009 | 20 | PASS |
| R6 端到端链路 B / 链路 C | 联动回归 | 23 | PASS |

分组由 `TEST_MODULES` 注册表确定（Phase5-1A 修订，见 `docs/architecture/adr/0004`）；
`sum(groups) == totals` 聚合一致性断言全绿；
按组运行（`run_all.py R5` = 20 项、`run_all.py R6` = 23 项）与全量运行（151 项）均验证通过；
0 项执行与未知分组返回退出码 2，不出现"无测试但 PASS"。

## 3. 三条端到端正向链路

| 链路 | 状态 | 通过/总数 |
|---|---|---|
| A 金标冻结工程链路（模拟） | PASS | 15/15 |
| B 简历→岗位推荐链路 | PASS | 8/8 |
| C 模型错误与降级链路 | PASS | 15/15 |

链路 A 的表述边界：**工程模拟 ≠ 真实 Gold 冻结通过**；
任何对外材料不得将其表述为真实 H2 结论。

## 4. 历史套件回归（A6）

| 套件 | 基线 | 本轮复跑 | 结论 |
|---|---|---|---|
| Phase4-3A | 237/237 | 237/237 PASS | 无回归 |
| Phase5-1 | 92/92 | 92/92 PASS | 无回归 |
| 数据管线 G1–G7 | 74/74 | 74/74（前轮记录） | 无回归 |
| 模型训练 | 25/25（训练环境） | 20/21（Serving 环境） | T5 因旧 checkpoint 环境不兼容**无法执行**，已登记（见下） |
| 学历训练 | 35/36 | 35/36 | 仅 `pip check` 失败（共享解释器三方包冲突，非项目依赖） |

## 5. 剩余风险与未解决事项

1. **旧模型环境不兼容（登记为"无法执行"，非业务失败）**：
   5 个 gradient_boosting checkpoint 在当前环境报
   `AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError'`
   （历史环境 py3.11.18 / sklearn 1.5.2 → 当前 3.13 / 1.8.0）。
   分类为 `env_incompatible`（`MODEL_ENV_INCOMPATIBLE`），禁止表述为"权重缺失"或"业务逻辑失败"；
   历史基线报告 `reports/model-training/model-tests.json` 保持训练环境记录不动，
   Serving 环境的复跑结果写入 `model-tests-run-*.json` 诊断报告。
   详见 `reports/phase5-1a/model-compatibility.md`。
2. **`pip check` 三方包冲突**：adalflow / f2 / grpcio-tools 等共享解释器内非项目依赖版本冲突。
3. **哈希 ≠ 防篡改**：冻结完整性检查为普通 SHA-256 自检，只能表述为"完整性自检通过"。

## 6. 隐私与数据保护抽查（A5）

- 姓名键值对 PII 已脱敏（二轮审计补漏，`domain/pii_masking.name_kv`）；
- 链路 B 验证响应与日志无 PII（`test_no_pii_in_response_or_logs`）；
- 掩码 ≠ 匿名化：全仓统一口径为"已脱敏/已掩码"，禁止声称"已匿名化"；
- Gold 阻断与冻结不可变性：R1/R2 全绿，`data/independent_eval/frozen/**` 未被本轮改动。
