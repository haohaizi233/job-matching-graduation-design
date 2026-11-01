# Phase7-B / B4：模型产物许可与可信分发风险报告

- 时间：2026-11-01（UTC+8）
- 机器可读清单：`reports/phase7-b/model-license-inventory.json`
  （`py -3.13 scripts/phase7/audit_model_licenses.py` 真实扫描生成）
- 事实基线：`models/LICENSE-MODELS.md`（models-license-v1）、
  `reports/phase6-r/05-model-artifact-audit.md`、`docs/datasets/README.md`

## 1. 现状：文件已公开 ≠ 许可已核实

真实扫描结果（本轮执行）：

| 指标 | 值 |
|---|---|
| `models/` 登记文件 | 433 |
| 二进制权重/预测产物（`.pt/.pkl/.npz/...`） | 150 |
| 总体积 | 37,230,912 bytes（≈35.5 MB） |
| `model_license = UNKNOWN` | **433 / 433（100%）** |
| 仓库根 `LICENSE` | **不存在**（整个仓库分发许可 UNKNOWN） |

**两个事实并存**：上述权重已被 Git 跟踪且在公开仓库可见；同时没有任何一个
模型族具备可核的再分发授权。仅新增声明文件**不构成**问题解决。

## 2. 逐族许可登记（只登记可核事实）

### 2.1 `models/matching/{ridge,gradient_boosting,mlp,ranknet}/`

| 字段 | 值 |
|---|---|
| source_dataset | `data/raw/job-resume-matching`（cv.csv 9,544 + job.csv 1,167 + matches.csv 122,560 行） |
| source_dataset_version | Hugging Face 快照（repo id 本地无记录） |
| source_url / source_license | **UNKNOWN**（卡片写 `license: mit` 与正文"请在发布前更新许可"**矛盾**） |
| model_license | **UNKNOWN** |
| redistribution_status | **BLOCKED_UNKNOWN_LICENSE** |
| privacy_risk | MEDIUM_UNVERIFIED_SOURCE：简历文本来源与授权链未核实；标签为英文代理标签 |
| license_evidence | `models/LICENSE-MODELS.md#2.1`、`docs/datasets/README.md#1` |
| 分类 | **来源未知 + 许可矛盾 + 不允许再分发（待人工确认）** |

### 2.2 `models/education/{tfidf,charcnn}/`

| 字段 | 值 |
|---|---|
| source_dataset | `data/raw/job-education`（train 197,574 / val 45,593 / test 22,730 行） |
| source_dataset_version | Hugging Face 快照（创建者 @wangzihaogithub） |
| source_url | UNKNOWN（repo id 未登记） |
| source_license | **apache-2.0**（卡片声明，本地可核） |
| model_license | **UNKNOWN**（无 LICENSE、manifest 无 license 字段） |
| redistribution_status | **NEEDS_MODEL_LICENSE** |
| privacy_risk | LOW：岗位文本非个人简历；训练语料与岗位候选池文本重合（评价须披露） |
| 分类 | **来源已核实 + 数据许可明确 + 模型许可待补** |

### 2.3 第三方预训练模型（BGE / Cross-Encoder，本地缓存，不在仓库）

模型卡/许可副本未随仓库登记 → 一律 **UNKNOWN**；使用前须补证据。

## 3. 推理安全回归（本轮真实执行，`tests/phase7/test_model_security_service.py`）

保留 P7-5 已修复的 `MODEL_ARTIFACT_TAMPERED` / `artifact_checksum_mismatch`，新增服务级契约测试（全绿）：

| 要求 | 测试 | 结果 |
|---|---|---|
| 哈希不一致 → HTTP 503 | `test_tampered_checksum_maps_to_503`、`test_tampered_hash_http_503_even_with_fallback` | PASS（含 `allow_fallback=True` 也不降级——不受信即拒绝） |
| 权重损坏不触发反序列化 | `test_corrupt_weights_never_deserialized` | PASS（loader 调用次数 0） |
| 不登记成功 load_event | `test_no_successful_load_event_on_tamper` | PASS |
| 非法错误码不吞原始故障 | `test_illegal_error_code_not_swallowed` | PASS（构造期 ValueError；loader 原始异常保留在 `__cause__`） |
| 失败分类不互相冒充 | `test_env_incompatible_distinct_from_missing` | PASS（env_incompatible ≠ artifact_missing） |
| 降级显式可审计 | `test_corrupt_weights_degrade_explicitly_when_fallback_allowed` | PASS（`degradation.reason_code` 登记，scoring 如实标 baseline） |
| 前端展示降级/不可用 | `TestFrontendDegradationDisplay` | PASS（组件契约核对：`MatchingView.vue` 渲染 `degradation_info`/`已降级`/`reason_code`；**浏览器级运行时验证登记 NOT_RUN**，前端无单测基础设施） |

## 4. 风险清单与非破坏性整改方案（未经批准不执行破坏性操作）

| # | 风险 | 等级 | 非破坏性处置 | 破坏性/需批准项 |
|---|---|---|---|---|
| R1 | 全部 433 个文件 model_license=UNKNOWN 且已公开 | 高 | ①立即停止添加许可不明的新权重（本报告即为门禁依据）；②整理权重与数据来源台账（已生成 inventory）；③`models/` README 显著披露「许可未核实，禁止再分发」 | 暂转私有仓库（改可见性，需用户批准） |
| R2 | 匹配模型训练数据许可矛盾（mit 声明 vs 正文保留） | 高 | 联系数据集作者取得书面许可；在论文/README 披露矛盾现状 | `git filter-repo` / 删除公开历史（需批准；且不消除已抓取副本） |
| R3 | 仓库根无 LICENSE | 中 | 由作者/导师选定 LICENSE 后添加（Agent **不得**代选） | — |
| R4 | 已公开权重的可执行反序列化风险（pickle/torch） | 中 | P7-5 哈希门禁已上线（加载前 sha256，不匹配拒绝）；本 B4 回归固化契约 | — |
| R5 | Git LFS / Release 迁移被误当作「消除历史」 | 提示 | 如迁移，仅解决仓库体积/后续分发；**既有公开历史中的内容不会消失** | 历史改写（需批准） |
| R6 | 第三方 BGE/Reranker 许可未随附 | 中 | 补模型卡/许可副本到 `data/private/consent/evidence/`（不入库）并登记 | — |

**本轮未执行（须用户批准）**：`git push --force`、`git filter-repo`、删除公开 Git 历史、
大规模移动模型权重、修改仓库可见性、替作者选定 LICENSE。

## 5. 可公开 / 不可公开口径（维持 P7-5 结论）

- 可公开：`*.json`（配置/指标/manifest/feature_map）、许可与审计文档、README；
- 补证据后方可公开：`*.pkl / *.pt / *.pth / *.npz` 等权重与预测矩阵；
- 绝不可公开：真实简历（`data/private/**`）、真实 Gold 配对、授权同意书。

## 6. 待人工决策

1. 是否将仓库暂转私有直至许可补齐（改可见性，需批准）；
2. 数据集作者联络与书面许可获取（真人事项）；
3. 仓库根 LICENSE 选择（作者/导师决定）；
4. 是否执行 Git LFS / Release 迁移（明确：不消除既有公开历史）；
5. 为可公开产物提供 SHA-256 清单已就绪（inventory），是否发布为 Release 附件。
