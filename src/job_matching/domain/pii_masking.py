# -*- coding: utf-8 -*-
"""个人信息检测与掩码（安全基础能力，Domain 层共享）。

范围：邮箱、手机号（中国大陆）、身份证号、座机、微信/QQ 号、详细住址关键词、
姓名键值对（`姓名：xxx` 形式的原文姓名必须脱敏）。

隐私口径（Phase5-1A 强制区分两类产物）：
  * 本模块产出的 `mask_matches()` 是**展示/日志/证据留存用掩码**，
    属于可逆改写（原始文本仍可能存在于上游内存与原始资料中），
    **不等于**不可逆匿名化；
  * 原始资料处理（data/private、真实简历）与公开研究产物（冻结数据集、报告）
    的隐私标准分别定义：公开产物必须经 `check_export()` 全量校验，
    且不得声称"已匿名化"，只能表述为"已脱敏/已掩码"。

原则：
  * 检测只报告「命中类型 + 命中数量」，日志中绝不输出原始号码；
  * 导出前必须过 scrub_record / check_export，违规直接抛错而不是静默放行。
"""
from __future__ import annotations

import re

MASK = "***"

# 命中 -> 正则。保守取向：宁可多报（进人工复核），不可漏报放行。
_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "mobile_cn": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card_cn": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "landline": re.compile(r"(?<!\d)0\d{2,3}-\d{7,8}(?!\d)"),
    "qq_wechat_id": re.compile(r"(?i)(?:qq|微信|vx|wechat|联系方式|电话|手机|邮箱|住址|地址)"
                               r"\s*[:：]?\s*[\w\-\.\@]{5,}"),
    # 姓名键值对（如「姓名：张三」）：键 + 冒号 + 中文/英文姓名。
    # 不匹配无键值结构的任意人名，避免误伤正文叙述。
    "name_kv": re.compile(r"(?:真实姓名|姓\s*名|名字)\s*[:：]\s*[\u4e00-\u9fff·]{2,6}"
                          r"(?:[·\s]?[A-Za-z]{1,20})?"),
}

# 结构化字段：命中即违规（不允许出现在导出数据里）
_PII_FIELD_TOKENS = (
    "phone", "mobile", "tel", "telephone", "email", "mail",
    "wechat", "weixin", "qq", "address", "addr", "contact",
    "联系方式", "电话", "手机", "邮箱", "身份证", "住址", "地址", "姓名",
)
_PII_FIELD_EXACT = {
    "name", "real_name", "full_name", "person_name", "candidate_name", "resume_name",
    "姓名", "真实姓名", "id_card", "id_card_no", "identity",
}


def detect_pii(text) -> dict[str, int]:
    """返回 {命中类型: 命中数量}；不含原文。"""
    s = "" if text is None else str(text)
    out: dict[str, int] = {}
    for kind, rx in _PATTERNS.items():
        n = len(rx.findall(s))
        if n:
            out[kind] = n
    return out


def mask_matches(text) -> str:
    """把命中片段替换为 ***（返回脱敏后文本）。展示级掩码，非不可逆匿名化。"""
    s = "" if text is None else str(text)
    for rx in _PATTERNS.values():
        s = rx.sub(MASK, s)
    return s


def scrub_record(record: dict, fields: tuple[str, ...] | list[str]) -> tuple[dict, dict]:
    """对指定文本字段做脱敏。返回 (脱敏后记录, 命中统计)。"""
    out = dict(record)
    hits: dict[str, int] = {}
    for f in fields:
        if f not in out:
            continue
        d = detect_pii(out[f])
        for k, v in d.items():
            hits[k] = hits.get(k, 0) + v
        out[f] = mask_matches(out[f])
    return out, hits


def pii_field_violations(record: dict) -> list[str]:
    """检查记录里是否残留 PII 结构化字段名（导出白名单之外的敏感列）。

    按分隔符切词做精确命中，避免把 job_name / company_name 之类的非 PII 列误伤。
    """
    bad = []
    for key in record:
        low = str(key).strip().lower()
        if low in _PII_FIELD_EXACT:
            bad.append(str(key))
            continue
        compact = re.sub(r"[^0-9a-zA-Z一-鿿]", "", low)
        if "idcard" in compact or "identitycard" in compact:
            bad.append(str(key))
            continue
        tokens = [t for t in re.split(r"[^0-9a-zA-Z一-鿿]+", low) if t]
        if any(t in _PII_FIELD_TOKENS for t in tokens):
            bad.append(str(key))
    return sorted(set(bad))


def check_export(record: dict, text_fields: tuple[str, ...] | list[str],
                 allowed_columns: tuple[str, ...] | list[str] | None = None
                 ) -> list[str]:
    """导出检查：返回违规描述列表；为空才允许导出。

    检查项：
      1. 文本字段是否残留 PII 命中；
      2. 是否存在 PII 结构化字段名——一律禁止导出，白名单不能覆盖此项；
      3. 是否出现白名单之外的列（防止把内部字段带出去）。
    """
    problems: list[str] = []
    for f in text_fields:
        if f not in record:
            continue
        hits = detect_pii(record[f])
        for kind, n in hits.items():
            problems.append(f"字段 {f} 残留个人信息 {kind} x{n}")
    allowed = set(allowed_columns) if allowed_columns is not None else None
    for key in pii_field_violations(record):
        problems.append(f"字段 {key} 属于个人信息字段，禁止导出")
    if allowed is not None:
        extra = [str(k) for k in record if str(k) not in allowed]
        for k in sorted(extra):
            problems.append(f"字段 {k} 不在导出白名单内")
    return problems
