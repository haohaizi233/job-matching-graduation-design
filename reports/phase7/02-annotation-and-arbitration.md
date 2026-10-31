# P7-2 双人独立盲标注执行准备与仲裁流程

- 生成时间：2026-10-31
- 分支：`feat/phase7-gold-evaluation`
- 状态：**工具链就绪 / 真实标注 0%（H2 维持 BLOCKED）**
- 证据产物：
  - `reports/phase7/annotation-drill.{json,md}`（隔离合成夹具完整演练）
  - `reports/phase7/11-phase7-regression.{json,md}`（34 项纯软件协议测试）
- 复用工具（未重写）：`scripts/phase4_3a_2/{export_annotation_packets,annotation_qa,leakage_gate}.py`、
  `src/job_matching/annotation/{blind_guard,importer,arbitration,completion,agreement}.py`

---

## 一、人工标注流程（可直接执行）

### 1.1 标签体系（沿用 `phase4-3a-annotation-v1`，未改）

| 值 | 含义 |
|---|---|
| `0` | 明显不匹配 |
| `1` | 部分匹配 |
| `2` | 高度匹配 |
| `unjudgeable` | 资料不足或信息自相矛盾，**无法可靠判断**（独立状态，不是 0） |

### 1.2 必留字段（以仓库 Schema 为准）

`src/job_matching/annotation/schema.py::ANNOTATION_FIELDS`：

```text
annotator_id, pair_id, relevance, confidence, reason,
evidence, annotation_timestamp, protocol_version
```

补充约束：
- `confidence ∈ {high, medium, low}`（`schema.norm_confidence`）；
- `reason` 须引用 `annotation-guidelines.md` 2.2 的判定依据编号 1–5；
- `evidence` 须引用简历/JD 的**脱敏后**具体片段；
- `protocol_version` 全表必须一致（当前 `phase4-3a-annotation-v1`）。

### 1.3 执行步骤

| 步 | 命令 / 动作 | 产出 |
|---|---|---|
| 1 | `py -3.13 scripts/phase4_3a_2/build_real_pairs.py` | 真实人岗配对 `pairs_real_v2.jsonl` |
| 2 | `py -3.13 scripts/phase4_3a_2/export_annotation_packets.py` | `packets/packet_<标注员>.csv` × 2 |
| 3 | 标注员 A、B **各自独立**填写 CSV（互不可见） | `annotations_A.csv` / `annotations_B.csv` |
| 4 | 放入 `data/private/annotations_raw/`（不入库） | — |
| 5 | `py -3.13 scripts/phase4_3a_2/annotation_qa.py` | 一致性、分歧、进度 |
| 6 | 分歧 → 人工仲裁 → `arbitration_filled.csv` | 最终标签 |
| 7 | `py -3.13 scripts/phase4_3a_2/leakage_gate.py` | 泄漏门禁 |
| 8 | `py -3.13 scripts/phase4_3a_2/freeze_gold.py` + `verify` | Gold 冻结 |

---

## 二、盲标保护（工具强制，非口头约定）

标注员**看不到**（`blind_guard._VIEW_HIDDEN_COLUMNS` + `schema.MODEL_OUTPUT_COLUMNS` 强制剔除）：

| 类别 | 具体列 |
|---|---|
| 模型评分 / 旧代理标签 | `model_score`、`pred_*`、`final_score`、`raw_score`、`label_strength`、`candidate_rank`、`semantic_score`、`llm_score`、`gpt_score`、`auto_label` 等 |
| 抽样难度 | `difficulty_tier`、`difficulty_factors`、`pair_provenance` |
| 切分与资格 | `split`、`eligible_for_gold`、`is_synthetic`、`dataset_version`、`content_hash` |
| 他人答案 | `annotator_a_*`、`annotator_b_*`、`relevance_a/b`、`final_relevance` 等 |

标注材料只包含：去标识化 `resume_text` / `job_text`、岗位要求字段、标注指南引用。
违规时 `blind_guard.build_annotation_view` **直接抛 `AnnotationError`**，不静默丢弃。

---

## 三、标注工具验收（隔离合成夹具完整演练）

演练脚本：`scripts/phase7/annotation_drill.py`
演练性质：**合成配对（12 组，`is_synthetic=true` / `eligible_for_gold=false`）+ 机械标签
（固定种子 PRNG，与任何模型输出无关）**。演练中的"标注员"是测试夹具记录，**不是真人**。

