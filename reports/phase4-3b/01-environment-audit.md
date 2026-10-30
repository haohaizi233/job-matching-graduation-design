# 01 环境审计（Phase4-3B / M1-4.1）

- 探测时间：2026-10-31
- 证据：`reports/phase4-3b/model-compatibility-runs.json` 的 `environment` 块、`10-resource-benchmark.json` 的 `device_probe`

## 1. 运行时

| 项 | 实测值 |
|---|---|
| Python | 3.11.18（conda env `graduation-design`） |
| NumPy | 1.26.4 |
| Pandas | 2.2.3 |
| scikit-learn | 1.5.2 |
| Joblib | 1.6.0 |
| SciPy | 1.15.3 |
| PyTorch | 2.1.2+cu121 |
| transformers | 4.40.2 |
| jieba | 0.42.1 |

未修改任何现有 Conda 环境依赖；BGE 系列全部通过 transformers + 显式 mean pooling 实现，不依赖 sentence-transformers。

## 2. 硬件

| 项 | 实测值 |
|---|---|
| CUDA 可用 | 是（torch.cuda.is_available()=True） |
| GPU | NVIDIA GeForce RTX 2050 |
| 显存 | 4096 MB |
| 本轮实验实际设备 | **CPU**（检索/精排基准均登记 device=cpu，显存预算不作为前置） |

## 3. 模型权重资产

| 模型 | revision（固定） | 许可证 | 来源 |
|---|---|---|---|
| BAAI/bge-small-zh-v1.5 | 7999e1d3359715c523056ef9478215996d62a620 | MIT | HF snapshot_download（固定 sha） |
| BAAI/bge-reranker-base | 2cfc18c9415c912f9d8155881c133215df768a70 | MIT | 同上 |

权重存放于 HF 本地缓存（`%USERPROFILE%\.cache\huggingface`），**不进入 Git**；`src/job_matching/models/text_encoder.py::KNOWN_REVISIONS` 登记精确 revision 与许可证，测试在 `local_files_only=True` 下运行（离线可复现）。

## 4. 历史模型依赖对齐情况

历史记录（sklearn 1.5.2 / torch 2.1.2 / CUDA 12.1）与本机实测**完全一致**，因此本轮未触发 Legacy 环境；历史「GB checkpoint 跨版本反序列化失败」风险在当前环境未复现（14/14 LOADED），但跨版本风险保留登记，见 `02-model-compatibility.md`。

## 5. 结论

当前环境具备：全部历史 checkpoint 加载与推理、中文向量编码（CPU/BGE）、Cross-Encoder 零样本精排、E00–E06 检索原型全流程。
不具备：真实人工 Gold（数据缺失，非环境问题）、4GB 显存下的大模型全参数微调（按任务书纪律不执行）。
