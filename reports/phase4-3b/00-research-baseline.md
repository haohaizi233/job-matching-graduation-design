# 00 研究基线报告（Phase4-3B / B0）

- 生成时间：2026-10-31
- 工作目录：`D:\desktop\job-matching-model-research`（Git worktree，分支 `feat/phase4-3b-model-research`）
- 证据文件：`reports/phase4-3b/model-registry.json`、`model-compatibility-runs.json`、`test-results.json`

## 1. 现有模型总览

来源：`scripts/phase4_3b/build_model_registry.py` 只读扫描 `models/`（43 个运行目录，全部真实探测）。

| model_id | 任务类型 | 运行数 | checkpoint | 推理状态 | 标签来源 | 切分协议 |
|---|---|---|---|---|---|---|
| matching.ridge | 排序/回归 | 8 | 8/8 存在（SHA-256 登记） | LOADED | derived_proxy_label_final_score_chain | candidate/job/double_cold |
| matching.gradient_boosting | 排序 | 5 | 5/5 | LOADED | 同上 | 三协议 |
| matching.mlp | 排序 | 5 | 5/5 | LOADED | 同上 | 三协议 |
| matching.ranknet | 排序 | 8 | 8/8 | LOADED | 同上 | 三协议 |
| education.tfidf | 多标签分类 | 7 | 7/7 | LOADED | pseudo_online_assistant_or_human_gold | 未登记 |
| education.charcnn | 多标签分类 | 10 | 10/10 | LOADED | 同上 | 未登记 |

登记表逐条记录 model_version、checkpoint_path、checkpoint_sha256、依赖版本、指标与限制，详见 `model-registry.json`。**43/43 checkpoint 均真实存在且哈希可复核**，不存在「报告有路径、机器无模型」的情况。

## 2. 数据集与标签来源

- 匹配特征：`data/processed/matching/features_pairs.csv`（122,560 对），目标 `targets_pairs.csv` **物理分离**。
- 标签 `label_strength` / `final_score` / `candidate_rank` 全部由原系统评分公式派生（代理标签链）。
- **代理标签拟合效果 ≠ 真实求职推荐效果**。matching 系列模型的指标只能解释为「与原系统代理偏好的一致程度」。
- 独立评估数据（`data/independent_eval/`）：合成夹具 75 对（全部 `is_synthetic=True`、`eligible_for_gold=False`），真实配对 0 对，人工最终标签 0 行。

## 3. 三种切分协议（`data/splits/matching/`，pipeline phase3-v1）

| 协议 | group_key | train/val/test | 互斥检查（manifest overlap_check） |
|---|---|---|---|
| candidate_cold | candidate_id | 98,029 / 12,270 / 12,261 | pair/candidate/group_key 交集=0 |
| job_cold | job_id | 97,887 / 12,251 / 12,422 | pair/job/group_key 交集=0 |
| double_cold | candidate_id+job_id | 68,932 / 2,369 / 2,225（excluded 49,034 保留） | 双侧交集=0 |

补充审计（本轮实测）：pair 级文本哈希跨子集交集=0；实体级近似重复（不同 ID 相同画像文本）在 double_cold train/test 间为候选 8 个、岗位 2 个哈希（占测试实体 <2%），见 `05-dataset-protocol.md` 与 `split-text-overlap.json`。

## 4. 当前模型指标（历史训练产物，代理标签口径）

matching 系列在各协议上的选择指标（selection_value，来自各 run manifest）示例：GB 0.951、MLP 0.937、Ridge 0.913（candidate_cold）。指标基于代理标签，**不构成真实推荐效果结论**。本轮独立复现见 `03-baseline-reproduction.md`。

## 5. 模型兼容性（详见 02）

14 个代表性 run 在当前环境全部 LOADED；12 个 matching run 重推理与历史预测**逐位一致**（max_abs_diff=0.0）；education.tfidf 数值差 ≤2.9e-8，education.charcnn ≤1.3e-4（torch 非确定性），决策层差异未登记（NOT_RUN）。

## 6. 数据泄漏风险清单

1. matching 标签由 final_score 评分链派生 → 语义/技能类特征与标签存在构造性耦合（循环性风险）。
2. 合成夹具的 `difficulty_tier` 与技能类基线共享构造信号（`06-retrieval-benchmark.json` 中已登记 circularity_warning）。
3. 岗位池与学历训练语料存在重合（历史报告已指出），不得宣称 strict-unseen。
4. double_cold 存在少量实体级文本近似重复（上表），新 Gold 需按 `quarantine_near_duplicates` 隔离。
5. 防护规则 IL-1~IL-6 已登记在 `feature_schema.json` 并有测试守护（tests/phase4_3b P2）。

## 7. 已有成果 / 未完成实验

- 已有：6 个模型家族、3 协议切分、特征/目标分离、模型登记与兼容性复现、中文检索与两阶段原型（E00–E06）、消融与统计分析、资源基准。
- 未完成（如实登记）：E07 微调（NOT_RUN，前置条件不满足）；多随机种子实验（NOT_RUN）；真实 Gold 上的正式对照（BLOCKED，H2）；教育模型决策层一致性比对（NOT_RUN）。

## 8. 当前环境可复现范围

Python 3.11.18 + sklearn 1.5.2 + torch 2.1.2+cu121（RTX 2050 4GB）下：
可复现 = checkpoint 加载、推理、指标重算、E00–E06 检索/精排原型、全部 127 项测试（`test-results.json`：PASS=127 FAIL=0）。
不可复现（缺前置） = 真实人工 Gold 结论、E07、跨环境 GB 反序列化（本机未复现问题，历史风险保留登记）。
