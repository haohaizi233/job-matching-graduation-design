# -*- coding: utf-8 -*-
"""R6（P1-06 门禁）：上传资源上限。

不变量：
  * 在读取/解码大对象**之前**建立约束：超限立即拒绝，不把超大对象整体读进内存；
  * Content-Length 缺失 / chunked 分块请求同样受限（上限不依赖请求头）；
  * JSON Base64 先做长度与膨胀率检查再解码；
  * 文件名/扩展名合法性与空文档拒绝；
  * 拒绝路径不留下任何简历元数据或存储文件。
"""
from __future__ import annotations

import base64
import unittest

from _util import BusinessHarness  # noqa: E402


def _status(code: str) -> int:
    from job_matching.service.errors import ServiceError
    return ServiceError(code, "").http_status


class R6UploadLimits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from job_matching.service.settings import ServiceSettings
        # 小上限夹具：真实走 HTTP 边界，测试快速且确定
        cls.st = ServiceSettings(max_upload_bytes=64 * 1024,
                                 max_base64_chars=100_000,
                                 max_request_bytes=2_000_000)
        cls.h = BusinessHarness(settings=cls.st)
        cls.token = cls.h.student_token("stu_r6")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def _count_resumes(self) -> int:
        from job_matching.infra.persistence import Resume
        s = self.h.biz.students._session_factory()
        try:
            return s.query(Resume).count()
        finally:
            s.close()

    # ---------------------------------------------------------- multipart
    def test_multipart_oversize_rejected(self):
        before = self._count_resumes()
        big = b"a" * (64 * 1024 + 1)
        r = self.h.client.post(
            "/api/v1/resumes", headers=self.h.auth(self.token),
            files={"file": ("big.txt", big, "text/plain")})
        self.assertEqual(r.status_code, _status("PAYLOAD_TOO_LARGE"), r.text)
        self.assertEqual(r.json()["error"]["code"], "PAYLOAD_TOO_LARGE")
        self.assertEqual(self._count_resumes(), before, "超限上传不得留下元数据")
        self.assertEqual(self.h.biz.store.scan_orphans(
            is_referenced=self.h.biz.students._is_storage_key_referenced), [],
            "超限上传不得留下存储文件")

    def test_chunked_without_content_length_still_rejected(self):
        """不带 Content-Length 的 chunked 请求同样受上限约束。"""
        boundary = "----jm-r6-boundary"
        head = (f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="big.txt"\r\n'
                "Content-Type: text/plain\r\n\r\n").encode()
        payload = b"a" * (64 * 1024 + 4096)
        tail = f"\r\n--{boundary}--\r\n".encode()

        def body_gen():
            yield head
            for i in range(0, len(payload), 8192):
                yield payload[i:i + 8192]
            yield tail

        headers = dict(self.h.auth(self.token))
        headers["content-type"] = f"multipart/form-data; boundary={boundary}"
        r = self.h.client.post("/api/v1/resumes", content=body_gen(), headers=headers)
        self.assertEqual(r.status_code, _status("PAYLOAD_TOO_LARGE"), r.text)
        self.assertEqual(r.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

    def test_small_upload_succeeds(self):
        r = self.h.upload_resume(self.token)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("resume", r.json()["data"])

    # ---------------------------------------------------------- JSON Base64
    def test_base64_char_limit_rejected(self):
        raw = "A" * (100_001)
        r = self.h.client.post("/api/v1/resumes/json", headers=self.h.auth(self.token),
                               json={"file_name": "a.txt", "content_base64": raw})
        self.assertEqual(r.status_code, _status("PAYLOAD_TOO_LARGE"), r.text)
        self.assertEqual(r.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

    def test_base64_expansion_rejected_before_decode(self):
        # 字符数未超上限，但按 3/4 膨胀率预估解码后超过文件上限
        raw = "A" * 95_000
        est = (len(raw) * 3) // 4
        self.assertGreater(est, self.st.max_upload_bytes)
        self.assertLessEqual(len(raw), self.st.max_base64_chars)
        r = self.h.client.post("/api/v1/resumes/json", headers=self.h.auth(self.token),
                               json={"file_name": "a.txt", "content_base64": raw})
        self.assertEqual(r.status_code, _status("PAYLOAD_TOO_LARGE"), r.text)

    def test_base64_invalid_encoding_rejected(self):
        r = self.h.client.post("/api/v1/resumes/json", headers=self.h.auth(self.token),
                               json={"file_name": "a.txt",
                                     "content_base64": "不是合法base64###"})
        self.assertEqual(r.status_code, _status("INVALID_REQUEST"), r.text)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_base64_small_valid_upload_succeeds(self):
        data = "R6 合成简历正文（非真人）\n求职意向：Java 开发\n".encode("utf-8")
        r = self.h.client.post(
            "/api/v1/resumes/json", headers=self.h.auth(self.token),
            json={"file_name": "r6.json.txt",
                  "content_base64": base64.b64encode(data).decode()})
        self.assertEqual(r.status_code, 200, r.text)

    # ---------------------------------------------------------- 格式与文件名
    def test_unsupported_extension_rejected(self):
        r = self.h.client.post(
            "/api/v1/resumes", headers=self.h.auth(self.token),
            files={"file": ("evil.exe", b"MZ fake", "application/octet-stream")})
        self.assertEqual(r.status_code, _status("UNSUPPORTED_FORMAT"), r.text)
        self.assertEqual(r.json()["error"]["code"], "UNSUPPORTED_FORMAT")

    def test_empty_file_rejected(self):
        r = self.h.client.post(
            "/api/v1/resumes", headers=self.h.auth(self.token),
            files={"file": ("empty.txt", b"", "text/plain")})
        self.assertEqual(r.status_code, _status("EMPTY_INPUT"), r.text)
        self.assertEqual(r.json()["error"]["code"], "EMPTY_INPUT")

    def test_path_traversal_filename_sanitized(self):
        r = self.h.client.post(
            "/api/v1/resumes", headers=self.h.auth(self.token),
            files={"file": ("..\\..\\evil.txt",
                            "R6 路径穿越合成简历\n求职意向：Java 开发\n".encode("utf-8"),
                            "text/plain")})
        self.assertEqual(r.status_code, 200, r.text)
        name = r.json()["data"]["resume"]["original_filename"]
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)
        self.assertNotIn("..", name)
        # 存储键为内容哈希路径，绝不回显绝对路径
        self.assertNotIn(str(self.h.storage_root.resolve()), r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
