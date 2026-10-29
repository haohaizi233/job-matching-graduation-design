# -*- coding: utf-8 -*-
"""S01~S04：中文文档解析（TXT / DOCX / 可提取文本 PDF / 扫描版拒识）。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import (RESUME_TEXT, RESUME_TEXT_NO_EVIDENCE, write_docx, write_pdf_scanned,
                   write_pdf_with_text, write_txt)

from job_matching.service import ServiceError, parse_resume_file
from job_matching.service.text_extract import extract_document, extract_document_bytes


class S01ChineseTxtParse(unittest.TestCase):
    """场景 1：中文 TXT 解析。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ph51_s01_")
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_txt_fields_extracted_with_status_ok(self):
        p = write_txt(self.dir / "resume.txt", RESUME_TEXT)
        profile = parse_resume_file(p, profile_id="stu_s01", is_synthetic=True)
        self.assertEqual(profile.parse_status, "ok")
        self.assertEqual(profile.employment_intention.status, "ok")
        self.assertIn("Java", str(profile.employment_intention.value))
        self.assertEqual(profile.graduation_year.value, "2027")
        self.assertEqual(profile.education_level.value, "本科")
        self.assertTrue(profile.skills)
        self.assertTrue(profile.is_synthetic)

    def test_txt_gbk_encoding_supported(self):
        p = self.dir / "resume_gbk.txt"
        write_txt(p, RESUME_TEXT, encoding="gbk")
        got = extract_document(p)
        self.assertEqual(got["parse_status"], "ok")
        self.assertIn("求职意向", got["text"])

    def test_unsupported_extension_rejected(self):
        p = self.dir / "resume.md"
        p.write_text(RESUME_TEXT, encoding="utf-8")
        with self.assertRaises(ServiceError) as ctx:
            extract_document(p)
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_FORMAT")


class S02DocxParse(unittest.TestCase):
    """场景 2：DOCX 解析。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ph51_s02_")
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_docx_text_and_profile(self):
        p = write_docx(self.dir / "resume.docx", RESUME_TEXT)
        got = extract_document(p)
        self.assertEqual(got["format"], "docx")
        self.assertIn("求职意向：Java开发工程师", got["text"])
        profile = parse_resume_file(p, profile_id="stu_s02", is_synthetic=True)
        self.assertEqual(profile.parse_status, "ok")
        self.assertEqual(profile.graduation_year.value, "2027")

    def test_broken_docx_rejected(self):
        p = self.dir / "broken.docx"
        p.write_bytes(b"not-a-zip")
        with self.assertRaises(ServiceError) as ctx:
            extract_document(p)
        self.assertEqual(ctx.exception.code, "PARSE_FAILED")

    def test_upload_bytes_docx(self):
        p = write_docx(self.dir / "u.docx", RESUME_TEXT)
        got = extract_document_bytes(p.read_bytes(), "u.docx")
        self.assertEqual(got["parse_status"], "ok")


class S03PdfWithText(unittest.TestCase):
    """场景 3：可提取文本 PDF 解析。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ph51_s03_")
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_pdf_text_layer_extracted(self):
        p = write_pdf_with_text(self.dir / "resume.pdf", RESUME_TEXT)
        got = extract_document(p)
        self.assertEqual(got["parse_status"], "ok")
        self.assertEqual(got["format"], "pdf")
        self.assertIn("求职意向", got["text"])
        profile = parse_resume_file(p, profile_id="stu_s03", is_synthetic=True)
        self.assertEqual(profile.parse_status, "ok")
        self.assertTrue(profile.skills)


class S04ScannedPdfRejection(unittest.TestCase):
    """场景 4：扫描版 PDF / 空文本必须显式失败，不得伪装解析成功。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ph51_s04_")
        self.dir = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_scanned_pdf_returns_ocr_required(self):
        p = write_pdf_scanned(self.dir / "scan.pdf")
        got = extract_document(p)
        self.assertEqual(got["parse_status"], "ocr_required")
        self.assertEqual(got["text"], "")
        profile = parse_resume_file(p, profile_id="stu_s04", is_synthetic=True)
        self.assertEqual(profile.parse_status, "ocr_required")
        self.assertFalse(profile.skills, "扫描版 PDF 不得凭空产出技能")
        self.assertEqual(profile.education_level.status, "unknown")
        self.assertTrue(any("ocr_required" in w for w in profile.warnings))

    def test_empty_text_status(self):
        p = write_txt(self.dir / "empty.txt", "   \n  ")
        profile = parse_resume_file(p, profile_id="stu_s04b", is_synthetic=True)
        self.assertEqual(profile.parse_status, "empty_text")

    def test_short_but_nonempty_resume_not_fabricated(self):
        from job_matching.service import parse_resume_text as prt
        profile = prt(RESUME_TEXT_NO_EVIDENCE, profile_id="stu_s04c", is_synthetic=True)
        self.assertEqual(profile.graduation_year.status, "unknown")
        self.assertEqual(profile.education_level.status, "unknown")


if __name__ == "__main__":
    unittest.main()
