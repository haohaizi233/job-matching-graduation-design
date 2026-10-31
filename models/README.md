# models/：训练产物登记（Phase6 交付物）

本目录存放**训练产物**（模型权重、checkpoint、预测矩阵、指标与配置元数据）。
Phase6 起这些产物作为毕业设计交付物按白名单入库，白名单之外的任何文件仍被
`.gitignore` 忽略（规则见仓库根 `.gitignore` 的 `models/**` 段落）。

## 入库白名单（与 .gitignore / C4 门禁一致）

| 扩展名 | 含义 |
| --- | --- |
| `*.pkl` / `*.pt` / `*.pth` / `*.npy` | 模型权重与训练 checkpoint（二进制，`.gitattributes` 钉死 binary） |
| `*.npz` | 预测矩阵 / 验证集打分等数组产物 |
| `*.json` | 运行元数据：`config.json`、`metrics.json`、`evaluation.json`、`manifest.json`、`feature_map.json`、`history.json`、`thresholds.json` 等 |
| `*.md` / `*.txt` | 说明与登记文本 |

## 目录结构

```
models/
├── matching/                      # 人岗匹配模型（Phase4-3）
│   └── <family>/                  # ridge / ranknet / mlp / gradient_boosting
│       └── <scenario>/            # candidate_cold / job_cold / double_cold
│           └── <family>-<scenario>-<tag>-<YYYYMMDD-HHMMSS>/
└── education/                     # 学历要求抽取模型（Phase4-3B）
    └── tfidf/ | charcnn/
        └── <family>-<tag>-<YYYYMMDD-HHMMSS>/
```

运行目录命名约定：`<family>-<scenario>-<tag>-<时间戳>`；`tag` 常见取值：
`final`（正式）、`smoke`（冒烟）、`ablation-*`（消融）、`highconf` / `balanced` /
`confw` / `holdout` / `vloss` / `title`（训练与采样口径变体）。

## 单个运行目录内的产物

* `model.pkl` / `model.pt`：最终导出权重；`checkpoint_best.pt` / `checkpoint_search_*.pt`：训练与搜索 checkpoint；
* `metrics.json` / `metrics_validation.json` / `metrics_test.json` / `evaluation.json`：指标与评估结论；
* `config.json` / `feature_map.json` / `history.json` / `thresholds.json` / `manifest.json` / `pair_stats.json`：可复现所需的配置与统计；
* `predictions_*.npz`：验证 / 测试 / Gold 盲测打分矩阵（复核阈值与误差分析用）。

## 一致性与复现

* 运行目录的登记与一致性校验见 `reports/model-research/runs/`（结构化实验记录，同样入库）；
* 学历模型训练与评估流水线记录见 `reports/education-training/`；
* 干净 checkout 导出时本目录整体被剥离（`scripts/phase5_1a/verify_fresh_checkout.py`），
  以证明 Core CI 不依赖真实数据与权重即可运行。
