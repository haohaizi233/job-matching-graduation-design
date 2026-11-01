# models/ 产物的来源、许可与安全边界（Phase7 / P7-5）

- 建立时间：2026-10-31
- 版本：`models-license-v1`
- 审计范围：Git 跟踪的 `models/**` 全部产物（约 433 个文件 / 35.5 MB，实测见
  `reports/phase6-r/05-model-artifact-audit.md`）
- **纪律**：本文件只登记**本地可核**的事实。凡无法证实的许可一律写 `UNKNOWN`，
  **不自行编造 MIT / Apache-2.0 或任何 SPDX 标识**。`UNKNOWN` 即保留分发阻断。

---

## 一、总览：能否公开分发？

| 结论 | 说明 |
|---|---|
| **当前不可公开分发权重** | 训练数据许可与模型分发许可均未完全证实 |
| 可公开 | `*.json`（配置/指标/manifest/feature_map）、本文件、README |
| 需补证据后方可公开 | `*.pkl` / `*.pt` / `*.pth` / `*.npz` / `*.npy` 权重与预测矩阵 |
| 绝不可公开 | 真实简历（`data/private/**`）、真实 Gold 配对、授权同意书（均不在 `models/`，保持） |

> 仓库根目录同样**没有** `LICENSE` 文件——整个仓库的分发许可本身是 `UNKNOWN`。
> 在补齐之前，`models/` 下的二进制权重即使已 Git 跟踪，也不代表已获得再分发授权。

---

## 二、按模型族的来源与许可登记

### 2.1 人岗匹配模型（`models/matching/{ridge,gradient_boosting,mlp,ranknet}/`）

| 项 | 值 | 证据 |
|---|---|---|
| 训练数据 | `data/raw/job-resume-matching/`（`cv.csv` 9,544 行 + `job.csv` 1,167 行 + `matches.csv` 122,560 行） | `docs/datasets/README.md` 第 1 节 |
| 数据来源 | Hugging Face `snapshot_download` 快照；**具体 repo id UNKNOWN（本地无证据）** | 同上 |
| **数据许可** | **UNKNOWN** | 卡片 front-matter 写 `license: mit`，但正文 "License" 一节写 *"Please update the dataset license before publishing."* —— **两者矛盾**，按 `UNKNOWN` 处理 |
| 标签性质 | **英文代理标签**（`label_strength` / `final_score` / `candidate_rank`），非人工中文相关性真值 | `matches.csv` 字段 |
| **模型分发许可** | **UNKNOWN** | 无 LICENSE 文件、`manifest.json` 无 `license` 字段（实测） |
| 允许用途 | 内部研究/诊断（`evaluation_status=research_only_proxy_labels`，`formal_use_allowed=False`） | `service/model_registry.py` |
| 禁止用途 | 作为中文人岗匹配效果结论、对外发布、商业使用 | 同上 |

### 2.2 学历要求抽取模型（`models/education/{tfidf,charcnn}/`）

| 项 | 值 | 证据 |
|---|---|---|
| 训练数据 | `data/raw/job-education/`（train 197,574 / validation 45,593 / test 22,730 / annotated 22,730 行） | `docs/datasets/README.md` 第 2 节 |
| 数据来源 | Hugging Face 快照，创建者 **@wangzihaogithub**（本地 README 明确声明）；repo id UNKNOWN | 同上 |
| **数据许可** | **`apache-2.0`** | 数据集卡片 front-matter 声明，本地文件可核 |
| **模型分发许可** | **UNKNOWN** | 无 LICENSE 文件、`manifest.json` 无 `license` 字段（实测） |
| 允许用途 | 研究用途（Apache-2.0 允许）；分发前仍需补模型许可声明 | — |
| 附加限制 | 训练语料与岗位候选池存在文本重合（见 `reports/phase7/01-data-intake-audit.md` 4.2），评价时必须披露 | — |

### 2.3 第三方预训练模型（不在 `models/` 下，由本地缓存提供）

| 组件 | 用途 | 许可 | 状态 |
|---|---|---|---|
| BGE 中文向量模型（`models/text_encoder.py` 调用） | 语义召回 | 由模型发布方的模型卡决定 | **UNKNOWN（本地未随仓库登记模型卡/许可副本）** |
| Cross-Encoder 精排器（`models/reranker.py`） | 精排 | 同上 | **UNKNOWN** |
| jieba | 中文分词 | MIT（上游声明） | 可用，但仓库内未随附许可副本 |

