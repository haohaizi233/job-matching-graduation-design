# Phase5-1 业务推理服务 API 文档（v1）

- 实现：`src/job_matching/service/api.py`（FastAPI，`create_app()` 工厂）
- 启动：`uvicorn job_matching.service.api:create_app --factory --port 8000`（或任意 ASGI 宿主）
- 交互式文档：`GET /docs`（Swagger UI）、`GET /openapi.json`
- 依赖缺口：`environment.yml` 未声明 `fastapi / pydantic / httpx`（测试），
  当前活动解释器已具备（fastapi 0.120.3 / pydantic 2.9.2 / httpx 0.28.1）；
  按 `environment.yml` 重建环境时需补装。业务核心（画像/解析/匹配）延迟导入 Web 框架，不被绑死。

> 分数语义：所有 `score` 均为**排序参考分**（`heuristic_score` / `model_raw_score`），
> 不是录用概率；不返回"录用成功概率"；`calibrated_score` 本轮禁用。

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 版本 | 路径前缀 `/api/v1`；响应含 `api_version`、`app_version` |
| 请求追踪 | 每个响应含 `request_id`；可传 `X-Request-ID` 覆盖，响应头回传 `X-Request-ID` / `X-API-Version` |
| 响应信封（成功） | `{"request_id", "api_version", "app_version", "data": {...}, "warnings": [...]}` |
| 响应信封（失败） | `{"error": {"code", "message", "request_id", "detail": {...}}}`，HTTP 状态见 §4 |
| 验证 | 全部请求/响应走 Pydantic 模型（`ResumeParseIn` / `JobParseIn` / `RankIn` 等） |
| 批量上限 | `jobs` ≤ 200（超出 -> `BATCH_LIMIT_EXCEEDED` / Pydantic 422） |
| 文本上限 | 单文本 ≤ 200 000 字符 |
| 超时 | `options.timeout_ms`（默认 30000，上限 600000），超预算 -> `INFERENCE_TIMEOUT`（408） |
| 日志 | 只记元信息（method/path/status/latency/request_id），不记正文；日志层 PII 掩码兜底 |
| 文件上传 | `file_name + content_base64`；支持 txt / docx / pdf（可提取文本层）；
扫描版或空文本 PDF -> `OCR_REQUIRED`，不伪装成功 |

## 2. 端点

### 2.1 `GET /api/v1/health`

无请求体。`data`：

```json
{"status": "ok", "api_version": "v1", "modes": ["baseline", "experimental_model", "future_verified"],
 "models_registered": ["baseline_skill_text_v1", "chinese_match_future_v1"],
 "note": "Phase5-1 工程集成服务；中文匹配模型效果未验收（H2 BLOCKED）"}
```

### 2.2 `POST /api/v1/profiles/resume/parse` — 中文简历 -> 学生画像

请求（`ResumeParseIn`）：

```json
{"text": "求职意向：Java开发工程师\n…", "profile_id": "stu_001",
 "file_name": null, "content_base64": null,
 "is_synthetic": true, "structured_fields": null}
```

`data.profile` 为 `StudentProfile`（`contracts.py`）：`profile_id / education_level / major /
graduation_year / employment_intention / preferred_cities / employment_type / skills /
project_experiences / internship_experiences / certificates / source_evidence /
profile_version / parse_status / warnings`。

字段三件套：`fact_source ∈ {stated_in_source, rule_parsed, model_inferred, human_corrected, unknown}`、
`evidence_text`（原文证据，PII 已掩码）、`extraction_method`；技能另有
`verification_status ∈ {self_reported, extracted_from_resume, assessment_supported,
manually_verified, unknown}` 与 `confidence`（**抽取置信度，不是技能掌握概率**）。

解析状态：`ok / partial / unknown / ocr_required / empty_text / needs_review`。
扫描版 PDF 触发 `OCR_REQUIRED`（422）。

### 2.3 `POST /api/v1/profiles/job/parse` — 中文岗位 JD -> 岗位画像

