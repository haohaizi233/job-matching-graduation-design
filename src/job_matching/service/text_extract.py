# -*- coding: utf-8 -*-
"""业务文档文本抽取（模块 A：中文 TXT / PDF / DOCX）。

复用 infra/documents.extract_text 的格式识别与解析器（Phase5-1A 已下沉适配层）；
补充业务层要求：
  * 扫描版 / 无文本层 PDF 必须显式返回 parse_status="ocr_required"，
    绝不允许用空文本伪装解析成功；
  * 不支持的格式返回 UNSUPPORTED_FORMAT 错误码，不静默跳过；
  * 解析器缺失（如未安装 PyMuPDF）返回 PARSE_FAILED，附带可读原因。
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from ..infra.documents import ResumeIntakeError, extract_text
from .errors import ServiceError

SUPPORTED_EXTENSIONS = ("txt", "docx", "pdf")
MIN_TEXT_CHARS = 8          # 低于该长度视为无有效文本层

# ---- 上传与解析资源上限（Phase5-1R F-007）----
MAX_UPLOAD_BYTES = 4 * 1024 * 1024            # 解码后文件大小上限
MAX_ZIP_UNCOMPRESSED_BYTES = 32 * 1024 * 1024  # DOCX(zip) 解压总量上限（防压缩炸弹）
MAX_ZIP_ENTRIES = 2000                         # zip 条目数上限
MAX_EXTRACT_TEXT_CHARS = 200_000               # 解析后文本长度上限


def _guard_docx_zip(path: Path) -> None:
    """DOCX 是 zip：先按中央目录核对解压预算，再交给解析器（防压缩炸弹）。"""
    try:
        with zipfile.ZipFile(path) as z:
            entries = z.infolist()
    except zipfile.BadZipFile as e:
        raise ServiceError("PARSE_FAILED", "DOCX 文件损坏或不是合法 zip 包",
                           {"file_name": path.name}) from e
    if len(entries) > MAX_ZIP_ENTRIES:
        raise ServiceError("PAYLOAD_TOO_LARGE",
                           f"DOCX zip 条目数 {len(entries)} 超过上限 {MAX_ZIP_ENTRIES}",
                           {"file_name": path.name})
    total = sum(int(i.file_size) for i in entries)
    if total > MAX_ZIP_UNCOMPRESSED_BYTES:
        raise ServiceError("PAYLOAD_TOO_LARGE",
                           f"DOCX 解压后总大小 {total} 字节超过上限 "
                           f"{MAX_ZIP_UNCOMPRESSED_BYTES}（疑似压缩炸弹），拒绝解析",
                           {"file_name": path.name})


def extract_document(path: Path | str) -> dict:
    """抽取文档正文。返回 {text, format, extractor, parse_status, note}。

    parse_status ∈ {ok, ocr_required, empty_text}；
    ocr_required / empty_text 时 text 一律为 ""，调用方不得当作成功解析。
    """
    p = Path(path)
    if not p.exists():
        raise ServiceError("PARSE_FAILED", f"文件不存在: {p.name}", {"file_name": p.name})
    ext = p.suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ServiceError("UNSUPPORTED_FORMAT",
                           f"不支持的文件格式 .{ext}，支持 {SUPPORTED_EXTENSIONS}",
                           {"file_name": p.name})
    if ext == "docx":
        _guard_docx_zip(p)
    try:
        got = extract_text(p)
    except ResumeIntakeError as e:
        raise ServiceError("PARSE_FAILED", str(e), {"file_name": p.name}) from e
    text = got.get("text", "") or ""
    fmt = got.get("format", ext)
    if len(text.strip()) >= MIN_TEXT_CHARS:
        return {"text": text, "format": fmt, "extractor": got.get("extractor", ""),
                "parse_status": "ok", "note": ""}
    if fmt == "pdf":
        return {"text": "", "format": fmt, "extractor": got.get("extractor", ""),
                "parse_status": "ocr_required",
                "note": "PDF 无可用文本层（疑似扫描版），需要 OCR 预处理后重试"}
    return {"text": "", "format": fmt, "extractor": got.get("extractor", ""),
            "parse_status": "empty_text",
            "note": "文档正文为空或过短，无法解析"}


def extract_document_bytes(content: bytes, file_name: str, *,
                           max_bytes: int = MAX_UPLOAD_BYTES) -> dict:
    """API 上传场景：先做格式/大小前置检查，再落临时文件走同一抽取路径（用完即删）。

    Phase5-1R F-007：解码后文件大小在**解析之前**检查；临时目录可靠清理；
    解析后文本长度由调用方按 MAX_EXTRACT_TEXT_CHARS 统一截断/拒绝。
    """
    if not file_name or "." not in file_name:
        raise ServiceError("UNSUPPORTED_FORMAT", "缺少合法文件名与扩展名",
                           {"file_name": file_name})
    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ServiceError("UNSUPPORTED_FORMAT",
                           f"不支持的文件格式 .{ext}，支持 {SUPPORTED_EXTENSIONS}",
                           {"file_name": file_name})
    raw = bytes(content)
    if len(raw) > int(max_bytes):
        raise ServiceError("PAYLOAD_TOO_LARGE",
                           f"上传文件解码后 {len(raw)} 字节超过上限 {int(max_bytes)}",
                           {"file_name": file_name, "bytes": len(raw)})
    suffix = "." + ext
    with tempfile.TemporaryDirectory(prefix="phase5_1_upload_") as td:
        tmp = Path(td) / f"upload{suffix}"
        tmp.write_bytes(raw)
        return extract_document(tmp)
