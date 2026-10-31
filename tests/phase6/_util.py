# -*- coding: utf-8 -*-
"""tests/phase6 共用工具：业务夹具复用 + 研究推荐策略专用辅助。

纪律（与 phase5 系列同口径）：
  * 全部夹具为**合成数据**（无真实简历、无真人信息、无 PII），绝不进入 Gold 评估集；
  * 复用 tests/phase5_2r/_util.BusinessHarness（不重复造业务夹具轮子），
    以 importlib 按路径加载，避免 `_util` 模块名自冲突；
  * ROOT 由 __file__ 推导，不硬编码绝对路径；
  * 历史模型权重（models/、data/independent_eval/frozen）只读，不写不删。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase6"


def _load_p52r_util():
    """按文件路径加载 tests/phase5_2r/_util.py（避免 `_util` 重名冲突）。"""
    path = ROOT / "tests" / "phase5_2r" / "_util.py"
    spec = importlib.util.spec_from_file_location("phase5_2r_util", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_p52r = _load_p52r_util()
BusinessHarness = _p52r.BusinessHarness
SYNTHETIC_RESUME_TEXT = _p52r.SYNTHETIC_RESUME_TEXT
SYNTHETIC_JOB_TEXT = _p52r.SYNTHETIC_JOB_TEXT
SYNTHETIC_JOB_TEXT_2 = _p52r.SYNTHETIC_JOB_TEXT_2
SYNTHETIC_JOB_TEXT_V2 = _p52r.SYNTHETIC_JOB_TEXT_V2
run_migrations = _p52r.run_migrations

RESEARCH_MODEL_ID = "zh_research_retrieval_v1"
BGE_MODEL_ID = "zh_research_bge_recall_v1"
RERANK_MODEL_ID = "zh_research_rerank_v1"

RESEARCH_SCORE_TYPE = "model_raw_score"
RESEARCH_SCORING_METHOD_PREFIX = "research_fusion."
RESEARCH_EVAL_STATUS = "research_only_zh"


# ---------------------------------------------------------------- 研究策略辅助
def reset_research_caches() -> None:
    """清空进程级研究策略缓存（索引缓存 + scorer 单例），保证用例互不影响。"""
    from job_matching.service.research_strategy import INDEX_CACHE, _SCORERS
    INDEX_CACHE.invalidate()
    _SCORERS.clear()


def research_specs() -> dict:
    from job_matching.service.research_strategy import RESEARCH_STRATEGY_SPECS
    return RESEARCH_STRATEGY_SPECS


def make_research_scorer(model_id: str, **kw):
    from job_matching.service.research_strategy import build_scorer
    return build_scorer(model_id, **kw)


def synthetic_job_pool(n: int, *, seed: int = 0) -> list[str]:
    """确定性合成岗位文本池（仅用于检索性能/等价性验证，非真实岗位）。"""
    titles = ["Java开发工程师", "前端开发工程师", "数据分析师", "测试开发工程师",
              "运维工程师", "算法工程师", "产品经理", "数据工程师"]
    skills = ["Java", "Spring Boot", "MySQL", "Redis", "JavaScript", "Vue",
              "Python", "SQL", "Linux", "Docker", "Kubernetes", "TensorFlow",
              "Selenium", "Jenkins", "Spark", "Flink"]
    out = []
    for i in range(n):
        t = titles[(i + seed) % len(titles)]
        s = "、".join(skills[(i * 3 + seed) % len(skills):(i * 3 + seed) % len(skills) + 5])
        out.append(f"{t}（合成岗位{i}） 岗位职责：负责{i % 7 + 1}个模块的设计与开发。"
                   f"任职要求：熟练掌握 {s}；有相关项目经验者优先。")
    return out


def synthetic_queries(k: int) -> list[str]:
    base = ["Java Spring Boot 后端开发", "Python 数据分析 SQL", "前端 Vue JavaScript",
            "运维 Linux Docker Kubernetes", "算法 机器学习 TensorFlow",
            "测试 自动化 Selenium", "数据仓库 Spark Flink", "产品经理 需求分析"]
    return [base[i % len(base)] + (f" 查询{i}" if i >= len(base) else "")
            for i in range(k)]
