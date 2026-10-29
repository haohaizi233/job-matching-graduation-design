# 第四阶段 4.2 · 学历要求规范化模型训练 — 阶段验收报告

- 生成时间：2026-10-28
- 验收对象：`run-all.json`（最终流水线）、`results.json`、`experiment-comparison.json`、
  `model-verification.json`、`education-tests.json` 及 16 个 run 目录。
- 配套报告：`experiment-comparison.md`（对照与统计）、`inference-validation.md`（重载与推理）、
  `data-learnability.md` / `label-noise-analysis.md` / `error-analysis.md`（数据与错误分析）。
- **本报告只汇总证据与建议，最终验收结论（A/B/C）由用户签发。**

## 1. 验收清单逐项对照

| 验收项 | 要求 | 实测证据 | 判定 |
|---|---|---|---|
| 16 组模型实验 | 16/16 完成、结果完整、无 NaN | `experiment-comparison.json`：16 条目（2 基线 + 14 训练模型）全部含 val/gold 双集合指标；NaN/Inf 扫描 0 处；21 处 `null` 均为 0 样本分桶的"不可评估"（符合"不许填 0"约定）。另有 2 个冒烟 run 完成训练链路验证，按约定不入对照 | 通过 |
| 统一统计比较 | 16/16、1000 次组级 Bootstrap | `experiment-comparison.json`→`bootstrap`：14 个训练模型全部给出相对 `empirical_slot_baseline` 的配对差值；`n_resamples=1000`，seed=20261031 | 通过 |
| 统计有效性 | 分组采样正确、CI 与差值有效 | 重采样单位 = 输入组（槽位表达，validation 52 组），同组行不拆散；输出配对差值均值 + 95% CI（`_bootstrap_diff`，`compare_models.py`）；结论按 CI 是否含 0 表述 | 通过 |
| 模型重载验证 | 保存与重载后推理一致 | `model-verification.json`：16/16 通过；TF-IDF 最大差 2.98e-08（容差 1e-5），CharCNN 最大差 1.16e-04（CUDA 训练/CPU 校验，容差 1e-3），阈值化标签逐行完全一致；单条/批量、重复推理一致 | 通过（含一次验证脚本缺陷修复，见 §3） |
| 自动化测试 | 36/36、无异常跳过 | `education-tests.json`：tests=36, pass=36, fail=0, **skip=0** | 通过 |
| 结果汇总 | `run-all.json` 及 `results.json` 有效 | `run-all.json` 由最终流水线落盘（全部步骤 rc=0）；`results.json` 由 `scripts/education_training/build_results.py` 从上述 JSON 汇总 | 通过 |
| 阶段文档 | 三份 Markdown 完整 | `experiment-comparison.md` / `inference-validation.md` / 本文件 | 通过 |

## 2. 实验真实性核查

### 2.1 数据划分（`data/splits/education/manifest.json`，seed=20261031）

- train 180,903 / validation 45,226 / gold_holdout 736，比例 0.8/0.2（开发集内部）。
- 分组键 `user_hash`（规范化输入文本）：保证输入文本与记录键在集合间互斥。
- 重叠检查：`train&gold=0`、`validation&gold=0`（user_hash 与 record_key 两口径均为 0）。
  已知瑕疵如实记录：`job_id` 在 train&validation 间有 **1** 个交叉
  （job_id 本身非行级唯一键，全量重复 779 行），分组键不受影响，不构成标签泄漏。
- gold 隔离：与 gold 输入哈希重叠的开发集 762 行已剔除，
  `gold_used_for_rule_fitting=false`，gold 只做一次性评估。

### 2.2 评估协议

- 阈值只在 `validation_pseudo` 上选择（各 run `manifest.threshold_selected_on`）；
  gold 不参与训练、阈值与模型选择（`manifest.gold_policy` 原文记录）。
- 无独立盲测集的原因已在第三阶段记录并延续：
  原 default/test 100% 被 default/validation 覆盖，可用人工标签即那 736 条
  （`manifest.test_set_decision`）——本阶段未制造新真值。
