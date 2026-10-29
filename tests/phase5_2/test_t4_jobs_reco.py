# -*- coding: utf-8 -*-
"""T4（B4 门禁，链路C）：岗位入库 -> 岗位画像 -> 学生检索 -> 推荐执行
-> 排序与解释快照 -> 历史查询 -> 反馈。

核心纪律：
  * 排序计算只经 Phase5-1 MatchingService.rank()（本组校验结果与其语义一致）；
  * 每次运行保存完整快照（画像版本 / 岗位集合与版本 / 方法 / 模型 / 配置 /
    排序 / 分数类型 / 解释 / 运行时间与状态），岗位后续被修改不影响历史解释；
  * 反馈是用户业务反馈，明确标注**不是**人工 Gold 标签；
  * 重复提交幂等（自然指纹 + Idempotency-Key）。
"""
from __future__ import annotations

import unittest

from _util import (SYNTHETIC_JOB_TEXT, SYNTHETIC_JOB_TEXT_2, BusinessHarness,
                   synthetic_resume_bytes)  # noqa: E402


class T4JobsAndRecommendations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_t4")
        _u, cls.admin_token = cls.h.login("admin_t4", "Adm1n!2026pass")

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 工具
    def _student(self, name: str) -> str:
        """自建学生：注册 -> 上传合成简历 -> 确认画像 -> 返回 token。"""
        self.h.register(name, "Stu!2026pass")
        _u, token = self.h.login(name, "Stu!2026pass")
        self.h.upload_resume(token)
        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(token),
                              json={"confirm": True})
        assert r.status_code == 200, r.text
        return token

    def _parsed_jobs(self, titles: tuple[str, ...] = ("T4-Java合成岗", "T4-Python合成岗")):
        items = [{"title": titles[0], "job_description": SYNTHETIC_JOB_TEXT,
                  "source": "synthetic", "source_license": "CC0-synthetic",
                  "is_synthetic": True},
                 {"title": titles[1], "job_description": SYNTHETIC_JOB_TEXT_2,
                  "source": "synthetic", "source_license": "CC0-synthetic",
                  "is_synthetic": True}]
        r = self.h.import_jobs(self.admin_token, items)
        assert r.status_code == 200, r.text
        ids = [c["job_id"] for c in r.json()["data"]["created"]]
        assert len(ids) == 2, r.text
        for jid in ids:
            rp = self.h.client.post(f"/api/v1/jobs/{jid}/parse",
                                    headers=self.h.auth(self.admin_token))
            assert rp.status_code == 200, rp.text
        return ids

    # ---------------------------------------------------------- 链路 C
    def test_link_c_full_recommendation_chain(self):
        h = self.h
        job_ids = self._parsed_jobs(("C链-Java岗", "C链-Python岗"))
        token = self._student("stu_c")

        # 学生读取岗位（按唯一标题检索）
        r = h.client.get("/api/v1/jobs", headers=h.auth(token), params={"q": "C链-"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["total"], 2, r.text)

        # 执行推荐（限定本次导入的岗位，结果可确定断言）
        prof = h.client.get("/api/v1/students/me/profile",
                            headers=h.auth(token)).json()["data"]["profile"]
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"mode": "baseline", "job_ids": job_ids, "top_k": 10})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertTrue(data["created"])
        run = data["run"]
        self.assertEqual(run["profile_version"], prof["profile_version"],
                         "推荐快照必须记录当时的画像版本")
        self.assertGreaterEqual(run["profile_version"], 1)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["scoring_method"], "baseline_skill_text_v1")
        self.assertEqual(len(run["job_set_snapshot"]), 2)
        self.assertIn("score_semantics", str(data["result_summary"]["warnings"]))

        # 快照：排序 + 分数类型 + 解释
        r = h.client.get(f"/api/v1/recommendations/{run['id']}", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json()["data"]["run"]["items"]
        self.assertEqual(len(items), 2)
        ranks = sorted(it["rank"] for it in items)
        self.assertEqual(ranks, [1, 2])
        for it in items:
            self.assertEqual(it["score_type"], "heuristic_score")
            self.assertIsInstance(it["explanation_snapshot"].get("evidence"), list)
            self.assertIn("job_snapshot_version", it)
            self.assertLessEqual(0.0, float(it["score"]))

        # 历史
        r = h.client.get("/api/v1/recommendations", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["total"], 1)

        # 反馈（业务反馈；不是 Gold）
        item_id = items[0]["id"]
        r = h.client.post(f"/api/v1/recommendations/{run['id']}/feedback",
                          headers=h.auth(token),
                          json={"item_id": item_id, "feedback_type": "interested"})
        self.assertEqual(r.status_code, 200, r.text)
        fb = r.json()["data"]["feedback"]
        self.assertTrue(fb["created"])
        self.assertIn("Gold", fb["gold_label_note"])
        r = h.client.post(f"/api/v1/recommendations/{run['id']}/feedback",
                          headers=h.auth(token),
                          json={"item_id": item_id, "feedback_type": "applied"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["data"]["feedback"]["created"], "同一用户同一条目只留一条反馈")

        # 岗位被修改后历史解释不变（快照可追溯）
        snapshot_before = items[0]["explanation_snapshot"]
        r = h.client.patch(f"/api/v1/jobs/{job_ids[0]}", headers=h.auth(self.admin_token),
                           json={"job_description": "完全不同的岗位职责：招聘合成数据管理员。"})
        self.assertEqual(r.status_code, 200, r.text)
        r = h.client.get(f"/api/v1/recommendations/{run['id']}", headers=h.auth(token))
        after = r.json()["data"]["run"]["items"]
        self.assertEqual({i["id"]: i["explanation_snapshot"] for i in after}[item_id],
                         snapshot_before, "历史推荐解释不得随岗位修改而改变")

    # ---------------------------------------------------------- 岗位管理
    def test_job_crud_and_offline_hidden_from_students(self):
        h = self.h
        r = h.client.post("/api/v1/jobs", headers=h.auth(self.admin_token),
                          json={"title": "T4-CRUD合成岗",
                                "job_description": SYNTHETIC_JOB_TEXT,
                                "source": "synthetic", "source_license": "CC0-synthetic"})
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()["data"]["job"]

        r = h.client.patch(f"/api/v1/jobs/{job['id']}", headers=h.auth(self.admin_token),
                           json={"title": "T4-CRUD合成岗-已更新"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["job"]["title"], "T4-CRUD合成岗-已更新")

        r = h.client.post(f"/api/v1/jobs/{job['id']}/status", headers=h.auth(self.admin_token),
                          json={"status": "offline"})
        self.assertEqual(r.status_code, 200, r.text)

        token = self._student("stu_crud")
        r = h.client.get("/api/v1/jobs", headers=h.auth(token),
                         params={"q": "T4-CRUD合成岗"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["total"], 0, "下架岗位不得出现在学生检索")
        r = h.client.get("/api/v1/jobs", headers=h.auth(self.admin_token),
                         params={"q": "T4-CRUD合成岗", "include_unpublished": True})
        self.assertEqual(r.json()["data"]["total"], 1)

    def test_job_import_partial_errors(self):
        items = [
            {"title": "T4-导入合法A", "job_description": SYNTHETIC_JOB_TEXT},
            {"title": "", "job_description": "缺标题应被拒绝"},
            {"job_description": "无标题"},
        ]
        r = self.h.import_jobs(self.admin_token, items)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()["data"]
        self.assertEqual(data["created_count"], 2, r.text)
        self.assertEqual(data["error_count"], 1)

    def test_job_parse_missing_is_404(self):
        r = self.h.client.post("/api/v1/jobs/no-such-job/parse",
                               headers=self.h.auth(self.admin_token))
        self.assertEqual(r.status_code, 404, r.text)

    # ---------------------------------------------------------- 推荐
    def test_recommend_requires_confirmed_profile(self):
        h = self.h
        h.register("stu_unconf", "Stu!2026pass")
        _u, token = h.login("stu_unconf", "Stu!2026pass")
        h.upload_resume(token)          # 画像生成但未确认
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token), json={})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_duplicate_submission_is_idempotent(self):
        job_ids = self._parsed_jobs(("T4-幂等Java岗", "T4-幂等Python岗"))
        token = self._student("stu_idem")
        body = {"mode": "baseline", "job_ids": job_ids}
        r1 = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json=body)
        r2 = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                                json=body)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r1.json()["data"]["created"])
        self.assertFalse(r2.json()["data"]["created"])
        self.assertEqual(r1.json()["data"]["run"]["id"], r2.json()["data"]["run"]["id"])

        # Idempotency-Key 重复提交同样只落一条
        headers = dict(self.h.auth(token), **{"Idempotency-Key": "k-t4-001"})
        r3 = self.h.client.post("/api/v1/recommendations", headers=headers, json=body)
        r4 = self.h.client.post("/api/v1/recommendations", headers=headers, json=body)
        self.assertEqual(r3.json()["data"]["run"]["id"], r4.json()["data"]["run"]["id"])
        self.assertTrue(r3.json()["data"]["created"])
        self.assertFalse(r4.json()["data"]["created"])

    def test_recommend_without_matchable_jobs_is_404(self):
        token = self._student("stu_nojob")
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"category": "不存在的合成类别"})
        self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(r.json()["error"]["code"], "NOT_FOUND")

    def test_feedback_type_validation(self):
        job_ids = self._parsed_jobs(("T4-反馈Java岗", "T4-反馈Python岗"))
        token = self._student("stu_fb")
        r = self.h.client.post("/api/v1/recommendations", headers=self.h.auth(token),
                               json={"job_ids": job_ids})
        self.assertEqual(r.status_code, 200, r.text)
        run = r.json()["data"]["run"]
        items = self.h.client.get(
            f"/api/v1/recommendations/{run['id']}",
            headers=self.h.auth(token)).json()["data"]["run"]["items"]
        item_id = items[0]["id"]
        r = self.h.client.post(f"/api/v1/recommendations/{run['id']}/feedback",
                               headers=self.h.auth(token),
                               json={"item_id": item_id, "feedback_type": "love_it"})
        self.assertEqual(r.status_code, 422, r.text)

    def test_job_search_by_skills_and_city(self):
        self._parsed_jobs(("T4-检索Java岗", "T4-检索Python岗"))
        token = self._student("stu_search")
        r = self.h.client.get("/api/v1/jobs", headers=self.h.auth(token),
                              params={"q": "T4-检索", "skills": "Python"})
        self.assertEqual(r.status_code, 200, r.text)
        titles = [i["title"] for i in r.json()["data"]["items"]]
        self.assertTrue(all("Python" in t for t in titles), titles)
        self.assertTrue(titles)

        r = self.h.client.get("/api/v1/jobs", headers=self.h.auth(token),
                              params={"q": "T4-检索", "city": "上海"})
        cities = {i["city"] for i in r.json()["data"]["items"]}
        self.assertEqual(cities, {"上海"}, r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
