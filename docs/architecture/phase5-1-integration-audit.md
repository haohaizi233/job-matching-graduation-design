# Phase5-1 集成审计报告（双向画像与智能匹配推理服务）

- 生成时间：2026-10-29
- 审计范围：`src/job_matching/`、`configs/`、`models/`、`tests/`、`docs/`、Python 依赖环境
- 审计方法：逐文件阅读源码 + 归档模型清单实际扫描 + 运行环境实测（不修改任何既有文件）
- 结论定位：本阶段是 **M03 双向画像 / M04 智能匹配的工程集成**，不是 Phase4-3B 模型最终选型；
  任何历史模型在本阶段只做"能力登记与适配验证"，不重新训练、不改指标、不覆盖 checkpoint。

---

## 0. 仓库状态快照（开发前实测）

| 项 | 实测值 |
|---|---|
| 分支 / HEAD | `main` / `4c86372` `fix(education): 修订数据集与模型校验逻辑并更新实验报告` |
| 未提交修改 | Phase4-3A/4-3A-2 的报告、标注计划、`job_pool_v2.jsonl`、`build_job_candidates.py`、`tests/phase4_3a/run_all.py` 等（均为他人阶段成果，**本轮不触碰、不覆盖、不提交**） |
| 运行解释器 | Python 3.13.2（`D:\APP\python`，现有 `__pycache__` 为 cpython-313，测试沿用同一解释器） |
| 目标环境文件 | `environment.yml`（conda，python=3.11 + torch 2.1.2+cu121，**未声明 FastAPI/Pydantic**） |
| 实测可用依赖 | `fastapi 0.120.3`、`pydantic 2.9.2`、`httpx 0.28.1`、`PyMuPDF(fitz)`、`jieba`、`joblib`、`sklearn`、`numpy`、`pandas` |
| 归档模型 | 42 个模型目录（ridge 8 / ranknet 8 / gradient_boosting 5 / mlp 5 / tfidf 7 / charcnn 9），**42/42 权重文件齐全** |
| 既有测试 | `tests/data_pipeline`（G1~G7）、`tests/model_training`（T1~T6）、`tests/education_training`（E1~E6）、`tests/phase4_3a`（P1~P18） |

---

## 1. 现有模型能够接受什么输入？

### 1.1 人岗匹配模型 `src/job_matching/inference/predictor.py`（Phase4-1）

`MatchPredictor(run_dir, device="cpu")`，硬性契约：

- `predict_score(resume: dict, job: dict) -> float`；
- `rank_jobs(resume: dict, jobs: list[dict]) -> list[dict]`，稳定排序（分数相同按输入顺序）；
- 输入字段（`training/feature_map.py` 的 `RESUME_FIELDS` / `JOB_FIELDS`，缺字段**立即抛 ValueError**）：
  - resume 侧：`target_position_norm`、`skills_canonical_json`（或 `clean_skills`）、`inferred_category`、`years_experience`；
  - job 侧：`job_title_norm`、`category`、`skills_canonical_json`（或 `clean_skills`）；
- 数值缺失（`years_experience` 无法转 float）置 NaN，由 FeatureMap 用 **train 统计均值**填充；
- 类别字段用 FeatureMap 词表 one-hot，未知值落 `__OOV__`；
- 禁止输入：`final_score / raw_score / candidate_rank / candidate_rank_pct / label_strength / semantic_score / skill_score / position_score / category_score / experience_score / education_score`（manifest `inference.forbidden_inputs` 明确登记，`policy.check_feature_columns` 强制）；
- 模型权重：`manifest.json + feature_map.json + model.pkl（ridge/GB）或 model.pt（mlp/ranknet）`；torch 权重 `map_location="cpu"`，CPU 可推理；
- `info()` 声明 `requires_labels=False`。

### 1.2 学历规范化模型 `src/job_matching/education/predictor.py`（Phase4-2）

`EducationNormalizer.from_model_dir(model_dir, fallback_to_rules=True)`：

