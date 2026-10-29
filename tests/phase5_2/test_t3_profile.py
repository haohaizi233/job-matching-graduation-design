# -*- coding: utf-8 -*-
"""T3（B3 门禁，链路B）：简历上传 -> 安全检查 -> 文本抽取 -> 画像 -> 入库 -> 重读
-> 人工修改 -> 版本变化。

证据纪律断言：
  * 画像字段带 fact_source / evidence_text；
  * 人工修改标记 human_corrected 且**不覆盖**原始抽取证据（extraction_snapshot 不变）；
  * 每次保存产生新 profile_version，历史版本可回看。

存储纪律断言：
  * 只返回受控存储键，不含本机绝对路径；
  * 重复上传同一内容幂等；删除简历后文件从私有存储消失。
"""
from __future__ import annotations

import unittest
from unittest import mock

from _util import BusinessHarness, synthetic_resume_bytes  # noqa: E402


class T3ResumeAndProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.user = cls.h.register("stu_b", "StuB!2026pass")
        _u, cls.token = cls.h.login("stu_b", "StuB!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 链路 B
    def test_link_b_upload_parse_save_reread_edit_version(self):
        h = self.h
        # 本用例断言"首次上传 -> 版本1 -> 人工编辑 -> 版本2"的绝对版本号，
        # 必须独占一个全新用户（同用户的历史上传会推进版本号；用例之间不得互相依赖）
        h.register("stu_linkb", "StuB!2026pass")
        _u, token = h.login("stu_linkb", "StuB!2026pass")
        r = h.upload_resume(token)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertTrue(data["created"])
        resume = data["resume"]
        self.assertIn(resume["parse_status"], ("ok", "partial"))
        self.assertEqual(resume["profile_version"], 1)

        # 重新读取（数据库 -> 响应）
        r = h.client.get("/api/v1/students/me/profile", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        prof = r.json()["data"]["profile"]
        self.assertEqual(prof["profile_version"], 1)
        self.assertFalse(prof["confirmed"])
        major = prof["profile_data"]["profile"]["major"]
        self.assertEqual(major["value"], "软件工程")
        self.assertIn(major["fact_source"], ("stated_in_source", "rule_parsed"))

        # 人工修改 + 确认 -> 新版本
        r = h.client.put("/api/v1/students/me/profile", headers=h.auth(token),
                         json={"edits": {"major": "计算机科学与技术",
                                         "preferred_cities": ["上海"]},
                               "confirm": True, "note": "合成测试修正",
                               "expected_version": 1})
        self.assertEqual(r.status_code, 200, r.text)
        v2 = r.json()["data"]["profile"]
        self.assertEqual(v2["profile_version"], 2)
        self.assertTrue(v2["confirmed"])
        edits = v2["profile_data"]["user_edits"]
        self.assertIn("major", edits)
        self.assertEqual(edits["major"]["previous"]["value"], "软件工程",
                         "人工修改必须保留修改前抽取值")
        self.assertEqual(v2["profile_data"]["profile"]["major"]["fact_source"],
                         "human_corrected")
        self.assertEqual(
            v2["profile_data"]["extraction_snapshot"]["major"]["value"], "软件工程",
            "人工修改不得覆盖原始抽取证据")

        # 历史版本可回看
        r = h.client.get("/api/v1/students/me/profile/versions/1",
                         headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        v1 = r.json()["data"]["profile"]
        self.assertEqual(v1["profile_data"]["profile"]["major"]["value"], "软件工程")

    def test_resume_list_and_metadata_no_absolute_path(self):
        r = self.h.client.get("/api/v1/resumes", headers=self.h.auth(self.token))
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json()["data"]["items"]
        self.assertTrue(items)
        body = r.text
        self.assertNotIn("D:\\", body)
        self.assertNotIn("D:/", body)
        for it in items:
            self.assertFalse(it["storage_key"].startswith(("/", "\\")))
            self.assertNotIn(":", it["storage_key"], "存储键不得含盘符/绝对路径")
            self.assertEqual(len(it["file_sha256"]), 64)

    def test_duplicate_upload_is_idempotent(self):
        content = synthetic_resume_bytes() + b"\n<!-- duplicate-case -->\n"
        r1 = self.h.upload_resume(self.token, content=content, unique=False)
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(r1.json()["data"]["created"])
        r2 = self.h.upload_resume(self.token, content=content, unique=False)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertFalse(r2.json()["data"]["created"])
        rid = r1.json()["data"]["resume"]["id"]
        self.assertEqual(r2.json()["data"]["resume"]["id"], rid)
        items = self.h.client.get("/api/v1/resumes",
                                  headers=self.h.auth(self.token)).json()["data"]["items"]
        self.assertEqual(len([i for i in items if i["file_sha256"]
                              == r1.json()["data"]["resume"]["file_sha256"]]), 1)

    def test_unsupported_format_rejected(self):
        r = self.h.client.post(
            "/api/v1/resumes", headers=self.h.auth(self.token),
            files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
            data={"is_synthetic": "true"})
        self.assertEqual(r.status_code, 415, r.text)
        self.assertEqual(r.json()["error"]["code"], "UNSUPPORTED_FORMAT")

    def test_oversize_upload_rejected(self):
        old = self.h.biz.students.max_upload_bytes
        self.h.biz.students.max_upload_bytes = 64
        try:
            r = self.h.upload_resume(self.token, content=b"x" * 128,
                                     filename="big.txt")
            self.assertEqual(r.status_code, 413, r.text)
            self.assertEqual(r.json()["error"]["code"], "PAYLOAD_TOO_LARGE")
        finally:
            self.h.biz.students.max_upload_bytes = old

    def test_empty_upload_rejected(self):
        r = self.h.upload_resume(self.token, content=b"", filename="empty.txt")
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(r.json()["error"]["code"], "EMPTY_INPUT")

    def test_parse_failure_marks_resume_and_reparse_recovers(self):
        from job_matching.service.profile_store import StudentDataService

        with mock.patch.object(StudentDataService, "_parse_profile",
                               side_effect=RuntimeError("模拟解析器崩溃")):
            r = self.h.upload_resume(self.token, content=synthetic_resume_bytes(),
                                     filename="recover_later.txt")
        self.assertEqual(r.status_code, 200, r.text)
        resume = r.json()["data"]["resume"]
        self.assertEqual(resume["parse_status"], "failed")
        self.assertTrue(resume["parse_error"])

        r = self.h.client.post(f"/api/v1/resumes/{resume['id']}/reparse",
                               headers=self.h.auth(self.token), json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(r.json()["data"]["resume"]["parse_status"], ("ok", "partial"))
        self.assertIn("profile", r.json()["data"])

    def test_delete_resume_removes_file_and_row(self):
        content = "删除测试合成简历\n求职意向：测试工程师\n最高学历：本科\n".encode("utf-8")
        r = self.h.upload_resume(self.token, content=content, filename="to_delete.txt")
        self.assertEqual(r.status_code, 200, r.text)
        resume = r.json()["data"]["resume"]
        storage_key = resume["storage_key"]
        self.assertTrue(self.h.biz.students.store.exists(storage_key))

        r = self.h.client.delete(f"/api/v1/resumes/{resume['id']}",
                                 headers=self.h.auth(self.token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.h.biz.students.store.exists(storage_key),
                         "删除简历后私有文件必须清理")
        r = self.h.client.get(f"/api/v1/resumes/{resume['id']}",
                              headers=self.h.auth(self.token))
        self.assertEqual(r.status_code, 404, r.text)

    def test_profile_edit_conflict_on_stale_version(self):
        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(self.token),
                              json={"edits": {"graduation_year": 2027},
                                    "expected_version": 999})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()["error"]["code"], "CONFLICT")

    def test_profile_edit_rejects_unknown_fields(self):
        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(self.token),
                              json={"edits": {"skills": ["Java"]}})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
