# P7-5 模型资产、许可与安全收口

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 审计范围：Git 跟踪的 `models/**`（约 433 文件 / 35.5 MB）+ 训练数据源 + 第三方预训练模型 + 反序列化边界
- 证据产物：
  - [`models/LICENSE-MODELS.md`](../../models/LICENSE-MODELS.md)（来源/许可/安全边界登记）
  - `src/job_matching/service/model_registry.py`（Phase7 新增加载前哈希门禁）
  - `tests/phase7/test_model_artifact_guard.py`（9 项含负向测试）
- **纪律**：未证实的许可一律 `UNKNOWN`，不编造 SPDX 标识；本轮**不**改写 Git 历史、
  **不**批量迁移 LFS、**不**删除 Release、**不** force-push。

---

## 一、训练数据真实来源与许可

| 模型族 | 训练数据 | 来源可核性 | 数据许可 | 结论 |
|---|---|---|---|---|
| `matching/{ridge,gradient_boosting,mlp,ranknet}` | `data/raw/job-resume-matching/`（英文，9,544 CV + 1,167 JD + 122,560 匹配） | HF `snapshot_download` 快照；**repo id UNKNOWN（本地无证据）** | **UNKNOWN** | 卡片 front-matter 写 `mit`，正文写"Please update the dataset license before publishing"——**自相矛盾**，按 UNKNOWN 处理，**保留阻断** |
| `education/{tfidf,charcnn}` | `data/raw/job-education/`（197,574 / 45,593 / 22,730 / 22,730 行） | HF 快照，创建者 **@wangzihaogithub**（本地 README 明确声明）；repo id UNKNOWN | **`apache-2.0`** | 卡片 front-matter 声明，本地文件可核 |
| 岗位候选池 `job_pool_v1` | `job-education/annotated` + `job-education/default-test` | 同上 | **`apache-2.0`** | 但含 `historical_gold_in_source=736` 条历史标注，须隔离 |
| 岗位字段补充 `all_df.csv` | `data/raw/other/all_df.csv` | 目录内无 README/元数据 | **UNKNOWN** | 无来源无许可，**保留阻断** |
| 预训练 BGE / Cross-Encoder | 本地缓存，不在 `models/` | 未随仓库登记模型卡 | **UNKNOWN** | 需补许可副本 |

**没有伪造任何许可**：以上 `UNKNOWN` 均为实测结论，不是遗漏。

---

## 二、模型发布许可

| 检查项 | 实测 |
|---|---|
| 仓库根 `LICENSE` | **不存在** → 整个仓库分发许可 `UNKNOWN` |
| `models/LICENSE-MODELS.md` | **本轮新增**（此前不存在） |
| 各运行目录 `manifest.json` 的 `license` 字段 | **全部缺失**（R5 审计实测） |
| `manifest.json` 的 `dataset_version` / `created_at` / `environment` | 齐全，来源可追溯 |
| `manifest.json` 逐文件 `sha256 + bytes` | 齐全 |

**结论：当前不具备公开分发模型权重的许可条件。** 权重虽已 Git 跟踪，但"已入库"≠"已获再分发授权"。

| 产物 | 分发处置 |
|---|---|
| `*.json`（配置/指标/manifest/feature_map） | 可公开 |
| `models/LICENSE-MODELS.md` | 可公开 |
| final 权重（`.pkl` / `.pt`） | **暂缓**，等数据许可 + 模型许可核实 |
| 预测矩阵（`.npz`） | **暂缓**，需 `record_key` 不可逆性声明 |
| smoke / ablation run | 建议迁 GitHub Release / LFS（**涉及历史重写，先报告后执行**） |
| 真实简历 / 真实 Gold / 同意书 | **绝不可公开**（不在 `models/`，`.gitignore` 已隔离） |

---

## 三、权重 SHA-256 与可信加载（Phase7 已落实）

### 3.1 威胁模型

`joblib.load` / `pickle.load` / `torch.load` 均可执行任意代码。
若不受信权重进入加载路径，等于向进程注入任意代码执行。

### 3.2 最小改动实现

`src/job_matching/service/model_registry.py::ModelRegistry.load`：

```text
load(model_id)
  ├─ 缓存命中 → 直接返回
  ├─ loader == "future" → FUTURE_MODEL_UNAVAILABLE
  ├─ [Phase7 新增] verify_before_load=True 时先 verify_checksum(model_id)
  │     └─ checksum_ok=False → 抛 ServiceError("MODEL_ARTIFACT_TAMPERED")
  │        **在反序列化之前**中断，绝不触发 joblib/torch/pickle 加载
  └─ _loader_impl(reg) 真正加载
```

兼容性最小改动原则：
- **未登记 `artifacts` 或未给 `sha256` 的模型跳过校验**（保持既有行为）；
- 一旦 manifest 登记了 `sha256`，校验即强制；
- 可用 `ModelRegistry(verify_before_load=False)` 显式关闭（仅限受控测试）。

### 3.3 负向测试（`tests/phase7/test_model_artifact_guard.py`，9 项）

| 用例 | 验证 |
|---|---|
| `test_load_ok_when_checksum_matches` | 正常加载不被误伤 |
| `test_load_refused_when_checksum_mismatched` | 哈希不符 → `MODEL_ARTIFACT_TAMPERED`，**加载器未被调用** |
| `test_load_refused_when_artifact_missing` | 文件缺失 → 同样拒绝 |
| `test_content_tamper_detected_after_registration` | 登记后改写文件也能检出 |
| `test_no_artifacts_registered_skips_check` | 未登记保持兼容 |
| `test_no_sha256_registered_skips_check` | 无 sha256 保持兼容 |
| `test_verify_can_be_disabled_explicitly` | 显式关闭开关可用 |
| `test_load_event_not_recorded_on_refusal` | 拒绝不产生 load_event（可审计性） |
| `test_untrusted_source_documented` | 纪律文档存在且含"禁止加载"/"UNKNOWN" |

