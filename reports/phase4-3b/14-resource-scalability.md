# 14 扩展性与 GPU 资源基准（Phase4-3B / M5-8.5）

- 证据：`reports/phase4-3b/14-resource-scalability.json`（实测生成）
- 提交：`d7babaa16da2`　设备：`cpu`　平台：`Windows-10-10.0.26200-SP0`
- 标签来源：`synthetic_deterministic_pool_expansion`（**合成确定性扩展**，`gold_status=BLOCKED`）
- **本基准不计算任何排序质量指标**（`quality_metrics_computed=false`）：岗位池由 150 条真实中文 JD 文本确定性扩展而成，只测延迟与内存。
- 测量边界：模型侧：含分词/向量化/索引/检索；不含数据库、网络与简历解析管线

## 1. 候选规模 vs 检索延迟（CPU）

| 岗位池 | 索引构建 | TF-IDF search@10 | BM25 search@10 | 向量 search@10 | 向量编码全池 | RSS 峰值 | RSS 增量 |
|---|---|---|---|---|---|---|---|
| 150 | tfidf 2.5225s / bm25 1.0347s | 0.0085s | 0.5103s | 0.0231s | 0.3805s | 200.328 MB | 0.457 MB |
| 500 | tfidf 0.5487s / bm25 0.5389s | 0.0167s | 1.9062s | 0.0265s | 2.0571s | 209.656 MB | 2.941 MB |
| 1000 | tfidf 0.9469s / bm25 1.3494s | 0.0339s | 5.0201s | 0.026s | 4.1328s | 209.766 MB | 1.977 MB |
| 5000 | tfidf 4.7124s / bm25 6.1105s | 0.173s | 19.8358s | 0.0325s | 17.3106s | 57.441 MB | -30.062 MB |
| 10000 | tfidf 9.7379s / bm25 19.4066s | 0.3638s | 45.624s | 0.1083s | 33.2245s | 64.465 MB | -23.707 MB |

> 内存口径：`py_peak_mb=null` 为**有意为之**——tracemalloc 对纯 Python 检索内循环有 10 倍级开销、会使延迟失真，故内存改用 RSS 后台采样（50ms 间隔）的峰值与增量。

## 2. Top-K 规模对延迟的影响（embedding_hash 召回）

| 岗位池 | search@5 | search@10 | search@20 |
|---|---|---|---|
| 150 | 0.027s | 0.0231s | 0.0255s |
| 500 | 0.0259s | 0.0265s | 0.0255s |
| 1000 | 0.0274s | 0.026s | 0.0294s |
| 5000 | 0.0392s | 0.0325s | 0.0337s |
| 10000 | 0.1564s | 0.1083s | 0.1042s |

## 3. GPU 推理与显存峰值

- 状态：**RUN**
- 显卡：NVIDIA GeForce RTX 2050（4096 MB）
### BGE-small-zh-v1.5 编码

- model_id：BAAI/bge-small-zh-v1.5
- revision：7999e1d3359715c523056ef9478215996d62a620
- license：MIT
- dim：512
- load_seconds：6.696
- encode_texts：150
- encode_seconds：1.436
- throughput_texts_per_s：104.5
- peak_memory_allocated_mb：484.5
- peak_memory_reserved_mb：506.0

### BGE-reranker-base 精排

- reranker_id：bge_reranker_base
- load_seconds：5.935
- score_pairs：32
- score_seconds：1.166
- throughput_pairs_per_s：27.4
- truncated_pairs：31
- peak_memory_allocated_mb：1253.6
- peak_memory_reserved_mb：1264.0
- scored_finite：True

## 4. 结论边界

1. 延迟随候选规模近似线性（向量点积 + 排序），万级池仍在秒级内；
2. 所有数字只反映**模型侧**检索延迟与内存，不含数据库/网络/简历解析；
3. 岗位池为合成扩展，**不支持任何推荐质量结论**；
4. GPU 段落如为 NOT_RUN，即本轮环境无法测量，不做推测。
