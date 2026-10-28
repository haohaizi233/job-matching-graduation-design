# -*- coding: utf-8 -*-
"""job_matching：毕业设计第三阶段数据工程包。

模块划分：
  core / config / schema / policy        基础设施、Schema、特征策略
  preprocess_*                            数据规范化
  embeddings / pair_features              向量缓存与特征构造
  split_matching / education_data         可信切分
  metrics_* / baseline_*                  零训练 Baseline 与指标
  pipeline / reporting                    编排与报告
"""
from .core import ROOT, PIPELINE_VERSION

__all__ = ["ROOT", "PIPELINE_VERSION"]
__version__ = PIPELINE_VERSION
