# -*- coding: utf-8 -*-
"""R1（P0-01 门禁）：岗位画像失效与版本管理。

不变量：
  * title / job_description 变更 -> job_content_hash 变化 -> 旧画像立即失效
    （needs_reparse），重新解析成功前不得作为可信画像参与推荐；
  * 判定依据是内容哈希（profile_source_hash == job_content_hash），不用 updated_at；
  * 解析失败显式落 failed 状态，不用旧画像伪装成功；
  * 无关元数据更新不触发失效；
  * 历史推荐解释保留原快照；
  * 解析期间原文被修改 -> 本次解析作废（409），不允许旧结果覆盖新版本。
"""
from __future__ import annotations

import unittest
from unittest import mock

from _util import (SYNTHETIC_JOB_TEXT, SYNTHETIC_JOB_TEXT_V2,  # noqa: E402
                   BusinessHarness)


class R1JobProfileInvalidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r1")
        _u, cls.admin_token = cls.h.login("admin_r1", "Adm1n!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 工具
    def _job(self, title: str, jd: str = SYNTHETIC_JOB_TEXT) -> str:
        return self.h.create_parsed_job(self.admin_token, title=title,
                                        job_description=jd)

    def _consistency(self, job_id: str) -> dict:
        return self.h.biz.jobs.job_profile_consistency(job_id)

    def _matchable_ids(self) -> set[str]:
        return {j.id for j, _p in self.h.biz.jobs.matchable_jobs()}

    # ---------------------------------------------------------- P0-01
    def test_jd_skill_change_invalidates_old_profile(self):
        h = self.h
        jid = self._job("R1-技能变更岗")
        self.assertTrue(self._consistency(jid)["profile_current"])

        r = h.client.patch(f"/api/v1/jobs/{jid}", headers=h.auth(self.admin_token),
                           json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()["data"]["job"]
        self.assertEqual(job["profile_status"], "needs_reparse",
                         "JD 必备技能变更后旧画像必须立即失效")
        self.assertIsNone(job["profile_source_hash"])
        self.assertFalse(job["profile_current"])

        # 失效画像不得进入推荐（不给学生看错的要求）
        self.assertNotIn(jid, self._matchable_ids())
        token = h.student("stu_r1_skill")
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"job_ids": [jid]})
        self.assertEqual(r.status_code, 404, r.text)

    def test_jd_education_change_blocks_matching(self):
        h = self.h
        jid = self._job("R1-学历变更岗")
        r = h.client.patch(f"/api/v1/jobs/{jid}", headers=h.auth(self.admin_token),
                           json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)
        # 学历要求从本科变为硕士：旧画像不得继续用于匹配
        self.assertNotIn(jid, self._matchable_ids())
        c = self._consistency(jid)
        self.assertFalse(c["profile_current"])
        self.assertEqual(c["profile_status"], "needs_reparse")

    def test_reparse_after_update_matches_new_hash(self):
        h = self.h
        jid = self._job("R1-重解析岗")
        r = h.client.patch(f"/api/v1/jobs/{jid}", headers=h.auth(self.admin_token),
                           json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)
        new_hash = r.json()["data"]["job"]["job_content_hash"]

        r = h.client.post(f"/api/v1/jobs/{jid}/parse", headers=h.auth(self.admin_token))
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()["data"]["job"]
        self.assertEqual(job["profile_status"], "parsed")
        self.assertEqual(job["profile_source_hash"], new_hash,
                         "画像必须登记其实际依据的原文哈希")
        self.assertTrue(job["profile_current"])
        self.assertIn(jid, self._matchable_ids())

    def test_parse_failure_keeps_failed_status_not_old_profile(self):
        h = self.h
        jid = self._job("R1-解析失败岗")
        r = h.client.patch(f"/api/v1/jobs/{jid}", headers=h.auth(self.admin_token),
                           json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)

        with mock.patch.object(self.h.biz.jobs.__class__, "_parse_job_profile",
                               side_effect=RuntimeError("模拟解析器崩溃")):
            r = h.client.post(f"/api/v1/jobs/{jid}/parse",
                              headers=h.auth(self.admin_token))
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()["data"]["job"]
        self.assertEqual(job["profile_status"], "failed",
                         "解析失败必须显式落失败状态")
        self.assertFalse(job["profile_parsed"] and job["profile_current"])
        self.assertIsNone(job["structured_profile"],
                          "解析失败不得用旧画像伪装成功")
        self.assertTrue(job["profile_error"])
        self.assertNotIn(jid, self._matchable_ids())

    def test_metadata_only_update_keeps_profile(self):
        h = self.h
        jid = self._job("R1-元数据更新岗")
        before = self._consistency(jid)
        r = h.client.patch(f"/api/v1/jobs/{jid}", headers=h.auth(self.admin_token),
                           json={"city": "北京", "job_category": "后端开发"})
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()["data"]["job"]
        self.assertEqual(job["profile_status"], "parsed",
                         "无关字段更新不得引发画像失效")
        self.assertTrue(job["profile_current"])
        self.assertEqual(job["job_content_hash"], before["job_content_hash"])
        self.assertEqual(job["profile_source_hash"], before["profile_source_hash"])

        # status 切换同样不触发失效
        r = h.client.post(f"/api/v1/jobs/{jid}/status", headers=h.auth(self.admin_token),
                          json={"status": "offline"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["job"]["profile_status"], "parsed")

    def test_history_explanation_snapshot_survives_jd_change(self):
        h = self.h
        jid_a = self._job("R1-快照岗A")
        jid_b = self._job("R1-快照岗B", jd=SYNTHETIC_JOB_TEXT_V2)
        token = h.student("stu_r1_snap")
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"job_ids": [jid_a, jid_b], "mode": "baseline"})
        self.assertEqual(r.status_code, 200, r.text)
        run_id = r.json()["data"]["run"]["id"]

        r = h.client.get(f"/api/v1/recommendations/{run_id}", headers=h.auth(token))
        items_before = r.json()["data"]["run"]["items"]
        self.assertEqual(len(items_before), 2)

        # 修改 JD 并重新解析：历史解释必须原样保留
        r = h.client.patch(f"/api/v1/jobs/{jid_a}", headers=h.auth(self.admin_token),
                           json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)
        h.client.post(f"/api/v1/jobs/{jid_a}/parse", headers=h.auth(self.admin_token))

        r = h.client.get(f"/api/v1/recommendations/{run_id}", headers=h.auth(token))
        items_after = r.json()["data"]["run"]["items"]
        self.assertEqual(len(items_after), len(items_before))
        before_by_id = {it["job_id"]: it for it in items_before}
        for it in items_after:
            old = before_by_id[it["job_id"]]
            self.assertEqual(it["job_snapshot_version"], old["job_snapshot_version"])
            self.assertEqual(it["explanation_snapshot"], old["explanation_snapshot"])
            self.assertEqual(it["job_content_hash"], old["job_content_hash"])

    def test_concurrent_jd_update_during_parse_conflicts(self):
        h = self.h
        jid = self._job("R1-并发解析岗")
        # 模拟：解析进行中管理员改了 JD（真实走 update_job 事务）
        real_parse = self.h.biz.jobs._parse_job_profile

        def _parse_with_mid_update(text, **kw):
            prof = real_parse(text, **kw)
            h.client.patch(f"/api/v1/jobs/{jid}", headers=h.auth(self.admin_token),
                           json={"job_description": SYNTHETIC_JOB_TEXT_V2})
            return prof

        with mock.patch.object(self.h.biz.jobs.__class__, "_parse_job_profile",
                               side_effect=_parse_with_mid_update):
            r = h.client.post(f"/api/v1/jobs/{jid}/parse",
                              headers=h.auth(self.admin_token))
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()["error"]["code"], "CONFLICT",
                         "解析期间原文被修改必须作废本次解析结果")

        # 旧解析结果不得覆盖新版本
        job = h.client.get(f"/api/v1/jobs/{jid}",
                           headers=h.auth(self.admin_token)).json()["data"]["job"]
        self.assertNotEqual(job["profile_status"], "parsed")
        self.assertIsNone(job["profile_source_hash"])
        self.assertFalse(job["profile_current"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
