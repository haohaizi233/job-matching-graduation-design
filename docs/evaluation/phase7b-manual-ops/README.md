# Phase7-B 人工操作包 · 使用说明

- 适用阶段：Phase7-B / B3（真实 Gold 数据采集准备与人工依赖闭环）
- 配套文档：`docs/evaluation/phase7-data-collection-operations.md`（既有操作流程）、
  `reports/phase7-b/03-gold-operational-readiness.md`（状态与规划）
- **总纪律（不可违反）**：
  1. 真实简历提供者、标注员 A/B、仲裁员必须是**真实人类**；
     AI/Agent 不得假冒任何参与者，不得代签知情同意，不得伪造签署时间；
  2. 未经本人明确授权的真实简历**不得**导入研究流程；
  3. 所有操作只在 `data/private/`（不入库、不入 CI）进行；
  4. 状态上报只显示聚合计数，不显示简历正文、姓名、联系方式、授权凭据；
  5. 任何批次未通过验收清单（`09-batch-acceptance-checklist.md`）不得进入 Gold。

## 文件清单

| 文件 | 用途 | 操作者 |
|---|---|---|
| `01-recruitment.md` | 简历提供者招募说明 | 组织者（真人） |
| `02-informed-consent.md` | 知情同意操作步骤 | 组织者 + 提供者（真人） |
| `03-data-intake-checklist.md` | 数据导入清单 | 数据管理员（真人） |
| `04-annotator-a-manual.md` | 标注员 A 独立操作手册 | 标注员 A（真人） |
| `05-annotator-b-manual.md` | 标注员 B 独立操作手册 | 标注员 B（真人） |
| `06-arbiter-manual.md` | 仲裁员操作手册 | 仲裁员（真人） |
| `07-withdrawal-and-deletion.md` | 数据撤回与删除流程 | 数据管理员（真人） |
| `08-daily-progress-template.md` | 每日进度统计模板 | 组织者 |
| `09-batch-acceptance-checklist.md` | 批次验收清单 | 组织者 + 仲裁员 |

演练工具（合成夹具）：`scripts/phase7/annotation_drill.py` 可先行演练工具链，
但演练结果**不计入**真实标注覆盖率。
