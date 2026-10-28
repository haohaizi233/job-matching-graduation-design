# 人岗匹配标签机制、目标泄漏与类别不平衡分析

- **审计日期**：2026-10-28
- **数据源**：`data/raw/job-resume-matching/{cv.csv, job.csv, matches.csv}`
- **执行脚本**：`scripts/data_audit/analyze_matching.py`、`scripts/data_audit/reverse_label_formula.py`、`scripts/data_audit/analyze_embeddings.py`
- **机器可读明细**：`reports/data-audit/matching-analysis.json`、`reports/data-audit/label-formula.json`、`reports/data-audit/audit-summary.json`

> **结论分级约定**
> - **【事实】** = 被数据直接证实（数值误差为 0 或机器精度，可 100% 复现）
> - **【推断】** = 有实验支持，但不是数据自明
> - **【未知】** = 无法从数据本身确定

---

## 1. 关联关系（全部为【事实】）

| 检查项 | 结果 |
|---|---|
| `cv.candidate_id` 唯一 | ✅ 9,544 个全部唯一，0 重复 |
| `job.job_id` 唯一 | ✅ 1,167 个全部唯一，0 重复 |
| `matches.candidate_id` 外键完整 | ✅ 9,532 个 **100% 命中** `cv.csv`，孤儿键 0 |
| `matches.job_id` 外键完整 | ✅ 1,164 个 **100% 命中** `job.csv`，孤儿键 0 |
| 未被引用的候选人 | 12 个（占 cv 表 0.13%） |
| 未被引用的岗位 | 3 个（占 job 表 0.26%） |
| `(candidate_id, job_id)` 重复组合 | **0 个**（122,560 个组合全部唯一） |
| 重复组合的标签冲突 | **0 个**（因无重复组合） |
| 同组合 `final_score` 冲突 | **0 个** |
| 观测组合占全交叉积比例 | **1.10%**（122,560 / 11,137,848） |

**度分布**

| 指标 | min | p25 | 中位 | p75 | max | 均值 |
|---|---:|---:|---:|---:|---:|---:|
| 每候选人对应岗位数 | 1 | 7 | 11 | 18 | 122 | 12.86 |
| 每岗位对应候选人数 | 1 | 9 | 19 | 122.25 | 500 | 105.29 |

- 候选人度分布：1 个岗位的有 60 人、2 个 230 人、3~10 个共 4,025 人，长尾到 122。
- **60 个候选人只有 1 条记录**，无法参与组内排序（Learning-to-Rank）评估。
- 岗位侧最大 500 人、最小 1 人，跨度 500 倍，评估时需注意长尾岗位的指标稳定性。

---

## 2. 标签 `label_strength` 分布

| 标签 | 数量 | 占比 | `final_score` 区间 | `raw_score` 区间 |
|---|---:|---:|---|---|
| `weak_positive` | 51,150 | 41.73% | 0.430009 ~ 0.580000 | 0.305954 ~ 0.524448 |
| `medium_positive` | 70,636 | 57.63% | 0.580000 ~ 0.679999 | 0.400054 ~ 0.570369 |
| `strong_positive` | **774** | **0.63%** | 0.680003 ~ 0.756099 | 0.543094 ~ 0.651570 |

**类别不平衡（【事实】）**

- `medium : strong` = **91.3 : 1**
- `weak : strong` = **66.1 : 1**
- `strong_positive` 只覆盖 **499 个候选人**（5.2%）和 **75 个岗位**（6.4%）
- 按候选人分组做 5 折交叉验证时，某些折的 `strong` 数量可能不足以给出稳定指标

**标签连续性（【事实】）**

`final_score` 在三个标签上的区间是**首尾相接的连续带**，不是三个可分簇：

- `weak` 最大 0.58000000 与 `medium` 最小 0.58000035 之间只有 3.5e-7 的间隙
- `medium` 最大 0.67999855 与 `strong` 最小 0.68000344 之间只有 4.9e-6 的间隙

这说明三档标签是**在一条连续分数上人为切两刀**得到的，`weak` 与 `medium` 在分数上几乎无法区分。

---

## 3. 六维评分与标签的关系：完整派生链（全部为【事实】）

审计把 `matches.csv` 的派生字段逐级反推，得到一条**闭环的确定性生成链**，每一环的数值误差都在机器精度量级：

