# -*- coding: utf-8 -*-
"""简历私有文件存储（Phase5-2 / Batch 3，Phase5-2R 文件生命周期修订）。

约束：
  * 原始文件只进**非公开私有目录**（默认 data/private/resumes，已被 .gitignore 忽略）；
  * 数据库只记录 storage_key（相对存储键），绝不暴露本机绝对路径；
  * 存储键由 内容哈希 决定（同一用户同一内容幂等，天然去重）；
  * 上传失败（校验/解析/落库任一步失败）必须清理**本次操作独占且未被引用**的文件，
    但**绝不删除其它成功请求正在引用的文件**（P1-04 并发上传竞态）；
  * 存储实现可替换（后续可换对象存储），调用方只依赖本类接口。

Phase5-2R 文件生命周期（P1-04）：
  * `save()` 返回 `(storage_key, sha256, size, created)`，`created` 表示文件是否由
    **本次调用**新建（False = 磁盘上已存在同名稳定键文件，本次请求不拥有它）；
  * `save()` 采用"暂存文件 -> 原子 rename 发布"，写入中途崩溃不会留下半个可见文件；
  * 删除一律走 `delete_if_unreferenced()`（调用方给引用检查回调）；
    已有数据库引用的文件禁止直接删除；
  * `scan_orphans()` / `cleanup_orphans()` 提供延迟清理（孤儿文件扫描）能力。

失败语义登记：
  * 校验/解析失败（写盘前）      -> 直接抛错，无文件副作用；
  * 写盘失败                    -> 清理暂存文件，抛 INTERNAL_ERROR；
  * 落库失败（本次新建的文件）   -> 补偿删除（若未被其它请求引用）；
  * 落库失败（复用既有文件）     -> **不删除**（可能被他人引用）；
  * 元数据已删但文件删除失败     -> 报告 file_cleanup="failed_pending"，留给孤儿扫描；
  * 文件已不存在但元数据还在     -> 读取抛 NOT_FOUND，由调用方决定重新上传或删元数据。
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Callable

from ..core import ROOT
from .errors import ServiceError

DEFAULT_STORAGE_ROOT = ROOT / "data" / "private" / "resumes"

# 允许的上传扩展名（与 text_extract 支持的格式一致）
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9._\-/]+$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_basename(original_filename: str) -> str:
    """文件名净化（跨平台）：剥掉任何路径成分，只留安全基名。

    Windows 与 POSIX 分隔符都处理（`..\\..\\evil.txt` 与 `../../evil.txt`），
    存储键不受此影响（本就由内容哈希决定），这里净化的是**元数据展示名**，
    防止路径穿越字符串流入下游（导出/下载/日志）。
    """
    name = str(original_filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = name.lstrip(".")
    return name or "upload"


class PrivateFileStore:
    """受控私有文件存储（本地目录实现）。"""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else DEFAULT_STORAGE_ROOT

    # -------------------------------------------------------------- 写入
    def save(self, *, user_id: str, original_filename: str,
             content: bytes) -> tuple[str, str, int, bool]:
        """保存文件 -> (storage_key, sha256, size, created)。

        `created=True` 仅当**本次调用**真正新建了文件；目标稳定键已存在时返回
        `created=False`（该文件不属于本次请求，失败时不得删除）。
        写入路径：暂存文件 -> os.replace 原子发布（中途崩溃不产生半成品可见文件）。
        """
        if not content:
            raise ServiceError("EMPTY_INPUT", "上传文件内容为空")
        ext = self._check_filename(original_filename)
        digest = sha256_bytes(content)
        storage_key = f"resumes/{user_id}/{digest[:2]}/{digest}{ext}"
        target = self._resolve(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # 稳定键已存在：天然去重，本次请求不拥有该文件
            return storage_key, digest, len(content), False

        tmp = target.parent / f".{digest}{uuid.uuid4().hex[:10]}.partial"
        created = False
        try:
            with open(tmp, "wb") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            # 原子"独占发布"：硬链接创建在目标已存在时抛 FileExistsError，
            # 且链接内容即暂存文件内容 -> 中途崩溃不会产生半成品可见文件。
            try:
                os.link(tmp, target)
                created = True
            except FileExistsError:
                created = False           # 并发先到者已发布同一内容
            except (OSError, NotImplementedError):  # pragma: no cover - 文件系统不支持硬链接
                existed_before = target.exists()
                os.replace(tmp, target)   # 内容同哈希，覆盖无害
                created = not existed_before
        except OSError as e:
            raise ServiceError("INTERNAL_ERROR", "文件写入失败") from e
        finally:
            if tmp.exists():              # 残留暂存文件一律清理
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return storage_key, digest, len(content), created

    def delete(self, storage_key: str) -> bool:
        p = self._resolve(storage_key)
        if p.exists():
            p.unlink()
            return True
        return False

    def delete_if_unreferenced(self, storage_key: str, *,
                               is_referenced: Callable[[str], bool]) -> dict:
        """仅在**无任何数据库引用**时删除（P1-04 核心不变量）。

        返回 {"deleted": bool, "kept": bool, "reason": str}：
          * referenced_by_others -> 保留文件（其它成功请求正在引用，删除即数据丢失）；
          * deleted               -> 本次补偿删除成功；
          * not_found             -> 文件本就不存在；
          * failed_pending        -> 删除失败，留下待处理状态（由孤儿扫描兜底）。
        """
        key = str(storage_key or "")
        p = self._resolve(key)
        if not p.exists():
            return {"deleted": False, "kept": False, "reason": "not_found"}
        try:
            if is_referenced(key):
                return {"deleted": False, "kept": True, "reason": "referenced_by_others"}
        except Exception:  # noqa: BLE001  引用检查不可用时宁可保留也不误删
            return {"deleted": False, "kept": True, "reason": "reference_check_failed"}
        try:
            p.unlink()
            return {"deleted": True, "kept": False, "reason": "unreferenced"}
        except OSError:
            return {"deleted": False, "kept": True, "reason": "failed_pending"}

    def read_bytes(self, storage_key: str) -> bytes:
        p = self._resolve(storage_key)
        if not p.exists():
            raise ServiceError("NOT_FOUND", "文件已不存在")
        return p.read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).exists()

    # -------------------------------------------------------------- 孤儿扫描
    def scan_orphans(self, *, is_referenced: Callable[[str], bool]) -> list[str]:
        """扫描磁盘上存在但**无数据库引用**的文件（延迟清理用）。"""
        out: list[str] = []
        root = self.root.resolve()
        if not root.exists():
            return out
        for p in root.rglob("*"):
            if not p.is_file() or p.name.endswith(".partial"):
                continue
            key = p.relative_to(root).as_posix()
            try:
                if not is_referenced(key):
                    out.append(key)
            except Exception:  # noqa: BLE001  引用检查失败 -> 不判定为孤儿
                continue
        return out

    def cleanup_orphans(self, *, is_referenced: Callable[[str], bool],
                        max_age_seconds: float = 0.0) -> dict:
        """删除孤儿文件（可按年龄过滤，避免误删刚写入还没来得及入库的文件）。"""
        import time
        root = self.root.resolve()
        deleted, kept = [], []
        for key in self.scan_orphans(is_referenced=is_referenced):
            p = self._resolve(key)
            try:
                if max_age_seconds > 0 and (time.time() - p.stat().st_mtime) < max_age_seconds:
                    kept.append(key)
                    continue
                if is_referenced(key):        # 二次核对（并发下引用可能刚建立）
                    kept.append(key)
                    continue
                p.unlink()
                deleted.append(key)
            except OSError:
                kept.append(key)
        return {"deleted": deleted, "kept": kept,
                "deleted_count": len(deleted), "kept_count": len(kept)}

    # -------------------------------------------------------------- 校验
    def _check_filename(self, original_filename: str) -> str:
        name = Path(str(original_filename or "")).name  # 去掉任何路径成分
        if not name or name in (".", ".."):
            raise ServiceError("INVALID_REQUEST", "文件名非法")
        m = _EXT_RE.search(name)
        if not m or m.group(0).lower() not in ALLOWED_EXTENSIONS:
            raise ServiceError("UNSUPPORTED_FORMAT",
                               f"不支持的文件格式，允许: {', '.join(ALLOWED_EXTENSIONS)}")
        return m.group(0).lower()

    def _resolve(self, storage_key: str) -> Path:
        """存储键 -> 绝对路径；拒绝任何路径穿越。"""
        key = str(storage_key or "")
        if not _SAFE_KEY_RE.match(key):
            raise ServiceError("INVALID_REQUEST", "存储键非法")
        p = (self.root / key).resolve()
        root = self.root.resolve()
        if root != p and root not in p.parents:
            raise ServiceError("INVALID_REQUEST", "存储键越界")
        return p
