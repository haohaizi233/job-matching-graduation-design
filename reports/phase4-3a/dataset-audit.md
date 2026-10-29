# Phase4-3A 数据可用性与工程审计

> 生成时间：2026-10-29T10:22:08 ｜ 机器可读版本：`reports/phase4-3a/dataset-audit.json`

## 一、数据可用性统计（任务书 5.1）

| 统计项 | 数量 | 状态/说明 |
|---|---|---|
| 中文简历 | 0 | 本地无真实中文简历；英文简历不得充当中国大学生就业画像数据 |
| 英文简历 | 9544 | 仅用于流程验证，禁止进入中文人工真值 |
| 中文岗位（唯一 job_id） | 243124 | 含 JD 正文行数 286902 |
| 英文岗位 | 1167 | 来自 Indeed，语言 en |
| 简历-岗位合法关联（英文） | 122560 | matches.csv 全部为正样本代理标签 |
| 简历-岗位合法关联（中文） | 0 | 依赖真实中文简历导入 |
| 含完整 JD 文本的记录 | 288069 |  |
| 只有标签/字段、无文本证据 | 373941 | matches.csv 评分记录 + all_df 结构化字段 |
| 缺少来源或使用许可 | 384652 | {"other/all_df (license UNKNOWN)": 251381, "job-resume-matching (license unverified)": 133271} |

## 二、数据缺口（G2 阻断项）

- **经授权脱敏的真实中文简历（目标 30–50 份）**：当前 0 ｜ 影响：G2 阻断：无法建立真实中文简历-岗位人工评估配对
- **真实中文简历-岗位人工标注（目标 300–600 对）**：当前 0 ｜ 影响：G2 阻断：blind_evaluation_status=blocked
- **other/all_df 来源与授权说明**：当前 UNKNOWN ｜ 影响：补齐前不得进入正式评估集

## 三、能力复用审计（任务书第三节）

### 可直接复用

- **文本规范化与哈希**（src/job_matching/core.py (norm_text/sha256_file/short_hash)）：pair content_hash、去重、冻结清单
- **排序指标 NDCG/MRR/Recall + 稳定 tie-breaking**（src/job_matching/metrics_ranking.py (evaluate_ranking)）：独立评估指标主体（Precision@K 为本阶段补充）
- **查询级配对 Bootstrap**（src/job_matching/evaluation/statistical_tests.py (bootstrap_diff)）：模型差值 95% CI，共享重采样组
- **模型加载与前向推理**（src/job_matching/inference/predictor.py (MatchPredictor)）：Ridge/GBDT/MLP/RankNet 在真实 pair 上打分
- **零训练基线打分口径**（src/job_matching/baseline_ranking.py / evaluation/statistical_tests.local_baseline_scores）：对照第三阶段基线口径
- **学历要求规范化**（src/job_matching/preprocess_education.py (normalize_label/parse_user_segments)）：岗位学历要求字段解析
- **隐私约束与日志规范**（src/job_matching/core.py / policy.py）：导出脱敏检查、特征黑名单
- **测试与报告机制**（tests/*/run_all.py (stdlib unittest + JSON 报告)）：tests/phase4_3a 沿用同一风格

### 本阶段新建

- **人工标注数据模式与校验**：src/job_matching/annotation/schema.py, importer.py
- **PII 检测/脱敏/导出检查**：src/job_matching/annotation/pii.py
- **三级重复检测（完全/规范化/近似）**：src/job_matching/annotation/dedup.py
- **候选池构建与分层采样**：src/job_matching/annotation/pool.py
- **双人标注一致性（Kappa/Weighted Kappa）**：src/job_matching/annotation/agreement.py
- **仲裁与最终标签留痕**：src/job_matching/annotation/arbitration.py
- **数据集冻结与 SHA-256 复验**：src/job_matching/annotation/freeze.py
- **人工 Gold 评估口径与护栏**：src/job_matching/independent_eval/
- **评估集泄漏检查**：scripts/phase4_3a/leakage_check.py

### 不复用的原因

- `metrics_ranking.precision`：原实现不含 Precision@K，本阶段在 independent_eval/metrics.py 补充并复用其余指标
- `existing_annotation_code`：仓库内不存在人工标注/独立评估相关代码（已全仓库检索确认）

## 四、泄漏检查摘要

| 检查项 | 结果 |
|---|---|
| 池内配对完全重复 | 0 |
| 池内配对近似重复 | 9 |
| 同一简历不同 ID | 0 |
| 同一岗位不同 ID | 0 |
| 与原历史 Gold 交叉（job_id） | 5 |
| 与学历训练语料文本重合（哈希） | 250 |
| 与学历训练语料近似重复 | 255 |
| 个人信息字段残留 | 0 |

预训练污染声明：预训练语料来源不可知，无法完全排除预训练污染；本报告只能声明『未发现已知泄漏』，不能声称绝对无泄漏
