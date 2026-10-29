# -*- coding: utf-8 -*-
"""可信评估程序（协议第六、七、八节）。

模块：
  dataset    冻结评估集加载、查询组构造、unjudgeable 处理
  metrics    排序指标（复用 metrics_ranking，补充 Precision@K）
  bootstrap  配对 Bootstrap（复用 evaluation/statistical_tests）
  baselines  可执行基线与模型适用性登记

纪律：无真实人工 Gold 时禁止输出正式性能结论（evaluation guardrail）。
"""
from .dataset import EvalSet, GoldUnavailableError, load_eval_set  # noqa: F401
from .metrics import evaluate_ranking_human  # noqa: F401
