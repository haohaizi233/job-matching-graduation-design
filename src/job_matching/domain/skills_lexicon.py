# -*- coding: utf-8 -*-
"""技能启发式词表与边界匹配（Domain 层唯一入口）。

分工（Phase5-1A 技能规范化治理）：
  * **规范名 / 别名映射**唯一入口是 `preprocess_skills.canonical_skill`
    （由 configs/skills.yaml 驱动，铁律：不做子串包含判断，
    Java ≠ JavaScript、C ≠ C++、Spring ≠ Spring Boot）；
  * **启发式扫描词表**（本模块）唯一入口是 `SKILL_LEXICON`，
    仅用于正文命中、抽样分层与标注辅助，不是人工真值；
  * 词表命中一律走 `boundary_regex()` 的边界匹配，避免 Java 命中 JavaScript、
    C 命中 C++/CSS、Spring 命中 Spring Boot 之类的子串误伤。

历史模型兼容：本词表只是"抽取"辅助，不进入历史 checkpoint 的训练特征；
训练特征口径由 `training/feature_map.py` + `configs/feature_policy.yaml` 冻结，
本模块不得改变其语义。
"""
from __future__ import annotations

import re

# 启发式技能词表（中英混合，仅用于抽样分层与标注辅助；非真值）
SKILL_LEXICON = (
    "python", "java", "c++", "c#", "go", "golang", "rust", "javascript", "typescript",
    "sql", "mysql", "postgresql", "oracle", "redis", "mongodb", "hive", "spark",
    "hadoop", "flink", "kafka", "etl", "tableau", "powerbi", "excel", "vba",
    "pytorch", "tensorflow", "机器学习", "深度学习", "自然语言处理", "计算机视觉",
    "数据分析", "数据挖掘", "数据治理", "数据仓库", "爬虫", "算法", "推荐系统",
    "大模型", "llm", "prompt", "transformer", "bert",
    "linux", "docker", "kubernetes", "k8s", "微服务", "spring", "django", "flask",
    "前端", "后端", "全栈", "vue", "react", "android", "ios", "小程序",
    "测试", "自动化测试", "运维", "网络安全", "信息安全",
    "财务分析", "会计", "审计", "税务", "成本核算", "财务报表", "预算管理", "资金管理",
    "投融资", "风控", "合规", "证券", "基金", "银行",
    "人力资源规划", "招聘", "绩效管理", "薪酬管理", "培训", "劳动关系", "社保公积金",
    "销售", "客户开发", "渠道管理", "商务谈判", "大客户", "招投标", "合同管理",
    "市场推广", "品牌策划", "活动策划", "新媒体运营", "内容运营", "用户运营", "社群运营",
    "电商运营", "文案策划", "平面设计", "ui设计", "ps", "pr", "ae", "剪辑",
    "产品经理", "需求分析", "项目管理", "敏捷开发", "英语", "日语",
)

# 首字符是 ASCII 字母数字/符号的词（java / c++ / k8s ...）需要左右边界保护，
# 否则 "java" 会命中 "javascript"、"c++" 会命中 "c+++x"、"ps" 会命中 "photoshop"。
_ASCII_HEAD = re.compile(r"^[A-Za-z0-9+#]")


def boundary_regex(term: str) -> re.Pattern:
    """技能词条 -> 安全边界正则（大小写不敏感的调用方自行 lower）。"""
    if _ASCII_HEAD.match(term):
        return re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(term.lower())}(?![A-Za-z0-9+#])")
    return re.compile(re.escape(term))


def lexicon_patterns(terms=None) -> list[tuple[str, re.Pattern]]:
    """词条序列 -> [(term, regex)]，保持传入顺序（顺序即优先级，输出确定性）。"""
    seq = SKILL_LEXICON if terms is None else terms
    return [(str(t), boundary_regex(str(t))) for t in seq]


def extract_skills(text) -> list[str]:
    """启发式技能词表命中（确定性、按词表顺序）。仅辅助字段，非人工真值。"""
    s = "" if text is None else str(text).lower()
    out = []
    for term, rx in lexicon_patterns():
        if rx.search(s):
            out.append(term)
    return out
