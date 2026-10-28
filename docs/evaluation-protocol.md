# 评估协议（第三阶段）

- 配置来源：`configs/matching_splits.yaml`（匹配切分）、`configs/education_labels.yaml`（学历标签与金标准政策）
- 实现：`src/job_matching/split_matching.py`、`src/job_matching/education_data.py`、
  `src/job_matching/metrics_ranking.py`、`src/job_matching/metrics_classification.py`
- 实测结果：`reports/data-split-validation.md`

本文定义**数据怎么切、指标怎么算、结论能说到什么程度**。
所有模型（含后续 BERT / 双塔 / 精排）必须在本协议下比较，不得自行改口径。

## 〇、评估语义的前提（必须随任何指标一起引用）

1. **匹配标签是代理标签**。`label_strength` / `candidate_rank` / `final_score` 全部由原系统
   评分公式派生（见 `docs/feature-schema.md` 第二节），不是真实投递或录用结果。
   因此排序/分类指标只能解释为「预测结果与原系统代理偏好之间的一致程度」，
   **不代表**真实录用概率、招聘成功率或用户满意度。
2. **Embedding Cosine 基线与代理标签机制耦合**。`semantic_score = 0.5*cosine+0.5`（R²=1.0 证实），
   而 `semantic_score` 占 `raw_score` 0.25 权重、`raw_score` 占 `final_score` 0.7 权重。
   该基线即使 NDCG 很高，也**不构成独立的语义匹配有效性证明**。
3. **无真实负例**。`matches.csv` 全部是 `*_positive` 观测记录，本阶段不做负采样，
   所有排序评估只在**观测组合内部**做组内排序。
4. **预计算 Embedding 来源未知**。「冷启动」只表示下游排序模型未用这些实体做监督训练，
   不能宣称预训练编码器从未见过相关文本。
5. **学历伪标签可信度低**。`default/*` 的 `assistant` 是线上旧系统输出，
   人工复核一致率 45.92%（338/736），只能作低置信开发信号。

## 一、人岗匹配：三套独立评估协议

共同约定：

- **绝不行级随机划分**。同一 `candidate_id` / `job_id` 的记录按组整体分配。
- 随机种子固定（`configs/data_pipeline.yaml` -> `seeds`）：
  candidate_cold `20261028`、job_cold `20261029`、double_cold `20261030`。
- 比例默认 80% / 10% / 10%。
- 组分配算法：种子洗牌 + 相对缺口贪心（`assign_groups`），
  同输入同种子必得同结果；平局规则确定，不依赖字典序偶然性。
- 每套协议落盘 `train.csv` / `validation.csv` / `test.csv` / `excluded.csv` / `manifest.json`
  到 `data/splits/matching/<协议>/`，索引列为 `pair_index`（= `matches.csv` 原始行号）、
  `candidate_id`、`job_id`，可精确定位回原始数据。

### 协议 A：Candidate Cold-start（主评估协议）

- 分组键：`candidate_id`
- 互斥要求：**候选人集合两两不相交**（`candidate_overlap = 0`）、`pair_overlap = 0`；
  **岗位允许跨集合出现**（`job_overlap` 不要求为 0）
- 语义：未在下游训练数据中出现过的**候选人**，对已有岗位集合做匹配排序
- 实测规模（seed=20261028）：train 98,029 / validation 12,270 / test 12,261 条，
  候选人 7,617 / 941 / 974，可排序组（≥2 条）7,565 / 934 / 973

### 协议 B：Job Cold-start

- 分组键：`job_id`
- 互斥要求：**岗位集合两两不相交**（`job_overlap = 0`）、`pair_overlap = 0`；
  **候选人允许跨集合出现**
- 语义：排序模型面对**新岗位**时的表现
- 记录每组候选人具有的可评估岗位数；**单岗位候选人不强行计入排序指标**
- 实测规模（seed=20261029）：train 97,887 / validation 12,251 / test 12,422 条

### 协议 C：Double Cold-start

- 分组键：`candidate_id` + `job_id`
- 互斥要求：候选人集合两两不相交 **且** 岗位集合两两不相交 **且** `pair_overlap = 0`
- 分配策略 `eval_first_greedy`（确定性两阶段）：
  1. 阶段 1：`candidate_id` 按观测边数贪心分配 80/10/10（**组完整、边不拆**）；
  2. 阶段 2：`job_id` 归属——先按「多数边集合」零代价归属，
     再用 gain/cost 贪心从 train 侧为验证/测试候选人补齐可排序性
     （每个次要集合带独立的训练边损失预算 `budget_ratio_per_minor_split=0.10`，
     软目标 `eval_soft_target=5`，缺口权重指数 `gain_deficit_power=2`）。
