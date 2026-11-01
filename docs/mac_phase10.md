# Phase 10：智能人岗匹配系统——排序学习算法升级、Mac MPS 训练优化与实验架构重构

## 一、你的身份与工作目标

你是一名高级机器学习研究工程师、搜索推荐系统架构师、MLOps 工程师和毕业设计实验负责人。

当前工作区是 `job-matching-graduation-design`，已在 Apple Silicon Mac（64GB 统一内存）本地部署。

本项目已有完整的数据工程、模型训练、中文语义检索、业务 API、前端与测试体系。现有 Phase 9 主要负责 Mac MPS 适配与训练验证。

**本次任务是 Phase 10：在保证现有实验可信度的基础上，实质性改进排序算法、训练架构、模型评估和中文推荐链路。**

不是从零重写，不是做一个新的 Demo，也不是单纯增加网络层数和 Epoch。

你的核心目标：

1. 找出并修复现有评价实现和实验架构的真正缺陷。
2. 新增成熟的 Learning to Rank 算法，与已有 RankNet、MLP 公平比较。
3. 建立高效、可恢复、可追踪的实验编排与超参数优化体系。
4. 优化现有中文 BM25、TF-IDF、BGE、Cross-Encoder 召回与精排链路。
5. 利用 Mac MPS 加速适合 GPU 的工作负载。
6. 保持实验结果可解释、可重复、可用于论文。
7. 在没有真实人工标签时坚持研究边界，不能制造虚假的模型优势。
8. 最终形成通过自动化验收的独立 PR。

**请直接检查代码、实现改造、执行实验、运行测试、保存证据。不要只输出实施计划。**

## 二、首先读取真实仓库

立即执行：

```
pwd
git status --short
git branch --show-current
git log -5 --oneline
uname -m
python3 --version
```

读取现有架构，至少包括：

```
configs/training/
configs/feature_policy.yaml
configs/matching_splits.yaml
configs/phase7-preregistered-protocol-v1.json

src/job_matching/training/
src/job_matching/evaluation/
src/job_matching/metrics_ranking.py
src/job_matching/models/
src/job_matching/independent_eval/

src/job_matching/service/model_registry.py
src/job_matching/service/research_strategy.py

scripts/model_training/
scripts/education_training/
scripts/phase4_3b/
scripts/phase7/

tests/model_training/
tests/phase4_3b/
tests/phase7/

docs/evaluation-protocol.md
docs/phase9-mac-mps-training-task.md
reports/phase7/06-model-selection.md
```

重点理解以下现有能力：

- Ridge / Gradient Boosting / MLP / RankNet。
- candidate_cold / job_cold / double_cold。
- 现有 FeatureMap 与特征白名单。
- RankNet 成对采样与训练循环。
- BM25 / TF-IDF / BGE 召回。
- RRF 召回融合。
- BGE Cross-Encoder 精排。
- FeatureFusion。
- ModelRegistry。
- 中文推荐四套 research strategy。
- Phase 7 的真实 Gold 标注及预注册门禁。

禁止重复创建同功能模块。

保护 Mac 上尚未提交的 Phase 9 工作。检查差异后创建独立分支：

```
feat/phase10-ranking-research-optimization
```

如存在未完成训练或工作树修改，先安全隔离并保存现场，绝不直接覆盖。

本任务的代码改造以当前真实仓库为准；不要盲目依赖历史说明文档。

## 三、P0：评估正确性与数据审计

### 3.1 修复 Pairwise Accuracy 统计缺陷

审计：

```
src/job_matching/evaluation/metrics.py
src/job_matching/evaluation/statistical_tests.py
```

当前实现通过上三角筛选 `diff > tie_eps`，可能遗漏原始行顺序相反的合法偏好对。

请修复为：

