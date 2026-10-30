# -*- coding: utf-8 -*-
"""R2（P0-02 门禁）：推荐请求幂等与输入指纹。

不变量：
  * 指纹覆盖全部有效输入（用户/画像版本与内容哈希/岗位集合与各岗位内容与画像版本/
    模式/模型 ID 与版本/评分配置版本/top_k/筛选条件/allow_fallback），
    规范化 JSON 后 SHA-256，与字典顺序无关；
  * Idempotency-Key：同 Key 同语义复用既有运行；同 Key 不同语义 409；
  * 无 Key 时仅全同输入自然去重；任一有效输入变化都必须生成新运行；
  * 并发重复请求只落一条运行记录；评分失败不产生任何运行/条目。
"""
from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from _util import (SYNTHETIC_JOB_TEXT, SYNTHETIC_JOB_TEXT_2,  # noqa: E402
                   SYNTHETIC_JOB_TEXT_V2, BusinessHarness)


class R2RecommendationIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r2")
        _u, cls.admin_token = cls.h.login("admin_r2", "Adm1n!2026pass")
        cls.jid_a = cls.h.create_parsed_job(cls.admin_token, title="R2-Java合成岗",
                                            job_description=SYNTHETIC_JOB_TEXT)
        cls.jid_b = cls.h.create_parsed_job(cls.admin_token, title="R2-Python合成岗",
                                            job_description=SYNTHETIC_JOB_TEXT_2)

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 工具
    def _run(self, token: str, body: dict, *, key: str | None = None):
        headers = self.h.auth(token)
        if key:
            headers = dict(headers, **{"Idempotency-Key": key})
        return self.h.client.post("/api/v1/recommendations", headers=headers, json=body)

    def _base_body(self) -> dict:
        return {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b]}

    def _history_total(self, token: str) -> int:
        r = self.h.client.get("/api/v1/recommendations", headers=self.h.auth(token))
        return r.json()["data"]["total"]

    # ---------------------------------------------------------- 幂等 Key
    def test_same_idempotency_key_same_request_reuses_run(self):
        token = self.h.student("stu_r2_key")
        body = self._base_body()
        r1 = self._run(token, body, key="k-r2-same")
        r2 = self._run(token, body, key="k-r2-same")
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r1.json()["data"]["created"])
        self.assertFalse(r2.json()["data"]["created"])
        self.assertEqual(r1.json()["data"]["run"]["id"], r2.json()["data"]["run"]["id"])
        self.assertEqual(self._history_total(token), 1)

    def test_same_key_different_semantics_409(self):
        token = self.h.student("stu_r2_conflict")
        r1 = self._run(token, self._base_body(), key="k-r2-conflict")
        self.assertEqual(r1.status_code, 200, r1.text)
        body2 = dict(self._base_body(), top_k=1)
        r2 = self._run(token, body2, key="k-r2-conflict")
        self.assertEqual(r2.status_code, 409, r2.text)
        self.assertEqual(r2.json()["error"]["code"], "CONFLICT")
        # 冲突请求不得落任何新记录
        self.assertEqual(self._history_total(token), 1)

    def test_natural_dedup_without_key(self):
        token = self.h.student("stu_r2_dedup")
        body = self._base_body()
        r1 = self._run(token, body)
        r2 = self._run(token, body)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r1.json()["data"]["created"])
        self.assertFalse(r2.json()["data"]["created"], "全同输入才允许自然去重")
        self.assertEqual(r1.json()["data"]["run"]["id"], r2.json()["data"]["run"]["id"])

    # ---------------------------------------------------------- 有效输入变化
    def test_jd_update_creates_new_run_version(self):
        token = self.h.student("stu_r2_jd")
        body = {"mode": "baseline", "job_ids": [self.jid_a]}
        r1 = self._run(token, body)
        self.assertEqual(r1.status_code, 200, r1.text)

        r = self.h.client.patch(f"/api/v1/jobs/{self.jid_a}",
                                headers=self.h.auth(self.admin_token),
                                json={"job_description": SYNTHETIC_JOB_TEXT_V2})
        self.assertEqual(r.status_code, 200, r.text)
        rp = self.h.client.post(f"/api/v1/jobs/{self.jid_a}/parse",
                                headers=self.h.auth(self.admin_token))
        self.assertEqual(rp.status_code, 200, rp.text)

        r2 = self._run(token, body)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json()["data"]["created"],
                        "JD 更新后必须生成新的推荐版本，不得复用旧运行")
        self.assertNotEqual(r1.json()["data"]["run"]["id"],
                            r2.json()["data"]["run"]["id"])
        # 历史保留两个版本
        self.assertEqual(self._history_total(token), 2)

    def test_profile_version_change_creates_new_run(self):
        token = self.h.student("stu_r2_prof")
        body = self._base_body()
        r1 = self._run(token, body)
        self.assertEqual(r1.status_code, 200, r1.text)
        cur = self.h.profile(token)["profile_version"]

        r = self.h.client.put("/api/v1/students/me/profile", headers=self.h.auth(token),
                              json={"edits": {"major": "计算机科学与技术"},
                                    "confirm": True, "note": "R2 版本变更",
                                    "expected_version": cur})
        self.assertEqual(r.status_code, 200, r.text)

        r2 = self._run(token, body)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json()["data"]["created"])
        self.assertNotEqual(r1.json()["data"]["run"]["id"],
                            r2.json()["data"]["run"]["id"])
        self.assertGreater(r2.json()["data"]["run"]["profile_version"],
                           r1.json()["data"]["run"]["profile_version"])

    def test_top_k_filter_fallback_no_false_reuse(self):
        token = self.h.student("stu_r2_matrix")
        ids = {}
        for name, body in (
                ("topk3", {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b],
                           "top_k": 3}),
                ("topk1", {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b],
                           "top_k": 1}),
                ("city_sh", {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b],
                             "city": "上海"}),
                ("city_hz", {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b],
                             "city": "杭州"}),
                ("nofb", {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b],
                          "allow_fallback": False}),
                ("fb", {"mode": "baseline", "job_ids": [self.jid_a, self.jid_b],
                        "allow_fallback": True})):
            r = self._run(token, body)
            self.assertEqual(r.status_code, 200, f"{name}: {r.text}")
            self.assertTrue(r.json()["data"]["created"], f"{name} 不得错误复用")
            ids[name] = r.json()["data"]["run"]["id"]
        self.assertEqual(len(set(ids.values())), len(ids),
                         "top_k/筛选条件/allow_fallback 任一变化都必须生成新运行")

    def test_fingerprint_covers_all_effective_inputs(self):
        """指纹矩阵（服务级）：每个有效输入单独变化都必须改变语义哈希。"""
        from job_matching.service.reco_store import (RecommendationService,
                                                     canonical_json, sha256_text)

        def h(**over):
            base = dict(user_id="u-1", profile_version=1,
                        profile_content_hash="ph-1", resume_id="r-1",
                        mode="baseline", model_id="", model_version="",
                        scoring_method="baseline_skill_text_v1",
                        top_k=None,
                        job_entries=[{"job_id": "j-1", "job_content_hash": "jh-1",
                                      "profile_source_hash": "ps-1",
                                      "profile_status": "parsed"}],
                        category="", city="", allow_fallback=True)
            base.update(over)
            payload = RecommendationService.semantic_payload(**base)
            return sha256_text(canonical_json(payload))

        base_h = h()
        variants = {
            "user_id": h(user_id="u-2"),
            "profile_version": h(profile_version=2),
            "profile_content_hash": h(profile_content_hash="ph-2"),
            "resume_id": h(resume_id="r-2"),
            "mode": h(mode="experimental_model"),
            "model_id": h(model_id="model-x"),
            "model_version": h(model_version="v2"),
            "scoring_method": h(scoring_method="other_v1"),
            "top_k": h(top_k=5),
            "job_set": h(job_entries=[{"job_id": "j-2", "job_content_hash": "jh-2",
                                       "profile_source_hash": "ps-2",
                                       "profile_status": "parsed"}]),
            "job_content_hash": h(job_entries=[{"job_id": "j-1",
                                                "job_content_hash": "jh-9",
                                                "profile_source_hash": "ps-1",
                                                "profile_status": "parsed"}]),
            "category": h(category="后端开发"),
            "city": h(city="上海"),
            "allow_fallback": h(allow_fallback=False),
        }
        for name, digest in variants.items():
            self.assertNotEqual(digest, base_h, f"{name} 未纳入指纹")
        self.assertEqual(len(set(variants.values())), len(variants),
                         "不同有效输入不得产生相同指纹")

        # 与字典插入顺序无关（规范化序列化）
        p1 = RecommendationService.semantic_payload(
            user_id="u-1", profile_version=1, profile_content_hash="ph-1",
            resume_id=None, mode="baseline", model_id="", model_version="",
            scoring_method="s1", top_k=None,
            job_entries=[{"job_id": "j-1", "job_content_hash": "h"}],
            category="", city="", allow_fallback=True)
        p2 = dict(reversed(list(p1.items())))
        self.assertEqual(sha256_text(canonical_json(p1)),
                         sha256_text(canonical_json(p2)))

    # ---------------------------------------------------------- 并发与失败
    def test_concurrent_requests_single_run(self):
        token = self.h.student("stu_r2_conc")
        body = self._base_body()

        def _post(_i: int):
            from fastapi.testclient import TestClient
            c = TestClient(self.h.app)
            try:
                return c.post("/api/v1/recommendations", headers=self.h.auth(token),
                              json=body)
            finally:
                c.close()

        with ThreadPoolExecutor(max_workers=4) as ex:
            rs = list(ex.map(_post, range(4)))

        run_ids = set()
        for r in rs:
            if r.status_code == 200:
                run_ids.add(r.json()["data"]["run"]["id"])
        self.assertLessEqual(len(run_ids), 1,
                             f"并发相同请求不得生成多条运行: {run_ids}")
        self.assertEqual(self._history_total(token), 1,
                         "并发重复请求只允许落一条运行记录")

    def test_scoring_failure_leaves_no_rows(self):
        token = self.h.student("stu_r2_fail")
        before = self._history_total(token)
        with mock.patch.object(self.h.biz.core.matching, "rank",
                               side_effect=RuntimeError("模拟评分服务崩溃")):
            r = self._run(token, {"mode": "baseline", "job_ids": [self.jid_a]})
        self.assertEqual(r.status_code, 500, r.text)
        self.assertEqual(self._history_total(token), before,
                         "评分失败不得产生推荐记录")

    def test_model_missing_without_fallback_leaves_no_rows(self):
        token = self.h.student("stu_r2_model")
        before = self._history_total(token)
        r = self._run(token, {"mode": "experimental_model", "model_id": "no_such_model",
                              "allow_fallback": False, "job_ids": [self.jid_a]})
        self.assertEqual(r.status_code, 503, r.text)
        self.assertEqual(r.json()["error"]["code"], "MODEL_MISSING")
        self.assertEqual(self._history_total(token), before)

        # 允许降级 -> 显式告警 + 启发式分（不得伪装成模型分）
        r = self._run(token, {"mode": "experimental_model", "model_id": "no_such_model",
                              "allow_fallback": True, "job_ids": [self.jid_a]})
        self.assertEqual(r.status_code, 200, r.text)
        summary = r.json()["data"]["result_summary"]
        self.assertEqual(summary["score_type"], "heuristic_score")
        self.assertTrue(any("degrad" in w or "fallback" in w.lower() or "baseline" in w
                            for w in summary["warnings"]), summary["warnings"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
