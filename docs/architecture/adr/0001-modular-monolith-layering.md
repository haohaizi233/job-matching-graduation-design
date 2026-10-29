# ADR-001：模块化单体分层与依赖方向

- 状态：已采纳（Phase5-1A）
- 日期：2026-10-29

## 背景

`src/job_matching` 同时承载研究（标注/训练/评估）与业务推理（FastAPI）。
重构前 `service/*` 直接导入 `annotation/*`，导致业务 API 被迫加载 pandas，
且研究层改动会波及业务（详见 `phase5-1a-current-state.md` §2.1）。

## 决策

采用**简化 Clean Architecture** 的模块化单体（非微服务）：

- `domain/`：纯业务规则（无 IO、无三方重依赖）；
- `service/`：应用用例 + 接口层（FastAPI 路由）；
- `infra/`：外部格式/外部系统适配；
- `research`（annotation/training/evaluation/independent_eval）：允许依赖 domain，
  反向禁止。

不引入 Ports & Adapters 的全套抽象：只保留两个真实接缝——`Services` 容器
（测试可整体替换）与 `ModelRegistry(loader_impl=...)`（模型加载可替换）。

## 后果

- 正面：`import job_matching.service.api` 不再加载 pandas；研究改动不波及业务；
  依赖方向可被 `tests/phase5_1a` 自动守卫。
- 负面：`annotation/pool.py` 等旧路径以 re-export 保留，短期内存在两处入口
  （新旧），需在文档中标明唯一实现位置。
- 未采纳的替代方案：把 `service/` 重命名为 `application/` 并引入用例类
  ——收益不足以覆盖 API/测试迁移风险（见 current-state §4）。