- 对每组的所有无序样本对进行遍历或矢量化计算。
- 只要真实相关性差的绝对值超过 `tie_eps`，该对就有资格参与评价。
- 根据真实相关性大小确定正确排序方向。
- 同分预测按既有协议记 0.5。
- 保持 query-level 宏平均。
- 不重复计算 `(i,j)` 与 `(j,i)`。
- 单样本组、全同分组、不可评估组单独统计。
- 校验顺序翻转不变性。

增加测试：

```
原数组顺序
反转数组顺序
随机置换顺序
所有预测相等
所有真实标签相等
单样本组
多个查询组
```

同一组内同时置换标签、预测和记录顺序后，结果应在浮点容差内一致。

注意：不要不经检查就修改 `pair_sampler.py`，其现有配对构造已先按目标分数排序，和评价代码的使用场景不同。

保存：

```
reports/phase10/evaluation-audit.md
reports/phase10/metric-correction.json
```

历史报告不得静默覆盖。

### 3.2 处理候选集过短的问题

目前已知 Test 集约束：

```
candidate_cold:
  可排序组约 973
  候选数中位数约 11

job_cold:
  可排序组约 3199
  候选数中位数约 1
  候选数 >= 10 的查询仅约 2 组

double_cold:
  可排序组约 717
  候选数中位数约 2
  候选数 >= 10 的查询仅约 1 组
```

必须通过实际数据复核这些历史统计。

增加统一的候选集规模分层：

```
group_size = 2~4
group_size = 5~9
group_size >= 10
```

同时输出：

```
NDCG@1 / @3 / @5 / @10（可定义时）
MRR@5
Recall@5
Query Count
Group Size Distribution
Random Ranking Baseline
Oracle Upper Bound
```

不能把 `group_size < 5` 时的 Recall@5≈1 当成真实召回能力。

分层中有效组数不足时输出 `INSUFFICIENT_GROUPS`，不得把不稳定数字包装成可靠结论。

新增指标属于探索性补充，不能替换或修改 Phase 7 已预注册的正式主指标。

### 3.3 增加随机排序对照与指标基准

现有代理 ordinal gain 是：

```
weak_positive   = 1
medium_positive = 2
strong_positive = 3
```

所有等级增益均为正值，因此随机排序的 NDCG 也可能很高。

必须在相同查询组、相同标签和相同指标口径上计算随机排序基准。

至少报告：

```
model_ndcg
random_mean_ndcg
oracle_ndcg
delta_vs_random
query_count
confidence_interval
```

对随机排序使用固定种子多次重复，禁止把单次随机结果作为稳定基线。

不得修改原始排序指标定义以人为扩大模型收益。

### 3.4 数据来源与许可证审计

现有 `job-resume-matching` 原始数据的具体来源和许可证仍存在未完全确认项。

检查数据血缘、原始哈希、卡片、manifest 和许可声明。

在证据不足时保留 UNKNOWN，不得编造来源或授权。

不得自动向外部模型服务、实验追踪服务或仓库上传原始简历文本。

## 四、P1：新增 LightGBM LambdaMART

这是本阶段最重要的新算法。

优先实现 `LightGBM LGBMRanker`，CPU 执行。

不得因为使用 Mac 就强行要求所有模型跑 MPS。LightGBM 的 CPU Learning to Rank 是合法且适合的基线。

### 4.1 训练输入

复用现有：

```
data/processed/matching/
data/splits/matching/
FeatureMap
FeaturePolicy
TrainConfig
```

不重新随机切分数据。

训练输入必须按照 `candidate_id` 分组，保证每个 query 的所有候选记录连续排列。

明确验证：

```
sum(group_sizes) == len(X)
sum(group_sizes) == len(y)
每组 candidate_id 一致
pair_index 没有重复
训练特征不含目标泄漏字段
train / validation 无不允许的实体交叉
```

不得将 `candidate_id` 或 `job_id` 本身作为模型训练特征。

### 4.2 相关性标签

当前排序评价口径：

