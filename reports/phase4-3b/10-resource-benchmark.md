# 10 资源与性能基准（Phase4-3B / M5-8.5）

- 证据：`reports/phase4-3b/10-resource-benchmark.json`（实测生成）
- 硬件：NVIDIA GeForce RTX 2050（4096 MB）可用，**本轮基准在 CPU 上执行**（device=cpu 逐项登记）。
- 测量范围说明：编码/精排基准**包含**分词与张量构建，**不含**数据库与文本预处理管线；端到端召回基准为纯召回阶段（离线向量）。

## 1. 编码器

| 项 | 哈希 n-gram（dim=512） | BGE-small-zh-v1.5（dim=512，CPU） |
|---|---|---|
| 模型加载 | 0.0004 s | 0.312 s |
| 单条编码 | 4.5 ms | 22.1 ms |
| 批量 64 条 | 180.9 ms | 286.7 ms |
| 吞吐 | ≈353 texts/s | **223.2 texts/s** |
| Python 峰值内存增量 | — | 4.38 MB |

## 2. 精排（BGE-Reranker-base，CPU）

| 项 | 实测 |
|---|---|
| 模型加载 | 3.439 s |
| 单对打分 | 61.1 ms |
| 批量 16 对 | 333.6 ms（≈20.9 pairs/s） |
| 截断 | max_length=256，逐批登记 truncated_pairs |

## 3. 端到端召回（8 查询 × 55 岗位池，离线哈希向量）

| Top-K | 耗时 |
|---|---|
| 5 | 60.1 ms |
| 10 | 114.0 ms |
| 20 | 81.2 ms |
| 55（全池） | 89.8 ms |

Top-K 规模对延迟无单调影响（候选少、开销由批量构造主导）；查询规模小时毫秒级。

## 4. 模型加载与检查点

- sklearn 系列 checkpoint 加载 0.3–0.8 s；torch（education charcnn）同量级。
- matching 系列万行级批量推理：1.5–3.7 ms（`predictions_*.npz` 复算，见 02）。

## 5. 扩展性与部署含义

1. 当前实现为纯 CPU 可运行（满足任务书「CPU 环境可跑基础模型」）；4GB 显存下 BGE-small + reranker-base 也完全可放 GPU，但非必需。
2. 岗位池 55 条的召回毫秒级完成；千级池**已实测**（见 14-resource-scalability.md：10000 条池 TF-IDF search@10 0.36s、向量 search@10 0.11s；BM25 45.6s 为当前实现瓶颈）。
3. 端到端推荐耗时（含解析/数据库/API）未在本报告测量——属于 Phase5-3 集成侧，本报告边界明确为模型侧。
4. ~~显存峰值未测~~ → **已测**（14-resource-scalability.md：BGE 编码峰值 84.5 MB、精排峰值 1253.6 MB，4GB 显存充裕）；GPU 混合精度可用性未测（无训练任务）——NOT_RUN。

## 6. 未执行登记

- ~~千级/万级岗位池扩展性：NOT_RUN~~ → **已执行**，见 `14-resource-scalability.md`（150/500/1000/5000/10000 五档实测 + GPU 显存峰值）。
- ~~GPU 推理基准与显存峰值：NOT_RUN~~ → **已执行**，见 `14-resource-scalability.md` 第 3 节（RTX 2050：BGE 编码 504.5 texts/s、峰值 84.5 MB；reranker 27.4 pairs/s、峰值 1253.6 MB）。
- 含数据库的端到端延迟：NOT_RUN（非本 Agent 职责边界）。