请求（`JobParseIn`）：`text` 或 `file_name + content_base64`，`job_id / source / source_license /
is_synthetic / structured_fields`。

`data.job_profile` 为 `JobProfile`：`job_id / job_title / job_category / employer / city /
employment_type / graduation_cohort / salary / education_requirement / experience_requirement /
required_skills / preferred_skills / responsibilities / source / source_license /
source_evidence / profile_version / warnings`。

- `required_skills` 与 `preferred_skills` 严格区分（"优先/加分/更佳"标记段）；
- 缺失字段保留 `status=unknown`，不凭空补齐；
- `education_requirement`：`tokens`（6 token 子集）、`status ∈ {ok, rules_only, model, rejected,
  needs_review, unknown}`、`model_version`、`expression_seen_in_train`、`rule`、
  `confidence`（附含义声明）、`needs_human_review`；异常表达 -> `rejected` / 人工复核。

### 2.4 `POST /api/v1/matching/rank` — 岗位排序与解释

请求（`RankIn`）：

```json
{"resume_text": "…", "resume_profile": null,
 "jobs": [{"job_id": "job_a", "text": "职位名称：…"}, {"profile": {"…JobProfile…"}}],
 "options": {"mode": "baseline", "top_k": 10, "model_id": null,
             "allow_fallback": true, "timeout_ms": 30000, "formal": false}}
```

`resume_profile` / `jobs[].profile` 可直接传画像对象（供服务内部复用），
否则走文本解析。`data.ranking`：

```json
{"mode": "baseline", "scoring_method": "baseline_skill_text_v1",
 "score_type": "heuristic_score", "model_version": "baseline_skill_text_v1-20261029",
 "evaluation_status": "not_a_trained_model", "formal_evaluation": false,
 "demo": true, "label_source": "synthetic_or_unlabeled",
 "options": {...}, "warnings": ["score_semantics:排序参考分，不是录用概率", ...],
 "results": [ {…} ], "request_id": "…", "api_version": "v1", "latency_ms": 12.3}
```

单条结果（模块 D）：

```json
{"job_id": "job_a", "rank": 1, "score": 0.9105, "score_type": "heuristic_score",
 "scoring_method": "baseline_skill_text_v1", "model_version": "…",
 "matched_skills": [{"canonical_name": "java", "evidence_text": "…", "evidence_source": "…",
                     "verification_status": "extracted_from_resume", "jd_evidence_text": "…"}],
 "missing_required_skills": [{"canonical_name": "spring boot", "status": "evidence_missing",
                              "jd_evidence_text": "…", "note": "当前简历证据未覆盖该技能，不代表候选人不具备该技能"}],
 "preferred_skills_missing": [...],
 "education_constraint": {"status": "satisfied", "needs_human_review": true,
                          "job_requirement": {...}, "student_education": {...}, "note": "..."},
 "experience_constraint": {"status": "requirement_unclear", "needs_human_review": true, ...},
 "graduation_cohort_constraint": {...}, "skill_constraint_status": "satisfied",
 "evidence": [{"type": "skill_matched", "skill": "java", "student_evidence_text": "…",
               "jd_evidence_text": "…"}],
 "warnings": ["education_constraint_needs_human_review"]}
```

约束四态：`satisfied / not_satisfied / insufficient_evidence / requirement_unclear`。
简历未命中技能一律 `evidence_missing`（证据不足），**不表述为"不会该技能"**；
学历/经验/毕业届别结论一律 `needs_human_review=true`，不做硬编码资格否决。

### 2.5 `GET /api/v1/models`

返回全部注册模型信息（§1 字段）+ `error_codes` 目录。
含 `baseline_skill_text_v1`、`chinese_match_future_v1`（future_verified 预留槽位），
按需含 `legacy_match_proxy_v1` / `education_normalizer_v1`（需指定 run 目录）。

### 2.6 `GET /api/v1/models/{model_id}/status`