```
weak_positive   -> gain 1
medium_positive -> gain 2
strong_positive -> gain 3
```

LightGBM 的训练标签和 `label_gain` 必须显式对齐。

可以采用连续等级编码：

```
weak_positive   -> label 0
medium_positive -> label 1
strong_positive -> label 2

label_gain = [1, 2, 3]
```

如果底层实现对非零初始增益存在行为限制，必须通过构造性测试与 NDCG 计算核验后再确定映射方式。

不能不经验证就使用 LightGBM 默认指数增益代替现有线性等级口径。

### 4.3 实验方案

基础配置方向：

```
objective = lambdarank
metric = ndcg
eval_at = [5, 10]
num_leaves = [15, 31, 63]
max_depth = [-1, 5, 8]
learning_rate = [0.02, 0.05, 0.1]
min_child_samples = [10, 20, 50]
feature_fraction = [0.8, 1.0]
lambda_l2 = [0, 1, 5]
```

根据数据规模采用 Optuna TPE 搜索，先执行 20～30 个 Trial 的有界实验。

只允许 Validation 指导模型选择、早停和超参数搜索。

报告训练 NDCG 与验证 NDCG，检查过拟合。

重点对照：

```
Ridge
Gradient Boosting
MLP
RankNet
LightGBM LambdaMART
```

首轮重点使用 candidate_cold。

其他两个协议保留原定义，但必须结合候选集稀疏性解释。

### 4.4 模型产物

增加：

```
configs/training/lambdamart.yaml
```

实现对应独立模型适配器，并与现有训练接口对接。

不要为了增加一个算法而重写所有模型基类。

输出标准格式：

```
model artifact
config.json
metrics.json
manifest.json
feature_map.json
validation predictions
training history
environment fingerprint
```

模型必须支持 CPU 推理和依赖版本核验。

旧 GBM 的 sklearn 反序列化兼容问题不得通过覆盖历史权重解决。

## 五、P2：优化已有 RankNet 和 MLP

### 5.1 RankNet

保留原始 RankNet 作为对照。

探索性实验包括：

- 不同网络宽度；
- 不同 batch size；
- AdamW 学习率；
- Weight Decay；
- Dropout；
- Pair sampling 数量；
- Query 等权采样；
- 训练数据中不同偏好差异的权重。

推荐比较：

```
Original RankNet
Query-balanced RankNet
Margin-weighted RankNet
```

但注意：

`final_score` 来自历史评分公式，不能把代理分差解释为真实用户偏好强度。

所有新策略均为探索性实验。

### 5.2 Listwise 模型

根据实际训练规模选择一个可维护的实现：

```
ListNet
或
NDCG-aware LambdaLoss
```

优先简单、可测试、与现有 TorchScorer 兼容的方案。

要求：

- 按完整 Query Group 构造 batch；
- 支持可变候选数量；
- mask 不得参与损失；
- 正确处理组内同分；
- 不发生组间样本混合；
- 不使用 Test 标签。

不要为增加技术名词而同时引入多个未经验证的损失函数。

### 5.3 训练稳定性

使用至少 5 个独立训练种子进行最终候选配置的稳定性研究。

记录：

```
mean
std
median
min
max
95% CI
```

对模型之间同一组查询上的表现进行配对 Bootstrap。

必须区分“不同训练种子的波动”与“查询采样带来的统计不确定性”。

不能仅凭单次 NDCG 多出 0.001 就宣布算法更优。

## 六、P3：Mac MPS 的有效训练与推理加速

复用 Phase 9 已有适配。

目标设备：

```
PyTorch MLP / RankNet / Listwise -> MPS
BGE Embedding -> 优先测试 MPS
BGE Cross-Encoder -> 优先测试 MPS
LightGBM / sklearn -> CPU
```

检查实际芯片名称、PyTorch、Transformers、Metal 后端和可用内存。

特别评估：

