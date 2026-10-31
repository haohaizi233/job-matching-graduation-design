# R1：Cross-Encoder（精排）实际推理缺陷整改

- 生成时间：2026-10-31
- 分支：`fix/phase6-research-integration-hardening`
- 相关代码：`src/job_matching/service/research_strategy.py`、`src/job_matching/models/reranker.py`
- 回归测试：`tests/phase6/test_reranker_contract.py`（14 用例）

## 1. 缺陷定位（真实复现）

原 `research_strategy.py` 精排消费端：

```python
rr = reranker.score(queries, documents)
rr_scores = list(getattr(rr, "scores", []) or [])
```

`RerankResult.scores` 的类型契约是 `np.ndarray`（`reranker.py`）。当 scores 为含多个
元素的 NumPy 数组时，`arr or []` 先对 arr 求布尔值，触发：

```
ValueError: The truth value of an array with more than one element is ambiguous.
```

该异常被下方宽泛 `except Exception` 捕获并重抛为 `ServiceError("MODEL_CORRUPT", ...)`，
把**返回数据类型问题伪装成权重损坏**，导致真实 Cross-Encoder 推理结果被误分类。

复现证据（`test_reranker_numpy_scores` 修复前失败栈）：

```
File ".../research_strategy.py", line 472, in rank
    rr_scores = list(getattr(rr, "scores", []) or [])
ValueError: The truth value of an array with more than one element is ambiguous.
...
ServiceError: [MODEL_CORRUPT] 精排模型推理失败: ValueError: ...
```

## 2. 整改要求与落实

| 要求 | 落实 | 验证用例 |
|---|---|---|
| 严格 RerankResult 类型契约 | `_extract_rerank_scores` 直接取 `result.scores` | `test_reranker_numpy_scores` |
| 显式判断 `scores is None` | `if scores is None` → 契约错误 | `test_reranker_none_scores` |
| 数组转一维数值序列 | `np.asarray(scores, float).reshape(-1)` | `test_reranker_numpy_scores` |
| 验证输出长度 | `arr.size != expected` → 契约错误 | `test_reranker_length_mismatch` |
| 验证 NaN / Inf | `np.all(np.isfinite)` 否则拒绝 | `test_reranker_nonfinite_scores` |
| 与候选 job_id 对应 | 按 `rerank_positions` 顺序映射，长度强校验 | `test_reranker_numpy_scores_order_preserved` |
| 同输入排序稳定 | 稳定排序（score desc，pos 兜底） | `test_reranker_stable_order_same_input` |
| 保留截断数量 | `rerank_truncated` 落 item + 信封 | `test_reranker_top50_boundary` |
| 不把类型错误伪装权重损坏 | 契约违规→`INTERNAL_ERROR`/`rerank_output_contract_violation`；真实推理异常→`MODEL_CORRUPT` | `test_reranker_*_contract`、`test_reranker_inference_exception_is_corrupt` |
| 禁止宽泛 `except Exception: pass` | 无静默吞异常；契约校验在 try 之外 | 全部 |

## 3. Logits 融合口径修正

原逻辑：

```python
m = max(rr_scores)
semantic = weight * (s / m)   # 仅当 m > 0 才施加
```

缺陷：全为负 logits（`m < 0`）、最大 logit 为 0、正负混合时静默跳过或越界；
`score/m` 不是有界、非严格单调、不可解释的变换；默认 logits 落在 0–1 是错误假设。

整改：批内 **min-max 归一化到 [0,1]**（`_minmax_normalize`）：

- `hi > lo` 时 `norm = (x - lo)/(hi - lo)`，**严格递增**、数值稳定、输出有界 [0,1]；
- 全等（含单元素）退化为**中性 0.5**，不除零、不产生 NaN/Inf；
- 覆盖全负 / 零最大 / 正负混合 / 全等 / 极端值（±1e6）/ 未校准 / Top-50 边界。

### 口径分层（每层明确）

| 层 | 含义 | 取值 | 用例 |
|---|---|---|---|
| 原始 Logit | Cross-Encoder 输出，未校准 | 实数（含负/极端） | `rerank_score` |
| 归一化排序信号 | 本批精排候选内的相对位置 | [0,1]（全等→0.5） | `rerank_norm` |
| FeatureFusion 输入 | 语义分量输入（替代召回语义分） | [0,1] | `breakdown.contributions.semantic` |
| 最终融合分数 | 结构化 + 语义线性加权 | 0..Σweight | `breakdown.total` / `score` |

> 归一化信号是**排序参考信号**，跨请求不可比；**不得**表述为录用概率/成功率；
> Sigmoid 输出同理（本实现未采用 Sigmoid，避免概率误读）。

## 4. 版本口径升级

评分算法变更 → `scoring_config_version` 升级：

- 精排策略（`zh_research_rerank_v1` / `zh_research_bge_rerank_v1`）→ `research_scoring_config_v2`；
- 无精排策略（`zh_research_retrieval_v1` / `zh_research_bge_recall_v1`）→ 保持 `research_scoring_config_v1`。

历史结果版本解释保留（v1 结果仍按 v1 口径解读）。见 `test_reranker_scoring_version`。

## 5. 真实模型推理

`test_reranker_real_model_inference`：本机存在 BGE-Reranker 权重（`BAAI/bge-reranker-base`）
时执行**真实业务级推理**（加载 201 权重张量 + 完整研究链路），断言有限分、不抛契约异常；
权重/依赖缺失时标记 `NOT_RUN`（SKIP），不以纯 Mock 冒充真实推理。

## 6. 结论

- 精排实际推理缺陷已修复，契约违规与权重损坏严格区分；
- Logits 融合严格单调、数值稳定、可解释，评分配置版本已升级；
- 14/14 回归用例通过（含真实 BGE-Reranker 推理）；
- 未触碰历史训练 checkpoint / 依赖锁定。
