# -*- coding: utf-8 -*-
"""简历与学生画像持久化（Phase5-2 / Batch 3）。

流程（任务 5.1）：
  上传 -> 格式/大小/安全检查 -> 私有文件存储 -> 文本解析 -> 画像生成
  -> 用户人工确认/修改 -> 保存画像版本。

证据纪律（任务 5.3）：
  * 每个字段保留来源等级（fact_source ∈ stated_in_source / rule_parsed /
    model_inferred / human_corrected / unknown）与原文证据；
  * 用户人工修改写入 `user_edits` 覆盖层并把字段标记为 human_corrected，
    原始抽取结果完整保留在 `extraction_snapshot`，**不静默覆盖**；
  * 画像每次保存产生新 profile_version，历史版本可回看。

所有权纪律（任务 4.2）：
  * 所有读写都在查询条件里带 user_id；越权访问一律 404（防资源枚举），
    角色不足（学生访问管理端）一律 403；
  * 管理员**不能**读取他人简历原文或原文解析结果（无后门）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..infra.persistence import (Resume, StudentProfile, User,
                                 get_session_factory, session_scope)
from .contracts import FACT_SOURCES, Field, StudentProfile as StudentProfileContract
from .errors import ServiceError
from .file_store import PrivateFileStore, sha256_bytes
from .text_extract import MAX_UPLOAD_BYTES, extract_document_bytes

# 允许人工编辑的画像字段（其余字段只读，避免伪造证据链）
EDITABLE_PROFILE_FIELDS = ("education_level", "major", "graduation_year",
                           "employment_intention", "preferred_cities",
                           "employment_type")


def _now() -> datetime:
    return datetime.utcnow()


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class StudentDataService:
    """简历文件 + 学生画像版本（依赖注入 store / session_factory 便于测试）。"""

    def __init__(self, *, store: PrivateFileStore,
                 session_factory: Callable | None = None,
                 max_upload_bytes: int = MAX_UPLOAD_BYTES):
        self.store = store
        self._session_factory = session_factory or get_session_factory()
        self.max_upload_bytes = int(max_upload_bytes)

    # ============================================================ 简历
    def upload_resume(self, user: dict, *, filename: str, content: bytes,
                      is_synthetic: bool = False) -> dict:
        """上传简历：安全检查 -> 存储 -> 解析 -> 生成画像草稿版本。"""
        content = bytes(content or b"")
        if len(content) > self.max_upload_bytes:
            raise ServiceError("PAYLOAD_TOO_LARGE",
                               f"上传文件 {len(content)} 字节超过上限 {self.max_upload_bytes}")
        # 1) 格式/安全检查 + 文本抽取（失败发生在写盘之前 -> 不产生孤儿文件）
        try:
            extracted = extract_document_bytes(content, filename,
                                               max_bytes=self.max_upload_bytes)
        except ServiceError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ServiceError("PARSE_FAILED", f"文档解析失败: {e}") from e

        # 空正文（空文件/全空白）拒绝入库：与 Phase5-1 解析接口的 EMPTY_INPUT 口径一致
        if extracted.get("parse_status") == "empty_text":
            raise ServiceError("EMPTY_INPUT", "上传文档正文为空，无法解析",
                               {"file_name": str(filename)[:255]})

        digest = sha256_bytes(content)
        session = self._session_factory()
        try:
            existing = (session.query(Resume)
                        .filter(Resume.user_id == user["id"],
                                Resume.file_sha256 == digest).first())
            if existing is not None:
                return {"resume": self._resume_row(existing), "created": False,
                        "note": "同一文件已上传（按内容哈希幂等返回既有简历）"}
        finally:
            session.close()

        # 2) 写私有存储（唯一允许落盘的时刻）
        storage_key, _sha, size = self.store.save(
            user_id=user["id"], original_filename=filename, content=content)

        profile_dict = None
        parse_status = extracted["parse_status"]
        parse_error = None
        if parse_status == "ok":
            try:
                profile_dict = self._parse_profile(extracted["text"], user,
                                                   filename=filename,
                                                   is_synthetic=is_synthetic)
                parse_status = "ok" if profile_dict["profile"]["parse_status"] == "ok" else "partial"
            except ServiceError as e:
                parse_status, parse_error = "failed", e.message[:500]
            except Exception as e:  # noqa: BLE001
                parse_status, parse_error = "failed", str(e)[:500]

        # 3) 落库（一个事务）；任何失败 -> 删除刚写入的文件（不留孤儿）
        try:
            with session_scope(self._session_factory) as s:
                row = Resume(user_id=user["id"],
                             original_filename=str(filename)[:255],
                             storage_key=storage_key, file_sha256=digest,
                             file_size=size, parse_status=parse_status,
                             parse_error=parse_error)
                s.add(row)
                s.flush()
                if profile_dict is not None:
                    prof = self._new_profile_row(s, user["id"], profile_dict,
                                                 resume_id=row.id, confirmed=0)
                    row.profile_version = prof.profile_version
                    profile_dict["profile_version"] = prof.profile_version
                s.flush()          # 先落库（含 profile_version），避免 refresh 丢弃未保存改动
                s.refresh(row)
                resume_out = self._resume_row(row)
        except Exception:
            self.store.delete(storage_key)   # 上传失败不得留下无人关联的敏感文件
            raise

        out = {"resume": resume_out, "created": True}
        if profile_dict is not None:
            out["profile"] = profile_dict
        if parse_error:
            out["warnings"] = [f"parse_failed:{parse_error}"]
        return out

    def list_resumes(self, user: dict) -> list[dict]:
        session = self._session_factory()
        try:
            rows = (session.query(Resume).filter(Resume.user_id == user["id"])
                    .order_by(Resume.uploaded_at.desc()).all())
            return [self._resume_row(r) for r in rows]
        finally:
            session.close()

    def get_resume(self, user: dict, resume_id: str) -> dict:
        return self._resume_row(self._owned_resume(user, resume_id))

    def delete_resume(self, user: dict, resume_id: str) -> dict:
        """删除自己的简历（数据库行 + 私有文件；画像版本保留可追溯）。"""
        session = self._session_factory()
        try:
            row = self._owned_resume(user, resume_id, session=session)
            storage_key = row.storage_key
            session.delete(row)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        self.store.delete(storage_key)   # 文件删除失败不回滚已提交的元数据删除
        return {"deleted": True, "resume_id": resume_id,
                "note": "画像版本保留（历史推荐解释仍可追溯）"}

    def reparse_resume(self, user: dict, resume_id: str, *,
                       is_synthetic: bool = False) -> dict:
        """失败重试 / 重新解析：重新抽取文本并生成新画像版本。"""
        session = self._session_factory()
        try:
            row = self._owned_resume(user, resume_id, session=session)
            content = self.store.read_bytes(row.storage_key)
            filename = row.original_filename
        finally:
            session.close()

        extracted = extract_document_bytes(content, filename,
                                           max_bytes=self.max_upload_bytes)
        parse_status = extracted["parse_status"]
        parse_error = None
        profile_dict = None
        if parse_status == "ok":
            try:
                profile_dict = self._parse_profile(extracted["text"], user,
                                                   filename=filename,
                                                   is_synthetic=is_synthetic)
                parse_status = "ok" if profile_dict["profile"]["parse_status"] == "ok" else "partial"
            except ServiceError as e:
                parse_status, parse_error = "failed", e.message[:500]

        with session_scope(self._session_factory) as s:
            row = self._owned_resume(user, resume_id, session=s)
            row.parse_status = parse_status
            row.parse_error = parse_error
            if profile_dict is not None:
                prof = self._new_profile_row(s, user["id"], profile_dict,
                                             resume_id=row.id, confirmed=0)
                row.profile_version = prof.profile_version
                profile_dict["profile_version"] = prof.profile_version
            s.flush()
            out = {"resume": self._resume_row(row)}
        if profile_dict is not None:
            out["profile"] = profile_dict
        return out

    # ============================================================ 画像
    def latest_profile(self, user: dict) -> dict:
        session = self._session_factory()
        try:
            row = self._latest_profile_row(user, session=session)
            return self._profile_row(row)
        finally:
            session.close()

    def profile_history(self, user: dict) -> list[dict]:
        session = self._session_factory()
        try:
            rows = (session.query(StudentProfile)
                    .filter(StudentProfile.user_id == user["id"])
                    .order_by(StudentProfile.profile_version.desc()).all())
            return [{"profile_version": r.profile_version, "confirmed": bool(r.confirmed),
                     "resume_id": r.resume_id, "created_at": _iso(r.created_at),
                     "updated_at": _iso(r.updated_at)} for r in rows]
        finally:
            session.close()

    def get_profile_version(self, user: dict, version: int) -> dict:
        session = self._session_factory()
        try:
            row = (session.query(StudentProfile)
                   .filter(StudentProfile.user_id == user["id"],
                           StudentProfile.profile_version == int(version)).first())
            if row is None:
                raise ServiceError("NOT_FOUND", "画像版本不存在")
            return self._profile_row(row)
        finally:
            session.close()

    def save_profile(self, user: dict, edits: dict | None = None, *,
                     confirm: bool = False, note: str | None = None,
                     expected_version: int | None = None) -> dict:
        """保存画像版本：人工修改进 user_edits 覆盖层，抽取证据不被覆盖。"""
        edits = dict(edits or {})
        unknown = [k for k in edits if k not in EDITABLE_PROFILE_FIELDS]
        if unknown:
            raise ServiceError("INVALID_REQUEST",
                               f"不允许编辑的字段: {unknown}",
                               {"editable_fields": list(EDITABLE_PROFILE_FIELDS)})
        session = self._session_factory()
        try:
            base = self._latest_profile_row(user, session=session, required=True)
            if expected_version is not None and int(expected_version) != base.profile_version:
                raise ServiceError("CONFLICT",
                                   f"画像已被其他操作更新（当前版本 {base.profile_version}）",
                                   {"current_version": base.profile_version})
            data = dict(base.profile_data or {})
            profile = dict(data.get("profile") or {})
            user_edits = dict(data.get("user_edits") or {})
            now_iso = _now().isoformat()

            for field_name, value in edits.items():
                prev = dict(profile.get(field_name) or {})
                user_edits[field_name] = {
                    "value": value, "edited_at": now_iso,
                    "note": note or "",
                    # 人工修改不得静默覆盖原始抽取证据 -> 保留修改前快照
                    "previous": {"value": prev.get("value"),
                                 "fact_source": prev.get("fact_source"),
                                 "evidence_text": prev.get("evidence_text", "")},
                }
                updated = dict(prev or Field.unknown().to_dict())
                updated["value"] = value
                updated["fact_source"] = "human_corrected"
                updated["note"] = ((updated.get("note") or "") + " | user_edited").strip(" |")
                profile[field_name] = updated

            profile["parse_status"] = profile.get("parse_status", "ok")
            data["profile"] = profile
            data["user_edits"] = user_edits
            data.setdefault("extraction_snapshot", None)

            new_row = self._new_profile_row(session, user["id"], data,
                                            resume_id=base.resume_id,
                                            confirmed=1 if confirm else base.confirmed)
            session.commit()
            session.refresh(new_row)
            return self._profile_row(new_row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ============================================================ 内部
    def _parse_profile(self, text: str, user: dict, *, filename: str,
                       is_synthetic: bool) -> dict:
        from .resume_parser import parse_resume_text
        profile = parse_resume_text(
            text,
            profile_id=f"user_{user['id'][:8]}",
            is_synthetic=bool(is_synthetic),
            source_document=str(filename)[:255])
        d = profile.to_dict()
        return {"profile": d,
                # 原始抽取快照（人工修改永不覆盖这里）
                "extraction_snapshot": d,
                "user_edits": {}}

    def _new_profile_row(self, session, user_id: str, data: dict, *,
                         resume_id: str | None, confirmed: int):
        latest = (session.query(StudentProfile)
                  .filter(StudentProfile.user_id == user_id)
                  .order_by(StudentProfile.profile_version.desc()).first())
        version = (latest.profile_version + 1) if latest else 1
        row = StudentProfile(user_id=user_id, profile_version=version,
                             profile_data=data, resume_id=resume_id,
                             confirmed=int(confirmed))
        session.add(row)
        session.flush()
        return row

    def _latest_profile_row(self, user: dict, *, session=None, required: bool = False):
        own = session is not None
        s = session or self._session_factory()
        try:
            row = (s.query(StudentProfile)
                   .filter(StudentProfile.user_id == user["id"])
                   .order_by(StudentProfile.profile_version.desc()).first())
            if row is None:
                if required:
                    raise ServiceError("NOT_FOUND", "尚未生成学生画像，请先上传简历")
                raise ServiceError("NOT_FOUND", "尚未生成学生画像")
            return row if own else self._profile_row(row)
        finally:
            if not own:
                s.close()

    def _owned_resume(self, user: dict, resume_id: str, *, session=None):
        own = session is not None
        s = session or self._session_factory()
        try:
            row = (s.query(Resume)
                   .filter(Resume.id == resume_id,
                           Resume.user_id == user["id"]).first())
            if row is None:
                # 越权/不存在统一 404（防资源枚举）
                raise ServiceError("NOT_FOUND", "简历不存在")
            return row
        finally:
            if not own:
                s.close()

    @staticmethod
    def _resume_row(r: Resume) -> dict:
        return {"id": r.id, "original_filename": r.original_filename,
                "storage_key": r.storage_key, "file_sha256": r.file_sha256,
                "file_size": r.file_size, "parse_status": r.parse_status,
                "parse_error": r.parse_error, "profile_version": r.profile_version,
                "uploaded_at": _iso(r.uploaded_at), "updated_at": _iso(r.updated_at),
                "note": "storage_key 为受控存储键，不含本机路径；原文不通过 API 返回"}

    @staticmethod
    def _profile_row(p: StudentProfile) -> dict:
        return {"id": p.id, "user_id": p.user_id,
                "profile_version": p.profile_version,
                "confirmed": bool(p.confirmed),
                "resume_id": p.resume_id,
                "profile_data": p.profile_data,
                "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at)}