---

## 四、`.pkl` 反序列化安全边界汇总

| 入口 | 文件类型 | 现有边界 | Phase7 补充 |
|---|---|---|---|
| `models/ridge.py::load` | `.pkl` (joblib) | 只加载本仓库自有 run 目录 | 加载前哈希校验（经 `ModelRegistry`） |
| `models/gradient_boosting.py::load` | `.pkl` (joblib) | 同上 | 同上 |
| `education/tfidf_model.py::load` | `.pkl` (pickle) | 同上 | 同上 |
| `models/{mlp,ranknet}.py::load` | `.pt` (torch) | `map_location="cpu"` | 同上 |
| `education/neural_model.py::load` | `.pt` (torch) | `map_location="cpu"` | 同上 |
| `models/text_encoder.py` / `embeddings.py` / `pipeline.py` | `.npy/.npz` | `np.load(allow_pickle=False)`（安全） | 无需 |
| `training/trainer.py` | `.pt` | `torch.load(map_location=...)` | 训练侧，受本地文件系统保护 |

**纪律**：不受信来源的权重**禁止加载**（`models/LICENSE-MODELS.md` 第四节）。
不升级 torch（历史 checkpoint 环境锁定为 Python 3.11.18 + torch 2.1.2+cu121 + sklearn 1.5.2）。

---

## 五、公开仓库预测文件的回链风险

| 产物 | 风险 | 处置 |
|---|---|---|
| `predictions_*.npz` 的 `record_key`（`rk<16 位 hex>`） | 若哈希算法/种子可得，理论上可回链原始数据行 | **需在 manifest 声明哈希算法与不可逆性**（待办 #4） |
| `predictions_validation_pseudo.npz`（45,226 条） | 回链目标为英文代理标签数据集，许可 `UNKNOWN` | 暂缓公开 |
| `predictions_gold_holdout_human.npz` | 名称含 "gold_holdout_human"，需确认其 Gold 口径与本项目人工 Gold 的区别 | **待人工核实**（不得与 H2 人工 Gold 混淆） |
| tfidf 词表权重（约 19 MB） | 记忆训练数据的风险 | 不得与训练原文同包分发 |

实测抽样（R5）：`.npz` 中未发现简历原文 / 姓名 / 联系方式；`.json` 为配置与指标，无 PII。

---

## 六、真实用户撤回数据后的影响

按 `docs/evaluation/phase7-data-collection-operations.md` 第六节撤回流程，派生产物联动：

| 派生产物 | 撤回后动作 |
|---|---|
| 简历原文 / 脱敏副本 | 删除 |
| 标注记录 / 仲裁记录 | 删除 |
| 已冻结 Gold 版本 | **作废并重新冻结**（升 `dataset_version`） |
| 依赖该样本的聚合统计 | 重建 |
| 训练产物（若曾入训，当前**未发生**） | 需重训或标注影响范围 |

**当前状态**：尚无真实用户数据进入训练或评估链路，故无既有产物受影响。
但 `data/private/resumes/` 中那 1 份无授权文件必须由真人决定处置（补授权或删除）。

---

## 七、风险登记与待办（不擅自执行）

| # | 事项 | 风险 | 需要 | 状态 |
|---|---|---|---|---|
| 1 | 向 `job-resume-matching` 提供方确认许可 | 高 | **人工** | 待核实 |
| 2 | 补 `all_df.csv` 来源与许可 | 高 | **人工** | 待核实 |
| 3 | 登记 BGE / Cross-Encoder 模型卡许可副本 | 中 | **人工** | 待核实 |
| 4 | `manifest.json` 增加 `license` + `record_key` 不可逆声明 | 中 | 代码 | 建议下轮 |
| 5 | 仓库补根 `LICENSE` | 中 | **人工**（作者选许可证） | 待决策 |
| 6 | `predictions_gold_holdout_human.npz` 的 Gold 口径核实 | 中 | **人工** | 待核实 |
| 7 | smoke/ablation 迁 Release / LFS + 历史瘦身 | 低 | 代码 + **授权** | **先报告后执行**（涉及历史重写） |

---

## 八、结论

| 维度 | 结论 |
|---|---|
| 训练数据来源可追溯 | **部分**（`job-education` 可核；`job-resume-matching` / `all_df` 不可核） |
| 数据集使用许可 | **部分**（`apache-2.0` 1 项；`UNKNOWN` 2 项） |
| 模型发布许可 | **UNKNOWN（阻断）** |
| 第三方预训练许可 | **UNKNOWN（阻断）** |
| 模型 Manifest | 齐全但缺 `license` 字段 |
| 权重 SHA-256 | 已登记，**且已强制加载前校验** |
| `.pkl` 反序列化边界 | 已收紧（哈希门禁 + 不受信禁载 + 负向测试） |
| 预测文件回链风险 | 有残余风险，需 manifest 声明 |
| 撤回联动 | 流程就绪，当前无受影响产物 |

**整体：`UNKNOWN` 项保留阻断，不宣布许可合规。** 本轮只补齐了可证实的部分与安全门禁。