- 现有 BGE Encoder 的 MPS 批量编码；
- BGE Reranker 的 MPS 批量推理；
- 256/512 token 长度的计算成本；
- 推理 batch size；
- 模型预热；
- CPU 与 MPS 延迟；
- 加载耗时；
- 批量吞吐；
- 内存压力；
- 同步后的真实设备计时。

对于 BGE：

优先复用仓库已登记的

```
BAAI/bge-small-zh-v1.5
```

及现有 BGE Reranker。

必须沿用已锁定的模型 revision 和许可证信息。

暂时不要任意换成更大模型并将结果宣称为公平架构优化。

如发现更大模型有潜在收益，作为独立探索实验登记。

优化原则：

1. 参数不重复加载。
2. 岗位向量尽可能离线预计算。
3. 缓存键包括模型版本、文本指纹、归一化配置和分词配置。
4. 模型或岗位更新后正确失效缓存。
5. MPS 出现不支持算子时明确记录原因。
6. 不允许静默 CPU fallback 后仍报告 MPS 加速。
7. 使用实际同步的 wall-clock 测试延迟。
8. 不为了跑满 GPU 而进行无意义计算。

如测试证实某模型 CPU 更快，就保留 CPU。

MLX 可以作为独立 Benchmark，但不得因此大规模迁移现有 PyTorch 模型。

## 七、P4：优化现有中文召回与精排架构

注意：

当前仓库已存在：

```
src/job_matching/models/retrieval.py
src/job_matching/models/reranker.py
src/job_matching/models/fusion.py
src/job_matching/models/text_encoder.py
src/job_matching/service/research_strategy.py
src/job_matching/service/model_registry.py
```

必须先复用，不得重造。

目标链路：

```
Resume / StudentProfile
          |
          v
    Text / Skill Query
          |
   +------+------+------+
   |             |      |
 BM25          TF-IDF   BGE
   |             |      |
   +------+------+------+
          |
       RRF Fusion
          |
  Candidate Deduplication
          |
    Candidate Top-N
          |
    Cross-Encoder
          |
    FeatureFusion
          |
  Business Constraints
          |
        Top-K
```

### 7.1 召回分析

补充：

```
BM25-only
TF-IDF-only
BGE-only
BM25 + TF-IDF
BM25 + TF-IDF + BGE
```

研究 RRF 参数、候选 Top-N 和召回路由。

所有比较必须使用完全相同的数据、候选库和查询集合。

### 7.2 完整候选池实验

原始匹配数据中存在：

```
9544 份简历
1167 个岗位
122560 条观测匹配
```

在许可与资源约束允许的前提下，构建基于全部可用岗位的**已知正例覆盖实验**。

对每份简历计算岗位检索排名，检查原有已观测匹配能否进入 Top-10 / Top-50 / Top-100。

该结果必须命名为：

```
observed-positive coverage@K
```

或等效明确名称。

它不能直接称为经过真实负例校准的 Recall@K。

未观测岗位不能自动算负例。

如果检索协议与现有训练数据存在泄漏可能，必须先设计合法隔离方案并说明限制。

### 7.3 中文研究集

复用现有 Phase4-3B 中文合成研究集。

当前该集合规模较小，仅适合：

- 链路冒烟；
- 组件消融；
- 失败案例分析；
- 计算性能验证。

不得把合成代理标签结果作为正式中文推荐有效性结论。

### 7.4 精排是否真的有益

仓库历史研究发现 Cross-Encoder 在部分合成代理标签上存在负贡献。

必须保留这个现象，不得因为精排模型更复杂而默认它一定更好。

对照：

```
Retrieval Only
Retrieval + FeatureFusion
Retrieval + Cross-Encoder
Retrieval + Cross-Encoder + FeatureFusion
```

输出每一步的质量指标、候选丢失数量与延迟成本。

如果精排未带来可靠收益，保留默认关闭状态。

## 八、P5：难负样本挖掘模块