```
【第 0 环】semantic_score
    semantic_score = 0.5 × cosine(cv.embedding, job.embedding) + 0.5
    证据：3,000 组匹配对上 pearson = 1.000000，spearman = 1.000000
          线性拟合 slope = 0.49999999, intercept = 0.50000000, R² = 1.00000000, max|resid| = 2.4e-7
          反解 cosine = 2×semantic − 1 亦为 R² = 1.0（max|resid| = 4.8e-7）

【第 1 环】raw_score
    raw_score = 0.25·semantic_score + 0.35·skill_score + 0.20·position_score
              + 0.10·category_score + 0.05·experience_score + 0.05·education_score
    证据：直接用固定权重计算，与 CSV 中 raw_score 的最大绝对误差 = 2.22e-16（float64 机器精度）
          最小二乘反解出的权重恰为 [0.25, 0.35, 0.20, 0.10, 0.05, 0.05]，bias = 0，R² = 1.0

【第 2 环】final_score
    final_score = 0.7 × raw_score + 0.3 × candidate_rank_pct
    证据：最小二乘反解权重 [0.7000000000, 0.3000000000]，bias = −0.0000000000
          R² = 1.000000000000，max|err| = 8.882e-16（机器精度）

【第 3 环】label_strength
    final_score <  0.58              → weak_positive
    0.58 ≤ final_score <  0.68      → medium_positive
    final_score ≥  0.68              → strong_positive
    证据：按此规则重新生成标签，与 CSV 中 label_strength 一致率 = 1.0000000000，例外 0 行
          决策树仅用 final_score 单特征、深度 2、3 个叶子，训练准确率 1.000000

【第 4 环】candidate_rank
    candidate_rank = 该候选人分组内 final_score 的降序名次（并列取最小名次）
    证据：9,532 / 9,532 个候选人分组 100% 复现
```

**决策树规则拟合对比**（`sklearn.tree.DecisionTreeClassifier`，训练集准确率）

| 使用的特征 | 深度 2 | 深度 4 | 实际树深 | 叶子数 |
|---|---:|---:|---:|---:|
| 仅 `final_score` | **1.000000** | **1.000000** | 2 | 3 |
| 仅 `raw_score` | 0.866319 | 0.871271 | 4 | 16 |
| 六维打分 | 0.691637 | 0.764246 | 4 | 16 |
| 六维 + `final_score` + `raw_score` | **1.000000** | **1.000000** | 2 | 3 |

**关键推论**：单用 `final_score` 一个字段就能 100% 复现三档标签；单用六维打分则不能（0.764），因为标签是切在 `final_score` 上而不是切在原始六维上。

### 3.1 六维打分与标签的相关性（【事实】）

| 特征 | Pearson×`final_score` | Pearson×`raw_score` | Pearson×标签序数 | Spearman×标签序数 |
|---|---:|---:|---:|---:|
| `semantic_score` | 0.2839 | 0.3139 | 0.2503 | 0.2525 |
| `skill_score` | 0.2731 | 0.2876 | 0.2069 | 0.1465 |
| `position_score` | 0.2719 | 0.3534 | 0.1837 | 0.2209 |
| `category_score` | 0.1861 | 0.1810 | 0.1470 | 0.1477 |
| `experience_score` | 0.3702 | 0.3732 | 0.3198 | 0.3162 |
| `education_score` | 0.1317 | 0.0980 | 0.1254 | 0.1255 |
| `raw_score` | — | — | 0.7115 | 0.7692 |
| `final_score` | — | — | **0.7866** | **0.8578** |
| `candidate_rank_pct` | — | — | 0.6080 | 0.6927 |

单个六维特征与标签的相关性都在 0.13~0.32 之间（弱—中），而 `final_score` 与标签的 Spearman 达 0.858 —— 这正说明**标签不是从任一单维切出来的，而是加权合成后再切阈值**。

### 3.2 完全相同的六维向量是否总是同标签（【事实】）

- 六维打分保留 8 位小数后，122,557 个唯一向量（122,560 行，仅 3 组重复）
- 其中**仅 1 组**出现标签不一致（该组 `final_score` 恰好跨过 0.58 阈值）
- 这 1 例是阈值边界上的浮点邻域效应，不改变"标签由 `final_score` 确定性决定"的结论

---

## 4. 目标泄漏判定：**存在完全确定的目标泄漏**

