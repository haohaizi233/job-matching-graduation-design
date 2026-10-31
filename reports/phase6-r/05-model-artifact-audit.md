# R5：模型产物与仓库质量审计（审计 + 整改建议）

- 生成时间：2026-10-31；分支 `fix/phase6-research-integration-hardening`
- 审计范围：公开仓库 `models/` 下全部 Git 跟踪产物（433 个文件，35.51 MB）
- 纪律：本轮**不**删除文件、**不**改写 Git 历史、**不** force-push。

## 1. 产物清单（实测）

| 扩展名 | 文件数 | 体积 | 内容 | 反序列化入口 |
|---|---|---|---|---|
| .json | 282 | 1.5 MB | manifest / config / feature_map / metrics | `json.load`（安全） |
| .npz | 71 | 10.7 MB | 预测矩阵（record_key / proba / pred） | `np.load(allow_pickle=False)`（安全） |
| .pt | 59 | 2.21 MB | PyTorch checkpoint（charcnn/mlp/ranknet） | `torch.load(map_location=cpu)` |
| .pkl | 20 | 21.09 MB | joblib 序列化模型（ridge/gbm/tfidf 词表权重） | `joblib.load` / `pickle.load` |
| .md | 1 | ~0 | models/README | — |

## 2. 逐项检查

### 2.1 模型文件来源
全部由本项目训练管线产出（`src/job_matching/training/`、`education/trainer.py`），
`manifest.json` 登记 `dataset_version` / `created_at` / `environment`（Python 3.11.18 +
torch 2.1.2+cu121 + sklearn 1.5.2 + RTX 2050）与逐文件 `sha256`。来源可追溯，
无第三方外来权重混入（BGE 编码器/精排器**不**在 models/ 下，由本地缓存提供）。

### 2.2 数据许可与分发许可
- **缺失**：`models/` 与仓库根均无 LICENSE 文件，训练数据源许可未随产物登记。
- 风险：公开分发 .pkl/.pt 权重前必须补充「训练数据许可 + 模型分发许可」声明。
- 建议：新增 `models/LICENSE-MODELS.md`（数据来源、许可、允许用途、免责），
  在每个 manifest 增加 `license` 字段（manifest 当前无任何许可字段，实测确认）。

### 2.3 敏感信息排查
- .npz 预测矩阵的 `record_key` 为 `rk<16位十六进制>` 哈希键（实测抽样
  `rk005690ee1fe17fe5`），**不含**原文/姓名/联系方式；proba/pred 为数值矩阵；
- .json 为配置/指标/特征映射，未发现简历原文、人名、PII；
- **残余风险**：`predictions_validation_pseudo.npz`（45226 条）基于伪标签验证集，
  record_key 若可回链到原始数据集需确认原始数据集许可；建议在 manifest 注明
  record_key 哈希算法与回链不可逆性声明。

### 2.4 预测矩阵与训练数据的泄露面
- 预测矩阵只有「键 + 概率 + 预测标签」，不含特征明细，反推训练样本难度高；
- 但模型本身记忆训练数据的风险存在（尤其 tfidf 词表权重 19 MB），
  **不得**把训练数据原文与权重放在同一公开包里（当前未发现原文，保持）。

### 2.5 哈希与版本
manifest 逐文件登记 `sha256 + bytes`；`configs/history-weights-baseline.json`
提供冻结基线，`scripts/phase5_1a/check_history_weights_integrity.py` 可校验
（缺失产物显式 NOT_RUN，不伪造）。

### 2.6 是否需要完整历史权重在公开仓库
- 433 个文件中 smoke/ablation 变体占多数（如 ridge 8 个 run 目录）；
- **建议**：公开仓库只保留 final 变体（论文引用所需），smoke/ablation 移至
  GitHub Release 资产；这属于「可选优化」，需用户批准后执行（涉及历史重写或
  大文件迁移，本轮不动）。

### 2.7 .gitignore 与 README 口径（不一致，已整改）
- `.gitignore` 现状：`models/**` 总忽略 + 扩展名白名单放行
  （json/md/txt/npz/npy/pkl/pt/pth），C4 门禁断言该敏感规则存在；
- README 原文称「`models/` 默认不入库」——与 433 个跟踪文件**矛盾**（缺陷 D8）；
- **整改**：README 口径已同步为「白名单入库 + 许可待补 + Release/LFS 迁移建议」
  （见 README『模型产物与分发』一节）。

### 2.8 .pkl 不安全反序列化边界
- `joblib.load` / `pickle.load` / `torch.load` 均可执行任意代码；
- 现有边界：只在 `ModelRegistry.load()` / 各 predictor 的 `from_model_dir()` 内
  加载**本仓库自有**产物，且注册表 `verify_checksum()` 可先校验 sha256；
- **建议（未实施，需用户批准）**：加载前强制 `verify_checksum`；对不受信来源
  的权重文档化「禁止加载」纪律；不升级 torch（历史 checkpoint 环境锁定）。

### 2.9 仓库体积与扩展影响
35.51 MB / 433 文件当前可接受；若追加多语言大模型或更多 run，建议改用
Git LFS（.pkl/.pt/.npz）或 GitHub Release 分发 + manifest 引用 sha256。

### 2.10 Artifact-dependent CI 覆盖
`artifact-dependent-validation` Job 对已跟踪权重执行 `check_history_weights_integrity.py`
与 `check_artifact_integrity.py`（必需 manifest，缺失显式 NOT_RUN 不计 PASS）。
已跟踪权重能被真实校验覆盖；但该 Job 仅 `workflow_dispatch` 触发，日常 PR
不跑（设计如此：真实产物检查与纯代码门禁分离）。

## 3. 三分法结论

| 类别 | 产物 | 处置 |
|---|---|---|
| 适合公开发布 | manifest/config/metrics/feature_map（.json）、final 权重（.pkl/.pt，补许可后） | 维持 Git 跟踪 |
| 适合 LFS / Release 分发 | smoke/ablation run、19MB tfidf 词表、预测矩阵（.npz） | 建议迁移（需批准） |
| 不可公开 | 真实简历（data/private/**）、真实 Gold 配对、授权文件 | **不在** models/，未跟踪（保持） |

## 4. 风险登记（不擅自执行）

1. 补充模型/数据许可文件（低成本，建议下轮执行）；
2. manifest 增加 `license` 与 record_key 不可逆声明（低成本）；
3. smoke/ablation 迁移 Release + git 历史瘦身（**涉及历史重写，先报告后执行**）；
4. 加载前强制 checksum 校验（行为变更，需回归验证）。
