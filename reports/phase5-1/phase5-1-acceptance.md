# Phase5-1 验收报告（双向画像与智能匹配推理服务集成）

- 生成时间：2026-10-29
- 范围：M03 双向画像 + M04 智能匹配的**工程集成**（不含 Phase4-3B 模型最终选型）
- 依据：任务书 §十 三级验收（K1/K2/K3）；审计见 `docs/architecture/phase5-1-integration-audit.md`

> **强制声明：Phase5-1 工程集成通过不代表中文人岗匹配模型的真实效果验收通过。Phase4-3A 的 H2 仍然 BLOCKED。**

---

## 1. 验收结论

| 级别 | 验收项 | 状态 | 证据 |
|---|---|---|---|
| **K1** | 业务画像契约通过：学生/岗位画像具备可验证的输入、输出、版本及证据追踪 | **通过** | `service/contracts.py`（`profile_version=phase5-1-profile-v1`、字段三件套 `fact_source/evidence_text/extraction_method`、技能 `verification_status`、`confidence` 含义显式声明）；S05–S09 14 项测试全过 |
| **K2** | 推理服务通过：至少一个真实可执行的排序方法在中文合成输入上运行成功，返回合法、可解释、可重复结果；旧模型不适用时正确拒绝或降级 | **通过** | baseline 模式（`heuristic_score`）e2e 成功（`reports/phase5-1/demo-output.json`）；experimental 模式用真实 ridge checkpoint e2e 成功（`reports/phase5-1/experimental-demo/`，`model_raw_score`）；GBM 权重不可加载时走 `MODEL_MISSING`/透明降级；中文正式模式拒绝旧模型（S13–S16）；确定性（S22） |
| **K3** | 端到端集成通过：从简历文本和岗位 JD 输入到推荐 JSON 输出稳定完成，测试全部通过 | **通过** | `scripts/phase5_1/demo_offline.py` 离线闭环 + FastAPI 6 端点；Phase5-1 自动化测试 **92/92 通过**（S01–S24，`reports/phase5-1/test-results.json`） |

## 2. 测试命令与结果

| 套件 | 命令 | 结果 |
|---|---|---|
| Phase5-1（本轮） | `python tests/phase5_1/run_all.py` | **92/92 PASS**，0 FAIL / 0 SKIP（8.2s） |
| Phase4-3A 回归 | `python tests/phase4_3a/run_all.py` | 237/237 PASS |
| 数据管线回归 | `python tests/data_pipeline/run_all.py` | 74/74 PASS（G1–G7） |
| 模型训练回归 | `python tests/model_training/run_all.py` | 20/21 PASS；T5 在当前解释器报 setUpClass ERROR（见 §4-L1，环境漂移，与本轮代码无关） |
| 学历训练回归 | `python tests/education_training/run_all.py` | 35/36 PASS；仅 `pip check` 失败（见 §4-L2，共享解释器包冲突） |

旧测试未删除、未跳过、未降低断言标准。运行旧套件时其自带报告写入器会重写归档报告，
本轮已用 `git restore` 恢复 `reports/model-training/model-tests.json`、
`reports/data-quality-gates.json`、`reports/education-training/education-tests.json`
至提交态（历史产物零改动）。

## 3. 关键能力验证

1. **文档解析**（S01–S04）：中文 TXT / DOCX / 可提取文本 PDF 解析成功；扫描版 PDF 与空文本
   返回 `ocr_required` / `empty_text`，**不用空文本伪装解析成功**。
2. **画像与证据**（S05–S07）：技能归一化（别名精确映射，Java≠JavaScript、C≠C++）；
   每个字段带原文证据与来源等级；必备/加分技能严格区分；未命中技能记
   `evidence_missing`（"不代表候选人不具备"），不产出"不会该技能"。
3. **学历解析**（S08、模型探测）：`EducationNormalizer.from_model_dir` 复用，批量推理 +
   规则回退 + `model_version` / `expression_seen_in_train` / `confidence`（含含义声明）；
   模型不可用进入显式 `rules_only` 模式；异常表达 `rejected`/人工复核。
