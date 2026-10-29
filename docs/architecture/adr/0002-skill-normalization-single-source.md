# ADR-002：技能规范化与词表的单一入口

- 状态：已采纳（Phase5-1A）
- 日期：2026-10-29

## 背景

技能相关逻辑分散在四处：`annotation/pool.SKILL_LEXICON`（扫描词表）、
`annotation/pool._SKILL_RES` 与 `service/skills_normalize._boundary_regex`（两份边界匹配实现）、
`preprocess_skills.canonical_skill`（规范名/别名）。重复实现带来
Java/JavaScript、C/C++、Spring/Spring Boot 判定口径漂移的风险。

## 决策

1. **规范名/别名唯一入口**：`preprocess_skills.canonical_skill`（`configs/skills.yaml` 驱动）。
   铁律：禁止子串包含判断；Java ≠ JavaScript、C ≠ C++、Spring ≠ Spring Boot。
2. **启发式扫描词表唯一入口**：`domain.skills_lexicon.SKILL_LEXICON`；
   边界匹配唯一实现 `domain.skills_lexicon.boundary_regex()`，
   `service/skills_normalize._boundary_regex` 改为薄委托。
3. 词表命中只表示"文本出现该技能字样"，**不是**技能掌握程度；
   未命中按"证据不足"处理，不推断为"不具备"。
4. 语义冻结：上述改动不改变历史 checkpoint 的输入特征语义
   （特征由 `training/feature_map.py` + `configs/feature_policy.yaml` 冻结）；
   若需变更语义必须新增版本号（如 `lexicon_v2`）并保留 v1。

## 后果

- 正面：一份实现、一处单测（`tests/phase5_1a` A2SharedRules）；
  业务层与研究层共享同一判定口径。
- 负面：`annotation.pool` 仍导出同名符号（兼容层），需靠文档与守卫测试防止新代码误用旧入口。
