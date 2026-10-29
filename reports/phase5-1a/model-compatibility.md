# 历史模型兼容性矩阵（Phase5-1A）

- 生成时间：2026-10-29T14:22:06
- 运行环境：Python 3.13.2 / sklearn 1.8.0 / numpy 2.2.6 / pandas 3.0.0rc1 / torch 2.12.0+cpu
- 汇总：{'loaded': 22, 'loaded_with_version_warning': 15, 'env_incompatible': 5}

| 模型目录 | 模型 | 状态 | 训练环境 | 说明 |
|---|---|---|---|---|
| models\education\charcnn\charcnn-final-20261028-212510 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-balanced-20261028-212534 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-confw-20261028-221032 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-highconf-20261028-221117 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-holdout-20261028-212622 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-holdout-vloss-20261028-213521 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-vloss-20261028-213415 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-final-vloss-balanced-20261028-213450 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\charcnn\charcnn-smoke-charcnn-20261028-211941 | None | loaded | 未记录 | 当前环境可加载 |
| models\education\tfidf\tfidf-final-20261028-212254 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\education\tfidf\tfidf-final-balanced-20261028-212312 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\education\tfidf\tfidf-final-confw-20261028-220908 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\education\tfidf\tfidf-final-highconf-20261028-221021 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\education\tfidf\tfidf-final-holdout-20261028-212556 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\education\tfidf\tfidf-final-title-20261028-212332 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\education\tfidf\tfidf-smoke-tfidf-20261028-211845 | None | loaded_with_version_warning | 未记录 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\gradient_boosting\candidate_cold\gradient_boosting-candidate_cold-final-20261028-203750 | gradient_boosting | env_incompatible | py3.11.18 / sklearn1.5.2 | 历史反序列化入口缺失（依赖版本变化）: AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError' on <module 'sklearn._loss._loss' from 'D:\\APP\\python 3.13.2\\Lib\\site-packages\\sklearn\\_loss\\_loss.cp313-win_amd64.pyd'> |
| models\matching\gradient_boosting\candidate_cold\gradient_boosting-candidate_cold-smoke-20261028-203750 | gradient_boosting | env_incompatible | py3.11.18 / sklearn1.5.2 | 历史反序列化入口缺失（依赖版本变化）: AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError' on <module 'sklearn._loss._loss' from 'D:\\APP\\python 3.13.2\\Lib\\site-packages\\sklearn\\_loss\\_loss.cp313-win_amd64.pyd'> |
| models\matching\gradient_boosting\candidate_cold\smoke-gb-002 | gradient_boosting | env_incompatible | py3.11.18 / sklearn1.5.2 | 历史反序列化入口缺失（依赖版本变化）: AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError' on <module 'sklearn._loss._loss' from 'D:\\APP\\python 3.13.2\\Lib\\site-packages\\sklearn\\_loss\\_loss.cp313-win_amd64.pyd'> |
| models\matching\gradient_boosting\double_cold\gradient_boosting-double_cold-final-20261028-203750 | gradient_boosting | env_incompatible | py3.11.18 / sklearn1.5.2 | 历史反序列化入口缺失（依赖版本变化）: AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError' on <module 'sklearn._loss._loss' from 'D:\\APP\\python 3.13.2\\Lib\\site-packages\\sklearn\\_loss\\_loss.cp313-win_amd64.pyd'> |
| models\matching\gradient_boosting\job_cold\gradient_boosting-job_cold-final-20261028-203750 | gradient_boosting | env_incompatible | py3.11.18 / sklearn1.5.2 | 历史反序列化入口缺失（依赖版本变化）: AttributeError: Can't get attribute '__pyx_unpickle_CyHalfSquaredError' on <module 'sklearn._loss._loss' from 'D:\\APP\\python 3.13.2\\Lib\\site-packages\\sklearn\\_loss\\_loss.cp313-win_amd64.pyd'> |
| models\matching\mlp\candidate_cold\mlp-candidate_cold-final-20261028-203750 | mlp | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\mlp\candidate_cold\mlp-candidate_cold-smoke-20261028-203750 | mlp | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\mlp\candidate_cold\smoke-mlp-001 | mlp | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\mlp\double_cold\mlp-double_cold-final-20261028-203750 | mlp | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\mlp\job_cold\mlp-job_cold-final-20261028-203750 | mlp | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\candidate_cold\ranknet-candidate_cold-ablation-category-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\candidate_cold\ranknet-candidate_cold-ablation-position-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\candidate_cold\ranknet-candidate_cold-ablation-skill-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\candidate_cold\ranknet-candidate_cold-final-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\candidate_cold\ranknet-candidate_cold-smoke-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\candidate_cold\smoke-ranknet-002 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\double_cold\ranknet-double_cold-final-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ranknet\job_cold\ranknet-job_cold-final-20261028-203750 | ranknet | loaded | py3.11.18 / sklearn1.5.2 | 当前环境可加载 |
| models\matching\ridge\candidate_cold\ridge-candidate_cold-ablation-category-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\candidate_cold\ridge-candidate_cold-ablation-position-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\candidate_cold\ridge-candidate_cold-ablation-skill-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\candidate_cold\ridge-candidate_cold-final-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\candidate_cold\ridge-candidate_cold-smoke-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\candidate_cold\smoke-ridge-001 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\double_cold\ridge-double_cold-final-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |
| models\matching\ridge\job_cold\ridge-job_cold-final-20261028-203750 | ridge | loaded_with_version_warning | py3.11.18 / sklearn1.5.2 | 可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核 |

说明：`env_incompatible` 表示历史 checkpoint 与当前依赖栈不兼容，
需要 Legacy Model Compatibility Environment 复现（Conda/venv 隔离，不引入微服务）；
历史权重一律不动；本矩阵不代表任何模型效果验收结论（H2 维持 BLOCKED）。