4. **排序与解释**（S10–S12、S17–S18）：稳定排序（分数降序、同分按输入顺序）、重复岗位去重告警、
   `score_type` 三态正确（本轮只出现 `heuristic_score` / `model_raw_score`）；解释与实际证据一致。
5. **防泄漏**（S14）：目标值/派生评分字段输入 -> `LEAKAGE_GUARD`；缺失特征一律
   `MODEL_INAPPLICABLE`，禁止伪造填充；不产出"录用成功概率"。
6. **API**（S19–S22）：PII 不入日志（掩码）；6 端点正常/异常/边界（批量 200 上限、超时、
   错误码、request_id、OpenAPI）；模型仅初始化/缓存失效时加载；同输入同模型版本结果确定。

## 4. 已知限制与阻断项登记

| 编号 | 项 | 状态 | 说明 |
|---|---|---|---|
| L1 | 归档 GBM checkpoint 与当前 sklearn 不兼容 | **BLOCKED（环境）** | 5 个 `gradient_boosting` run 在 sklearn 1.8.0 下反序列化失败（`__pyx_unpickle_CyHalfSquaredError`；checkpoint 按 `environment.yml` 的 sklearn 1.5.2 训练）。连带 `tests/model_training` T5 在当前解释器报 setUpClass ERROR。**不重训、不覆盖 checkpoint**；按 `environment.yml`（python 3.11 + sklearn 1.5.2）运行即可恢复；业务侧已按降级路径处理（`reports/phase5-1/model-compatibility.json`） |
| L2 | 共享解释器 `pip check` 不通过 | 已登记 | 全局 Python 3.13.2 中 adalflow/f2/moviepy 等无关包版本冲突；与本仓库代码无关，仅影响 `education_training` 的 E6 环境检查 |
| L3 | `environment.yml` 未声明 Web 依赖 | 已登记 | `fastapi/pydantic/httpx` 需在重建环境时补装（`docs/api/phase5-1-api.md`） |
| L4 | 扫描版 PDF 无 OCR | 已明确拒识 | 返回 `ocr_required`，转人工/OCR 预处理 |
| L5 | 中文人岗匹配模型缺失 | **BLOCKED（继承 H2）** | `future_verified` 仅预留槽位（`pending_phase4_3b`），不伪称存在已验证中文模型 |
| L6 | 旧匹配模型中文不适配 | 已隔离 | 仅 `experimental_model` 研究/诊断可用；中文类别/职位全部 OOV、`years_experience` 显式缺失由 train 均值填充 |
| L7 | 技能词表覆盖有限 | 已知 | 中文职能技能未命中词表时保留原值 + `needs_review`，按证据不足处理，不强行归并 |
| L8 | 真实中文简历与人工 Gold 未到位 | **BLOCKED（继承）** | 本阶段不创建 Gold、不伪造中文训练数据、不把演示输出当人工标签 |

## 5. 下一阶段建议

1. **H2 解锁前置**：真实中文简历（授权脱敏）+ 人工 Gold 标注按 Phase4-3A-2 标注方案推进；
   Gold 只进评估，不进训练与阈值选择。
2. **Phase4-3B 选型**：以中文数据训练候选模型，验证完成后按
   `docs/architecture/phase5-1-model-contract.md` §7 登记 `verified` 并接入
   `future_verified` 槽位；如需 `calibrated_score` 必须先做 Gold 校准验证。
3. **环境固化**：按 `environment.yml` 建 conda 环境并补装 `fastapi/pydantic/httpx`，
   消除 L1/L2/L3；或升级 `environment.yml` 锁定版本并重导出模型清单（需重新验证指标）。
4. **OCR 预处理**：接入离线 OCR 生成带置信度的文本层，输出仍保留原文证据与
   `ocr_required` 状态迁移记录。
5. **业务化扩展（按需）**：画像持久化、批量岗位库、人工修正回写（`human_corrected`
   来源等级已预留）。

## 6. 强制声明（重复登记）

**Phase5-1 工程集成通过不代表中文人岗匹配模型的真实效果验收通过。Phase4-3A 的 H2 仍然 BLOCKED。**
所有演示输出均标注 `demo=true`、`label_source=synthetic_or_unlabeled`、`formal_evaluation=false`；
所有分数为排序参考分（`heuristic_score` / `model_raw_score`），不是录用概率。
