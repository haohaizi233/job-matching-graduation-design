# 03 · 数据导入清单

操作者：数据管理员（真人）。每导入一个批次填写一份。

## 前置条件（缺一不可）

- [ ] 对应提供者已完成 `02-informed-consent.md` 签署（consent-log 有记录）；
- [ ] 简历文件已按编号重命名（`R-###.pdf/docx/md`），文件名**不含姓名**；
- [ ] 简历正文已由提供者确认可提交（排除身份证号等无关敏感信息）；
- [ ] 导入目标目录为 `data/private/resumes/`（不入库）。

## 导入步骤

1. 记录批次号（`BATCH-YYYYMMDD-##`）与操作者姓名、时间；
2. 将文件移入 `data/private/resumes/BATCH-###/`；
3. 逐个计算文件 sha256，登记到 `data/private/intake/intake-log.jsonl`：
   `batch_id / resume_id / file_sha256 / bytes / consent_log_ref / imported_at / imported_by`；
4. 运行 `py -3.13 scripts/phase7/audit_real_data_status.py` 核对
   `intake_accepted` 计数；
5. 勾选 `09-batch-acceptance-checklist.md` 对应项。

## 配对构建（岗位侧）

- 每份简历配 **8 个真实岗位**（Scenario B）：岗位来自已冻结岗位池
  （`data/independent_eval/pool/`，岗位许可按其 manifest 登记）；
- 禁止机械复制简历或岗位凑数；重复配对须在清单中显式登记并隔离；
- 配对表存 `data/private/pairs/BATCH-###.jsonl`（resume_id / job_id / 构建人 / 时间）。

## 禁止事项

- 导入未签署同意的简历；
- 把 `data/private/` 内容复制进仓库目录或上传 CI；
- 修改已登记哈希的原始文件（撤回/更正走 `07-withdrawal-and-deletion.md`）。
