# -*- coding: utf-8 -*-
"""G4：切分互斥。

按各协议的定义检查（不错误要求 Candidate Cold-start 的 job_overlap 为 0），
并检查原始数据覆盖率、被排除的交叉边与可评估候选人数量。
学历侧检查组合键重复、文本重复、标签冲突与人工金标准隔离。
"""
from __future__ import annotations

import unittest

from _util import cfg, jload, read_csv, read_csv_sig

SPLITS = ("train", "validation", "test")


class G4SplitDisjoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c = cfg()
        cls.c = c
        cls.raw_matches = read_csv_sig(c.src("matching", "matches"))
        cls.protocols = {}
        for name in ("candidate_cold", "job_cold", "double_cold"):
            d = c.out("splits_matching") / name
            frames = {}
            for s in SPLITS + ("excluded",):
                p = d / f"{s}.csv"
                frames[s] = read_csv(p) if p.exists() else None
            cls.protocols[name] = {"dir": d, "frames": frames,
                                   "manifest": jload(d / "manifest.json")}
        es = c.out("splits_education")
        cls.edu = {s: read_csv(es / f"{s}.csv")
                   for s in ("train", "validation", "gold_holdout", "excluded")}
        cls.edu_manifest = jload(es / "manifest.json")

    # ---------------- 通用
    def _pairs(self, name, split):
        f = self.protocols[name]["frames"][split]
        return set(map(tuple, f[["candidate_id", "job_id"]].astype(str).to_numpy()))

    def test_raw_pair_coverage_full(self):
        raw = len(self.raw_matches)
        for name, blk in self.protocols.items():
            total = sum(len(f) for f in blk["frames"].values() if f is not None)
            self.assertEqual(total, raw,
                             f"{name}: 划分 + excluded 未覆盖全部原始匹配记录 "
                             f"({total}/{raw})")

    def test_no_pair_reused_across_splits(self):
        for name in self.protocols:
            sets = {s: self._pairs(name, s) for s in SPLITS}
            for a in SPLITS:
                for b in SPLITS:
                    if a < b:
                        self.assertEqual(len(sets[a] & sets[b]), 0,
                                         f"{name}: {a} 与 {b} 存在 pair 交叉")

    def test_pair_index_disjoint_and_valid(self):
        raw_n = len(self.raw_matches)
        for name, blk in self.protocols.items():
            seen = set()
            for s, f in blk["frames"].items():
                if f is None:
                    continue
                idx = set(int(x) for x in f["pair_index"])
                self.assertEqual(len(idx), len(f), f"{name}/{s}: pair_index 重复")
                self.assertTrue(all(0 <= i < raw_n for i in idx),
                                f"{name}/{s}: pair_index 越界")
                self.assertEqual(seen & idx, set(), f"{name}: {s} 与其它集合索引交叉")
                seen |= idx

    # ---------------- 协议 A
    def test_candidate_cold_candidate_overlap_zero(self):
        f = self.protocols["candidate_cold"]["frames"]
        sets = {s: set(f[s]["candidate_id"].astype(str)) for s in SPLITS}
        for a in SPLITS:
            for b in SPLITS:
                if a < b:
                    self.assertEqual(len(sets[a] & sets[b]), 0,
                                     f"candidate_cold: {a}&{b} 候选人交叉")
        m = self.protocols["candidate_cold"]["manifest"]["overlap_check"]
        self.assertTrue(all(v == 0 for v in m["candidate_overlap"].values()))

    def test_candidate_cold_keeps_all_records_of_a_candidate_together(self):
        f = self.protocols["candidate_cold"]["frames"]
        owner = {}
        for s in SPLITS:
            for cid in f[s]["candidate_id"].astype(str):
                owner.setdefault(cid, set()).add(s)
        multi = {k: v for k, v in owner.items() if len(v) > 1}
        self.assertEqual(multi, {}, f"candidate_cold: {len(multi)} 个候选人跨集合")

    # ---------------- 协议 B
    def test_job_cold_job_overlap_zero(self):
        f = self.protocols["job_cold"]["frames"]
        sets = {s: set(f[s]["job_id"].astype(str)) for s in SPLITS}
        for a in SPLITS:
            for b in SPLITS:
                if a < b:
                    self.assertEqual(len(sets[a] & sets[b]), 0,
                                     f"job_cold: {a}&{b} 岗位交叉")

    # ---------------- 协议 C
    def test_double_cold_both_sides_disjoint(self):
        f = self.protocols["double_cold"]["frames"]
        csets = {s: set(f[s]["candidate_id"].astype(str)) for s in SPLITS}
        jsets = {s: set(f[s]["job_id"].astype(str)) for s in SPLITS}
        for a in SPLITS:
            for b in SPLITS:
                if a < b:
                    self.assertEqual(len(csets[a] & csets[b]), 0,
                                     f"double_cold: {a}&{b} 候选人交叉")
                    self.assertEqual(len(jsets[a] & jsets[b]), 0,
                                     f"double_cold: {a}&{b} 岗位交叉")

    def test_double_cold_excluded_edges_not_in_any_split(self):
        blk = self.protocols["double_cold"]
        exc = self._pairs("double_cold", "excluded")
        kept = set()
        for s in SPLITS:
            kept |= self._pairs("double_cold", s)
        self.assertEqual(len(exc & kept), 0, "excluded 交叉边被偷偷归入某个集合")
        self.assertGreater(len(exc), 0, "double_cold 应记录未采用的交叉边")
        self.assertEqual(len(exc | kept), len(self.raw_matches))

    def test_double_cold_reports_retention(self):
        cov = self.protocols["double_cold"]["manifest"]["coverage"]
        self.assertIn("retention_ratio", cov)
        self.assertGreater(cov["retention_ratio"], 0.0)
        self.assertEqual(cov["assigned_pairs"] + cov["excluded_pairs"],
                         cov["raw_pairs"])

    # ---------------- 可评估组
    def test_rankable_groups_recorded(self):
        for name in ("candidate_cold", "double_cold"):
            for s in SPLITS:
                info = self.protocols[name]["manifest"]["splits"][s]
                self.assertIn("groups_size_ge_2", info)
                self.assertGreaterEqual(info["groups_size_ge_2"], 0)

    # ---------------- 学历
    def test_education_record_key_disjoint(self):
        sets = {k: set(v["record_key"].astype(str)) for k, v in self.edu.items()}
        keys = list(sets)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                self.assertEqual(len(sets[a] & sets[b]), 0,
                                 f"学历 {a}&{b} 记录键交叉")

    def test_education_input_text_disjoint_across_train_val(self):
        a = set(self.edu["train"]["user_hash"].astype(str))
        b = set(self.edu["validation"]["user_hash"].astype(str))
        self.assertEqual(len(a & b), 0, "学历 train 与 validation 存在输入文本交叉")

    def test_education_gold_isolation(self):
        gold_hashes = set(self.edu["gold_holdout"]["user_hash"].astype(str))
        for s in ("train", "validation"):
            overlap = gold_hashes & set(self.edu[s]["user_hash"].astype(str))
            self.assertEqual(len(overlap), 0,
                             f"金标准输入泄漏进开发集 {s}: {len(overlap)} 条")
        self.assertEqual(len(self.edu["gold_holdout"]), 736,
                         "人工金标准条数与审计结论不一致")

    def test_education_gold_provenance_high_confidence(self):
        self.assertTrue((self.edu["gold_holdout"]["label_provenance"] == "human_gold").all())
        self.assertTrue((self.edu["train"]["label_provenance"] == "pseudo_online").all())
        self.assertTrue((self.edu["validation"]["label_provenance"] == "pseudo_online").all())

    def test_education_excluded_records_reasons(self):
        exc = self.edu["excluded"]
        self.assertGreater(len(exc), 0)
        self.assertIn("split", exc.columns)
        reasons = set(exc["split"].astype(str))
        self.assertTrue(reasons <= {"excluded_gold_input_overlap",
                                    "excluded_label_conflict",
                                    "excluded_input_duplicate"},
                        f"未知排除原因: {reasons}")

    def test_education_label_conflict_excluded(self):
        exc = self.edu["excluded"]
        n = int((exc["split"] == "excluded_label_conflict").sum())
        self.assertEqual(n, self.edu_manifest["excluded"]["by_reason"].get(
            "excluded_label_conflict", 0))

    def test_education_no_test_split_without_trustworthy_labels(self):
        self.assertFalse(self.edu_manifest["test_set_decision"]["built"],
                         "在无可信测试集时不得伪造 test 划分")


if __name__ == "__main__":
    unittest.main()
