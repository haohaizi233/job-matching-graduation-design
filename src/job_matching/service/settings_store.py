"""用户级设置服务（Phase5-3 / M2 个人设置真实持久化）。

设计边界（任务书 4.3）：
  * 只持久化**用户级业务设置**：基本资料、通知偏好、简历解析偏好、隐私权限、求职意向；
  * 主题等**纯客户端显示偏好**不入库（localStorage）；
  * 不把用户偏好写入后端部署配置 ServiceSettings（那是运维配置，不是用户数据）；
  * 严格输入校验：未知分区/未知字段/超长取值一律 INVALID_REQUEST（422），
    不静默丢弃、不静默截断；
  * 用户隔离：所有读写只针对当前登录用户，服务层不提供跨用户访问入口。
"""
from __future__ import annotations

import re
from typing import Callable

from ..infra.persistence import UserSetting, get_session_factory
from .errors import ServiceError

# ---- 分区 schema（与前端 DTO 同源；新增字段必须同时改这里和前端类型）----
_STR_FIELDS = {
    "basic": ("nickname", "school", "major", "enrollYear", "graduateYear", "region"),
}
_YEAR_FIELDS = ("enrollYear", "graduateYear")
_BOOL_SECTIONS = {
    "notifications": ("siteMessage", "emailNotice", "matchAlert", "weeklyReport"),
    "resume_prefs": ("autoParse", "ocrImages"),
    "privacy": ("publicResume", "companyView", "hideSalary"),
}
_LIST_FIELDS = {"job_intent": ("intentTags",)}

MAX_STR_LEN = 64
MAX_TAG_LEN = 24
MAX_TAGS = 20

_YEAR_RE = re.compile(r"^\d{4}$")

DEFAULT_SETTINGS: dict = {
    "basic": {"nickname": "", "school": "", "major": "",
              "enrollYear": "", "graduateYear": "", "region": ""},
    "notifications": {"siteMessage": True, "emailNotice": False,
                      "matchAlert": True, "weeklyReport": True},
    "resume_prefs": {"autoParse": True, "ocrImages": False},
    "privacy": {"publicResume": True, "companyView": True, "hideSalary": False},
    "job_intent": {"intentTags": []},
}

ALLOWED_SECTIONS = tuple(DEFAULT_SETTINGS.keys())


def _validate_section(name: str, value: object, problems: list[str]) -> dict | None:
    """单分区校验；返回规范化值（None = 该分区非法，问题记入 problems）。"""
    if not isinstance(value, dict):
        problems.append(f"{name} 必须是对象")
        return None

    if name in _STR_FIELDS:
        allowed = set(_STR_FIELDS[name])
        out: dict = {}
        for key, v in value.items():
            if key not in allowed:
                problems.append(f"{name}.{key} 不是允许的字段")
                continue
            if not isinstance(v, str):
                problems.append(f"{name}.{key} 必须是字符串")
                continue
            if len(v) > MAX_STR_LEN:
                problems.append(f"{name}.{key} 长度不得超过 {MAX_STR_LEN}")
                continue
            if key in _YEAR_FIELDS and v and not _YEAR_RE.match(v):
                problems.append(f"{name}.{key} 必须是 4 位年份或留空")
                continue
            out[key] = v
        return out

    if name in _BOOL_SECTIONS:
        allowed = set(_BOOL_SECTIONS[name])
        out = {}
        for key, v in value.items():
            if key not in allowed:
                problems.append(f"{name}.{key} 不是允许的字段")
                continue
            if not isinstance(v, bool):
                problems.append(f"{name}.{key} 必须是布尔值")
                continue
            out[key] = v
        return out

    if name in _LIST_FIELDS:
        allowed = set(_LIST_FIELDS[name])
        out = {}
        for key, v in value.items():
            if key not in allowed:
                problems.append(f"{name}.{key} 不是允许的字段")
                continue
            if not isinstance(v, list):
                problems.append(f"{name}.{key} 必须是数组")
                continue
            tags: list[str] = []
            for tag in v:
                if not isinstance(tag, str) or not tag.strip():
                    problems.append(f"{name}.{key} 含非法标签")
                    continue
                t = tag.strip()
                if len(t) > MAX_TAG_LEN:
                    problems.append(f"{name}.{key} 标签长度不得超过 {MAX_TAG_LEN}")
                    continue
                if t not in tags:
                    tags.append(t)
            if len(tags) > MAX_TAGS:
                problems.append(f"{name}.{key} 标签数量不得超过 {MAX_TAGS}")
                continue
            out[key] = tags
        return out

    problems.append(f"{name} 不是允许的设置分区")
    return None


def validate_settings(payload: object) -> dict:
    """整体校验：返回规范化后的**分区增量**（只含调用方给出的分区）。"""
    if not isinstance(payload, dict) or not payload:
        raise ServiceError("INVALID_REQUEST", "settings 必须是非空对象")
    problems: list[str] = []
    out: dict = {}
    for name, value in payload.items():
        if name not in ALLOWED_SECTIONS:
            problems.append(f"{name} 不是允许的设置分区")
            continue
        normalized = _validate_section(name, value, problems)
        if normalized is not None:
            out[name] = normalized
    if problems:
        raise ServiceError("INVALID_REQUEST", "；".join(problems), {"fields": problems})
    return out


def _defaults() -> dict:
    import copy
    return copy.deepcopy(DEFAULT_SETTINGS)


class UserSettingsService:
    """用户设置读写（依赖注入 session_factory 便于测试；按当前用户隔离）。"""

    def __init__(self, session_factory: Callable | None = None):
        self._session_factory = session_factory or get_session_factory()

    def get(self, user: dict) -> dict:
        """读取当前用户设置（默认值与已存值按分区合并；未知存量键被忽略）。"""
        session = self._session_factory()
        try:
            row = session.query(UserSetting).filter(
                UserSetting.user_id == user["id"]).first()
            merged = _defaults()
            if row and isinstance(row.payload, dict):
                for name in ALLOWED_SECTIONS:
                    stored = row.payload.get(name)
                    if isinstance(stored, dict):
                        merged[name].update(
                            {k: v for k, v in stored.items() if k in merged[name]})
            return merged
        finally:
            session.close()

    def update(self, user: dict, payload: object) -> dict:
        """按分区合并保存（只替换调用方给出的分区），返回保存后的完整设置。"""
        delta = validate_settings(payload)
        session = self._session_factory()
        try:
            row = session.query(UserSetting).filter(
                UserSetting.user_id == user["id"]).first()
            current = _defaults()
            if row and isinstance(row.payload, dict):
                for name in ALLOWED_SECTIONS:
                    stored = row.payload.get(name)
                    if isinstance(stored, dict):
                        current[name].update(
                            {k: v for k, v in stored.items() if k in current[name]})
            for name, section in delta.items():
                current[name].update(section)
            if row is None:
                row = UserSetting(user_id=user["id"], payload=current)
                session.add(row)
            else:
                row.payload = current
            session.commit()
            return current
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
