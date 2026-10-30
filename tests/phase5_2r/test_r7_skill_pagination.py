# -*- coding: utf-8 -*-
"""R7（P1-07 门禁）：岗位筛选与分页语义。

不变量（修复"先分页后过滤"导致的 total 虚假/跨页漏项）：
  * total = 所有符合过滤条件的岗位数（不受 page/page_size 影响）；
  * 分页边界不漏项、不越界、不重复：各页并集 == 全部符合条件集合；
  * 同等条件排序稳定（翻页结果可重现）；
  * 多条件组合（技能 + 城市等）结果正确。
"""
from __future__ import annotations

import unittest

from _util import (SYNTHETIC_JOB_TEXT, SYNTHETIC_JOB_TEXT_2,  # noqa: E402
                   BusinessHarness)


def _skill_names(job: dict) -> set[str]:
    """独立参考实现：从结构化画像读取技能名（不调用被测过滤器）。"""
    prof = job.get("structured_profile") or {}
    out = set()
    for key in ("required_skills", "preferred_skills"):
        for s in prof.get(key) or []:
            name = str((s or {}).get("canonical_name") or "").strip().lower()
            if name:
                out.add(name)
    return out


class R7SkillFilterPagination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()
        cls.admin = cls.h.make_admin("admin_r7")
        _u, cls.admin_token = cls.h.login("admin_r7", "Adm1n!2026pass")
        cls.jobs: list[dict] = []
        for i in range(6):
            jid = cls.h.create_parsed_job(
                cls.admin_token, title=f"R7-Java岗-{i:02d}",
                job_description=SYNTHETIC_JOB_TEXT)
            cls.jobs.append(cls.h.client.get(
                f"/api/v1/jobs/{jid}",
                headers=cls.h.auth(cls.admin_token)).json()["data"]["job"])
        for i in range(6):
            jid = cls.h.create_parsed_job(
                cls.admin_token, title=f"R7-Python岗-{i:02d}",
                job_description=SYNTHETIC_JOB_TEXT_2)
            cls.jobs.append(cls.h.client.get(
                f"/api/v1/jobs/{jid}",
                headers=cls.h.auth(cls.admin_token)).json()["data"]["job"])

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 工具
    def _query(self, *, skills: str | None = None, city: str | None = None,
               q: str = "R7-", page: int = 1, page_size: int = 5) -> dict:
        params = {"q": q, "page": page, "page_size": page_size}
        if skills:
            params["skills"] = skills
        if city:
            params["city"] = city
        r = self.h.client.get("/api/v1/jobs", headers=self.h.auth(self.admin_token),
                              params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["data"]

    def _paged_ids(self, **kw) -> tuple[list[str], int]:
        ids: list[str] = []
        page = 1
        total = None
        while True:
            data = self._query(page=page, **kw)
            if total is None:
                total = data["total"]
            batch = [it["id"] for it in data["items"]]
            if not batch:
                break
            ids.extend(batch)
            if len(ids) >= data["total"]:
                break
            page += 1
        return ids, int(total or 0)

    # ---------------------------------------------------------- 分页语义
    def test_unfiltered_pagination_partitions_all(self):
        ids, total = self._paged_ids(page_size=5)
        self.assertEqual(total, 12)
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(set(ids)), 12, "翻页不得重复或漏项")
        self.assertEqual(set(ids), {j["id"] for j in self.jobs})

    def test_skill_filter_total_is_global_not_page_local(self):
        """复现原缺陷：第 1 页只有部分匹配项时，total 不得被页内过滤结果污染。"""
        matched = {j["id"] for j in self.jobs if "java" in _skill_names(j)}
        self.assertTrue(matched, "合成 JD 应解析出 java 技能（若失败需核对解析器词表）")

        # page_size=2：旧实现在此返回 total=len(第一页内匹配) 而非全局匹配数
        data = self._query(skills="java", page=1, page_size=2)
        self.assertEqual(data["total"], len(matched),
                         "total 必须是全部符合条件的数量")

        ids, total = self._paged_ids(skills="java", page_size=2)
        self.assertEqual(total, len(matched))
        self.assertEqual(set(ids), matched, "各页并集必须等于全部匹配集合")
        self.assertEqual(len(ids), len(matched), "分页边界不得漏项或越界")

    def test_skill_filter_python_partition(self):
        matched = {j["id"] for j in self.jobs if "python" in _skill_names(j)}
        self.assertTrue(matched, "合成 JD 应解析出 python 技能")
        ids, total = self._paged_ids(skills="Python", page_size=4)
        self.assertEqual(total, len(matched))
        self.assertEqual(set(ids), matched)
        self.assertEqual(len(set(ids)), len(ids))

    def test_combined_filters_correct(self):
        matched = {j["id"] for j in self.jobs
                   if "java" in _skill_names(j) and j.get("city") == "上海"}
        self.assertTrue(matched)
        ids, total = self._paged_ids(skills="java", city="上海", page_size=3)
        self.assertEqual(total, len(matched))
        self.assertEqual(set(ids), matched)

    def test_stable_order_across_repeated_queries(self):
        first = [it["id"] for it in self._query(skills="java", page=1,
                                                page_size=3)["items"]]
        again = [it["id"] for it in self._query(skills="java", page=1,
                                                page_size=3)["items"]]
        self.assertEqual(first, again, "同等条件排序必须稳定")
        second = [it["id"] for it in self._query(skills="java", page=2,
                                                 page_size=3)["items"]]
        self.assertFalse(set(first) & set(second), "相邻页不得重复")

    def test_pagination_bounds_are_safe(self):
        data = self._query(page=0, page_size=3)
        self.assertEqual(data["page"], 1, "page=0 必须被规范化为 1")
        data = self._query(page=99, page_size=3)
        self.assertEqual(data["items"], [], "越界页返回空页而非报错")
        self.assertEqual(data["total"], 12)
        data = self._query(page=1, page_size=1000)
        self.assertLessEqual(data["page_size"], 100, "page_size 必须有上限")


if __name__ == "__main__":
    unittest.main(verbosity=2)
