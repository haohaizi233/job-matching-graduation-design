# P7-2 双人盲标注工作流演练（隔离合成夹具）

- 生成时间：2026-10-31T22:40:00+08:00
- 状态：`PASS`（14/15 通过）
- **性质**：工具链演练：合成夹具 + 机械标签（固定种子 PRNG，与模型输出无关）。演练中的 '标注员' 不是真人，本结果不计为真实人工标注，不解除 H2 阻断。
- 协议版本：`phase4-3a-annotation-v1`
- 夹具：12 个合成配对，seed=20261031

## 逐项验收（任务书 6.3）

| # | 能力 | 结果 | 说明 |
|---|---|---|---|
| 1 | 隔离工作区安全边界（负向） | `PASS` | 真实数据目录（data/private、data/independent_eval/frozen）均拒绝执行；项目根（生产工作区）与隔离临时目录允许 |
| 2 | 独立导出（盲化） | `PASS` | 两人各一份独立标注包；列白名单通过；无模型预测/难度层/split/他人答案列 |
| 3 | 标注保存 | `PASS` | 先标一半 → 中断 → 续标剩余，导入校验通过且无遗漏 |
| 4 | 断点续标 | `PASS` | 断点续标：半程中断后可继续，最终无遗漏 |
| 5 | 输入字段检查 | `PASS` | 缺列文件被拒收，错误码=['missing_columns'] |
| 6 | 非法标签拒绝 | `PASS` | 非法标签错误码=['invalid_relevance']；机器标识标注员错误码=['machine_annotator'] |
| 7 | 隐私残留扫描 | `PASS` | 干净合成文本通过=True；注入手机号/邮箱后被拦截=True |
| 8 | 标注文件导入校验 | `PASS` | A 有效 12 行 / B 有效 12 行 |
| 9 | 同人冒充两个标注员拒绝 | `PASS` | 同一 annotator_id 出现在两份标注中，检测到 ['shared_annotator_id'] |
| 10 | 镜像答案异常检测 | `PASS` | 全表镜像检出=['mirrored_annotations']；独立标注未误报=[] |
| 11 | 标注进度统计 | `PASS` | 进度统计可计算：annotation_status=blocked |
| 12 | 仲裁流程 | `PASS` | 分歧 12 组 → 最终标签 12 条，双方原始结论均保留（A=12, B=12） |
| 13 | 一致性统计（drill-only） | `COMPUTED_ON_DRILL_FIXTURE_ONLY` | 仅证明一致性统计代码可运行；数值来自合成夹具，不代表任何真实标注质量 |
| 14 | 无真实数据拒绝冻结 | `PASS` | precheck status=blocked passed=False |
| 15 | 合成数据不得进入 Gold | `PASS` | 合成配对经 is_real_gold_record 计数 = {'real_gold': 0, 'synthetic_excluded': 12, 'non_gold_excluded': 0, 'total_records': 12, 'note': '合成样本、未授权、非中文、被隔离记录一律不计入真实 Gold 数量'} |

## 结论

标注工具链在隔离合成夹具上完整可操作：导出、保存、续标、校验、独立性、隐私扫描、仲裁与进度统计全部按预期工作。

**但演练通过 ≠ 真实人工标注完成**：当前真实配对 0、标注员 0、H2 仍为 BLOCKED。解除阻断必须由两名真实人类标注员在授权真实数据上独立标注并经人类仲裁。

## 纪律声明

- 不伪造真实简历：夹具全部为合成文本并带水印声明
- 不让 AI 冒充人工标注员：标签由 PRNG 机械生成，标注员 ID 带 Drill 前缀
- 不把演练结果当作 Gold：synthetic_not_gold 负向校验保证
- 不触碰 data/private 与 data/independent_eval 真实对象