- **两侧归属不一致的交叉边一律进 `excluded.csv`，绝不偷偷归入任何集合**；
  排除索引保留 `pair_index`，原始数据不删除。
- 三种策略（`majority_edge` / `proportional` / `eval_first_greedy`）的实测对比写入
  `manifest.json` -> `strategy_comparison`：`majority_edge` 保留率最高（~80%）但验证/测试集
  几乎为空（3 / 3 条），无法评估；`eval_first_greedy` 在保留率与可评估性之间做显式权衡。
- 实测（seed=20261030）：保留 73,526 / 122,560 条（保留率 0.5999），
  排除 49,034 条（丢弃率 0.4001）；validation 2,369 条 / test 2,225 条，
  可排序组（≥2）739 / 717。
- **稀疏性限制**：双侧互斥必然丢弃交叉边，评估时必须按保留率解释；
  若某次配置下可排序组过少（例如 < 200），不得宣布该协议实验可靠，
  应改用更宽松的预算参数重新划分并重新登记 manifest。

### 互斥性自动检查（G4 门禁）

按**协议定义**检查，不错误地要求 Candidate Cold-start 的 `job_overlap` 为 0，
也不错误地要求 Job Cold-start 的 `candidate_overlap` 为 0：

```text
candidate_cold:  candidate_overlap = 0, pair_overlap = 0, job_overlap 不要求
job_cold:        job_overlap = 0, pair_overlap = 0, candidate_overlap 不要求
double_cold:     candidate_overlap = 0, job_overlap = 0, pair_overlap = 0
```

同时检查：原始数据覆盖率、被排除的交叉边数、可评估组数量、
同组记录是否被拆到不同集合。

## 二、学历数据：重新划分与金标准隔离

### 2.1 重复检查（全部集合两两检查，不只 test 与 validation）

检查维度与实测结果（`data/splits/education/manifest.json` -> `duplicate_analysis`）：

| 维度 | 实测 |
|---|---|
| `job_id` 重复行 | 779 |
| 输入文本（`user_hash`）重复行 | 17,072 |
| `(record_key)` 重复 | 0 |
| 同输入不同标签（冲突组） | 374 组 / 812 行 |
| 跨来源输入交叉（gold & default_validation） | 702 |
| 原 default/test 被 default/validation 包含 | 22,730/22,730（job_id 100%） |

四类重复严格区分：① 输入重复；② 输入+标签重复；③ 相同输入不同标签；
④ 不同 ID 但实质相同的输入文本（用规范化文本哈希判定）。

### 2.2 处置顺序（`education_data.build_education_splits`）

1. 金标准 736 条整体隔离为 `gold_holdout`；
2. 开发池中**与金标准输入重复**的行剔除（762 行）——保留真实金标准做独立评估，
   不让开发集见过金标准输入；
3. 标签冲突的输入组剔除；
4. 输入文本重复的每组只保留一条（确定性：按 `record_key` 升序）；
5. 剩余开发池按 `user_hash`（规范化输入文本）分组 80/20 切 `train` / `validation`；
6. 所有被剔除的行写入 `excluded.csv` 并标注原因，不删除原始数据。

### 2.3 标签定义与可信度

- 6 个合法 token：`博士`、`硕士`、`本科`、`大专`、`学历不限`、`学历不明`
  （顺序即 `configs/education_labels.yaml` -> `label_order`，多热向量按此顺序编码）；
- 标签语义是「**可接受学历集合**」，按从高到低用「、」连接，如 `博士、硕士、本科`；
- 同义表达（`专科`→`大专`、`学士`→`本科` 等）按 `canonical_tokens` **精确映射**，不做子串判断；
- `X及以上` 的展开规则（`above_expansion`）来源于对伪标注数据的实测条件分布
  （P(标签 | 槽位表达)），标注为 `pseudo_convention`（来源系统惯例），
  **不是人工标注规范**；736 条人工金标准不做任何规则拟合；
- 无法映射的 token 保留原值、样本标记 `oov_token`，不强行归并；
- 可信度标识：`human_gold`（high）/ `pseudo_online`（low）/ `model_new`（unusable，含长文本噪声）。

### 2.4 评估集合

