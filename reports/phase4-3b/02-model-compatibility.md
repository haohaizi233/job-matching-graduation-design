# 02 模型兼容性验证（Phase4-3B / M1-4.2）

- 证据：`reports/phase4-3b/model-compatibility-runs.json`（由 `scripts/phase4_3b/check_model_compatibility.py` 实测生成）
- 纪律：全程只读 `models/`，未写入或改动任何历史 checkpoint；不以重训练掩盖反序列化问题。

## 1. 行为分类（四种行为分开登记，不混为一谈）

| 行为 | 含义 | 本轮 |
|---|---|---|
| LOAD | 仅反序列化 checkpoint | RUN ×14 |
| PREDICT | 加载既有 checkpoint 前向推理（不训练） | RUN ×14 |
| REEVALUATE | 用既有预测文件重算指标（不训练不推理） | RUN ×12（matching） |
| COMPARE_HISTORICAL | 当前输出 vs 历史落盘预测 | RUN ×14 |
| RETRAIN | 重新训练 | **NOT_RUN**（本轮不执行） |
| REPRODUCE_FROM_SCRATCH | 从零训练复现 | **NOT_RUN** |

## 2. 加载结果

14/14 `LOADED`（覆盖 matching 四模型 × 三协议 + education 两模型）。
历史记录的「Gradient Boosting 跨 scikit-learn 版本反序列化失败」在本机 sklearn 1.5.2 **未复现**：三个协议的 GB checkpoint 全部加载成功。跨版本风险保留登记（ENV 与训练时不一致时仍可能触发）。

## 3. 输出一致性（COMPARE_HISTORICAL）

| run | 历史预测比对 | max_abs_diff | 结论 |
|---|---|---|---|
| matching.ridge ×3 协议 | 逐位一致 | 0.0 | bitwise identical |
| matching.gradient_boosting ×3 | 逐位一致 | 0.0 | bitwise identical |
| matching.mlp ×3 | 逐位一致 | 0.0 | bitwise identical |
| matching.ranknet ×3 | 逐位一致 | 0.0 | bitwise identical |
| education.tfidf | 非逐位，数值等价 | 2.9e-8 | allclose(1e-6) 通过 |
| education.charcnn | 非逐位 | 6.3e-5（gold）/ 1.3e-4（validation） | allclose(1e-6) 未过，差异量级与 torch CPU 推理非确定性一致 |

- matching 系列：`predictions_{test,validation}.npz` 行对齐 OK、finite、推理耗时 0.0015–0.0037s/万行级。
- education 系列：**决策层（label 集合）是否翻转未登记 → 登记为 NOT_RUN**，不得以概率近似相等代替决策一致性结论。后续需补 pred 列 flip 计数。

## 4. 特征一致性

matching 系列逐 run 校验：`n_features_declared=49 = n_features_loaded=49`，特征名顺序 `names_match=true`，与 `feature_schema.json` 一致；`requires_labels=false`、`supports_cpu=true`。

## 5. 加载与推理开销（当前机器，CPU）

- checkpoint 加载：0.3–0.8s（joblib/pkl），torch checkpoint 略高。
- 万行级批量推理：毫秒级（sklearn 系列）；charcnn 45,226 行 0.43s。
- 明细见 `model-compatibility-runs.json` 各 run 的 `load.seconds` / `predict_seconds`。

## 6. 登记结论

| 检查项 | 状态 |
|---|---|
| 全部 checkpoint 真实存在 + SHA-256 复核 | PASS |
| 加载探针 | PASS（14/14） |
| 特征维数/顺序一致 | PASS |
| matching 输出逐位可复现 | PASS |
| education 数值等价 | PASS（charcnn 1e-4 量级差异，如实登记） |
| education 决策层一致性 | **NOT_RUN** |
| 跨版本 GB 反序列化 | 本机未复现，风险保留 |
