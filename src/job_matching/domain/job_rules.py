# -*- coding: utf-8 -*-
"""岗位 / JD 文本纯规则（Domain 层唯一入口）。

包含：
  * 岗位类别启发式分类 classify_job_category（关键词映射，v1 口径）；
  * JD「优先/加分」偏好段落切分 preferred_segment；
  * 语言判定 detect_language（zh / en / mixed / unknown）。

这些都是确定性纯函数：无 IO、无第三方库、无研究数据依赖。
历史口径 `heuristic_keyword_v1` 保持不变——历史评估与模型特征依赖该语义，
不得在本模块内"顺手改进"分类规则；如需变更必须新增版本号并保留 v1。
"""
from __future__ import annotations

import re

# 岗位类别启发式关键词（顺序即优先级）
CATEGORY_KEYWORDS = (
    ("INFORMATION-TECHNOLOGY",
     ("工程师", "开发", "程序员", "算法", "数据", "运维", "测试", "前端", "后端",
      "java", "python", "c++", "嵌入式", "信息安全", "网络安全", "架构师", "人工智能",
      "机器学习", "产品经理", "技术支持")),
    ("FINANCE",
     ("财务", "会计", "金融", "审计", "税务", "出纳", "银行", "投资", "基金", "证券", "风控")),
    ("HR",
     ("人力", "招聘", "人事", "薪酬", "绩效", "培训专员", "劳动关系")),
    ("SALES",
     ("销售", "商务", "渠道", "客户经理", "业务员", "市场拓展", "招投标")),
    ("MARKETING-OPS",
     ("运营", "市场", "品牌", "策划", "文案", "新媒体", "内容", "编辑")),
)
CATEGORY_OTHER = "OTHER"

PREFERRED_MARKERS = ("优先", "加分", "更佳", "尤佳", "者优先")
SECTION_MARKERS = ("任职要求", "岗位要求", "任职资格", "岗位职责", "工作职责", "职位描述")

# 职位/岗位名称词元化（纯文本规则；历史特征口径不变，原实现位于 pair_features）
_TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z0-9+#\.]*|[\u4e00-\u9fff]")


def title_tokens(s: str) -> set[str]:
    """职位/岗位名称的独立词元化：ASCII 取单词，CJK 取单字。"""
    if not isinstance(s, str) or not s:
        return set()
    return {t.lower() for t in _TOKEN_RX.findall(s) if len(t.strip()) >= 1}


def classify_job_category(title, description="") -> tuple[str, str]:
    """启发式岗位类别分类。返回 (category, source)；source 恒为 heuristic_keyword_v1。"""
    s = f"{title or ''} {description or ''}".lower()
    for cat, kws in CATEGORY_KEYWORDS:
        for kw in kws:
            if kw.lower() in s:
                return cat, "heuristic_keyword_v1"
    return CATEGORY_OTHER, "heuristic_keyword_v1"


def preferred_segment(text: str) -> str:
    """返回首个「优先/加分」标记起到结尾的片段；无标记返回空串。"""
    s = "" if text is None else str(text)
    for marker in PREFERRED_MARKERS:
        i = s.find(marker)
        if i >= 0:
            return s[i:]
    return ""


def detect_language(text) -> str:
    """CJK/拉丁字符占比判定语言。返回 zh / en / mixed / unknown。"""
    s = "" if text is None else str(text)
    if not s.strip():
        return "unknown"
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    latin = len(re.findall(r"[A-Za-z]", s))
    total = max(1, cjk + latin)
    zh_ratio = cjk / total
    if zh_ratio >= 0.5:
        return "zh"
    if zh_ratio <= 0.1:
        return "en"
    return "mixed"
