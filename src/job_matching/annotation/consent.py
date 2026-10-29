# -*- coding: utf-8 -*-
"""数据来源授权（知情同意）记录与门禁（Phase4-3A-2 模块 A / 测试场景 1、3）。

三类来源严格隔离：
  A_consented_individual  经本人同意提供的真实大学生简历；
  B_licensed_public       许可明确允许研究用途的公开简历数据集；
  C_synthetic             仅为工具测试生成的合成简历（永不充当人工 Gold）。

纪律：
  * 无授权记录的真实简历**拒绝进入 Gold**（intake 严格模式直接报错）；
  * 同意状态非 granted 的记录一律隔离，不静默放行；
  * 合成来源必须显式声明 C_synthetic，冒充真实来源直接报错；
  * 授权记录本身可能含个人信息，默认存放在不入库目录。
"""
from __future__ import annotations

import re

CONSENT_FIELDS = (
    "consent_id", "resume_id", "source_class", "subject_pseudo_id",
    "consent_status", "purpose", "data_categories", "storage_note",
    "access_scope", "withdrawal_method", "granted_at", "license",
    "license_evidence",
)

SOURCE_CLASSES = ("A_consented_individual", "B_licensed_public", "C_synthetic")
CONSENT_STATUS_VALUES = ("granted", "licensed", "withdrawn", "denied", "not_applicable")

_PSEUDO_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{2,31}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")


class ConsentError(ValueError):
    """授权记录非法。code 用于测试与报告分类。"""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def validate_consent_record(row: dict) -> dict:
    """校验一条授权记录，返回规范化结果；非法直接报错。"""
    missing = [f for f in CONSENT_FIELDS if f not in row]
    if missing:
        raise ConsentError("missing_fields", f"授权记录缺少字段: {missing}")

    source_class = str(row["source_class"]).strip()
    if source_class not in SOURCE_CLASSES:
        raise ConsentError("invalid_source_class",
                           f"来源类别非法: {source_class!r}，合法值 {SOURCE_CLASSES}")
    consent_id = str(row["consent_id"]).strip()
    if not consent_id:
        raise ConsentError("missing_consent_id", "consent_id 为空")
    pseudo = str(row["subject_pseudo_id"]).strip()
    if not _PSEUDO_RE.match(pseudo):
        raise ConsentError("invalid_pseudo_id",
                           "subject_pseudo_id 必须是随机化代号（禁止使用真实姓名）")
    if re.search(r"[\u4e00-\u9fff]", pseudo):
        raise ConsentError("invalid_pseudo_id", "subject_pseudo_id 不得含中文（防止真实姓名）")

    status = str(row["consent_status"]).strip().lower()
    if status not in CONSENT_STATUS_VALUES:
        raise ConsentError("invalid_consent_status",
                           f"consent_status 非法: {status!r}，合法值 {CONSENT_STATUS_VALUES}")

    if source_class == "C_synthetic":
        if status != "not_applicable":
            raise ConsentError("synthetic_consent_mismatch",
                               "合成来源（C_synthetic）的 consent_status 必须是 not_applicable")
    else:
        if status not in ("granted", "licensed"):
            raise ConsentError("consent_not_granted",
                               f"来源 {source_class} 的授权状态为 {status!r}，禁止进入 Gold")
        if not str(row["granted_at"]).strip() or not _TS_RE.match(str(row["granted_at"]).strip()):
            raise ConsentError("invalid_granted_at", "granted_at 缺失或格式非法")
        if not str(row["withdrawal_method"]).strip():
            raise ConsentError("missing_withdrawal_method",
                               "必须提供授权撤回与删除方式（withdrawal_method）")

    if source_class == "B_licensed_public":
        if not str(row["license"]).strip():
            raise ConsentError("missing_license", "公开数据集来源必须登记 license")
        if not str(row["license_evidence"]).strip():
            raise ConsentError("missing_license_evidence",
                               "公开数据集来源必须登记许可证据（license_evidence）")

    for f in ("purpose", "data_categories", "storage_note", "access_scope"):
        if not str(row[f]).strip():
            raise ConsentError("empty_fields", f"授权记录字段为空: {f}")

    return {
        "consent_id": consent_id,
        "resume_id": str(row["resume_id"]).strip(),
        "source_class": source_class,
        "subject_pseudo_id": pseudo,
        "consent_status": status,
        "purpose": str(row["purpose"]).strip(),
        "data_categories": str(row["data_categories"]).strip(),
        "storage_note": str(row["storage_note"]).strip(),
        "access_scope": str(row["access_scope"]).strip(),
        "withdrawal_method": str(row["withdrawal_method"]).strip(),
        "granted_at": str(row["granted_at"]).strip(),
        "license": str(row["license"]).strip(),
        "license_evidence": str(row["license_evidence"]).strip(),
    }


def consent_index(records: list[dict]) -> dict[str, dict]:
    """按 resume_id 建索引；同一 resume_id 多条授权记录直接报错（禁止覆盖）。"""
    out: dict[str, dict] = {}
    for row in records:
        rec = validate_consent_record(row)
        rid = rec["resume_id"]
        if rid in out:
            raise ConsentError("duplicate_consent",
                               f"resume_id {rid} 存在多条授权记录，禁止静默覆盖")
        out[rid] = rec
    return out


def gold_eligibility(rec: dict) -> tuple[bool, str]:
    """(是否可进 Gold, 原因)。任何不满足项都给出显式原因。"""
    if rec.get("is_synthetic"):
        return False, "synthetic_not_gold"
    if str(rec.get("consent_status", "")).lower() not in ("granted", "licensed"):
        return False, "consent_not_granted"
    if rec.get("source_class") not in SOURCE_CLASSES[:2]:
        return False, "source_class_not_real"
    if rec.get("language") not in ("zh", "mixed"):
        return False, "non_chinese_resume"
    return True, ""