### 3.1 逐项结果（任务书 6.3）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 独立导出 | **PASS** | 两人各一份标注包，列白名单通过，无隐藏列泄漏 |
| 2 | 标注保存 | **PASS** | 12 行写入 CSV 并经 `importer.validate_annotation_file` 校验 |
| 3 | 断点续标 | **PASS** | 半程中断（6/12）→ 续标剩余 → 无遗漏 |
| 4 | 输入字段检查 | **PASS** | 缺列文件被拒，错误码 `missing_columns` |
| 5 | 非法标签拒绝 | **PASS** | `relevance="3"` 被拒；机器标识标注员 `gpt_annotator` 被拒 |
| 6 | 同人冒充两个标注员 | **PASS** | `shared_annotator_id` 违规被检出 |
| 7 | 镜像答案异常检测 | **PASS** | 全表镜像 → `mirrored_annotations`；独立标注不误报 |
| 8 | 隐私残留扫描 | **PASS** | 干净合成文本通过；注入手机号/邮箱后被 `check_export` 拦截 |
| 9 | 标注进度统计 | **PASS** | `completion.assess_annotation_completion` 输出进度与阻断项 |
| + | 仲裁流程 | **PASS** | 12 组分歧 → 仲裁表 → 12 条最终标签，双方原始结论均保留 |
| + | 一致性统计 | **PASS** | `agreement_report` 可计算（数值仅为夹具，不代表真实质量） |
| + | 无真实数据拒冻结 | **PASS** | `evaluate_precheck` 返回 `blocked` 并给出 4 条阻断原因 |
| + | 合成不入 Gold | **PASS** | `count_real_gold` = 0 |
| + | 工作区安全边界（负向） | **PASS** | 指向 `data/private`、`data/independent_eval/frozen` 均拒绝执行 |

**14/14 通过**（`reports/phase7/annotation-drill.json`）。

### 3.2 演练通过 ≠ 真实人工标注完成

| 项 | 演练 | 真实 |
|---|---|---|
| 样本 | 12 个合成配对 | **0** 个真实配对 |
| 标注员 | 脚本生成的 `DrillAnnotatorA/B` | **0** 个自然人 |
| 标签来源 | 固定种子 PRNG | 人类判断 |
| 是否构成 Gold | **否** | 未开始 |

---

## 四、仲裁规范

### 4.1 触发条件

两人 `relevance` 不同（含 `unjudgeable` vs 0/1/2）→ 进入仲裁。

### 4.2 仲裁记录字段（`schema.ARBITRATION_FIELDS`）

```text
arbitrator_id, pair_id, final_relevance, final_confidence, reason,
evidence, annotation_timestamp, protocol_version
```

### 4.3 必须保留

| 保留项 | 说明 |
|---|---|
| 标注员 A 原始结论 | 原 CSV 不覆盖、不改写 |
| 标注员 B 原始结论 | 同上 |
| 分歧类型 | `arbitration.find_disagreements` 输出 `relevance_a/relevance_b` |
| 仲裁员最终结论 | `final_relevance` |
| 仲裁理由 | `reason`（须说明为何采纳该标签） |
| 仲裁时间 | `annotation_timestamp` |
| 协议版本 | `protocol_version` |

### 4.4 禁止事项

- **禁止简单取平均**：`arbitration.build_final_labels` 只在两人一致时用 `both_agree`，
  不一致时必须有仲裁记录，否则标记 `pending`/`insufficient`，**不产生最终标签**；
- **禁止 AI 代替人类仲裁员**：AI 可以检查 CSV 格式、统计分歧分布、提示字段缺失，
  但**不能**给出"Gold 真值"。演练中的仲裁记录由脚本机械生成，已显式标注非真人仲裁；
- **禁止覆盖原始标注**：`FINAL_LABEL_FIELDS` 同时保留 `annotator_a_relevance` /
  `annotator_b_relevance` 与 `final_relevance`；
- **`unjudgeable` 保护**：双方均判 `unjudgeable` 时，仲裁给出数值标签的记录会被
  `checks.unjudgeable_forced` 标记并**不予采纳**。

---

## 五、当前真实标注进度

| 指标 | 值 |
|---|---|
| 真实配对总数 | 0 |
| 标注文件 | 0 |
| 独立标注员 | 0 |
| 已完成标注的配对 | 0 |
| 分歧待仲裁 | 0（无对象） |
| 仲裁完成 | 0 |
| `annotation_status` | `pending`（`waiting_real_pairs`） |
| **标注进度** | **0%** |

阻断原因（如实）：
1. 无经授权的真实中文简历（有效 0 份）；
2. 无人岗配对对象（0 组）；
3. 无独立标注员（0 人）；
4. 无人类仲裁员。

---

## 六、结论

- **工具链就绪**：导出、保存、续标、校验、独立性、镜像检测、隐私扫描、仲裁、进度统计
  全部在隔离合成夹具上验收通过，并有 34 项纯软件协议测试守护；
- **真实双人标注未开始**，进度 0%，H2 维持 `BLOCKED`；
- 解除阻断只能由**两名真实人类标注员 + 一名人类仲裁员**在**经授权的真实数据**上完成；
  Agent 不能冒充标注员或仲裁员。

### 纪律遵守

不让 AI 冒充人工标注员、不用模型评分自动生成 Gold 标签、不把业务用户反馈当人工标签、
不把合成夹具结果计为真实标注、不改写原始标注记录。
