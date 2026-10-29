# Phase5-1A 兼容性矩阵（compatibility-matrix）

- 日期：2026-10-29 ｜ 基线：`0225fcb`
- 逐模型兼容性明细见 `model-compatibility.{json,md}`（由
  `python scripts/phase5_1a/diagnose_model_compat.py` 实测生成）。

## 1. API 兼容（Phase5-1 既有契约）

| 维度 | 结论 | 证据 |
|---|---|---|
| 请求/响应结构 | 完全兼容，无字段增删改义 | `tests/phase5_1` S19–S22（92/92 PASS） |
| 公开错误码 | 旧码全部保留；仅**新增** `MODEL_ENV_INCOMPATIBLE`（503） | `service/errors.py`、`tests/phase5_1r` R6 链路 C |
| 错误信封脱敏 | 保持"不含本机绝对路径" | `R4ErrorHygiene`（4 项） |
| 配置键 | `ServiceSettings.to_config_dict()` 保留旧键输出，新增环境变量为叠加能力 | `tests/phase5_1a` A7 组 |
| 请求边界 | 上限语义不变（请求体 8MB / 上传 4MB / 文本 20 万字符 / 批量岗位 200 / 限流 300 rpm） | `R4UploadLimits`、`R4DeploymentScope` |
| 模型注册缓存 | 惰性加载 + 缓存语义不变（仅初始化或缓存失效时加载） | `R6.test_load_only_on_init_or_cache_invalidation` |

## 2. CLI 兼容

| 入口 | 结论 | 证据 |
|---|---|---|
| `scripts/phase4_3a_2/freeze_gold.py`（precheck / freeze / verify） | 参数、退出码语义不变 | R1 CLI 链路 15 项 |
| `scripts/phase4_3a_2/annotation_qa.py` | 不变 | R2 CLI 链路 |
| `tests/phase5_1r/run_all.py [GROUP]` | 兼容保留；新增：未知分组/0 测试退出码 2（原为隐式 0，属缺陷修复而非破坏） | `tests/phase5_1a` A1 组 |
| `tests/model_training/run_all.py [GROUP]` | 兼容保留；失败/部分运行不再覆盖基线报告（新增诊断文件） | `tests/phase5_1a` A6 组 |
| 其余 `tests/**/run_all.py` | 不变 | A6 回归 |

## 3. 导入路径兼容（Python API）

| 旧导入路径 | 现状 | 证据 |
|---|---|---|
| `job_matching.annotation.pool`（词表/类别等符号） | re-export 兼容 | `A2SharedRules.test_legacy_import_paths_still_work` |
| `job_matching.annotation.pii`（detect_pii/mask_matches） | re-export 兼容（同一实现对象） | 同上 |
| `job_matching.annotation.resume_intake`（extract_text/ResumeIntakeError） | re-export 兼容 | 同上 |
| `job_matching.service.*` 各公开函数/类签名 | 不变 | Phase5-1 92 项 |

## 4. 历史模型兼容（A4）

| 状态 | 数量 | 含义 | 处置 |
|---|---:|---|---|
| loaded | 22 | 当前环境可加载 | 直接可用 |
| loaded_with_version_warning | 15 | sklearn 1.5.2→1.8.0 版本漂移，输出不保证与训练时逐位一致 | 正式口径数值需在 Legacy 兼容环境复核后引用 |
| env_incompatible | 5 | gradient_boosting：`__pyx_unpickle_CyHalfSquaredError` 反序列化入口缺失（py3.11.18/sklearn1.5.2 → py3.13/1.8.0） | `MODEL_ENV_INCOMPATIBLE`；Legacy 环境（`environment-legacy-model.yml`）执行；**不重训、不改权重** |

历史 checkpoint 与 manifest 零改动（`scripts/phase5_1r/artifact_integrity.py` SHA-256 登记）。
模型训练基线报告 `reports/model-training/model-tests.json`（训练环境 25/25）保持归档不动；
Serving 环境复跑结果写 `model-tests-run-*.json` 诊断报告。

## 5. 环境清单

| 环境 | 文件 | 用途 |
|---|---|---|
| Training | `environment.yml` | 历史训练与实验复现（冻结不动） |
| Serving | `environment-service.yml` | FastAPI 业务推理 / 开发 / CI |
| Legacy Model Compatibility | `environment-legacy-model.yml` | 旧 checkpoint 加载与历史指标复算 |
| 测试附加 | `requirements-test.txt` | 测试客户端等 |

## 6. 已知限制

1. 共享解释器 `pip check` 存在三方包冲突（非项目依赖）；
2. 哈希完整性自检 ≠ 可信签名防篡改；
3. 内存限流仅对单进程有效，未经认证/网关防护不得宣称公网生产就绪
   （`ServiceSettings.check_deployment_safety()` 强制声明本地开发边界）。