**要求**：使用第三方权重前必须把其 LICENSE / 模型卡许可副本存入
`data/private/consent/evidence/`（不入库）并在本表登记名称与版本；缺证据即 `UNKNOWN`。

### 2.4 预测矩阵（`predictions_*.npz`）

| 项 | 值 |
|---|---|
| 内容 | `record_key`（`rk<16 位十六进制>` 哈希键）+ `proba` / `pred` 数值矩阵 |
| PII | 实测抽样未发现原文/姓名/联系方式 |
| **回链风险** | `record_key` 由原始数据集行派生；若哈希算法与种子可获得，理论上可回链 |
| 要求 | manifest 必须注明 `record_key` 哈希算法与**回链不可逆性声明**；`predictions_validation_pseudo.npz`（45,226 条）基于伪标签验证集，回链目标数据集许可 = `UNKNOWN` |

---

## 三、反序列化安全边界（Phase7 已落地）

`joblib.load` / `pickle.load` / `torch.load` 都可能执行任意代码。当前边界：

| 边界 | 实现 | 状态 |
|---|---|---|
| 只加载本仓库自有产物 | `ModelRegistry._default_loader` / 各 predictor `from_model_dir` | 已有 |
| **加载前强制 sha256 校验** | `service/model_registry.py::ModelRegistry.load` → `verify_checksum`，不匹配抛 `MODEL_ARTIFACT_TAMPERED` | **Phase7 新增** |
| 校验可显式关闭 | `ModelRegistry(verify_before_load=False)`（仅限受控测试） | Phase7 新增 |
| 负向测试 | `tests/phase7/test_model_artifact_guard.py`（篡改/缺失/登记后改写/未登记跳过/关闭开关） | Phase7 新增 |
| 不受信来源 | **禁止加载**（见第四节纪律） | 纪律条款 |

兼容性说明：未登记 `artifacts` 或未给 `sha256` 的模型**跳过**校验，保持既有行为
（最小改动原则）；一旦 manifest 登记了 `sha256`，校验即强制。

---

## 四、许可与安全纪律（不可协商）

1. **禁止加载不受信来源的权重**：任何非本仓库训练管线产出的 `.pkl` / `.pt` / `.pth`，
   在来源与许可未证实前一律不得进入加载路径；
2. **禁止编造许可**：无法证实的许可只能写 `UNKNOWN`，并保留分发阻断；
3. **禁止把训练数据原文与权重同包分发**：`.pkl`（尤其 tfidf 词表权重约 19 MB）
   有记忆训练数据的风险；
4. **禁止改写历史权重**：历史 checkpoint 的环境锁定（Python 3.11.18 + torch 2.1.2+cu121
   + sklearn 1.5.2）不得为"让它能加载"而重训或覆盖；
5. **撤回联动**：真实用户撤回授权后，若某产物可回链到该用户，必须一并删除/重建
   （见 `docs/evaluation/phase7-data-collection-operations.md` 第六节）。

---

## 五、待办（需人工决策，本轮不擅自执行）

| # | 事项 | 风险等级 | 状态 |
|---|---|---|---|
| 1 | 向 `job-resume-matching` 数据提供方确认许可（`mit` 与正文声明矛盾） | 高 | **待人工核实** |
| 2 | 补 `all_df.csv` 来源与许可 | 高 | **待人工核实** |
| 3 | 登记 BGE / Cross-Encoder 模型卡许可副本 | 中 | **待人工核实** |
| 4 | 每个 `manifest.json` 增加 `license` 与 `record_key` 不可逆声明字段 | 中 | 建议下轮执行 |
| 5 | 为仓库补根 `LICENSE` | 中 | 需作者决定许可证类型 |
| 6 | smoke/ablation run 迁移到 GitHub Release / LFS | 低 | 涉及历史重写，**先报告后执行** |

---

## 六、三分法结论（沿用 R5 审计，已按 P7-5 更新）

| 类别 | 产物 | 处置 |
|---|---|---|
| 适合公开 | manifest / config / metrics / feature_map（.json）、本文件 | 维持 Git 跟踪 |
| 补许可后方可公开 | final 权重（.pkl/.pt）、预测矩阵（.npz） | **暂缓公开**，等第 1–3 项核实 |
| 绝不可公开 | 真实简历、真实 Gold 配对、授权同意书 | 不在 `models/`，`.gitignore` 已隔离 |
