# Phase 10-R2 训练验证报告

## LambdaMART 三协议训练结果

| 协议 | NDCG@5 | Recall@5 | 训练时间 | 树数 | 状态 |
|------|--------|----------|----------|------|------|
| candidate_cold | 0.318 | 0.376 | 1.2s | 5 | PASS |
| job_cold | 0.469 | 0.670 | 0.4s | 14 | PASS |
| double_cold | 0.437 | 0.568 | 0.1s | 1 | PASS |

## 撤回旧结论

| 旧结论 | 状态 | 原因 |
|--------|------|------|
| NDCG@5=1.000 | **RETRACTED** | 合成数据过拟合，非真实信号 |
| Recall@5=0.952 | **RETRACTED** | 合成数据+不同口径，不可与真实数据对比 |

## 全链路验证

| 步骤 | 状态 |
|------|------|
| 训练 → 保存 → 加载 → 预测 → 评估 | ✅ PASS |
| 标签映射严格性（未知标签报错） | ✅ PASS |
| Query Group连续性验证 | ✅ PASS |
| 保存/加载预测一致性 | ✅ PASS |

## 环境

- PyTorch: 2.10.0 (MPS available)
- LightGBM: 4.7.0
- Device: Apple M1 Max (CPU for LambdaMART)