### 4.1 泄漏特征清单（禁止作为预测 `label_strength` 的输入）

| 字段 | 泄漏等级 | 理由 |
|---|---|---|
| `final_score` | **致命** | 与标签是同一信息的两种写法（阈值切分，100% 复现） |
| `raw_score` | **致命** | `final_score` 的线性输入，且自身由六维精确合成 |
| `candidate_rank` | **致命** | 由 `final_score` 组内排序确定性派生 |
| `candidate_rank_pct` | **致命** | `final_score` 的线性输入（0.3 权重） |
| `semantic_score` | **高** | 由 embedding 余弦精确派生，是 `raw_score` 的第一输入 |
| `skill_score` / `position_score` / `category_score` / `experience_score` / `education_score` | **高** | `raw_score` 的输入，合起来决定 71% 权重 |
| `cv.embedding` / `job.embedding` | **中—高** | 经 `semantic_score` 参与标签生成（见第 5 节） |

### 4.2 泄漏的严格表述

把上述任一字段（尤其是 `final_score`）作为特征去预测 `label_strength`，**等价于让模型复现数据生成公式**，得到的 100% 准确率不构成任何泛化能力证据。

`matching-analysis.json` 中的实验证据：

- 只用 `final_score` 单特征的深度 2 决策树，训练准确率 **1.000000**
- 用六维打分的深度 4 决策树，训练准确率仅 0.764246
- 加回 `final_score` 后立刻回到 1.000000

### 4.3 行级随机划分泄漏（【事实】）

模拟一次 8:1:1 的行级随机切分（`numpy.random.default_rng(42)`）：

| 指标 | 数值 |
|---|---:|
| 验证集行数 | 12,256 |
| 验证集中在训练集出现过的**候选人**比例 | **99.617%** |
| 验证集中在训练集出现过的**岗位**比例 | **100.000%** |
| 有 ≥2 行记录的候选人 | 9,472 个（99.4%） |
| 多行候选人的行数占比 | **99.951%** |
| 单候选人最大行数 | 122 |
| 多行岗位 | 1,162 个 |
| 单岗位最大行数 | 500 |

**结论**：行级随机切分下，验证集几乎每个候选人都在训练集出现过、每个岗位都出现过。模型只需记住"这个候选人/这个岗位的历史分数"即可高分，评估指标被严重高估。**必须按 `candidate_id` 或 `job_id` 分组切分。**

### 4.4 预计算 Embedding 是否含标签信息（【事实 + 推断】）

- 【事实】`semantic_score` **完全等于**两侧 embedding 余弦的仿射变换（R² = 1.0）
- 【事实】`semantic_score` 在 `raw_score` 中占 0.25 权重，`raw_score` 决定 `final_score` 的 0.7 权重
- 【推断】因此 embedding 经 `semantic_score → raw_score → final_score → label_strength` 这条链**参与了标签的生成**。用预计算 embedding 去预测 `label_strength` 时，模型能学到这条链的一部分，属于**派生信息泄漏**（derived-feature leakage）。
- 【未知】无法确定 embedding 的编码模型、编码输入（原文还是清洗后文本）、单塔还是双塔（详见 `embedding-analysis.md`）。

---

## 5. 负样本问题

### 5.1 现有标签到底表示什么（【事实】）

| 标签 | 实际含义 | 是否可当负例 |
|---|---|---|
| `weak_positive` | `final_score` 落在 [0.430, 0.580) 的**正样本低档** | ❌ **不可**。名字带 `positive`，且其 `semantic_score` 均值 0.7687 高于随机配对基线 0.4244 |
| `medium_positive` | `final_score` 落在 [0.580, 0.680) 的正样本中档 | ❌ 不可 |
| `strong_positive` | `final_score` ≥ 0.680 的正样本高档 | ❌ 不可 |
| 未出现在 `matches.csv` 的组合 | **未观测组合**（11,015,288 个，占 98.90%） | ❌ **不可直接标为负例** |

**核心结论**：`matches.csv` **只包含正样本记录**（三档全部是 `*_positive`），**没有任何显式负例标签**（已验证：`has_explicit_negative_label = False`）。

- `weak_positive` 的 `semantic_score` 均值 0.7687、`final_score` 均值 0.5532，与随机配对（余弦均值 0.4244）有明显差距 —— 它是"弱匹配"而不是"不匹配"。
- 三档标签在分数上是连续带，`weak` 与 `medium` 的边界只有 3.5e-7，把 `weak` 当负例会让正负类在特征空间严重重叠。

