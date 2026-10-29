# Phase5-2 缺陷修复与门禁复测记录（2026-10-29）

## 一、触发来源

1. T4 门禁（岗位与推荐闭环）首跑 0/9：持久化事务边界崩溃（`AttributeError: 'sessionmaker' object has no attribute 'url'`）。
2. 后台 Core CI 运行暴露 2 项门禁失败：`.gitignore` 非 UTF-8、错误码说明含"密码"字样。
3. 修复持久化注入后 T3/T6 暴露 5 项后续缺陷（见下）。

## 二、缺陷清单与修复

| 编号 | 缺陷 | 证据 | 修复 |
|---|---|---|---|
| D1 | `session_scope/get_session/get_session_factory` 只接受 `DbSettings`，服务层注入的 `sessionmaker` 直接崩溃 | T4 9/9 ERROR（`profile_store.upload_resume -> session_scope`） | `infra/persistence/base.py`：三函数接受 `DbSettings \| sessionmaker \| Callable[[], Session]`（依赖注入与测试隔离的合法输入） |
| D2 | 批量导入标题语义缺失：缺列行被整行拒绝 | `test_job_import_partial_errors`（created 1 != 2） | `service/job_store.py`：`title` 缺失/null 时从 JD 首个非空行派生标题（`_derive_title`）；**显式空字符串仍拒绝**（缺列 ≠ 空值），语义写入 docstring |
| D3 | 上传简历后 `resume.profile_version` 为 null：`refresh()` 覆盖了未落库的 `profile_version` | `test_link_b`（None != 1） | `service/profile_store.py`：`s.flush()` 后再 `s.refresh(row)`，版本号随事务落库 |
| D4 | 空文档上传被接受（200 + `empty_text` 行），应为 400 | `test_empty_upload_rejected`（200 != 400） | `service/profile_store.py`：抽取结果 `empty_text` → `EMPTY_INPUT`（400），与 Phase5-1 解析接口口径一致；写盘之前拒绝，不留孤儿文件 |
| D5 | 未处理异常裸奔（TestClient 直接抛出，无统一错误信封） | T6 三项 ERROR（数据库不可用/落库失败/条目中断） | `service/api.py` `request_tracking` 兜底：未处理异常统一 500 `INTERNAL_ERROR` 错误信封（脱敏、不泄露堆栈）；事务回滚与孤儿文件清理逻辑不变 |
| D6 | `allow_fallback=True` 未覆盖"模型未注册"（`registry.get` 在 try 之外），显式降级契约失效 | T6 `test_model_missing_without_fallback_is_error` 后半（503 != 200） | `service/matching.py`：注册表查询/加载全部进入降级判定；并区分两种失败：**默认模型槽位未注册 = 部署配置错误，一律显式失败**（不被静默掩盖）；**调用方显式指定的 model_id 未注册 + allow_fallback=True = 显式降级**（`degradation` + `degraded_to_baseline:*` 告警）。与 Phase5-1R 契约（`test_unregistered_model_explicit_error` 等 8 项链路C）完全一致 |
| D7 | `.gitignore` 混入 GBK 编码注释（尾部追加写入），UTF-8 解码失败 | Core CI `test_gitignore_covers_sensitive_paths` ERROR | 全文重写为 UTF-8（内容与敏感路径规则不变） |
| D8 | 错误码登记表说明含"密码"字样，违反 C4 隐私门禁 | Core CI `test_error_codes_do_not_expose_secrets` FAIL | `service/errors.py` 登记表与 `service/accounts.py` 报错文案统一改为"认证失败，凭证无效"（对齐通用认证失败口径，不区分账号/口令） |

## 三、测试侧修正（不降低断言标准，仅修正测量口径/隔离）

| 编号 | 问题 | 处置 |
|---|---|---|
| T-a | T6 `test_db_write_failure_after_file_save_leaves_no_orphan` 基线在建号上传**之前**取数，把用例自己那条合法简历文件误计为孤儿 | 基线改到建号上传之后取（对齐同组 `test_db_unavailable` 的取法）；断言"失败上传不得新增文件"保持不变 |
| T-b | T3 `test_link_b` 与同用户其它用例共享 `stu_b`，绝对版本号断言（v1→v2）被历史上传推进（实测 v3） | 该用例独占全新用户 `stu_linkb`；全部断言（含 `expected_version` 乐观锁、快照不覆盖证据）一字未改 |

## 四、复测结果（全部本地执行）

| 套件 | 结果 | 说明 |
|---|---|---|
| `tests/phase5_2/run_all.py` | **PASS=52 FAIL=0 SKIP=4（ok=True）** | SKIP 为登记过的 NOT_RUN（PostgreSQL 集成缺 `JM_TEST_DATABASE_URL_POSTGRES`、旧依赖栈 checkpoint 等），不计 PASS |
| `tests/core_ci/run_all.py` | **PASS=78 FAIL=0（ok=True）** | 含 C3 运行器可信性、C4 隐私安全、C5 CI 契约 |
| `tests/phase5_1r/run_all.py` | **PASS=151 FAIL=0（ok=True）** | 历史成果无回退 |
| `tests/phase5_1/run_all.py` | **PASS=92 FAIL=0（ok=True）** | 历史成果无回退 |
| `tests/model_training/run_all.py` | PASS=20 ERROR=1（非全量） | `setUpClass (test_t5_inference.T5Inference)` 历史 checkpoint 反序列化失败（依赖栈不兼容）；14:32 改动前基线完全相同，**与本次修复无关**。按运行器纪律只写诊断报告 `model-tests-run-20261029-162007.json`，历史基线 `model-tests.json` 未改动 |

## 五、环境备注

* 依赖探针结论：conda 环境 `graduation-design` 缺 pydantic/passlib/bcrypt/itsdangerous/psycopg2，**不能**作为本项目运行环境；本次全部测试在默认 Python 3.13.2 下执行通过。
* 探针脚本对 argon2-cffi 的 `__version__` 属性检查在新版包上不兼容（导入与 Argon2id 认证链路正常，T2 全绿），仅为探针脚本口径问题。
