# -*- coding: utf-8 -*-
"""Phase6 / M2 索引生命周期：内容哈希失效、缓存容量、用户数据隔离。

任务书 5.2/5.3：
  * 索引构建与查询生命周期分离（缓存命中不重建）；
  * 岗位集内容哈希 + 索引版本 -> 岗位新增/修改产生新键 = 安全失效；
  * 缓存容量上限 + LRU 淘汰；
  * 用户数据与索引隔离（不同岗位集不共享索引）。
"""
from __future__ import annotations

import unittest

from _util import synthetic_job_pool

from job_matching.service.research_strategy import (RecallIndexCache,
                                                    ResearchRetrievalScorer,
                                                    RESEARCH_STRATEGY_SPECS)


class M2IndexInvalidation(unittest.TestCase):
    def _scorer(self, cache: RecallIndexCache) -> ResearchRetrievalScorer:
        return ResearchRetrievalScorer(RESEARCH_STRATEGY_SPECS["zh_research_retrieval_v1"],
                                       cache=cache)

    def test_content_key_changes_on_doc_edit(self):
        docs = synthetic_job_pool(5)
        k1 = RecallIndexCache.content_key("m", docs)
        k2 = RecallIndexCache.content_key("m", docs)
        self.assertEqual(k1, k2, "同内容必须同键（可复用索引）")
        edited = list(docs)
        edited[2] = edited[2] + "（岗位已更新）"
        self.assertNotEqual(k1, RecallIndexCache.content_key("m", edited),
                            "岗位内容修改必须产生新键（安全失效）")
        appended = docs + [synthetic_job_pool(1, seed=99)[0]]
        self.assertNotEqual(k1, RecallIndexCache.content_key("m", appended),
                            "岗位新增必须产生新键")
        self.assertNotEqual(k1, RecallIndexCache.content_key("other_model", docs),
                            "不同策略标识必须隔离索引")

    def test_cache_hit_skips_rebuild(self):
        cache = RecallIndexCache(max_entries=4)
        docs = synthetic_job_pool(8)
        builds = {"n": 0}

        def builder():
            builds["n"] += 1
            return {"ok": True}

        key = cache.content_key("m", docs)
        e1 = cache.get_or_build(key, builder)
        e2 = cache.get_or_build(key, builder)
        self.assertEqual(1, builds["n"], "缓存命中不得重建索引")
        self.assertIs(e1["index"], e2["index"])
        self.assertEqual(1, cache.stats()["builds"])
        self.assertEqual(1, cache.stats()["hits"])
        self.assertTrue(e1["index_version"])

    def test_lru_eviction_respects_capacity(self):
        cache = RecallIndexCache(max_entries=2)
        for i in range(4):
            cache.get_or_build(f"k{i}", lambda i=i: {"i": i})
        st = cache.stats()
        self.assertEqual(2, st["entries"])
        self.assertGreaterEqual(st["evictions"], 2)

    def test_invalidate_specific_and_all(self):
        cache = RecallIndexCache(max_entries=4)
        cache.get_or_build("a", lambda: 1)
        cache.get_or_build("b", lambda: 2)
        self.assertEqual(1, cache.invalidate("a"))
        self.assertEqual(1, cache.stats()["entries"])
        self.assertEqual(1, cache.invalidate())
        self.assertEqual(0, cache.stats()["entries"])

    def test_index_refresh_after_job_edit(self):
        """岗位修改后重查必须反映新内容（旧索引不被误用）。"""
        from job_matching.service.contracts import JobProfile, StudentProfile
        cache = RecallIndexCache(max_entries=4)
        scorer = self._scorer(cache)
        student = StudentProfile.from_dict({
            "profile_id": "p", "employment_intention": {"value": "Java", "status": "ok"},
            "skills": [{"skill_id": "s", "canonical_name": "Java"}]})
        job_a = JobProfile.from_dict({
            "job_id": "j0", "job_title": {"value": "Java 工程师", "status": "ok"},
            "required_skills": [{"skill_id": "k", "canonical_name": "Java"}]})
        job_b = JobProfile.from_dict({
            "job_id": "j1", "job_title": {"value": "前端 工程师", "status": "ok"},
            "required_skills": [{"skill_id": "k2", "canonical_name": "Vue"}]})
        r1 = scorer.rank(student, [job_a, job_b], top_k=2)
        # 更新 j0 的岗位内容 -> 内容哈希变化 -> 必须重建索引
        job_a2 = JobProfile.from_dict({
            "job_id": "j0", "job_title": {"value": "Java 工程师", "status": "ok"},
            "required_skills": [{"skill_id": "k", "canonical_name": "Java"}],
            "responsibilities": {"value": ["负责 Java 服务开发"], "status": "ok"}})
        r2 = scorer.rank(student, [job_a2, job_b], top_k=2)
        self.assertEqual(2, cache.stats()["builds"], "岗位内容变化必须触发重建")
        self.assertNotEqual(r1[0]["index_version"], r2[0]["index_version"])
        self.assertEqual(2, len(r2))

    def test_user_data_isolation_via_content_key(self):
        """不同用户岗位集内容不同 -> 索引键不同（不共享、不串数据）。"""
        docs_a = synthetic_job_pool(4, seed=1)
        docs_b = synthetic_job_pool(4, seed=2)
        self.assertNotEqual(RecallIndexCache.content_key("m", docs_a),
                            RecallIndexCache.content_key("m", docs_b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
