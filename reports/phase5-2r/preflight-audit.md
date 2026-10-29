# Phase5-2R 预检审计（Preflight Audit）

- 生成时间：2026-10-29T16:40 (UTC+8)
- 仓库：`D:\desktop\毕业设计`
- 验收基准（远端）：`fce73e7e45c2e192797be4e197ff75be2e5ce9ab`
- 本地 HEAD：`fce73e7e45c2e192797be4e197ff75be2e5ce9ab`（**与远端基准一致，无本地提交差异**）

---

## 1. Git 工作区状态

`git status --short` 在本轮开始时为空（工作区干净）；任务书给定的 `??` 未跟踪清单是更早时间点的快照，
其对应文件（`src/job_matching/service/*.py`、`src/job_matching/infra/persistence/*`、
`alembic/`、`tests/phase5_2/`、`reports/phase5-2/*`）已经随 `542f745 / 0257943 / 9593f4f / fce73e7`
提交入库。本轮**未清理、未覆盖任何既有文件**。

当前新增/修改仅限本轮交付物，详见 `git diff` 记录与 `fix-summary.md`。

## 2. 本地可执行基线（真实执行结果）

| 套件 | 命令 | 结果 | 备注 |
|---|---|---|---|
| Phase5-2 | `python tests/phase5_2/run_all.py` | **PASS=52 FAIL=0 SKIP=4**（56 项，29.97s，ok=True） | 与任务书基线 52 PASS / 4 SKIP 完全一致 |
| Core CI | `python tests/core_ci/run_all.py` | **PASS=78 FAIL=0 SKIP=0**（退出码 0） | 与任务书基线 78 PASS 一致 |

Phase5-2 的 4 项 SKIP 逐条登记：
1. `T6.test_model_env_incompatible_is_registered_not_run` —— `NOT_RUN`：需旧依赖栈 checkpoint 才能真实复现 `MODEL_ENV_INCOMPATIBLE`；
2–4. `T7.test_migrate_and_schema_on_postgresql` / `test_jsonb_query_and_constraints_on_postgresql` /
   `test_downgrade_reupgrade_on_postgresql` —— `NOT_RUN`：未提供 `JM_TEST_DATABASE_URL_POSTGRES`。

## 3. 环境探测（PostgreSQL 可用性）

| 检查项 | 结果 |
|---|---|
| `JM_TEST_DATABASE_URL_POSTGRES` | **未设置**（空） |
| `JM_DATABASE_URL` | 未设置（走 SQLite 默认值） |
| `psql` / `initdb` / `pg_ctl` / `pg_isready` | **均不存在**（PATH 无 PostgreSQL 客户端/服务端） |
| `C:\Program Files\PostgreSQL`、`C:\Program Files (x86)\PostgreSQL` | **不存在** |
| Windows 服务 `*postgres*` | **无** |
| TCP `localhost:5432` | **关闭**（`Test-NetConnection` = False） |
| `psycopg2` Python 驱动 | 2.9.10 **已安装**（dt dec pq3 ext lo64） |
| Docker Desktop | 已安装（`C:\Program Files\Docker\Docker`），**daemon 启动中/未就绪**（`docker version` 无法连接 `dockerDesktopLinuxEngine`） |
| WSL 发行版 | `docker-desktop` Running / `Ubuntu` Stopped |
| `pgserver`（内嵌 PostgreSQL wheel） | PyPI / 阿里云镜像均无 Windows 发行版，**安装失败** |

**结论**：本机当前**没有可用的 PostgreSQL 连接**。按任务书第十节执行原则，不猜测连接参数、不清空任何现有库、
不把 T7 标为 PASS。T7 保持 `NOT_RUN/BLOCKED`，并单独输出 PostgreSQL 验证报告记录前置条件。

## 4. 运行时依赖

| 组件 | 版本 |
|---|---|
| Python | 3.13 |
| SQLAlchemy | 2.0.45 |
| Alembic | 1.18.1 |
| FastAPI | 0.120.3 |
| psycopg2 | 2.9.10 |
| argon2-cffi | 可用（`accounts._HAS_ARGON2`） |

## 5. 缺陷确认（逐条指向真实代码位置）

