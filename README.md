# 大学生就业岗位画像与简历智能匹配系统的设计与实现

面向大学生求职场景的「岗位画像 + 简历画像 + 智能匹配」机器学习系统毕业设计。

- **项目总览与快速开始**：[docs/project-overview.md](docs/project-overview.md)
  （内含**统一阶段状态清单**：Phase3 / Phase4-1 / Phase4-2 / Phase4-3A / Phase4-3A-2 / Phase5-1 / Phase5-1R
  的工程实现、自动化测试、独立复现、真实业务有效性与阻断项口径，其他文档一律引用该表）
- **项目结构**：[docs/project-structure.md](docs/project-structure.md)
- **环境搭建**：[docs/environment-setup.md](docs/environment-setup.md)
- **数据集索引**：[docs/datasets/README.md](docs/datasets/README.md)

> ⚠ 业务有效性口径：自动化测试通过（含 Phase5-1R 工程整改 A 级通过）**不等于**
> 真实 Gold H2 通过；H2 维持 **BLOCKED**，直至真实中文简历、人工标签与合法盲测集完成。
> 分数（heuristic_score / model_raw_score）均为排序参考分，不是录用概率。
> 业务 API 默认仅本地开发使用（无认证），外网部署为上线阻断项。

> 说明：原始数据集与训练产物体积较大，默认不入库（见 `.gitignore`）；
> 子项目 `chinese-skillspan-benchmark` 为独立仓库，另有远端。