- 输入：**中文文本**（`user` 槽位串：`<岗位名称>…</岗位名称><岗位描述>…</岗位描述><学历描述>…</学历描述>`，或其片段）；
- 输出：`labels`（6 token 多标签：博士/硕士/本科/大专/学历不限/学历不明）、逐标签 `scores`、`confidence`、
  `expression_seen_in_train`（表达式是否出现在训练槽位词表）、`fallback_to_rule`、`rule`、冲突消解 `note`；
- `normalize()` 单条、`batch()` 批量（批量一次前向，已支持）；
- **`confidence` 已自带声明**："模型分数在预测标签上的均值，未经校准，不是真实正确概率"；
- 空输入不进模型，确定性返回 `学历不明`；
- 无标签过阈值时回退 `baseline_education.rule_predict`（规则模式），并标注 `fallback`；
- 权重：`manifest.json`（含 `model_type ∈ {tfidf_char_ovr_logreg, char_cnn}`、`thresholds`、`train_slot_vocab`）+ `model.pkl` 或 `model.pt/tokenizer.json`。

### 1.3 Baseline（零训练）

- `baseline_ranking.py`：random / embedding_cosine / skill_jaccard / position_token_overlap（**旧英文语料评估口径**，指标绑 `candidate_id` 分组与 `final_score` 相关性，不能直接当业务排序器）；
- `annotation/pool.py` 的启发式抽取（**中文**）：`extract_skills`（词表命中）、`classify_job_category`、
  `parse_experience_requirement`、`education_requirement_fields`、`min_required_degree`、`preferred_segment`、`detect_language`；
- `education/rules.py` → `baseline_education.rule_predict`：中文学历规则基线。

---

## 2. 哪些输入必须预处理？

| 输入 | 预处理要求 | 现成实现 |
|---|---|---|
| 简历文本 | 编码识别（utf-8-sig/utf-8/gbk）、PDF/DOCX 抽取、NFKC 规范化、PII 脱敏 | `annotation/resume_intake.py::extract_text`、`annotation/pii.py::scrub_record`、`core.norm_text` |
| 技能列表 | 字符串化 list 还原 → 形式规范化（NFKC/casefold/去首尾标点）→ 显式别名精确映射（**禁止子串包含**） | `preprocess_skills.py::canonicalize_skills/canonical_skill/parse_skill_list` |
| 目标职位 | 文本规范化 + 词元化 | `pair_features.title_tokens` |
| 年限 | 转 float，失败置 NaN（不允许编造） | `feature_map.compute_pair_raw_features` 内部 |
| 岗位类别 | 中文 JD 需启发式分类（旧 `category` 是 5 个英文枚举） | `pool.classify_job_category`（返回 `*_source`） |
| 岗位学历 | 抽取 `<学历描述>` 槽位/全文 → 模型或规则解析 6 token | `preprocess_education.parse_user_segments/normalize_label`、`EducationNormalizer` |
| 岗位年限 | "3年以上 / 经验不限 / 应届" 模式抽取 | `pool.parse_experience_requirement` |
| 必备/加分技能 | 按"优先/加分/更佳"标记切段区分 | `pool.preferred_segment` |

---

## 3. 哪些特征只能从旧英文数据生成？

1. **类别 one-hot 词表**：`inferred_category`（6 英文枚举，`schema.py` 实测）与 `job_category`（5 英文枚举）的词表
   由英文 `cv.csv / job.csv` 的 train 拟合；中文岗位类别（如 `OTHER`）落入 `__OOV__`，信息量为零。
2. **职位 one-hot 词表**：`target_position_norm` 词表来自英文 28 个 target_position；中文职位全部 OOV。
3. **年限标准化统计**：`years_experience` 的 mean/std 来自英文候选人分布（0~31 年），与中国应届生（0~少量实习年数）分布不同。
4. **技能规范词表**：`configs/skills.yaml` 别名表以英文/技术栈技能为主（java/python/sql/spring boot…），
   中文职能技能（如"财务分析""招聘"）不在别名表，会标记 `needs_review` 保留原值——符合"不强行归并"铁律，但覆盖率有限。
