# P7-4 统计分析

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 状态：**`not_computable`（无真实 Gold 查询组，Bootstrap 无对象）**
- 上游：[`04-real-model-evaluation.md`](04-real-model-evaluation.md)（`BLOCKED`）

> 本报告不含任何置信区间、显著性或差值数值。**不伪造统计结果**。

---

## 一、统计方法（预注册锁定，`phase7-eval-protocol-v1`）

| 项 | 锁定值 |
|---|---|
| 重采样单位 | **查询组（`resume_id`）** |
| 方法 | **paired bootstrap**（配对比较，同一组集） |
| `n_boot` | 1000 |
| 种子 | `20261205` |
| 置信水平 | 95% |
| 同组重采样 | 所有模型在同一次 Bootstrap 中使用**完全相同**的重采样组 |
| 实现 | `src/job_matching/evaluation/statistical_tests.py::bootstrap_diff`（确定性） |
| multiplicity | 主指标唯一（NDCG@10）；次指标仅解释性 |

**为什么必须以查询组为单位**：同一份简历的多个 (resume, job) pair 高度相关，
若把它们当独立样本会严重低估方差、制造虚假的显著性。这是本项目统计口径的硬约束。

---

## 二、必须报告的统计量（模板）

对每个模型 × 每个指标：

| 统计量 | 说明 |
|---|---|
| `mean` | 组级均值 |
| `n_groups` | 有效查询组数 |
| `ci_95` | 组级 Bootstrap 95% 置信区间 `[lo, hi]` |
| `delta_vs_baseline` | 与 E00 / E02 基线的配对差值均值 |
| `delta_ci_95` | 差值的 95% 置信区间 |
| `statistical_stability` | `stable` / `unstable`（`n_groups < 20` 必为 `unstable`） |
| `not_computable_reason` | 无法计算时的显式原因 |

### 模型与基线差值表（模板，当前全部 `not_computable`）

| 模型 | 指标 | mean | n_groups | ci_95 | Δ vs E00 | Δ ci_95 | 稳定性 | 状态 |
|---|---|---|---|---|---|---|---|---|
| E00 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E01 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E02 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E03 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E04 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E05 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E06 | NDCG@10 | — | 0 | — | — | — | — | `not_computable` |
| E07 | NDCG@10 | — | 0 | — | — | — | — | `BLOCKED`（无训练标签） |

`—` 表示无数据，**不是 0**。

---

## 三、统计稳定性规则

| 规则 | 内容 |
|---|---|
| 硬下限 | 有效查询组 < 20 → `statistical_stability="unstable"` |
| 禁止声明 | 不稳定状态下**禁止**声明"显著优于 Baseline" |
| 分类别 | 某岗位类别样本量 < 5 → 该类别指标 `not_computable` |
| 退化分布 | 期望一致率 = 1 → Kappa `not_computable` |

### 规划层最小可检测效应（MDE，假设测算）

`MDE = (z_0.975 + z_0.80) × sd_diff / sqrt(n_groups)`，`sd_diff = 0.20`（**ASSUMPTION**）

| 盲测查询组 | MDE (NDCG@10) | 对应方案 |
|---:|---:|---|
| 9 | 0.1868 | Scenario A（**不稳定**） |
| 21 | 0.1223 | Scenario B |
| 36 | 0.0934 | Scenario C |

> `sd_diff` 是规划假设，不是实测值。真实 `dev_validation` 数据到位后必须实测
> 组级差值标准差并回填复算，否则 MDE 无意义。

---

## 四、无法计算项的处理（预注册纪律）

| 情形 | 处理 |
|---|---|
| 无真实 Gold 查询组 | `status="not_computable"` + `reason="no_real_gold_query_groups"` |
| 有效组 < 20 | 指标照算，但 `statistical_stability="unstable"`，禁止显著性声明 |
| 某模型失败 / 缺权重 | 登记 `NOT_RUN` + 原因，**不填 0** |
| 某指标口径退化 | `not_computable` + 原因 |

**禁止**：填充 0、用合成数据补足、用英文代理标签替代、隐藏失败或不可计算项、
为了显著性删除低质量样本。

---

## 五、当前结论

- 全部统计量 **`not_computable`**，原因：**无真实 Gold 查询组（0 组）**；
- 未做任何显著性检验，**未声明任何模型优于基线**；
- 解除条件：真实 Gold 冻结完成 → `dev_validation` 评测 → 本报告填充真实数值；
- 若届时复杂模型低于 BM25，**必须保留结果并分析原因**，不得因其复杂就宣布更好。
