# ADR-003：历史模型兼容性治理（不重训、不迁移）

- 状态：已采纳（Phase5-1A）
- 日期：2026-10-29

## 背景

`models/**` 下的历史 checkpoint 由训练环境产出
（`manifest.environment`：python 3.11.18 / scikit-learn 1.5.2 / numpy 1.26.4 /
pandas 2.2.3 / torch 2.1.2+cu121）。当前开发/CI 环境（python 3.13 / sklearn 1.8.0 /
numpy 2.2.6）无法反序列化其中 5 个 gradient_boosting 权重：

```
AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError'
```

另有 15 个 sklearn 权重可加载但触发 `InconsistentVersionWarning`
（1.5.2 → 1.8.0），输出不保证与训练时逐位一致。

## 决策

1. **历史成果不动**：不重训、不转换、不改写 checkpoint 与 manifest；
2. **准确分类**：`classify_load_failure()` 把加载失败分为
   `env_incompatible`（环境问题）/ `artifact_corrupt_or_load_failed`（文件损坏），
   `FileNotFoundError` 保持 `MODEL_MISSING` + `artifact_missing`；
   旧 scikit-learn 反序列化失败**不得**记为权重缺失或模型业务失败；
3. **兼容环境**：新增 `environment-legacy-model.yml`（独立 Conda 环境），
   仅在确有需要时启用（如复算历史指标）；不引入微服务；
4. **诊断工具**：`scripts/phase5_1a/diagnose_model_compat.py` 生成
   `reports/phase5-1a/model-compatibility.{json,md}`，逐模型登记状态与环境漂移；
5. 新增公开错误码 `MODEL_ENV_INCOMPATIBLE`，旧错误码全部保留（见依赖规则 §4）。

## 后果

- 正面：A4 可准确登记"旧模型不可用"的真实原因；业务 API 不受影响
  （torch/sklearn 不在导入期加载，模型加载为惰性）。
- 负面：存在两种运行环境的维护成本；版本漂移警告的 15 个权重在正式口径下
  必须在兼容环境复核后才能引用其数值。
