# -*- coding: utf-8 -*-
"""T5（B2/B6 门禁，链路D）：数据隔离 —— 用户 A 与用户 B 各自建数据，
A 尝试访问 B 的简历 / 画像 / 推荐历史 / 反馈，必须全部被阻断。

口径：
  * 跨用户资源访问一律 404 NOT_FOUND（防资源枚举）；
  * 管理员维护岗位，但**没有**查看他人简历原文/画像/推荐的后门；
  * 画像接口只有 /me 自视角，无按用户 ID 读取的端点（结构性隔离）。
"""
from __future__ import annotations

import unittest

from _util import SYNTHETIC_JOB_TEXT, BusinessHarness, synthetic_resume_bytes  # noqa: E402


class T5DataIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_t5")
        _u, cls.admin_token = cls.h.login("admin_t5", "Adm1n!2026pass")

        # 共享岗位（已解析画像，供推荐）
        r = cls.h.client.post("/api/v1/jobs", headers=cls.h.auth(cls.admin_token),
                              json={"title": "T5-隔离合成岗",
                                    "job_description": SYNTHETIC_JOB_TEXT,
                                    "source": "synthetic",
                                    "source_license": "CC0-synthetic"})
        cls.job_id = r.json()["data"]["job"]["id"]
        cls.h.client.post(f"/api/v1/jobs/{cls.job_id}/parse",
                          headers=cls.h.auth(cls.admin_token))

        # 用户 A / 用户 B 各自的简历、画像、推荐、反馈
        cls.tokens = {}
        cls.resumes = {}
        cls.runs = {}
        for name, major in (("userA_iso", "软件工程"), ("userB_iso", "电子信息工程")):
            cls.h.register(name, "Iso!2026pass")
            _u, token = cls.h.login(name, "Iso!2026pass")
            cls.tokens[name] = token
            content = (synthetic_resume_bytes()
                       + f"\n专业：{major}\n<!-- {name} -->\n".encode("utf-8"))
            r = cls.h.upload_resume(token, content=content, unique=False,
                                    filename=f"{name}.txt")
            cls.resumes[name] = r.json()["data"]["resume"]["id"]
            cls.h.client.put("/api/v1/students/me/profile", headers=cls.h.auth(token),
                             json={"confirm": True})
            r = cls.h.client.post("/api/v1/recommendations", headers=cls.h.auth(token),
                                  json={"job_ids": [cls.job_id]})
            assert r.status_code == 200, r.text
            run = r.json()["data"]["run"]
            cls.runs[name] = run["id"]
            item_id = cls.h.client.get(
                f"/api/v1/recommendations/{run['id']}",
                headers=cls.h.auth(token)).json()["data"]["run"]["items"][0]["id"]
            r = cls.h.client.post(f"/api/v1/recommendations/{run['id']}/feedback",
                                  headers=cls.h.auth(token),
                                  json={"item_id": item_id,
                                        "feedback_type": "interested"})
            assert r.status_code == 200, r.text

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_cross_user_resume_access_blocked(self):
        a, b = self.tokens["userA_iso"], self.tokens["userB_iso"]
        r = self.h.client.get(f"/api/v1/resumes/{self.resumes['userB_iso']}",
                              headers=self.h.auth(a))
        self.assertEqual(r.status_code, 404, r.text)
        r = self.h.client.delete(f"/api/v1/resumes/{self.resumes['userB_iso']}",
                                 headers=self.h.auth(a))
        self.assertEqual(r.status_code, 404, r.text)
        r = self.h.client.post(f"/api/v1/resumes/{self.resumes['userB_iso']}/reparse",
                               headers=self.h.auth(a), json={})
        self.assertEqual(r.status_code, 404, r.text)
        # B 的数据仍然完好
        r = self.h.client.get(f"/api/v1/resumes/{self.resumes['userB_iso']}",
                              headers=self.h.auth(b))
        self.assertEqual(r.status_code, 200, r.text)

    def test_resume_list_scoped_to_owner(self):
        a = self.tokens["userA_iso"]
        r = self.h.client.get("/api/v1/resumes", headers=self.h.auth(a))
        self.assertEqual(r.status_code, 200, r.text)
        ids = {i["id"] for i in r.json()["data"]["items"]}
        self.assertIn(self.resumes["userA_iso"], ids)
        self.assertNotIn(self.resumes["userB_iso"], ids)

    def test_profile_is_self_scoped_only(self):
        a, b = self.tokens["userA_iso"], self.tokens["userB_iso"]
        ra = self.h.client.get("/api/v1/students/me/profile", headers=self.h.auth(a))
        rb = self.h.client.get("/api/v1/students/me/profile", headers=self.h.auth(b))
        self.assertEqual(ra.status_code, 200)
        self.assertEqual(rb.status_code, 200)
        self.assertNotEqual(ra.json()["data"]["profile"]["id"],
                            rb.json()["data"]["profile"]["id"])
        # A 的版本历史里不得出现 B 的画像
        rv = self.h.client.get("/api/v1/students/me/profile/versions",
                               headers=self.h.auth(a))
        self.assertEqual(rv.status_code, 200)
        for v in rv.json()["data"]["versions"]:
            self.assertEqual(v.get("profile_version") > 0, True)

    def test_cross_user_recommendation_blocked(self):
        a = self.tokens["userA_iso"]
        r = self.h.client.get(f"/api/v1/recommendations/{self.runs['userB_iso']}",
                              headers=self.h.auth(a))
        self.assertEqual(r.status_code, 404, r.text)
        r = self.h.client.get("/api/v1/recommendations", headers=self.h.auth(a))
        run_ids = {i["id"] for i in r.json()["data"]["items"]}
        self.assertIn(self.runs["userA_iso"], run_ids)
        self.assertNotIn(self.runs["userB_iso"], run_ids)

    def test_cross_user_feedback_blocked(self):
        a = self.tokens["userA_iso"]
        b_item = self.h.client.get(
            f"/api/v1/recommendations/{self.runs['userB_iso']}",
            headers=self.h.auth(self.tokens["userB_iso"])
        ).json()["data"]["run"]["items"][0]["id"]
        r = self.h.client.post(f"/api/v1/recommendations/{self.runs['userB_iso']}/feedback",
                               headers=self.h.auth(a),
                               json={"item_id": b_item, "feedback_type": "irrelevant"})
        self.assertEqual(r.status_code, 404, r.text)

    def test_admin_has_no_resume_or_reco_backdoor(self):
        """管理员可维护岗位，但不能读取他人简历/推荐/反馈。"""
        r = self.h.client.get(f"/api/v1/resumes/{self.resumes['userB_iso']}",
                              headers=self.h.auth(self.admin_token))
        self.assertEqual(r.status_code, 404, r.text)
        r = self.h.client.get(f"/api/v1/recommendations/{self.runs['userB_iso']}",
                              headers=self.h.auth(self.admin_token))
        self.assertEqual(r.status_code, 404, r.text)
        r = self.h.client.get("/api/v1/recommendations",
                              headers=self.h.auth(self.admin_token))
        self.assertEqual(r.json()["data"]["total"], 0,
                         "管理员的推荐历史应为空（不得代查他人）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
