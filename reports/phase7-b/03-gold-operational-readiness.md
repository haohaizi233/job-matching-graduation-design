# Phase7-B / B3：真实 Gold 数据采集准备与人工依赖闭环

- 时间：2026-11-01（UTC+8）
- 真实执行的状态审计：`py -3.13 scripts/phase7/audit_real_data_status.py`
- 人工操作包：`docs/evaluation/phase7b-manual-ops/`（9 份操作文档）
- 纪律：真实数据收集、签署、标注必须由真人完成，**Agent 不代签、不代标、不伪造时间**。

## 1. 当前真实状态（本轮执行结果，非旧报告）

```text
[BLOCKED] H2=blocked file_exists=1 consent=0 intake=False eligible=0 real_pairs=0
  - 有效真实简历缺失 30 份（协议下限 30）
  - 真实人岗配对缺失 300 对（协议下限 300）
  - 真实标注员缺失 2 人（协议要求 ≥2）
  - 授权记录缺失（当前无任何 consent 记录文件）
```

| 指标 | 值 | 口径 |
|---|---|---|
| 有效授权（consent_verified） | **0** | 本人签署 + 哈希登记 |
| 已接受简历（intake_accepted） | **0** | 合法导入 + 哈希登记 |
| 可入 Gold（eligible_for_gold） | **0** | 过批次验收清单 |
| 真实配对（real_pairs） | **0** | 简历×岗位 8/份（Scenario B） |
| 双人标注覆盖率 / 分歧 / 待仲裁 | **0 / 0 / 0** | — |
| 查询组有效数量 | **0** | ≥2 可判候选 |
| Gold 状态 | **未冻结** | H2 **BLOCKED** |
| 业务上传文件 | 1（`file_exists=1`） | **≠ 授权研究简历**，`consent_verified=0`，不得导入 Gold |

## 2. 只读状态报告（可复用命令）

```powershell
py -3.13 scripts/phase7/audit_real_data_status.py            # 打印聚合状态
py -3.13 scripts/phase7/audit_real_data_status.py --write-report  # 另写 JSON 报告
```

（CLI 以脚本真实 argparse 为准：仅 `--write-report` 一个可选参数。）

报告**只显示**：有效授权数 / 已接受简历数 / 配对数 / 双人标注覆盖率 / 分歧数 /
待仲裁数 / 查询组有效数量 / Gold 状态。**不显示**简历正文、姓名、联系方式、
授权凭据（脚本内已做 PII 屏蔽；见 `scripts/phase7/audit_real_data_status.py`）。

## 3. Scenario B 规划与安全余量（规划目标 ≠ 已采集数据）

| 规划项 | Scenario B |
|---|---|
| 真实简历 | 70 份 |
| 每份简历岗位 | 8 |
| 真实配对 | 560 |
| dev_validation 查询组 | 49 |
| blind_test 查询组 | 21 |
| 稳定性门槛 | 20 组（`MIN_GROUPS_FOR_STABILITY`） |

**余量风险（如实登记）**：blind 21 组仅略高于 20 组门槛；一旦出现无效简历组、
重复隔离、`unjudgeable` 标签或撤回（07 流程），最终有效盲测组**可能跌破门槛**。

**招募安全余量建议**（写入 `08-daily-progress-template.md` 执行）：

- 招募目标提高至 **80–85 份**（盲测组期望 24–25，留 4–5 组缓冲）；
- 以**真实有效查询组数**判断是否满足 G4，不以采集份数判断；
- 严禁为凑数机械复制简历/岗位；重复组合一律隔离登记并剔除。

## 4. 人工操作包（本轮交付）

| 文件 | 内容 |
|---|---|
| `01-recruitment.md` | 招募说明（用途/风险/权利如实告知，禁止虚假承诺） |
| `02-informed-consent.md` | 知情同意步骤（本人签署，禁止代签/补签/自动勾选） |
| `03-data-intake-checklist.md` | 导入清单（哈希登记、命名去 PII、配对构建） |
| `04/05-annotator-*.md` | A/B 独立标注手册（隔离、不看模型输出、0/1/2 口径） |
| `06-arbiter-manual.md` | 仲裁手册（必须写理由、抽查一致项、不改原始标注） |
| `07-withdrawal-and-deletion.md` | 撤回与删除（T+3 完成、两人核对、Gold 影响评估） |
| `08-daily-progress-template.md` | 每日进度模板（只登记计数，与状态脚本对账） |
| `09-batch-acceptance-checklist.md` | 批次验收（合法性/质量/标注/对账四段，双签） |

工具复用（不重复开发）：`scripts/phase4_3a_2/`、`audit_real_data_status.py`、
`sample_size_planning.py`、`annotation_drill.py`、
`docs/evaluation/phase7-data-collection-operations.md`。

## 5. 人工依赖（等待真人，Agent 无法推进）

1. 简历提供者招募与知情同意签署（≥30，建议 80–85）；
2. 标注员 A、标注员 B（≥2 人，互相隔离）；
3. 仲裁员（1 人，不得由 A/B 兼任）；
4. 批次验收双签（组织者 + 仲裁员）；
5. 同意书/授权文件保管（`data/private/consent/evidence/`，不入库）。

## 6. 结论

- 数据采集**准备**已闭环：状态可查、流程可执行、验收可对账；
- 真实数据**未到位**（consent=0 / real_pairs=0），**H2 维持 BLOCKED**；
- 在 Gold 冻结并通过批次验收前，任何「匹配效果」结论均不得输出
  （状态机 `blind_eval_state_machine.py` 强制，见 02 报告）。
