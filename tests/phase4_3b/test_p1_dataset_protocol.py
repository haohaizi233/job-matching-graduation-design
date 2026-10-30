# -*- coding: utf-8 -*-
"""P1 数据集协议 / 代理标签边界 / Gold 门禁语义。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

PAIRS = ROOT / "data/independent_eval/pairs/pairs_synthetic_v1.jsonl"
REAL_PAIRS = ROOT / "data/independent_eval/pairs/pairs_real_v2.jsonl"


def _load(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class P1DatasetProtocol(unittest.TestCase):
    def test_synthetic_fixture_present_and_marked(self):
        rows = _load(PAIRS)
        self.assertGreater(len(rows), 0, "合成中文研究夹具应存在")
        for r in rows:
            self.assertEqual(str(r.get("is_synthetic")), "True")
            self.assertEqual(str(r.get("eligible_for_gold")), "False",
                             "合成夹具必须标记为不可进 Gold")

    def test_synthetic_pairs_cannot_become_gold(self):
        from job_matching.annotation.gold_gate import is_real_gold_record
        rows = _load(PAIRS)
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertFalse(is_real_gold_record(r),
                             "合成记录不得被判为真实 Gold")

    def test_real_pairs_are_empty_or_marked(self):
        rows = _load(REAL_PAIRS)
        for r in rows:
            self.assertNotEqual(str(r.get("is_synthetic")), "True",
                                "真实配对文件不得混入合成记录")

    def test_pair_ids_unique(self):
        rows = _load(PAIRS)
        ids = [r["pair_id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "pair_id 必须唯一")

    def test_content_hash_stable(self):
        rows = _load(PAIRS)
        self.assertGreater(len(rows), 0)
        for r in rows[:20]:
            self.assertTrue(str(r.get("content_hash")), "每条配对必须有 content_hash")

    def test_requires_gold_raises_without_gold(self):
        from job_matching.independent_eval.dataset import EvalSet, GoldUnavailableError
        rows = _load(PAIRS)[:5]
        ev = EvalSet(rows, [], meta={"label_source": "synthetic_fixture_tier_proxy"})
        with self.assertRaises(GoldUnavailableError):
            ev.require_gold()

    def test_unlabeled_evalset_blocks_formal_conclusion(self):
        from job_matching.independent_eval.dataset import EvalSet, GoldUnavailableError
        rows = _load(PAIRS)[:3]
        ev = EvalSet(rows, [], meta={"label_source": "human_gold",
                                     "annotation_status": "in_progress"})
        with self.assertRaises(GoldUnavailableError):
            ev.require_gold()

    def test_research_label_source_is_proxy(self):
        sys.path.insert(0, str(ROOT / "scripts" / "phase4_3b"))
        from run_research_experiments import LABEL_SOURCE, TIER_RELEVANCE
        self.assertIn("synthetic", LABEL_SOURCE)
        self.assertNotEqual(LABEL_SOURCE, "human_gold")
        self.assertEqual(set(TIER_RELEVANCE.values()), {0, 1, 2, 3})


if __name__ == "__main__":
    unittest.main()
