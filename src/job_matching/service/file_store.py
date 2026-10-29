# -*- coding: utf-8 -*-
"""简历私有文件存储（Phase5-2 / Batch 3）。

约束：
  * 原始文件只进**非公开私有目录**（默认 data/private/resumes，已被 .gitignore 忽略）；
  * 数据库只记录 storage_key（相对存储键），绝不暴露本机绝对路径；
  * 存储键由 内容哈希 决定（同一用户同一内容幂等，天然去重）；
  * 上传失败（校验/解析/落库任一步失败）必须清理已写文件，不得留下无人关联的敏感文件；
  * 存储实现可替换（后续可换对象存储），调用方只依赖本类接口。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..core import ROOT
from .errors import ServiceError

DEFAULT_STORAGE_ROOT = ROOT / "data" / "private" / "resumes"

# 允许的上传扩展名（与 text_extract 支持的格式一致）
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9._\-/]+$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PrivateFileStore:
    """受控私有文件存储（本地目录实现）。"""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else DEFAULT_STORAGE_ROOT

    # -------------------------------------------------------------- 写入
    def save(self, *, user_id: str, original_filename: str,
             content: bytes) -> tuple[str, str, int]:
        """保存文件 -> (storage_key, sha256, size)。任何失败清理已写文件。"""
        if not content:
            raise ServiceError("EMPTY_INPUT", "上传文件内容为空")
        ext = self._check_filename(original_filename)
        digest = sha256_bytes(content)
        storage_key = f"resumes/{user_id}/{digest[:2]}/{digest}{ext}"
        target = self._resolve(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        try:
            if not existed:
                target.write_bytes(content)
        except OSError as e:
            raise ServiceError("INTERNAL_ERROR", "文件写入失败") from e
        return storage_key, digest, len(content)

    def delete(self, storage_key: str) -> bool:
        p = self._resolve(storage_key)
        if p.exists():
            p.unlink()
            return True
        return False

    def read_bytes(self, storage_key: str) -> bytes:
        p = self._resolve(storage_key)
        if not p.exists():
            raise ServiceError("NOT_FOUND", "文件已不存在")
        return p.read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self._resolve(storage_key).exists()

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