5. **代理标签本身**：`label_strength / candidate_rank / final_score` 全部由原系统评分公式派生
   （`semantic_score → raw_score → final_score → label_strength` 闭环已审计，见 `baseline_ranking.CAVEATS`），
   只能代表"与旧系统代理偏好的一致度"，**不是**中国大学生求职适配度或录用概率。

## 4. 哪些模型能直接处理真实中文岗位？

| 模型 | 中文可用性 | 依据 |
|---|---|---|
| 学历规范化（tfidf / charcnn） | **可直接用**（中文岗位学历解析） | 训练数据即中文岗位 job-education（19.7万+4.6万条），输入为中文槽位文本 |
| 学历规则基线 `rule_predict` | 可直接用 | 纯中文规则/词表 |
| 人岗匹配 ridge / GB / mlp / ranknet | **不可直接用** | 训练输入词表与标签均为英文代理口径；中文输入全 OOV，语义靠不上 |
| embedding_cosine baseline | 不可独立用 | 预计算 768 维 embedding 属派生评分链一环（feature_policy.yaml `uncertain_features`，与代理标签耦合） |

## 5. 哪些模型只能用于研究演示？

- **Phase4-1 全部匹配模型**（ridge/gradient_boosting/mlp/ranknet，8 协议×消融）：目标是 `final_score`/`candidate_rank` 代理值，
  评估指标是与代理偏好的一致性。→ 仅限 `experimental_model` 模式做研究/诊断输出，`score_type=model_raw_score`，
  **禁止**作为正式中文人岗匹配分数，禁止表述为录用概率。
- **学历模型输出的 confidence**：未经校准，只能作为排序参考，禁止表述为正确率。

## 6. 模型权重缺失时如何降级？

| 场景 | 现有行为 | 本轮集成行为 |
|---|---|---|
| 匹配模型目录缺 `manifest.json` | `MatchPredictor` 抛 `FileNotFoundError` | 捕获 → API 错误码 `MODEL_MISSING`，或 `allow_fallback=true` 时**透明降级 baseline** 并在结果 `warnings` 标注 `degraded_to_baseline` |
| 匹配模型权重缺失（缺 `model.pkl`/`model.pt`） | `joblib.load`/`torch.load` 抛异常 | 注册表预检 artifact → `MODEL_MISSING`，绝不伪造分数 |
| 学历模型目录不可用 | `from_model_dir` 抛异常 | 显式进入 **规则模式**（`source=rule`、`mode=rules_only`），不生成任何 `model_*` 字段，不伪造模型输出 |
| 中文业务输入无法合法构建旧模型特征 | （原无业务适配层） | `MODEL_INAPPLICABLE`：列出缺失字段，禁止用目标值/旧评分/虚假 embedding 填充 |

## 7. 现有代码哪些可以直接复用？

| 复用点 | 位置 | 用途 |
|---|---|---|
| 文本抽取（TXT/DOCX/PDF，含编码与格式拒识） | `annotation/resume_intake.py::extract_text` | 模块 A 简历解析 |
| PII 检测/掩码/导出检查 | `annotation/pii.py` | 日志脱敏与证据安全 |
| 技能规范化与集合相似度 | `preprocess_skills.py` | 技能归一化 + baseline 覆盖率 |
| 中文 JD 启发式抽取 | `annotation/pool.py`（技能词表、类别、年限、学历字段、加分段、语言） | 模块 B |
| 学历标签词表/槽位解析/规则基线 | `education/labels.py`、`preprocess_education.py`、`education/rules.py` | 模块 B |
| 学历推理器（批量+规则回退+版本记录） | `education/predictor.py::EducationNormalizer` | 模块 B |
| 匹配推理器与单 pair 特征 | `inference/predictor.py::MatchPredictor`、`training/feature_map.py` | 模块 C（experimental_model） |
| 特征黑白名单强制 | `policy.check_feature_columns`、`configs/feature_policy.yaml` | 防泄漏断言 |
| JSON/文本/哈希基础工具 | `core.py`（`jload/jdump/norm_text/sha256_text/short_hash`） | 全局 |
| 评估/独立评估/标注工程 | `evaluation/`、`independent_eval/`、`annotation/` 其余 | **只读引用，本轮不改** |