- 输入特征只有槽位文本（及 title 变体的岗位名称文本），
  10 个派生评分字段与 `label_strength` **结构上不可能**进入输入；推理接口无标签依赖（`inference-validation.md` §5）。

### 2.3 随机种子

- 模型/训练种子：各 run `config.json`→`seeds.model=20261031`；
  训练入口构造模型前调用 `seed_everything`（含 cudnn.deterministic）。
- 切分种子：20261031；Bootstrap 种子：20261031（`compare_models.BOOTSTRAP_SEED`）。

### 2.4 标签来源与泄漏风险（口径声明）

- 开发集真值为 `pseudo_online` 伪标签（线上旧系统输出，人工一致率 45.92% = 338/736）；
  gold 为 `human_gold`（736 条）。所有指标均已随集合标注标签来源（`label_provenance` 字段）。
- 本阶段学习目标是**拟合旧系统的规范化口径**，不是真实就业结果；报告未做超出证据的表述。

## 3. 一次验证脚本缺陷：根因、修复与复核

最终流水线第 1 轮 `verify_models` 步骤 rc=1，唯一失败项 `tfidf-final-title` 重载一致性
（max_abs_diff=0.976）。根因是 `verify_models.py` 未按 `manifest.input_mode` 构造输入
（对该 slot_title 模型漏掉了岗位名称拼接），与落盘预测的输入不同；模型本身重载正常
（`compare_models.py` 按正确输入评估无异常，异常输入/单条/批量/重复检查全过）。
修复方式为复用 `evaluate.py::_input_texts` 统一输入构造，未改模型、数据与依赖；
修复后 max_abs_diff=2.98e-08，16/16 通过，随后最终流水线整链重跑再次全绿。
备份留痕：`logs/_run1_run_all.json`、`logs/_run1_model-verification.json`、
`logs/_run1_experiment-comparison.json`。

## 4. 资源与规模实测

| 项目 | 实测值 | 来源 |
|---|---|---|
| 训练数据 | 180,903 行（train）/ 45,226 行（validation）/ 736 行（gold） | `manifest.data` |
| 标签空间 | 6 token 多标签（`博士/硕士/本科/大专/学历不限/学历不明`） | `labels.LABEL_ORDER` |
| 参数量 | TF-IDF 2,160 / CharCNN 9,158 / title 变体 1,704,018 | 各 run `manifest.n_parameters` |
| 模型大小 | 27 KB（tfidf）/ 39 KB（charcnn）/ 20 MB（title） | `experiment-comparison.json` |
| 训练耗时 | TF-IDF 7~68 s/次；CharCNN 13~48 s/次（含评估落盘） | `logs/train-*.log` 首末时间戳 |
| GPU | RTX 2050（4 GB），CharCNN 训练 `device=cuda`，峰值显存 ~57 MB | `manifest.train_info`、训练日志 |
| 推理延迟 | CPU 0.017~0.087 ms/样本 | `model-verification.json` |
| 重复一致性 | 重复推理/单条 vs 批量 16/16 标签一致 | `model-verification.json` |

## 5. 学历语义专项核查（任务书重点）

证据来自 `error-analysis.md` §2/§3 与各 run `evaluation.json`（可复算）：

1. **学历层级错误**：主要错误形态不是"层级判低"，而是"层级过度展开"——
   `博士`/`硕士` 在伪标签上 recall≈1.0 但 precision 0.54~0.66（把「及以上」展开到更高层级的拟合副作用）。
   真正的层级替换错误（substitution）占比很小：validation 235~362 行、gold 4~12 行。
2. **学历缺失处理**：空输入走确定性规则返回 `学历不明`（产品行为固定，`inference-validation.md` §3）；
   但伪标签对空槽位口径分裂（48.7% vs 20.6% 两种惯例），导致该处行级 exact 仅 ~0.49——
   是标签口径问题，模型已按规范兜底。