### 5.2 候选负采样方案（**本阶段不生成正式训练负例**）

| 方案 | 做法 | 优点 | 风险 |
|---|---|---|---|
| **A. 组内随机负采样** | 对每个候选人，从其未观测的 1,164 岗位中随机抽 k 个作负例 | 简单、可控正负比 | 未观测 ≠ 不匹配，会有假负例（false negative） |
| **B. 难负例挖掘** | 从已观测的 `weak_positive` 中按 `final_score` 低分位取样作"难负例" | 贴近决策边界 | 与正类高度重叠，需用排序目标而非分类目标 |
| **C. BPR / 成对排序** | 不显式建负类，只用 `candidate_rank` 组内序构造偏好对 | 避开负例定义问题 | 只能评估排序指标，无法输出绝对匹配概率 |
| **D. 对比学习负例** | 同批次内其它候选人的岗位作 in-batch negatives | 适合双塔检索 | 依赖 batch 构成，需与召回任务对齐 |

**推荐路径**：优先 **C（成对排序）** 作为主目标，A 作为二分类的补充实验，B 只用于消融。评估时三者都必须按 `candidate_id` 分组。

---

## 6. 类别不平衡处理建议

1. **改目标**：把三分类改成**回归**（预测 `final_score`）或**排序**（预测组内序），避开 774 条 `strong` 的稀缺问题。
2. 若坚持三分类：用**分层采样**保证每折 `strong` 数量，或对 `strong` 过采样 / 对 `medium` 欠采样。
3. **指标选择**：不要用 overall accuracy（把全部预测成 `medium` 就有 57.6%）；用 macro-F1、per-class recall、Cohen's κ、以及 ordinal metrics（MAE over ordinal labels）。
4. **折外报告**：按候选人分组 5 折，报告每折的 `strong` 支持数，若某折 < 30 条则该折 `strong` 指标不具统计意义。

---

## 7. 结论分级汇总

### 【事实】—— 数据直接证实
- 主键唯一、外键 100% 完整、无重复组合、无标签冲突。
- `raw_score` 是六维打分的固定权重线性组合（权重 0.25/0.35/0.20/0.10/0.05/0.05，误差 2.22e-16）。
- `semantic_score = 0.5 × cosine + 0.5`（R² = 1.0）。
- `final_score = 0.7 × raw_score + 0.3 × candidate_rank_pct`（误差 8.88e-16）。
- `label_strength` 由 `final_score` 的 0.58 / 0.68 两阈值完全决定（复现率 100%，0 例外）。
- `candidate_rank` 是组内 `final_score` 降序名次（9,532/9,532 组复现）。
- `strong_positive` 仅 774 条（0.63%），medium/strong = 91.3:1。
- `matches.csv` 无显式负例；未观测组合 11,015,288 个。
- 行级随机切分下 99.6% 验证候选人、100% 验证岗位在训练集出现过。

### 【推断】—— 有实验支持
- 整条标签链为**规则/公式派生**，而非人工标注或真实招聘结果。
- 预计算 embedding 经 `semantic_score` 参与标签生成，存在派生特征泄漏。
- `weak_positive` 应理解为"弱匹配正样本"，不是真实负例。

### 【未知】—— 无法从数据本身确定
- 六维打分中除 `semantic_score` 外，其余 5 维（`skill_score` / `position_score` / `category_score` / `experience_score` / `education_score`）的计算方法。
- `candidate_rank_pct` 的确切定义（其分母在候选人/岗位两个方向上都不恒定，无法自证；只知它是 `final_score` 的线性输入）。
- 0.58 / 0.68 两个阈值的设定依据。
- embedding 的编码模型与编码输入。
- 标签是否最终源自人工规则调参、第三方评分模型还是合成数据。

### 【严禁声称】
- ❌ 不得称 `label_strength` 为"人工标注的匹配结论"。
- ❌ 不得称 `label_strength` 来自"真实招聘/投递/录用结果"。
- ❌ 不得把 `weak_positive` 直接当作真实负例。
- ❌ 不得把未出现在 `matches.csv` 的组合直接标注为负样本。
- ❌ 不得用六维评分/分数/排名字段预测 `label_strength` 后把结果当作模型能力证据。
