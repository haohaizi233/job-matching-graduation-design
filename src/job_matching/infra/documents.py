# -*- coding: utf-8 -*-
"""基础设施层（Infrastructure/Adapters）：文档文本抽取适配器。

Phase5-1A 抽取说明：
  原实现在 `annotation/resume_intake.py`（研究标注层）内，导致业务服务
  `service/text_extract.py` 反向依赖研究层并连带加载 pandas/研究数据依赖。
  文档解析属外部格式适配器，与标注无关，故下沉到本模块；
  `annotation/resume_intake.py` 保留旧导入路径兼容（re-export）。

支持格式：PDF（PyMuPDF/fitz，缺失时显式报错）、DOCX（stdlib zipfile+XML 最小适配器）、
UTF-8 TXT、结构化 CSV / JSONL（结构化导入仍在 resume_intake）。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

SUPPORTED_FORMATS = ("pdf", "docx", "txt", "csv", "jsonl")


class ResumeIntakeError(ValueError):
    """文档解析/简历导入非法（格式不支持、解析器缺失、文件不存在等）。"""
    pass


def _extract_txt(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ResumeIntakeError(f"TXT 编码无法识别（尝试 utf-8/gbk 均失败）: {path}")


def _extract_docx(path: Path) -> str:
    """最小 DOCX 适配器：读 word/document.xml 去标签（不引入 python-docx）。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ResumeIntakeError(f"DOCX 解析失败（不是合法 docx 或缺 document.xml）: {path} ({e})")
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return text


def _extract_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:  # pragma: no cover - 环境相关
        raise ResumeIntakeError(
            f"PDF 解析器不可用（需要 PyMuPDF/fitz）: {path}；"
            "请先转成 TXT/DOCX 或安装 fitz，不静默跳过") from e
    try:
        with fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception as e:
        raise ResumeIntakeError(f"PDF 解析失败: {path} ({e})")


def extract_text(path: Path | str) -> dict:
    """抽取文档正文。返回 {text, format, extractor}；不支持的格式显式报错。"""
    p = Path(path)
    if not p.exists():
        raise ResumeIntakeError(f"简历文件不存在: {p}")
    ext = p.suffix.lower().lstrip(".")
    if ext == "txt":
        return {"text": _extract_txt(p), "format": "txt", "extractor": "stdlib"}
    if ext == "docx":
        return {"text": _extract_docx(p), "format": "docx", "extractor": "zipfile+xml(minimal)"}
    if ext == "pdf":
        return {"text": _extract_pdf(p), "format": "pdf", "extractor": "fitz(PyMuPDF)"}
    raise ResumeIntakeError(
        f"不支持的简历格式: .{ext}（支持 {SUPPORTED_FORMATS}；"
        "csv/jsonl 请走结构化导入 parse_structured）")