3. **"本科及以上"→"仅本科"语义风险**：实测**未发生**。gold 上「本科及以上」exact=1.000（7 行）、
   「硕士及以上」exact=1.000（27 行），模型按"含更高层级"展开，与人工一致；
   反方向的风险（在裸「本科」「大专」上过度展开到博士/硕士）真实存在，源于 50/50 展开惯例冲突
   （gold「本科」exact 0.318、「大专/专科」0.238，人工惯例偏多多学历展开）。
   即：**该模型不会把"及以上"缩成"仅"，但会在歧义裸词上猜一种展开惯例**，
   这是当前标签噪声下的天花板（`data-learnability.md` §2）。
4. `学历不限`（gold 支持 1）/`学历不明`（gold 支持 2）样本不足，不做强结论。

## 6. 可复现性核查范围

已验证：同输入重复推理与单条/批量一致（16/16）；全部 run 文件 SHA-256 存档；
训练/切分/Bootstrap 种子固定并落盘。
全流程独立执行两轮（第 1 轮含验证脚本缺陷、第 2 轮修复后重跑）逐字段对比
（排除 `created_at`/`seconds`/`inference_latency` 等计时类字段）：

- `experiment-comparison.json`：全部主指标（exact / micro / macro P-R-F1 / Hamming /
  组合错误率 / 逐标签 / 错误类型 / 组宏 exact）、**全部 14 组 Bootstrap 配对差值与置信区间完全一致**；
- 差异仅 **1 个描述性单元格**：`tfidf-final-title` 的 validation `group_modal_match_rate`
  （0.826923 vs 0.884615）。根因已定位到 `src/job_matching/education/evaluator.py:46-47`：
  `max(set(keys), key=count)` 在**并列众数**时按 set 迭代顺序取值，
  受 Python 字符串哈希随机化（PYTHONHASHSEED）影响，跨进程可选出不同并列项。
- 影响评估：该字段是描述性指标，不参与模型选择、不进 Bootstrap、不进本报告任何结论表；
  对其余约 1500 个指标单元格零影响。对照第 1 轮备份可复核
  （`logs/_run1_experiment-comparison.json`）。
- 处置：为保持"已验收产物与代码一致"，本轮**不改**该指标实现（改后代码将无法复现已归档数值）；
  建议在 4-3 统一比较开始前把并列众数改为确定性规则（如先按字典序取候选）并统一重算，
  已列入"可暂缓处理"项。

未验证（如实声明）：跨机器复现、不同 CUDA/驱动版本下的复现、长时间训练的完全确定性。

## 7. 限制与后续人工标注建议

1. **标签质量是当前最大瓶颈**：伪标签人工一致率仅 45.92%，`本科/大专/硕士` 三个高频槽位
   存在两种展开惯例各占约 50%，冲突覆盖 99.91% 训练行——从输入不可消解。
2. 建议下一阶段（训练前）优先做：**① 定义唯一展开规范（推荐"含更高层级"）并人工改标
   79 个槽位表达的众数组合（约 55~79 次决策即可覆盖全量）；② 补 `学历不限/学历不明`
   各 ≥50 例；③ 补"应届/在校/实习"类表达样本（现仅 1 行，无法评估）**。
3. gold 非盲测（第三阶段已用于规则/阈值定义），若需可信盲测结论需另采一批人工标注。
4. 评估口径都是对代理标签/人工口径的拟合，不代表真实招聘效果。

## 8. 验收建议

工程与实验口径的硬性检查全部有实测证据支撑（16/16 实验、16/16 重载、36/36 测试、
统计口径正确、无 NaN、产物齐全、两次流水线留痕）。
制约项在数据侧而非工程侧：伪标签口径冲突与 gold 非盲测限制了"模型质量"结论的强度。

**建议结论：B（有条件通过）**——工程交付完整可信，但模型效果结论受标签质量与评估独立性限制，
须以 §7 的人工标注计划为后续条件。若验收方将"验证脚本曾需修复后重跑"视为过程性事项
（已披露、已复核、不影响模型与数据），则不构成阻断。
