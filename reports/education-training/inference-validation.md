# 第四阶段 4.2 · 推理与模型交付验证

- 生成时间：2026-10-28
- 机器可读来源：`reports/education-training/model-verification.json`
  （`scripts/education_training/verify_models.py` 产出，覆盖全部 16 个 run 目录，含冒烟 run）；
  推理接口测试另见 `tests/education_training/test_e5_inference.py`（本轮 36/36 全过）。
- 验证对象：`models/education/<model>/<run_id>/` 的 checkpoint + manifest + thresholds；
  每个 run 的文件清单（字节数 + SHA-256）记录在 `model-verification.json` 的 `files` 字段，可审计。

## 1. 保存→重载一致性

方法：训练/评估时落盘的 `predictions_validation_pseudo.npz` 前 2,000 行概率，
与**重新加载模型后**在同一批输入上重算的概率逐元素比较；阈值化标签要求逐行完全一致。

| 模型族 | 数值容差 | 实测最大绝对差 | 阈值化标签一致 | 判定 |
|---|---|---|---|---|
| TF-IDF×6 + 冒烟 | 1e-5（同设备重算） | 2.90e-08 ~ 2.98e-08 | 6/6 完全一致 | PASS |
| CharCNN×8 + 冒烟 | 1e-3（训练 CUDA / 校验 CPU 浮点差 ~1e-4） | 5.23e-05 ~ 1.16e-04 | 9/9 完全一致 | PASS |
| **合计 16/16** | | 全局最大 1.16e-04 | 16/16 | **PASS** |

配套一致性检查（16/16 全过）：单条推理 vs 批量推理标签一致；同一输入重复推理标签一致。

## 2. 验证脚本缺陷的披露与修复（重要）

最终流水线第一轮的 `verify_models` 步骤曾返回 rc=1（`run-all.json` step 31），
唯一失败项是 `tfidf-final-title` 的重载一致性（max_abs_diff=0.976）。

- **根因**：`verify_models.py` 构造验证输入时一律只取 `slot` 列，
  而 `tfidf-final-title` 的 `input_mode=slot_title`，
  评估落盘的预测由 `evaluate.py::_input_texts` 生成的 `slot ‖ 岗位名称` 输入产生。
  两边喂给同一个模型的输入不同，比较失去意义——**是验证脚本输入构造缺陷，不是模型损坏**：
  该模型在 `compare_models.py`（按 `input_mode` 构造输入）中评估正常，
  重载后异常输入、单条/批量、重复推理检查全部通过。
- **修复**：`verify_models.py` 改为复用 `evaluate.py::_input_texts`（与评估同一输入构造），
  按 `manifest.input_mode` 取 `slot` 或 `slot ‖ 岗位名称`。只改验证脚本，未动任何模型文件、数据与依赖。
- **复核**：修复后单独重跑 `verify_models.py`，`tfidf-final-title` max_abs_diff 从 0.976 降为 **2.98e-08**，
  全部 16/16 通过（单独复核记录见 `logs/verify_models.log` 23:35 行）；
  随后最终流水线整链重跑再次通过（`model-verification.json`，2026-10-29T00:29:17，16/16）。
- **工程接口提示**：`slot_title` 模型要求调用方传入 `槽位 ‖ 岗位名称` 拼接文本
  （`EducationNormalizer.batch()` 直接透传文本给模型）；slot-only 模型传原始槽位文本即可。
  推荐交付的 `tfidf-final` 为 slot-only，无此拼接要求。

## 3. 异常输入鲁棒性（8 类 × 16 run = 128 项，全部不崩溃）

| 输入 | 行为 | 评价 |
|---|---|---|
| 空字符串 / `None` / 纯空白 | 确定性规则兜底 → `学历不明`，`fallback_to_rule=true` | 符合标签规范 |
| `🎓硕士`（emoji） | 正常预测 `硕士` | 可接受 |
| `本科/硕士、博士；及以上?`（混合标点） | 预测 `博士,硕士` | 可接受 |
| `博士`×200（超长） | 预测 `博士` | 可接受 |
| `火星文学历`（未见表达） | 直接给出 `博士,硕士,本科`（无兜底） | **局限**：无输入合法性校验，低置信输出不拒识 |
| `985`（纯数字） | 直接给出 `博士,硕士,本科` | **局限**：同上；产品端应加输入类型校验 |

结论：接口层面不会因异常输入抛异常或返回空；但模型对"与学历无关的文本"不拒识，
输出的是拟合伪标签展开惯例的猜测。建议产品端在 4.3 之后补输入校验与低置信拒识策略，
本阶段如实记录，不掩饰。

## 4. CPU 推理延迟与资源

- 单样本延迟（CPU，`model-verification.json` 实测，16 个 run 区间）：**0.0165~0.0817 ms/样本**，
  全部低于 0.1 ms；批量 200 条探针（`experiment-comparison.json`→`inference_latency`）同量级。
- 模型大小：tfidf-final **27 KB**（2,160 参数）；charcnn **39 KB**（9,158 参数）；
  tfidf-final-title 20 MB（1,704,018 参数，词表占主）。
- 推理为纯 CPU 路径，不依赖 CUDA，符合 RTX 2050 部署后把 GPU 让给其他模块的约束。

## 5. 无标签依赖（推理不查真值）

- `predictor.py` 源码扫描（剥离注释与文档字符串后）：
  `label_tokens_json / label_multi_hot / label_status / label_raw / assistant / 人工正确结果 /
  label_provenance / is_gold` 命中数 **0**（`model-verification.json`→`predictor_source_check`）。
- 模型配置记录 `inference.requires_labels=false`、`supports_cpu=true`（各 run `config.json`）。
- 空输入/低置信时兜底走 `rules.rule_predict`（确定性规则），不查询任何历史标注。
- `test_e5_inference.py` 对上述接口语义有自动化覆盖（本轮 36/36 通过）。

## 6. 可重复性

- 同一输入重复推理、单条 vs 批量：16/16 run 标签逐行一致。
- 全流程两次独立执行（流水线第 1 轮 / 修复后第 2 轮）的对照指标一致性，
  记录于 `phase4-2-acceptance.md` §6。
- 所有 run 的模型文件 SHA-256 已存档（`model-verification.json`→`files`），
  可用于核对交付权重未被改动。