## 8. 是否已有业务 API、数据库或画像服务？

**没有。** 实测结论：

- 全仓无 FastAPI/Flask/uvicorn 业务服务代码（仅文档/测试中提及依赖词），无 ORM/数据库、无画像服务、无模型注册表；
- `schema.py` 是 **CSV 数据表 Schema**（cv/job/matches/job-education），不是业务 API 协议，不能直接当线上契约；
- 因此本轮新建 `src/job_matching/service/`（业务画像、解析、匹配服务、模型注册表、FastAPI 应用），
  与既有训练/评估工程物理隔离；不引入 Redis/Celery/微服务注册中心/用户系统；
- **依赖缺口登记**：`environment.yml`（conda py3.11）未声明 `fastapi/pydantic/httpx`。当前活动解释器（3.13.2）已具备三者，
  API 可运行；若按 `environment.yml` 重建环境需补装（已在 `docs/api/phase5-1-api.md` 登记）。业务核心模块只依赖
  numpy/pandas/sklearn，API 层做延迟导入，核心能力不被 Web 框架绑死。

---

## 9. 风险与阻断项登记

| 编号 | 项 | 状态 | 说明 |
|---|---|---|---|
| R1 | 真实中文简历 + 人工 Gold 未到位 | **BLOCKED（继承）** | Phase4-3A 的 H2 仍 BLOCKED；本阶段不创建 Gold、不伪造中文训练数据 |
| R2 | 中文人岗匹配模型缺失 | 已知限制 | `future_verified` 模式仅预留注册接口，`evaluation_status=pending_phase4_3b`，本轮不伪称存在已验证中文模型 |
| R3 | 旧匹配模型中文不适配 | 已适配 | experimental 模式默认拒绝中文正式用途（`formal_use_allowed=false`），仅研究输出 |
| R4 | 扫描版 PDF 无 OCR | 已处理 | 明确返回 `ocr_required` 状态，不用空文本伪装成功 |
| R5 | `environment.yml` 缺 Web 依赖 | 已登记 | 见 §8；API 层延迟导入 + 文档登记 |
| R6 | 未提交的 Phase4-3A-2 工作区修改 | 不触碰 | 本轮所有新文件均为新增路径，不 `git add` 他人文件、不 push |
| R7 | 归档 GBM checkpoint 与当前 sklearn 不兼容 | **BLOCKED（登记）** | 只读探测（`scripts/phase5_1/model_compatibility_report.py`，2026-10-29）：42 个 run 中 37 个可加载；5 个 `gradient_boosting` run 在 sklearn 1.8.0 下反序列化失败（`__pyx_unpickle_CyHalfSquaredError`，checkpoint 为 environment.yml 声明的 sklearn 1.5.2 训练）。**不通过重训/覆盖 checkpoint 修复**；业务侧已按 §6 走 `MODEL_MISSING`/透明降级。同一根因导致 `tests/model_training` 的 T5 在当前解释器报 setUpClass ERROR（`any_run_dir()` 命中 GBM run），按 environment.yml（python 3.11 + sklearn 1.5.2）运行即可恢复 |

## 10. 结论

1. 现有推理契约清晰、防泄漏约束完备，**不需要重构训练工程**即可做业务集成；
2. 业务侧缺口集中在：中文简历/岗位解析、业务画像契约、匹配适配层、可解释结果、API 与模型注册；
3. 学历规范化是本轮唯一"可直接服务真实中文岗位"的模型，匹配模型全部降级为研究模式；
4. 依据本审计，模块 A~F 全部以**新增文件**方式落地，历史模型、数据、指标零改动。