本阶段只实现合法的样本发现与人工审核支持。

可由 BM25、BGE 或 Cross-Encoder 找出：

- 语义相似但关键技能可能不满足的岗位；
- 标题相近但职责差异明显的岗位；
- 学历硬门槛可能不满足的岗位；
- 专业领域相似但岗位类别不同的岗位；
- 已观测正例之外的其他未标注候选。

所有未标注组合默认：

```
label_status = UNLABELED
```

不得默认赋值为 0。

候选记录需要包括：

```
resume_id
job_id
mining_source
difficulty_tier
label_status
annotation_status
source_dataset_version
split_scope
```

禁止将验证集或 Test 的标签和已锁定 Gold 信息泄漏到训练集。

提供人工标注导出能力，经过独立审核和明确许可之后才能形成监督训练样本。

在没有足够可信训练标签之前：

```
E07 = BLOCKED
```

不得绕过 Phase 7 既有门禁。

## 九、P6：训练实验框架与架构优化

建立轻量实验系统，推荐：

```
configs/experiments/phase10/

scripts/phase10/
    audit_data.py
    audit_metrics.py
    train_ranker.py
    tune_ranker.py
    benchmark_retrieval.py
    benchmark_mps.py
    compare_experiments.py
    validate_artifacts.py
    run_all.py

reports/phase10/
```

实际目录允许调整，但不要引入冗余抽象。

### 9.1 统一实验契约

每次实验记录：

```
experiment_id
run_id
git_sha
model_id
model_version
device
seed
dataset_version
split_manifest_sha256
feature_schema_version
training_config
validation_metrics
test_access_status
runtime_seconds
artifact_sha256
label_source
research_status
```

必须能根据 Run ID 精确定位模型和报告。

不允许 `compare_models.py` 自动选到“最新目录”就把它认定为最佳模型。

应有明确的 Run Selection 规则，按 Validation 和实验状态选择。

### 9.2 Optuna 调参

使用 SQLite 持久化：

```
TPE Sampler
Median / Hyperband Pruner
fixed seed
max_trials
time_budget
```

需要支持终止后恢复。

不重复执行已经完成且结果完整的 Trial。

GPU 密集训练默认串行，防止多个进程占满 Apple 统一内存。

记录被剪枝、失败和完成的全部 Trial。

### 9.3 模型兼容性

新增模型需符合现有 ModelRegistry 约定。

必须区分：

```
research_only_proxy_labels
research_only_zh
pending_phase4_3b
verified
```

不得凭代理指标把模型升级为 `verified`。

保留服务的硬性业务规则、认证边界、降级策略与响应结构。

不要替换当前默认推荐策略。

### 9.4 修复旧的实验报告硬编码

检查：

```
scripts/model_training/compare_models.py
```

设备类型不能根据模型名称硬编码成 CUDA。

从实际 Run Manifest 读取：

```
cpu
cuda
mps
```

报告还应记录真实训练设备、推理设备及精确运行环境。

禁止用修改历史模型的方式纠正旧报告。

## 十、P7：研究结果与论文实验材料

生成：

```
reports/phase10/
    00-repository-audit.md
    01-data-and-metric-audit.md
    02-lambdamart-experiments.md
    03-ranknet-listwise-study.md
    04-mps-performance.md
    05-retrieval-rerank-study.md
    06-negative-mining-policy.md
    07-statistical-analysis.md
    08-model-serving-compatibility.md
    09-final-acceptance.md
    experiment-results.json
    experiment-results.csv
```

绘制实际实验图：

- Ridge / GBM / MLP / RankNet / LambdaMART 对比；
- Candidate Cold 查询规模分层；
- 随机排序与模型 NDCG 对比；
- 模型训练损失曲线；
- 不同网络与损失函数的消融；
- CPU / MPS 实测延迟与吞吐；
- 召回方式与候选 Top-N 的性能关系；
- 多种子模型稳定性；
- 推理延迟—推荐质量权衡。

