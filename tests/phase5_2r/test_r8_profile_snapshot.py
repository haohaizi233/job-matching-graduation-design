# -*- coding: utf-8 -*-
"""R8（P2 门禁）：推荐快照与用户画像版本一致性。

不变量：
  * 推荐运行记录**实际使用**的画像版本与内容指纹（profile_content_hash），
    与持久化画像一致（不靠 updated_at 证明一致性）；
  * 推荐计算期间/之后画像或 JD 被修改，历史运行与条目快照不变；
  * job_set_snapshot 真实反映当时输入（含岗位内容哈希与快照版本）；
  * 推荐记录保存必要证据，但不复制简历原文；
  * 同一用户并发保存画像：乐观锁生效，只有一个版本落地（stale -> 409）。
"""
from __future__ import annotations

import threading
import unittest

from _util import (SYNTHETIC_JOB_TEXT, SYNTHETIC_JOB_TEXT_V2,  # noqa: E402
                   BusinessHarness)


class R8ProfileSnapshotConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r8")
        _u, cls.admin_token = cls.h.login("admin_r8", "Adm1n!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 乐观锁
    def test_stale_version_edit_conflicts(self):
        token = self.h.student("stu_r8_stale")
        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(token),
                              json={"edits": {"major": "计算机科学与技术"},
                                    "confirm": True, "expected_version": 999})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()["error"]["code"], "CONFLICT")

    def test_concurrent_profile_saves_one_wins(self):
        token = self.h.student("stu_r8_conc")
        cur = self.h.profile(token)["profile_version"]
        barrier = threading.Barrier(2)
        results: list = []

        def _save(major: str):
            from fastapi.testclient import TestClient
            c = TestClient(self.h.app)
            try:
                barrier.wait(timeout=30)
                results.append(c.put(
                    "/api/v1/students/me/profile", headers=self.h.auth(token),
                    json={"edits": {"major": major}, "confirm": True,
                          "expected_version": cur}))
            finally:
                c.close()

        ts = [threading.Thread(target=_save, args=(m,))
              for m in ("并发专业A", "并发专业B")]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=60)

        codes = sorted(r.status_code for r in results)
        self.assertEqual(codes, [200, 409],
                         f"并发保存必须一个成功一个冲突: {codes}")
        r = self.h.client.get("/api/v1/students/me/profile", headers=self.h.auth(token))
        self.assertEqual(r.json()["data"]["profile"]["profile_version"], cur + 1,
                         "并发保存不得跳版本或产生中间版本")

    # ---------------------------------------------------------- 快照一致性
    def test_run_records_actual_profile_version_and_hash(self):
        token = self.h.student("stu_r8_hash")
        jid = self.h.create_parsed_job(self.admin_token, title="R8-快照岗A",
                                       job_description=SYNTHETIC_JOB_TEXT)

        from job_matching.service.reco_store import canonical_json, sha256_text
        cur = self.h.profile(token)["profile_version"]
        r = self.h.client.get(f"/api/v1/students/me/profile/versions/{cur}",
                              headers=self.h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        prof_cur = r.json()["data"]["profile"]
        expected_hash = sha256_text(canonical_json(prof_cur["profile_data"]))

        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"mode": "baseline", "job_ids": [jid]})
        self.assertEqual(r.status_code, 200, r.text)
        run = r.json()["data"]["run"]
        self.assertEqual(run["profile_version"], cur,
                         "运行必须记录推荐时刻实际生效的画像版本")
        self.assertEqual(run["profile_content_hash"], expected_hash,
                         "运行必须记录推荐时刻画像的内容指纹")

    def test_old_run_snapshot_stable_after_changes(self):
        token = self.h.student("stu_r8_stable")
        jid = self.h.create_parsed_job(self.admin_token, title="R8-快照岗B",
                                       job_description=SYNTHETIC_JOB_TEXT)
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"mode": "baseline", "job_ids": [jid]})
        self.assertEqual(r.status_code, 200, r.text)
        run_id = r.json()["data"]["run"]["id"]

        r = self.h.client.get(f"/api/v1/recommendations/{run_id}", headers=self.h.auth(token))
        run_before = r.json()["data"]["run"]

        # 画像修改（新版本）+ JD 修改并重解析
        cur = self.h.profile(token)["profile_version"]
        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(token),
                              json={"edits": {"major": "并发与分布式"}, "confirm": True,
                                    "expected_version": cur})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.h.client.patch(f"/api/v1/jobs/{jid}", headers=self.h.auth(self.admin_token),
                                json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)
        self.h.client.post(f"/api/v1/jobs/{jid}/parse", headers=self.h.auth(self.admin_token))

        r = self.h.client.get(f"/api/v1/recommendations/{run_id}", headers=self.h.auth(token))
        run_after = r.json()["data"]["run"]
        self.assertEqual(run_after["profile_version"], run_before["profile_version"])
        self.assertEqual(run_after["profile_content_hash"],
                         run_before["profile_content_hash"])
        self.assertEqual(run_after["job_set_snapshot"], run_before["job_set_snapshot"],
                         "历史 job_set_snapshot 不得被后续修改回写")
        self.assertEqual(run_after["items"], run_before["items"],
                         "历史条目与解释快照必须不可变")

    def test_job_set_snapshot_reflects_inputs_at_run_time(self):
        token = self.h.student("stu_r8_inputs")
        jid = self.h.create_parsed_job(self.admin_token, title="R8-快照岗C",
                                       job_description=SYNTHETIC_JOB_TEXT)
        job = self.h.client.get(f"/api/v1/jobs/{jid}",
                                headers=self.h.auth(self.admin_token)).json()["data"]["job"]
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"mode": "baseline", "job_ids": [jid]})
        run = r.json()["data"]["run"]
        snaps = run["job_set_snapshot"]
        self.assertEqual(len(snaps), 1)
        snap = snaps[0]
        self.assertEqual(snap["job_content_hash"], job["job_content_hash"])
        self.assertTrue(str(snap["snapshot_version"]).startswith(jid))
        self.assertEqual(snap["profile_status"], "parsed")

    def test_run_history_contains_no_resume_plaintext(self):
        from _util import SYNTHETIC_RESUME_TEXT
        token = self.h.student("stu_r8_privacy")
        jid = self.h.create_parsed_job(self.admin_token, title="R8-隐私岗",
                                       job_description=SYNTHETIC_JOB_TEXT)
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"mode": "baseline", "job_ids": [jid]})
        self.assertEqual(r.status_code, 200, r.text)
        run_id = r.json()["data"]["run"]["id"]
        r = self.h.client.get(f"/api/v1/recommendations/{run_id}", headers=self.h.auth(token))
        body = r.text
        # 不得未经论证复制简历原文（只留证据摘要）
        self.assertNotIn("开发招聘管理演示系统", body)
        self.assertNotIn(SYNTHETIC_RESUME_TEXT.splitlines()[0], body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
