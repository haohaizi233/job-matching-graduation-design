# -*- coding: utf-8 -*-
"""业务文档文本抽取（模块 A：中文 TXT / PDF / DOCX）。

复用 annotation/resume_intake.extract_text 的格式识别与解析器；
补充业务层要求：
  * 扫描版 / 无文本层 PDF 必须显式返回 parse_status="ocr_required"，
    绝不允许用空文本伪装解析成功；
  * 不支持的格式返回 UNSUPPORTED_FORMAT 错误码，不静默跳过；
  * 解析器缺失（如未安装 PyMuPDF）返回 PARSE_FAILED，附带可读原因。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from ..annotation.resume_intake import ResumeIntakeError, extract_text
from .errors import ServiceError

SUPPORTED_EXTENSIONS = ("txt", "docx", "pdf")
MIN_TEXT_CHARS = 8          # 低于该长度视为无有效文本层


def extract_document(path: Path | str) -> dict:
    """抽取文档正文。返回 {text, format, extractor, parse_status, note}。

    parse_status ∈ {ok, ocr_required, empty_text}；
    ocr_required / empty_text 时 text 一律为 ""，调用方不得当作成功解析。
    """
    p = Path(path)
    if not p.exists():
        raise ServiceError("PARSE_FAILED", f"文件不存在: {p.name}", {"path": str(p)})
    ext = p.suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ServiceError("UNSUPPORTED_FORMAT",
                           f"不支持的文件格式 .{ext}，支持 {SUPPORTED_EXTENSIONS}",
                           {"file_name": p.name})
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


def extract_document_bytes(content: bytes, file_name: str) -> dict:
    """API 上传场景：字节流落临时文件后走同一抽取路径（用完即删）。"""
    if not file_name or "." not in file_name:
        raise ServiceError("UNSUPPORTED_FORMAT", "缺少合法文件名与扩展名",
                           {"file_name": file_name})
    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ServiceError("UNSUPPORTED_FORMAT",
                           f"不支持的文件格式 .{ext}，支持 {SUPPORTED_EXTENSIONS}",
                           {"file_name": file_name})
    suffix = "." + ext
    with tempfile.TemporaryDirectory(prefix="phase5_1_upload_") as td:
        tmp = Path(td) / f"upload{suffix}"
        tmp.write_bytes(content)
        return extract_document(tmp)
