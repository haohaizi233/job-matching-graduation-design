# -*- coding: utf-8 -*-
"""R4（P1-04 门禁）：并发上传与文件生命周期。

不变量：
  * 存储键 = f(user_id, 内容 SHA-256, 扩展名)，同内容幂等去重；
  * 保存采用"暂存 -> 原子发布"，写入只在唯一时刻发生；
  * **请求失败不得删除其它成功请求正在引用的文件**（并发同内容上传竞态）；
  * 删除只在无任何数据库引用时执行；删除失败留 failed_pending，由孤儿扫描兜底；
  * 文件缺失但元数据存在时，元数据删除路径明确（not_found）。
"""
from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest import mock

from _util import BusinessHarness, synthetic_resume_bytes  # noqa: E402


class R4FileLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        from job_matching.infra.persistence import Resume
        cls.Resume = Resume

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 工具
    def _session(self):
        return self.h.biz.students._session_factory()

    def _resume_rows(self, digest: str) -> list:
        s = self._session()
        try:
            return (s.query(self.Resume)
                    .filter(self.Resume.file_sha256 == digest).all())
        finally:
            s.close()

    @staticmethod
    def _digest(data: bytes) -> str:
        import hashlib
        return hashlib.sha256(data).hexdigest()

    def _storage_key(self, user_id: str, digest: str) -> str:
        return f"resumes/{user_id}/{digest[:2]}/{digest}.txt"

    # ---------------------------------------------------------- 存储语义
    def test_save_same_content_dedup_with_created_flag(self):
        from job_matching.service.file_store import PrivateFileStore, sha256_bytes
        store = PrivateFileStore(self.h.storage_root / "unit")
        data = synthetic_resume_bytes() + b"\n<!-- r4-save -->\n"
        k1, d1, _s1, created1 = store.save(user_id="u1", original_filename="a.txt",
                                           content=data)
        k2, d2, _s2, created2 = store.save(user_id="u1", original_filename="a.txt",
                                           content=data)
        self.assertEqual(k1, k2)
        self.assertEqual(d1, sha256_bytes(data))
        self.assertTrue(created1, "首次写入必须由本次请求创建")
        self.assertFalse(created2, "稳定键已存在时本次请求不拥有该文件")

    def test_failed_upload_cleanup_never_deletes_referenced_file(self):
        h = self.h
        token = h.student_token("stu_r4_ref")
        user_id = None
        r = h.upload_resume(token, content=synthetic_resume_bytes(),
                            unique=False)
        self.assertEqual(r.status_code, 200, r.text)
        rows = self._resume_rows(self._digest(synthetic_resume_bytes()))
        self.assertEqual(len(rows), 1)
        user_id = rows[0].user_id
        key = rows[0].storage_key
        self.assertTrue(h.biz.store.exists(key))

        # 竞态场景：另一请求写入同内容文件（created=False）后落库失败
        _k, _d, _sz, created = h.biz.store.save(
            user_id=user_id, original_filename="x.txt",
            content=synthetic_resume_bytes())
        self.assertFalse(created)
        out = h.biz.students._cleanup_failed_upload(key, created=created)
        self.assertFalse(out["deleted"], "非本次新建的文件不得删除")
        self.assertTrue(h.biz.store.exists(key),
                        "失败请求不得删除成功请求正在引用的文件")

        # 即使是本次新建，只要已有数据库引用也必须保留
        out = h.biz.students._cleanup_failed_upload(key, created=True)
        self.assertFalse(out["deleted"])
        self.assertEqual(out.get("reason"), "referenced_by_others")
        self.assertTrue(h.biz.store.exists(key))

        # 无引用 + 本次新建 -> 允许补偿删除
        stray_key, _d2, _sz2, c2 = h.biz.store.save(
            user_id="u_orphan_" + user_id[:4], original_filename="y.txt",
            content=synthetic_resume_bytes() + b"\n<!-- r4-stray -->\n")
        self.assertTrue(c2)
        out = h.biz.students._cleanup_failed_upload(stray_key, created=True)
        self.assertTrue(out["deleted"])
        self.assertFalse(h.biz.store.exists(stray_key))

    def test_concurrent_same_content_upload_keeps_file_and_single_row(self):
        h = self.h
        token = h.student_token("stu_r4_conc")
        data = synthetic_resume_bytes() + b"\n<!-- r4-conc -->\n"
        digest = self._digest(data)
        barrier = threading.Barrier(4)
        results: list = []

        def _upload(_i: int):
            from fastapi.testclient import TestClient
            c = TestClient(h.app)
            try:
                barrier.wait(timeout=30)
                results.append(c.post(
                    "/api/v1/resumes", headers=h.auth(token),
                    files={"file": ("synthetic_resume.txt", data, "text/plain")},
                    data={"is_synthetic": "true"}))
            finally:
                c.close()

        threads = [threading.Thread(target=_upload, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        rows = self._resume_rows(digest)
        self.assertEqual(len(rows), 1, "并发同内容上传只允许一条简历元数据")
        key = rows[0].storage_key
        self.assertTrue(h.biz.store.exists(key),
                        "失败的并发请求不得删除共享文件")
        # 成功的响应里不得出现绝对路径
        for r in results:
            if r.status_code == 200:
                self.assertNotIn(str(h.storage_root.resolve()),
                                 r.text.replace("\\\\", "\\"))

    def test_delete_file_failure_reports_pending_and_orphan_scan_recovers(self):
        h = self.h
        token = h.student_token("stu_r4_pending")
        r = h.upload_resume(token)
        self.assertEqual(r.status_code, 200, r.text)
        resume_id = r.json()["data"]["resume"]["id"]
        rows = self._resume_rows(r.json()["data"]["resume"]["file_sha256"])
        key = rows[0].storage_key

        # 模拟"数据库已提交、文件删除失败"（例如文件被占用）
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("模拟占用")):
            r = h.client.delete(f"/api/v1/resumes/{resume_id}", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()["data"]
        self.assertTrue(out["deleted"])
        self.assertEqual(out["file_cleanup"], "failed_pending",
                         "文件删除失败必须留待处理状态，不谎报已清理")
        self.assertTrue(h.biz.store.exists(key))

        # 元数据已删 -> 文件成为孤儿，由扫描兜底清理
        s = self._session()
        try:
            self.assertEqual(s.query(self.Resume)
                             .filter(self.Resume.id == resume_id).count(), 0)
        finally:
            s.close()
        report = h.biz.store.cleanup_orphans(
            is_referenced=h.biz.students._is_storage_key_referenced)
        self.assertIn(key, report["deleted"])
        self.assertFalse(h.biz.store.exists(key))

    def test_missing_file_with_metadata_delete_is_not_found(self):
        h = self.h
        token = h.student_token("stu_r4_missing")
        r = h.upload_resume(token)
        resume_id = r.json()["data"]["resume"]["id"]
        rows = self._resume_rows(r.json()["data"]["resume"]["file_sha256"])
        key = rows[0].storage_key
        h.biz.store.delete(key)          # 文件意外丢失（元数据仍在）

        r = h.client.delete(f"/api/v1/resumes/{resume_id}", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["file_cleanup"], "not_found",
                         "文件已不存在时删除路径必须明确登记")
        self.assertTrue(r.json()["data"]["deleted"])

    def test_shared_storage_key_never_deleted_while_referenced(self):
        h = self.h
        token = h.student_token("stu_r4_shared")
        data = synthetic_resume_bytes() + b"\n<!-- r4-shared -->\n"
        r = h.upload_resume(token, content=data, unique=False)
        rows = self._resume_rows(self._digest(data))
        self.assertEqual(len(rows), 1)
        key = rows[0].storage_key

        # 模拟历史数据：另一条简历行引用同一存储键（如迁移前旧账）
        legacy_digest = "legacy_digest_placeholder"
        s = self._session()
        try:
            s.add(self.Resume(user_id=rows[0].user_id,
                              original_filename="legacy_copy.txt",
                              storage_key=key,
                              file_sha256=legacy_digest,
                              file_size=1, parse_status="ok",
                              data_source="unknown", source_audit=[]))
            s.commit()
            other_id = (s.query(self.Resume)
                        .filter(self.Resume.file_sha256 == legacy_digest)
                        .first()).id
        finally:
            s.close()

        # 删除真实那条（HTTP）：文件仍被其它行引用，不得删除
        r = h.client.delete(f"/api/v1/resumes/{rows[0].id}",
                            headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["file_cleanup"], "referenced_by_others",
                         "存储键仍被其它行引用时禁止删除文件")
        self.assertTrue(h.biz.store.exists(key))

        # 清掉残留行，避免影响后续用例
        s = self._session()
        try:
            s.query(self.Resume).filter(self.Resume.id == other_id).delete()
            s.commit()
        finally:
            s.close()

    def test_orphan_scan_respects_age_filter(self):
        h = self.h
        key, _d, _sz, created = h.biz.store.save(
            user_id="u_r4_age", original_filename="fresh.txt",
            content=synthetic_resume_bytes() + b"\n<!-- r4-age -->\n")
        self.assertTrue(created)
        ref = h.biz.students._is_storage_key_referenced
        self.assertIn(key, h.biz.store.scan_orphans(is_referenced=ref))

        kept = h.biz.store.cleanup_orphans(is_referenced=ref, max_age_seconds=3600)
        self.assertIn(key, kept["kept"], "刚写入的文件不得被年龄过滤误删")
        done = h.biz.store.cleanup_orphans(is_referenced=ref, max_age_seconds=0)
        self.assertIn(key, done["deleted"])
        self.assertFalse(h.biz.store.exists(key))


if __name__ == "__main__":
    unittest.main(verbosity=2)