`data.model_status`：注册信息 + `load_state`（`loaded / not_loaded`）、
`load_count_total`（真正加载次数）、`checksum_check`（`checksum_ok / missing / mismatch`）。
未注册 -> `MODEL_MISSING`（503）。

## 3. 模型版本与确定性

- 每条排名结果记录 `model_version` 与 `scoring_method`；
- 同输入 + 同模型版本 -> 结果确定（稳定排序：分数降序，同分按输入顺序；S22 自动化验证）；
- 模型只在初始化或缓存失效时加载（S21 验证 `load_count / cache_hits`）。

## 4. 错误码（`service/errors.py`，唯一事实来源）

| code | HTTP | 含义 |
|---|---|---|
| `INVALID_REQUEST` | 422 | 请求字段缺失或取值非法（含非法 mode / 画像反序列化失败） |
| `UNSUPPORTED_FORMAT` | 415 | 文件格式不支持 |
| `EMPTY_INPUT` | 400 | 输入正文为空 |
| `OCR_REQUIRED` | 422 | 扫描版或无文本层 PDF，需要 OCR |
| `PARSE_FAILED` | 422 | 文档解析失败 |
| `BATCH_LIMIT_EXCEEDED` | 400 | 批量条数超上限 |
| `INFERENCE_TIMEOUT` | 408 | 推理超时 |
| `MODEL_MISSING` | 503 | 模型权重/清单缺失或加载失败 |
| `MODEL_INAPPLICABLE` | 422 | 业务输入无法合法构建旧模型特征（detail 列缺失字段） |
| `MODEL_FORMAL_USE_FORBIDDEN` | 422 | 未通过中文正式用途验证，拒绝正式模式 |
| `FUTURE_MODEL_UNAVAILABLE` | 503 | future_verified 暂无已验证中文模型 |
| `LEAKAGE_GUARD` | 422 | 输入携带目标值/派生评分禁用字段 |
| `INTERNAL_ERROR` | 500 | 服务内部错误 |

## 5. 端到端调用示例（实测）

```bash
# 1) 健康检查
curl http://127.0.0.1:8000/api/v1/health

# 2) 简历解析
curl -X POST http://127.0.0.1:8000/api/v1/profiles/resume/parse \
  -H "Content-Type: application/json" \
  -d '{"text":"求职意向：Java开发工程师\\n专业技能：Java、MySQL","profile_id":"stu_demo","is_synthetic":true}'

# 3) 岗位解析 + 4) 排序（一次性）
curl -X POST http://127.0.0.1:8000/api/v1/matching/rank \
  -H "Content-Type: application/json" \
  -d '{"resume_text":"求职意向：Java开发工程师\\n专业技能：Java、MySQL",
       "jobs":[{"job_id":"job_a","text":"职位名称：Java开发工程师\\n任职要求：\\n1. 本科及以上学历\\n2. 熟悉 Java、MySQL"}],
       "options":{"mode":"baseline"}}'
```

Python（`fastapi.testclient` 或 `httpx`）：

```python
from job_matching.service.api import create_app, make_services
from fastapi.testclient import TestClient

client = TestClient(create_app(make_services()))
r = client.post("/api/v1/matching/rank", json={
    "resume_text": "求职意向：Java开发工程师\n专业技能：Java、MySQL",
    "jobs": [{"job_id": "job_a", "text": "职位名称：Java开发工程师\n任职要求：\n1. 本科及以上学历\n2. 熟悉 Java、MySQL"}],
    "options": {"mode": "baseline"}})
print(r.json()["data"]["ranking"]["score_type"])   # heuristic_score
```

依赖注入（可测试性）：`create_app(services)` 接受替换后的 `Services` 容器
（`registry / matching / education_resolver / config`），测试用桩注册表整体替换，
不触碰真实 checkpoint（见 `tests/phase5_1/_util.py::StubMatchPredictor`）。

## 6. 非目标（本阶段明确不做）

不引入 Redis / Celery / 微服务注册中心 / 用户系统 / 前端；不做模型训练与重训；
不写 `models/` 与 `data/independent_eval/`；不输出"录用成功概率"。
