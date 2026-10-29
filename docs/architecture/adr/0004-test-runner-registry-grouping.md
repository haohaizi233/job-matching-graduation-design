# ADR-004：测试运行器以注册表分组（与类名解耦）

- 状态：已采纳（Phase5-1A）
- 日期：2026-10-29

## 背景

`tests/phase5_1r/run_all.py` 原先用**测试类名前缀**推断分组：
`test_r5_metrics_input.py` 的类名为 `R9*`、`test_r6_e2e_chains.py` 的类名为
`ChainB*/ChainC*`，于是：

- 正式分组只汇总 R1–R4（报告遗漏 R5/R6）；
- `run_all.py R5` 会按类名过滤到 0 项测试，却仍返回成功（假 PASS）；
- 部分组运行会覆盖正式全量报告。

## 决策

1. **分组唯一来源** = `TEST_MODULES` 注册表（按"用例从哪个模块加载"归属分组），
   与类名无关；加载时登记 `test.id() -> group`；
2. **0 测试 = 运行器错误**：收集/执行为 0 项一律返回非零退出码（2），
   禁止"无测试但 PASS"；
3. **未知分组拒绝**：退出码 2 + 可用分组列表；
4. **报告隔离**：部分组运行写 `test-results-<GROUP>.json`，仅全量运行更新
   `test-results.json` / `positive-flow-validation.json`；
5. **聚合一致性断言**：`sum(groups) == totals`、全部记录分组合法、
   无空跑，断言失败整体判定失败；
6. 报告记录 commit SHA、Python 版本、依赖版本、时间戳与逐项稳定 test_id。

## 后果

- 正面：R5/R6 归属正确（20/23 项），全量 151 项准确分到 R1–R6；
  报告与执行结果一致；部分运行不会污染正式报告。
- 负面：新增测试类时必须同步注册到 `TEST_MODULES`，否则收集报错
  （这是刻意的显式化成本）。
