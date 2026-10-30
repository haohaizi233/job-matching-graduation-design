# -*- coding: utf-8 -*-
"""R3（P1-03 门禁）：岗位来源与合成标记。

不变量：
  * data_source ∈ {synthetic, user_provided, licensed_dataset, unknown} 由数据来源层确定；
  * is_synthetic 不得由解析器硬编码；合成岗仍为合成，真实手工岗不得自动变合成；
  * 许可不明确不得冒充 licensed_dataset；未声明保留 unknown；
  * 更新 / 重新解析 / 导入不静默改写来源；显式声明改写记审计。
"""
from __future__ import annotations

import unittest

from _util import SYNTHETIC_JOB_TEXT, BusinessHarness  # noqa: E402


class R3DataSourceProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r3")
        _u, cls.admin_token = cls.h.login("admin_r3", "Adm1n!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def _create(self, **kw) -> dict:
        r = self.h.create_job(self.admin_token, title=kw.pop("title", "R3-来源岗"),
                              job_description=SYNTHETIC_JOB_TEXT, **kw)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]["job"]

    # ---------------------------------------------------------- 岗位来源
    def test_synthetic_job_stays_synthetic(self):
        job = self._create(title="R3-合成岗", source="synthetic",
                           source_license="CC0-synthetic", is_synthetic=True)
        self.assertEqual(job["data_source"], "synthetic")
        # 解析不得改写来源
        r = self.h.client.post(f"/api/v1/jobs/{job['id']}/parse",
                               headers=self.h.auth(self.admin_token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["job"]["data_source"], "synthetic")

    def test_manual_real_job_is_not_synthetic(self):
        job = self._create(title="R3-真实手工岗", source="manual",
                           source_license="UNKNOWN", is_synthetic=False)
        self.assertEqual(job["data_source"], "user_provided",
                         "真实手工录入岗位不得被标成合成，也不得冒充授权数据")
        r = self.h.client.post(f"/api/v1/jobs/{job['id']}/parse",
                               headers=self.h.auth(self.admin_token))
        self.assertEqual(r.json()["data"]["job"]["data_source"], "user_provided",
                         "解析器不得硬编码 is_synthetic")

    def test_unspecified_source_is_unknown(self):
        job = self._create(title="R3-未声明岗", source="crawler",
                           source_license="UNKNOWN")
        self.assertEqual(job["data_source"], "unknown",
                         "未声明来源不得臆造为合成或授权数据")

    def test_unclear_license_never_licensed(self):
        for lic in ("UNKNOWN", "NONE", "N/A", ""):
            job = self._create(title=f"R3-许可不明确[{lic}]", source="partner_feed",
                               source_license=lic, is_synthetic=False)
            self.assertNotEqual(job["data_source"], "licensed_dataset",
                                f"许可 {lic!r} 不明确时不得冒充授权数据集")
            self.assertIn(job["data_source"], ("user_provided", "unknown"))

    def test_clear_license_is_licensed_dataset(self):
        job = self._create(title="R3-授权数据岗", source="open_dataset",
                           source_license="CC-BY-4.0", is_synthetic=False)
        self.assertEqual(job["data_source"], "licensed_dataset")

    def test_import_and_update_do_not_silently_change_source(self):
        r = self.h.import_jobs(self.admin_token, [
            {"title": "R3-导入合成岗", "job_description": SYNTHETIC_JOB_TEXT,
             "source": "synthetic", "source_license": "CC0-synthetic",
             "is_synthetic": True},
            {"title": "R3-导入未声明岗", "job_description": SYNTHETIC_JOB_TEXT,
             "source": "feed", "source_license": "UNKNOWN"},
        ])
        self.assertEqual(r.status_code, 200, r.text)
        created = r.json()["data"]["created"]
        self.assertEqual(len(created), 2, r.text)
        by_title = {}
        for c in created:
            job = self.h.client.get(f"/api/v1/jobs/{c['job_id']}",
                                    headers=self.h.auth(self.admin_token)).json()["data"]["job"]
            by_title[job["title"]] = job
        self.assertEqual(by_title["R3-导入合成岗"]["data_source"], "synthetic")
        self.assertEqual(by_title["R3-导入未声明岗"]["data_source"], "unknown")

        # 更新 JD 不得静默改写来源
        jid = by_title["R3-导入合成岗"]["id"]
        r = self.h.client.patch(f"/api/v1/jobs/{jid}", headers=self.h.auth(self.admin_token),
                                json={"job_description": SYNTHETIC_JOB_TEXT + "\n补充要求。"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["job"]["data_source"], "synthetic")

    def test_explicit_source_change_is_audited(self):
        job = self._create(title="R3-审计岗", source="manual",
                           source_license="UNKNOWN", is_synthetic=False)
        self.assertEqual(job["data_source"], "user_provided")
        r = self.h.client.patch(f"/api/v1/jobs/{job['id']}",
                                headers=self.h.auth(self.admin_token),
                                json={"data_source": "licensed_dataset"})
        self.assertEqual(r.status_code, 200, r.text)
        upd = r.json()["data"]["job"]
        self.assertEqual(upd["data_source"], "licensed_dataset")
        self.assertTrue(upd["data_source_declared"])
        audit = upd["source_audit"]
        self.assertGreaterEqual(len(audit), 2, "来源改写必须留下审计流水")
        self.assertEqual(audit[-1]["from"], "user_provided")
        self.assertEqual(audit[-1]["to"], "licensed_dataset")
        self.assertEqual(audit[-1]["reason"], "explicit_update")

    def test_invalid_data_source_rejected(self):
        from job_matching.service.errors import ServiceError
        job = self._create(title="R3-非法来源岗")
        r = self.h.client.patch(f"/api/v1/jobs/{job['id']}",
                                headers=self.h.auth(self.admin_token),
                                json={"data_source": "totally_made_up"})
        self.assertEqual(r.status_code, ServiceError("INVALID_REQUEST", "").http_status)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    # ---------------------------------------------------------- 简历来源
    def test_resume_reparse_preserves_source(self):
        token = self.h.student_token("stu_r3_src")
        r = self.h.upload_resume(token, is_synthetic=False)
        self.assertEqual(r.status_code, 200, r.text)
        resume = r.json()["data"]["resume"]
        self.assertEqual(resume["data_source"], "user_provided")

        # 重新解析（未声明）不得静默改写来源
        r = self.h.client.post(f"/api/v1/resumes/{resume['id']}/reparse",
                               headers=self.h.auth(token), json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["resume"]["data_source"], "user_provided")

        # 显式声明才改写并记审计
        r = self.h.client.post(f"/api/v1/resumes/{resume['id']}/reparse",
                               headers=self.h.auth(token),
                               json={"data_source": "synthetic"})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()["data"]["resume"]
        self.assertEqual(out["data_source"], "synthetic")

    def test_resume_synthetic_flag_stays_synthetic(self):
        token = self.h.student_token("stu_r3_synth")
        r = self.h.upload_resume(token, is_synthetic=True)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["resume"]["data_source"], "synthetic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