| 编号 | 任务书条目 | 确认结论 | 证据位置 |
|---|---|---|---|
| D1 | P0-01 岗位画像失效 | **确认**。`update_job()` 直接 `setattr(row, k, v)`，改 `job_description` 不失效 `structured_profile`；`matchable_jobs()` 只判 `row.structured_profile` 非空即用于推荐 | `src/job_matching/service/job_store.py:78-89`、`:186-202` |
| D2 | P0-02 推荐指纹 | **确认**。`_fingerprint()` 在有 `idempotency_key` 时指纹退化为 `idk:{user}:{key}`，与请求语义完全脱钩（不同语义会被错误合并，不返回 409）；无 Key 时未纳入 category/city、`allow_fallback`、模型版本、评分配置版本、画像内容指纹、岗位内容/画像版本 | `src/job_matching/service/reco_store.py:245-254` |
| D2b | P0-02 并发判定 | **确认**。`_persist_run()` 用 `"UNIQUE" in str(e).upper()` 字符串匹配识别唯一约束冲突，未识别 `sqlalchemy.exc.IntegrityError` 与具体约束名 | `src/job_matching/service/reco_store.py:283` |
| D3 | P1-03 来源语义 | **确认**。`_parse_job_profile()` 硬编码 `is_synthetic=True`，真实岗位被标合成；`create_job()`/`import_jobs()` 收下 `is_synthetic` 后**完全未使用、未存储、未传递** | `src/job_matching/service/job_store.py:223-228`、`:52-76`、`:143-150` |
| D3b | P1-03 来源漂移 | **确认**。`reparse_resume(is_synthetic=False)` 默认值会在重新解析时把来源**静默改回非合成**，违反"更新/重新解析不静默改变数据来源" | `src/job_matching/service/profile_store.py:166-190` |
| D4 | P1-04 文件误删 | **确认**。`upload_resume()` 落库异常分支无条件 `self.store.delete(storage_key)`；`PrivateFileStore.save()` 的存储键是 `user_id + 内容SHA-256` 的稳定键，同用户并发上传同内容会共享同一文件，失败方会删除成功方引用的文件 | `src/job_matching/service/profile_store.py:120-121`、`src/job_matching/service/file_store.py:41-54` |
| D5 | P1-05 配置注入 | **确认**。`make_business_services()` 用 `os.environ["JM_DATABASE_URL"] = ...` 改写进程全局环境；engine/factory 缓存键只用 `url`，忽略 `echo`；缓存字典无锁 | `src/job_matching/service/business_api.py:66-72`、`src/job_matching/infra/persistence/base.py:67-116` |
| D6 | P1-06 上传上限 | **确认**。`upload_resume()` 端点 `content = file.file.read()` 全量读入后才进业务层大小校验；JSON Base64 端点先 `b64decode` 再校验 | `src/job_matching/service/business_api.py:251-272` |
| D7 | P1-07 分页语义 | **确认**。`list_jobs()` 先 `offset/limit` 再用 Python 过滤技能，`total` 被覆写为"本页命中数"，跨页漏项且 total 错误 | `src/job_matching/service/job_store.py:175-184` |
| D8 | P1-08 PostgreSQL | **环境 BLOCKED**（见第 3 节） | — |
| D9 | P1-09 部署边界 | **确认**。`ServiceSettings.check_deployment_safety()` 只是返回问题列表，`create_app()/create_business_app()` **从不调用**，production 可带着 `local_dev_only` 与未保护的 Phase5-1 端点直接启动；注册接口无独立频率限制；登录失败计数非原子自增 | `src/job_matching/service/settings.py:125-133`、`src/job_matching/service/accounts.py:148-160` |
| D10 | P2 快照一致性 | **确认**。`RecommendationRun` 无画像内容指纹；`job_set_snapshot` 只存 `updated_at` 快照版本，未存岗位内容哈希，无法证明与 JD 一致 | `src/job_matching/infra/persistence/models.py:187-215` |

## 6. 本轮红线（不做的事）

- 不重新训练模型、不改动 `models/` 归档、不动 `data/` 与研究 Gold；
- 不重构模块化单体分层，不迁移目录；
- 不为岗位检索引入 Elasticsearch；
- 不引入对象存储或分布式事务；
- 不批量改写原有 150 条中文岗位与历史训练数据。

## 7. 外部依赖登记（人工登记项）

| 项 | 状态 | 影响 |
|---|---|---|
| PostgreSQL 服务端 | 本机不可用（无安装、无服务、无端口） | T7 = **BLOCKED**，S5 = 有条件通过 |
| Docker Desktop daemon | 未就绪（无法连接 Linux engine） | 备选 PostgreSQL 运行时不可用 |
| 旧依赖栈 checkpoint | 不在本轮范围 | `MODEL_ENV_INCOMPATIBLE` 用例维持历史 `NOT_RUN` |
