# Phase 10-R 评估审计报告

## P0-1: Pairwise Accuracy 修复

### 问题
原实现使用 `np.triu(diff > tie_eps, k=1)` 只取上三角，遗漏反向偏好对。

### 修复
- 遍历所有无序对：`abs_diff > tie_eps`
- 根据真实相关性确定正确排序方向
- 同分预测计0.5

### 测试验证
- 7/7 顺序置换不变性测试通过
- 原始/反转/随机置换结果一致

## P0-2: LambdaMART 标签映射

### 标签映射
- weak_positive → 1
- medium_positive → 2
- strong_positive → 3

### 查询组验证
- 连续性检查
- 样本对齐验证

## P0-4: FastAPI 静态托管安全

### 目录穿越漏洞
原实现：`file_path = frontend_dist / path`（未验证路径）

### 修复
```python
file_path = (frontend_dist / path).resolve()
if not str(file_path).startswith(str(frontend_dist.resolve())):
    return {'detail': 'Not Found'}
```

## 评估指标口径

| 指标 | 定义 | 说明 |
|------|------|------|
| NDCG@5/10 | 归一化折损累计增益 | 主指标 |
| MRR@5 | 平均倒数排名 | 辅助 |
| Recall@5 | 召回率 | 注意上限=min(5,相关项数)/相关项数 |
| Pairwise Accuracy | 成对一致性 | 遍历所有无序对 |