| 集合 | 标签来源 | 用途 |
|---|---|---|
| `train` | pseudo_online | 拟合统计量（词表、映射、阈值） |
| `validation` | pseudo_online | 开发期评估与调参 |
| `gold_holdout` | human_gold（736 条） | **一次性最终评估**，禁止反复调参 |
| （独立 test） | — | **不构建**：原 test ⊂ validation 且伪标签可信度低，无法构建独立可信测试集 |

**调参纪律**：规则定义、`X及以上` 展开、标签映射、阈值必须在开发集上确定并锁定后，
才对 `gold_holdout` 做一次正式评估。任何在金标准上反复试出来的数字都不可信，不得写入结论。

### 2.5 任务范围的准确表述

实测输入 `user` 中的 `<学历描述>` 是**上游已抽取的短槽位**（中位长度 2 字符），
不是完整招聘 JD。因此本数据支撑的任务是
「**学历要求表达的规范化 / 槽位校验与多标签归一**」，
**不是**「从完整招聘 JD 端到端抽取学历要求」。报告中不得使用后者表述。

## 三、指标定义

### 3.1 排序指标（`metrics_ranking.evaluate_ranking`）

- **NDCG@K**：增益用代理相关性，折损 `1/log2(rank+1)`；
  `gain_mode='score'` 直接用 `final_score`，`gain_mode='ordinal'` 用
  `weak=1 / medium=2 / strong=3`。两种口径都在报告中给出。
- **MRR@K**：首个二值相关项的倒数排名。
- **Recall@K**：top-K 命中的相关项数 / 该组相关项总数。
- **二值相关性定义（显式、代理）**：`label_strength ∈ {medium_positive, strong_positive}`。
  没有这个定义就不会输出 MRR / Recall。
- **有效查询数量**：`queries_total` / `queries_size_ge_2` / `queries_evaluated` /
  `queries_skipped_zero_relevance`。
- **候选数量分布**：组大小 min / p25 / median / p75 / max / mean。

**K 与组大小的统一口径**（所有 Baseline 与模型共用，禁止各自为政）：

- `min_group_size_for_ranking = 2`：只有 1 条观测记录的组无法形成排序，单独统计不计指标；
- 三个统计范围同时给出：`all`（组 ≥ min_group_size）、`size_ge_2`、`size_ge_maxk`（组 ≥ max(K)）；
- 组内候选数不足 K 时按实际组大小计算（`dcg_at_k` 自然截断到 `min(K, 组内候选数)`），
  IDCG 同样取理想排序的 top-K 增益，所有方法口径一致；
  不把不足 K 的组剔除，而是单独给出 `size_ge_maxk` 范围供对照；
- tie-breaking 固定：分数相同按原始行序（稳定排序 `np.lexsort`），保证跨 Baseline 可比。

**K 的选择**：K ∈ {5, 10}。数据中每候选人中位观测岗位数 11，
`size_ge_maxk` 范围保证 K=10 有意义；若未来数据分布变化，须重新确认 K 的有效性再登记配置。

### 3.2 分类/多标签指标（`metrics_classification.multilabel_metrics`）

- Exact Match Ratio（子集精确匹配）
- Micro-F1 / Macro-F1
- 每标签 Precision / Recall / F1（6 个 token 逐个报告）
- 错误类型分布：`OOV_TOKEN`、`EMPTY`、`CONFLICT` 等，单独统计

伪标签验证集与人工金标准测试集的指标**严格分开报告**，不得混合平均。

## 四、Baseline 与模型共用的评估纪律

1. **同一候选集合**：所有方法在完全相同的 `pair_index` 集合上评估
   （`run_matching_baselines` 从切分索引重建子集，任何方法不得私自过滤样本）。
2. **开发/测试分离**：规则定义、超参数、标签映射、候选集合策略、tie-breaking 策略
   只在 Train/Validation 上确定，锁定后对 Test 做**一次**正式评估。
   当前仍处于数据工程阶段时，优先只看开发集结果。
3. **可复现**：随机 Baseline 使用固定种子序列多次运行并报告均值±标准差
   （`baseline_random_ranking=20261101`，20 次）。
4. **禁止跨协议混用结论**：协议 A 的指标只能与协议 A 的指标比较；
   Double Cold-start 的结果必须同时报告保留率与可排序组数。
5. **禁止用指标数字代替限制说明**：任何报告 Baseline 或模型指标的位置，
   必须同时引用本文件第 〇 节的 5 条限制。
