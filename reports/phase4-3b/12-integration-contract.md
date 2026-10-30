# 12 集成契约（Phase4-3B → Phase5-3 交付）

- 交付物定位：**独立推理适配层**，不修改 `src/job_matching/service/`、`frontend/`、API 契约文件；如需接入由 Phase5-3 侧调用本层接口。
- 代码位置：`src/job_matching/models/`（text_encoder / retrieval / reranker / fusion）、`src/job_matching/evaluation/`。

## 1. 统一模型输出（建议结构，不破坏现有 API 契约）

```json
{
  "model_id": "bge-small-zh-v1.5+lexical-fusion",
  "model_version": "research-v1",
  "score": 0.7234,
  "score_type": "ranking_score",
  "explanation": {
    "contributions": {"semantic": 0.24, "skill": 0.18, "education": 0.15},
    "constraints": [{"name": "education", "kind": "hard", "passed": true, "reason": "学历满足：本科 >= [本科]"}],
    "filtered": false,
    "filter_reason": null
  },
  "feature_version": "v1",
  "degradation": null
}
```

硬性语义约束：
1. `score` 是**排序分数**，禁止解释为录用概率/成功率；
2. `score_type` 必填，禁止省略；
3. 模型缺失/加载失败时：按原契约显式失败或降级（`degradation` 写明原因），禁止静默返回随机分；
4. NaN/Inf 分数禁止出层（契约测试守护）；
5. 日志/导出禁止落简历原文与 PII（`job_matching.annotation.pii.check_export` 出口校验）。

## 2. 推理接口（概念签名，遵循项目既有抽象）

```python
# 召回：统一 RecallIndex 契约
index = RecallFusion(indexes=[BM25Recall(), TfidfRecall(), EmbeddingRecall(build_encoder("bge_small_zh_v15"))])
index.build(job_texts)                       # 语料构建，无标签
hits = index.search(query_texts, top_k=10)   # [[(doc_id, score), ...], ...]

# 精排：可选
rr = build_reranker("bge_reranker_base", local_files_only=True)
result = rr.score(queries, documents)        # RerankResult(scores=np.ndarray, truncated=int)

# 融合与硬/软约束
breakdown = FeatureFusion().score(resume_profile, job_profile, semantic_score=...)
breakdown.to_dict()                          # 可解释明细
```

## 3. 特征 Schema 与版本

- `data/processed/matching/feature_schema.json`（feature_version=v1）：登记特征列、禁止列、IL-1~IL-6 间接泄漏规则、教育子任务输入。
- 输入列禁止清单（摘要）：`final_score / raw_score / skill_score / ... / candidate_rank / candidate_rank_pct / label_strength` 及 ID 列（ID 仅可作连接键）。
- 变更 schema 必须升 feature_version，并回归 `tests/phase4_3b` P2/P7。

## 4. 模型注册与加载配置

- 注册表：`reports/phase4-3b/model-registry.json`（43 条，含 checkpoint SHA-256、依赖版本、指标、限制）。
- 加载配置：`KNOWN_REVISIONS`（`text_encoder.py`）固定 BGE 两模型精确 revision 与许可证（MIT）；`local_files_only=True` 支持离线。
- 运行资源要求：纯 CPU 可运行；BGE 编码 223 texts/s、精排 20.9 pairs/s（CPU，见 10 报告）；模型加载 <4s。

## 5. 权重分发策略

- 大模型权重（BGE 系列）**不入 Git**：`model-registry.json` + `KNOWN_REVISIONS` 登记来源、revision、许可证、SHA-256；可复现获取方式：`snapshot_download(repo, revision=<sha>)`。
- 项目自有 checkpoint（models/ 下 joblib/pt）已存在仓库工作区并登记哈希；历史 checkpoint 只读，新产物写入独立目录。

## 6. 已验证 / 未验证能力清单

| 能力 | 状态 |
|---|---|
| checkpoint 加载/推理/输出逐位复现（matching 12 run） | **已验证** |
| TF-IDF / BM25 / 向量召回、RRF 融合 | **已验证**（契约测试 P4/P5） |
| 硬约束过滤 + 软约束加权 + 可解释明细 | **已验证**（P7） |
| 空文本/超长文本/缺模型/NaN 分数防护 | **已验证**（P5/P6/P8/P10） |
| 冻结数据不可改、导出脱敏 | **已验证**（P10） |
| 研究模型相对基线的**真实**优劣 | **未验证**（H2 BLOCKED） |
| E07 微调模型 | NOT_RUN |
| 千级岗位池延迟、GPU 推理 | NOT_RUN |
| service 层集成行为 | 未验证（Phase5-3 侧） |

## 7. 示例输入输出

输入（简历画像 dict）：`{"education_level": "本科", "skills": ["Python","SQL"], "years_experience": 3.0, "inferred_category": "IT", "city": "上海", "target_position": "算法工程师"}`
输入（岗位 dict）：`{"education_tokens": ["本科"], "skills": ["Python"], "years_min": 1.0, "category": "IT", "city": "上海", "job_title": "算法工程师"}`
输出：上文第 1 节 JSON；`filtered=true` 时 `score=0` 且 `filter_reason` 非空（硬约束不满足原因）。