实验结果不得伪造。

没有实际执行的实验写 `NOT_RUN`。

没有真实 Gold 的有效性结论写 `BLOCKED`。

无法解释清楚的指标不能写成正式效果。

特别注意：旧数据集的 Test 已参与过历史对照。Phase 10 的反复探索必须限制在 Train / Validation，不能反复用历史 Test 选型。若需要新一轮无偏确认评价，应准备新的隔离评价集并按协议执行。

## 十一、P8：自动化门禁

至少增加以下测试：

```
T01 训练数据与特征白名单正确
T02 三种冷启动分组无泄漏
T03 LambdaMART Query Group 连续性
T04 Label Gain 与已有 NDCG 口径对齐
T05 Pairwise Accuracy 顺序置换不变
T06 候选组过短指标不误导
T07 随机排序基线可复现
T08 MPS 训练与 CPU 推理兼容
T09 模型 Checkpoint 跨平台加载
T10 Optuna Trial 可恢复
T11 实验 Run ID 不覆盖
T12 Test / Gold 访问受限
T13 未标注候选不得当真实负例
T14 ModelRegistry 不允许非法 verified
T15 推荐 API 契约与回退策略兼容
T16 旧有训练和业务回归保持通过
```

新 CI 以轻量合成夹具为主。

大型模型训练放在本地 Mac 上执行，保留完整运行日志与产物哈希。

不要让 GitHub Actions 每次提交都下载 BGE 权重或执行数小时训练。

## 十二、执行顺序与资源预算

严格分阶段实施：

```
Phase 10.0
评估修复、基线冻结、数据统计

Phase 10.1
LambdaMART 实现、单元测试、首轮训练

Phase 10.2
RankNet / MLP 的有效搜索和统计实验

Phase 10.3
BGE / Reranker 的 MPS 优化和 Benchmark

Phase 10.4
完整候选池实验与难例挖掘准备

Phase 10.5
实验追踪、模型兼容、CI 和论文报告
```

先执行正确性门禁，再消耗 GPU 计算预算。

第一轮建议：

```
LambdaMART：20~30 trials
RankNet：10~20 trials
MLP：10~15 trials
Listwise：先做正确性与小规模有效性研究
最终候选：5 seeds
MPS Benchmark：每个代表性配置至少 3 repeats
```

资源不足时按照研究价值裁剪，而不是缩减测试严谨性。

新增算法即使未超过旧模型，也应如实保留负结果。

不得强制追求某个 NDCG 分数。

## 十三、最终交付要求

必须实际完成以下内容：

1. 修改代码并提交独立分支。
2. 提供真实模型训练日志。
3. 完成 LambdaMART 与旧模型的公平对照。
4. 修复成对准确率统计缺陷。
5. 输出三协议候选规模与指标分析。
6. 建立可恢复的训练实验记录。
7. 完成 CPU/MPS 性能测试。
8. 完成模型加载、推理和 API 兼容测试。
9. 生成真实统计报告和论文图表。
10. 执行相关 CI，并说明跳过原因。
11. 给出可以精确复现的命令。
12. 给出 PR 链接及 HEAD SHA。

验收标准：

- A：基础评价修复、LambdaMART 完整实验、统计验证、跨平台推理、回归与报告全部通过。
- B：核心算法与评估通过，部分探索性实验受资源限制。
- C：有新算法代码，但未完成真实训练与可复现验证。
- D：训练失败、实验数据不可信或破坏现有功能。

真实中文人工 Gold 仍是独立阻断项，不影响 Phase 10 工程与探索性研究通过，但不得据此宣称中文匹配模型正式通过效果验收。

**现在立即读取当前本地仓库，执行 Phase 10.0 的实际审计与修复，然后推进 LambdaMART 实验。不要只输出计划，不要中途用未经验证的成绩替代验收。**