# -*- coding: utf-8 -*-
"""第四阶段 4.2：中文岗位学历要求规范化 / 多标签分类。

任务范围（必须严格遵守，见 configs/education_labels.yaml 的 task_scope_statement）：
  输入是上游已抽取的 <学历描述> 短槽位，本模块做的是"学历要求表达的规范化 /
  多标签归一"，**不是**从完整 JD 端到端抽取学历信息。

复用关系（不重复造轮子）：
  * 标签规范化 : job_matching.preprocess_education
  * 规则/经验基线 : job_matching.baseline_education
  * 多标签指标 : job_matching.metrics_classification
"""
from .labels import (LABEL_ORDER, encode_multi_hot, label_names,
                     multi_hot_to_tokens, normalize_label, tokens_to_multi_hot)
from .rules import empirical_predict, rule_predict

__all__ = [
    "LABEL_ORDER", "label_names", "normalize_label", "encode_multi_hot",
    "tokens_to_multi_hot", "multi_hot_to_tokens",
    "rule_predict", "empirical_predict",
]
