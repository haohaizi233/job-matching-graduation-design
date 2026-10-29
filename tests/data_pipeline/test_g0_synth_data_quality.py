# -*- coding: utf-8 -*-
"""G0：合成夹具驱动的数据质量门禁（Core CI 可移植子集）。

定位（Phase5-2 / Batch 0）：
  `tests/data_pipeline/` 的 G1~G7 依赖不入库的真实数据，在全新 checkout 上无法执行。
  本套件用**临时合成夹具** + **生产代码**验证门禁逻辑本身，做到：
    * 不需要真实简历 / 训练数据 / checkpoint / GPU；
    * 跑完即删，不写入 data/、models/、历史基线报告；
    * 既验证"合法数据能通过"，也验证"违规数据能被抓住"（负向测试）。

覆盖门禁语义（与 G2/G3/G4/G5/G6 对齐，但不硬编码真实数据规模）：
  G2 字段约束   -> 主键唯一 / 外键完整 / 向量形状 / 多标签编码
  G3 泄漏防护   -> 黑名单 / 目标列隔离 / 间接泄漏 / 白名单与黑名单冲突
  G4 切分互斥   -> 三协议互斥 / excluded 不入集合 / 覆盖完整
  G5 可复现性   -> 同种子同结果 / 分块不影响数值 / manifest 哈希一致
  G6 可加载性   -> 向量可读 / ID 映射可逆 / 数值 ID 不进特征

明确不覆盖（真实数据专有断言，留在 Artifact-dependent Validation）：
  * G1 的 RAW_HASH_BASELINE 哈希基线（需要真实 data/raw/）；
  * G4 的"人工金标准恰好 736 条"等真实数据规模断言；
  * G2/G6 的真实 embedding 维度/规模与真实 ID 语义。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from synth_fixtures import LABEL_ORDER, SynthLandscape, _resolve  # noqa: E402
from job_matching.baseline_ranking import cosine_scores  # noqa: E402
from job_matching.metrics_ranking import random_ranking_scores  # noqa: E402
from job_matching.pair_features import NUMERIC_FEATURE_COLUMNS, build_pair_features  # noqa: E402
from job_matching.policy import (audit_feature_set, check_feature_columns,  # noqa: E402
                                 detect_indirect_leakage)
from job_matching.split_matching import build_single_key_protocol  # noqa: E402


class _SynthBase(unittest.TestCase):
    """共享一套合成景观（只构造一次，测试结束清理）。"""

    land: SynthLandscape
    _built = False

    @classmethod
    def setUpClass(cls):
        if not _SynthBase._built:
            _SynthBase.land = SynthLandscape(n_candidates=60, n_jobs=40, n_pairs=260)
            _SynthBase.land.build()
            _SynthBase._built = True
        land = _SynthBase.land
        cls.land = land
        cls.c = land.cfg
        cls.matches = land.read("data/raw/job-resume-matching/matches.csv")
        cls.resume = land.read("data/interim/matching/resume_normalized.csv")
        cls.job = land.read("data/interim/matching/job_normalized.csv")
        cls.features = land.read("data/processed/matching/features_pairs.csv")
        cls.targets = land.read("data/processed/matching/targets_pairs.csv")
        cls.schema = json.loads((land.root / "data/processed/matching/feature_schema.json")
                                .read_text(encoding="utf-8"))
        cls.matrix = np.load(land.root / "data/processed/matching" /
                             "feature_matrix_match_label_strength.npz", allow_pickle=True)
        cls.edu_lab = land.read("data/processed/education/education_labels.csv",
                                dtype={"label_multi_hot": str})
        cls.edu_in = land.read("data/processed/education/education_inputs.csv")

    @classmethod
    def tearDownClass(cls):
        if getattr(_SynthBase, "land", None) is not None and _SynthBase._built:
            _SynthBase.land.__exit__(None, None, None)
            _SynthBase._built = False


# ============================================================ G2 字段约束
class G0FieldConstraints(_SynthBase):
    """G2 语义：主键 / 外键 / 向量 / 数值域 / 多标签编码。"""

    def test_resume_primary_key_unique(self):
        self.assertTrue(self.resume["candidate_id"].is_unique)
        self.assertEqual(int(self.resume["candidate_id"].isna().sum()), 0)

    def test_job_primary_key_unique(self):
        self.assertTrue(self.job["job_id"].is_unique)

    def test_match_composite_key_unique(self):
        self.assertEqual(int(self.targets.duplicated(["candidate_id", "job_id"]).sum()), 0)

    def test_match_foreign_keys_complete(self):
        cand = set(self.resume["candidate_id"].astype(str))
        jobs = set(self.job["job_id"].astype(str))
        self.assertEqual(set(self.targets["candidate_id"].astype(str)) - cand, set())
        self.assertEqual(set(self.targets["job_id"].astype(str)) - jobs, set())

    def test_embedding_shape_dtype_finite(self):
        d = self.land.root / "data/processed/embeddings"
        for side, rows in (("cv", len(self.resume)), ("job", len(self.job))):
            a = np.load(d / f"{side}_embeddings.npy")
            self.assertEqual(a.dtype, np.float32)
            self.assertEqual(a.shape, (rows, 768))
            self.assertTrue(np.isfinite(a).all())

    def test_id_map_is_bijection(self):
        d = self.land.root / "data/processed/embeddings"
        for side in ("cv", "job"):
            m = json.loads((d / f"{side}_id_map.json").read_text(encoding="utf-8"))
            self.assertEqual(len(m["id_to_row"]), len(m["row_to_id"]))
            for k, v in m["id_to_row"].items():
                self.assertEqual(m["row_to_id"][str(v)], k)
            self.assertEqual(sorted(int(x) for x in m["id_to_row"].values()),
                             list(range(len(m["row_to_id"]))))

    def test_pair_numeric_features_finite_and_bounded(self):
        cols = NUMERIC_FEATURE_COLUMNS
        X = self.features[cols].to_numpy(dtype=np.float64)
        self.assertTrue(np.isfinite(X).all())
        for col in cols[:4]:
            v = self.features[col].to_numpy(dtype=np.float64)
            self.assertTrue((v >= 0).all() and (v <= 1).all(), f"{col} 超出 [0,1]")
        self.assertTrue(set(self.features["category_match"].unique()) <= {0.0, 1.0})

    def test_label_strength_in_declared_enum(self):
        vals = set(self.targets["label_strength"].unique())
        self.assertTrue(vals <= {"weak_positive", "medium_positive", "strong_positive"},
                        f"非法 label_strength: {vals}")

    def test_label_ordinal_consistent(self):
        m = {"weak_positive": 1, "medium_positive": 2, "strong_positive": 3}
        expect = self.targets["label_strength"].map(m)
        self.assertTrue((expect.to_numpy() == self.targets["label_ordinal"].to_numpy()).all())

    def test_education_multihot_all_rows_valid(self):
        order = LABEL_ORDER
        bad = 0
        for mh, toks in zip(self.edu_lab["label_multi_hot"].astype(str),
                            self.edu_lab["label_tokens_json"].astype(str)):
            if len(mh) != len(order) or set(mh) - {"0", "1"}:
                bad += 1
                continue
            if {order[i] for i, ch in enumerate(mh) if ch == "1"} != set(json.loads(toks)):
                bad += 1
        self.assertEqual(bad, 0, f"{bad} 行多热编码与词表不一致")

    def test_education_tokens_within_vocabulary_or_flagged(self):
        order = set(LABEL_ORDER)
        for toks, status in zip(self.edu_lab["label_tokens_json"].astype(str),
                                self.edu_lab["label_status"].astype(str)):
            for t in json.loads(toks):
                self.assertIn(t, order)
                self.assertEqual(status, "ok")


# ============================================================ G3 泄漏防护
class G0LeakageGuard(_SynthBase):
    """G3 语义：派生评分 / 目标列不得进入特征。"""

    def test_forbidden_score_fields_not_in_features(self):
        forbidden = set(self.c.derived_score_chain())
        self.assertEqual(forbidden & set(self.features.columns), set())

    def test_feature_columns_pass_task_policy(self):
        cols = [c for c in self.features.columns if c not in ("candidate_id", "job_id")]
        res = check_feature_columns("match_label_strength", cols, raise_on_violation=False)
        self.assertTrue(res.ok, f"违反任务特征策略: {res.violations}")

    def test_target_columns_not_in_features(self):
        task = self.c.task("match_label_strength")
        targets = set(task["target_columns"]) | set(task["target_derived_columns"])
        self.assertEqual(targets & set(self.features.columns), set())

    def test_id_columns_are_metadata_not_features(self):
        id_like = set(self.c.id_like_columns())
        self.assertEqual(id_like & set(self.schema["all_feature_columns"]), set())
        self.assertEqual(id_like & set(self.schema["numeric_feature_columns"]), set())

    def test_targets_physically_isolated_from_features(self):
        share = (set(self.features.columns) & set(self.targets.columns)) - {
            "candidate_id", "job_id"}
        self.assertEqual(share, set())

    def test_education_inputs_do_not_contain_label_columns(self):
        leak_like = {"label_tokens_json", "label_multi_hot", "label_status",
                     "assistant", "ai", "diff"}
        self.assertEqual(leak_like & set(self.edu_in.columns), set())

    def test_education_labels_do_not_contain_features(self):
        feat_like = {"user_norm", "slot_education_norm", "user_len"}
        self.assertEqual(feat_like & set(self.edu_lab.columns), set())

    def test_matrix_feature_names_within_policy(self):
        names = [str(x) for x in self.matrix["feature_names"].tolist()]
        self.assertEqual(names, NUMERIC_FEATURE_COLUMNS)
        check_feature_columns("match_label_strength", names)

    def test_matrix_matches_declared_columns(self):
        X = self.matrix["X"]
        names = [str(x) for x in self.matrix["feature_names"].tolist()]
        self.assertEqual(X.shape, (len(self.features), len(names)))
        ref = self.features[names].to_numpy(dtype=np.float32)
        self.assertTrue(np.allclose(X, ref, rtol=0, atol=1e-6))

    def test_features_cannot_reconstruct_derived_scores(self):
        reference = {c: self.targets[c].to_numpy(dtype=np.float64)
                     for c in ("final_score", "candidate_rank", "candidate_rank_pct")
                     if c in self.targets.columns}
        num = self.features[NUMERIC_FEATURE_COLUMNS]
        findings = detect_indirect_leakage(num, reference, "match_label_strength")
        hard = [f for f in findings if f.get("severity") != "warn"]
        self.assertEqual(hard, [], f"检出间接泄漏: {hard}")

    def test_audit_feature_set_reports_no_violation(self):
        reference = {"final_score": self.targets["final_score"].to_numpy(dtype=np.float64)}
        res = audit_feature_set("match_label_strength",
                                self.features[NUMERIC_FEATURE_COLUMNS], reference,
                                raise_on_violation=False)
        self.assertTrue(res.ok, f"特征集审计未通过: {res.violations}")

    def test_no_forbidden_field_in_any_declared_allowed_feature(self):
        task = self.c.task("match_label_strength")
        forbidden = set(task["forbidden_features"]) | set(self.c.always_forbidden())
        allowed = {a.split(".", 1)[-1] for a in task["allowed_features"]}
        self.assertEqual(forbidden & allowed, set())

    def test_derived_score_chain_listed_as_forbidden_for_both_matching_tasks(self):
        chain = set(self.c.derived_score_chain())
        for task in ("match_label_strength", "match_ranking"):
            self.assertTrue(chain <= set(self.c.task(task)["forbidden_features"]))


# ============================================================ G4 切分互斥
class G0SplitDisjoint(_SynthBase):
    """G4 语义：三协议互斥、excluded 不入集合、覆盖完整。"""

    SPLITS = ("train", "validation", "test")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.protocols = {}
        for name in ("candidate_cold", "job_cold", "double_cold"):
            d = cls.land.root / "data/splits/matching" / name
            frames = {}
            for s in cls.SPLITS + ("excluded",):
                p = d / f"{s}.csv"
                frames[s] = pd.read_csv(p) if p.exists() else None
            cls.protocols[name] = {"dir": d, "frames": frames,
                                   "manifest": json.loads((d / "manifest.json")
                                                          .read_text(encoding="utf-8"))}

    def _pairs(self, name, split):
        f = self.protocols[name]["frames"][split]
        return set(map(tuple, f[["candidate_id", "job_id"]].astype(str).to_numpy()))

    def test_raw_pair_coverage_full(self):
        raw = len(self.matches)
        for name, blk in self.protocols.items():
            total = sum(len(f) for f in blk["frames"].values() if f is not None)
            self.assertEqual(total, raw, f"{name}: 划分 + excluded 未覆盖全部记录")

    def test_no_pair_reused_across_splits(self):
        for name in self.protocols:
            sets = {s: self._pairs(name, s) for s in self.SPLITS}
            for i, a in enumerate(self.SPLITS):
                for b in self.SPLITS[i + 1:]:
                    self.assertEqual(len(sets[a] & sets[b]), 0,
                                     f"{name}: {a} 与 {b} 存在 pair 交叉")

    def test_pair_index_disjoint_and_valid(self):
        raw_n = len(self.matches)
        for name, blk in self.protocols.items():
            seen = set()
            for s, f in blk["frames"].items():
                if f is None:
                    continue
                idx = set(int(x) for x in f["pair_index"])
                self.assertEqual(len(idx), len(f), f"{name}/{s}: pair_index 重复")
                self.assertTrue(all(0 <= i < raw_n for i in idx))
                self.assertEqual(seen & idx, set())
                seen |= idx

    def test_candidate_cold_keeps_candidate_together(self):
        f = self.protocols["candidate_cold"]["frames"]
        owner: dict[str, set] = {}
        for s in self.SPLITS:
            for cid in f[s]["candidate_id"].astype(str):
                owner.setdefault(cid, set()).add(s)
        self.assertEqual({k: v for k, v in owner.items() if len(v) > 1}, {})

    def test_job_cold_job_overlap_zero(self):
        f = self.protocols["job_cold"]["frames"]
        sets = {s: set(f[s]["job_id"].astype(str)) for s in self.SPLITS}
        for i, a in enumerate(self.SPLITS):
            for b in self.SPLITS[i + 1:]:
                self.assertEqual(len(sets[a] & sets[b]), 0)

    def test_double_cold_both_sides_disjoint(self):
        f = self.protocols["double_cold"]["frames"]
        csets = {s: set(f[s]["candidate_id"].astype(str)) for s in self.SPLITS}
        jsets = {s: set(f[s]["job_id"].astype(str)) for s in self.SPLITS}
        for i, a in enumerate(self.SPLITS):
            for b in self.SPLITS[i + 1:]:
                self.assertEqual(len(csets[a] & csets[b]), 0)
                self.assertEqual(len(jsets[a] & jsets[b]), 0)

    def test_double_cold_excluded_edges_not_in_any_split(self):
        exc = self._pairs("double_cold", "excluded")
        kept = set()
        for s in self.SPLITS:
            kept |= self._pairs("double_cold", s)
        self.assertEqual(len(exc & kept), 0, "excluded 交叉边被偷偷归入某个集合")
        self.assertGreater(len(exc), 0, "double_cold 应记录未采用的交叉边")
        self.assertEqual(len(exc | kept), len(self.matches))

    def test_double_cold_reports_retention(self):
        cov = self.protocols["double_cold"]["manifest"]["coverage"]
        self.assertGreater(cov["retention_ratio"], 0.0)
        self.assertEqual(cov["assigned_pairs"] + cov["excluded_pairs"], cov["raw_pairs"])

    def test_rankable_groups_recorded(self):
        for name in ("candidate_cold", "double_cold"):
            for s in self.SPLITS:
                info = self.protocols[name]["manifest"]["splits"][s]
                self.assertIn("groups_size_ge_2", info)
                self.assertGreaterEqual(info["groups_size_ge_2"], 0)

    def test_education_record_key_disjoint(self):
        es = self.land.root / "data/splits/education"
        frames = {s: pd.read_csv(es / f"{s}.csv")
                  for s in ("train", "validation", "gold_holdout", "excluded")}
        sets = {k: set(v["record_key"].astype(str)) for k, v in frames.items()}
        keys = list(sets)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                self.assertEqual(len(sets[a] & sets[b]), 0)

    def test_education_gold_isolation(self):
        es = self.land.root / "data/splits/education"
        frames = {s: pd.read_csv(es / f"{s}.csv") for s in ("train", "validation", "gold_holdout")}
        gold_hashes = set(frames["gold_holdout"]["user_hash"].astype(str))
        for s in ("train", "validation"):
            self.assertEqual(gold_hashes & set(frames[s]["user_hash"].astype(str)), set())

    def test_education_gold_provenance(self):
        es = self.land.root / "data/splits/education"
        gold = pd.read_csv(es / "gold_holdout.csv")
        train = pd.read_csv(es / "train.csv")
        self.assertTrue((gold["label_provenance"] == "human_gold").all())
        self.assertTrue((train["label_provenance"] == "pseudo_online").all())

    def test_education_excluded_reasons_registered(self):
        es = self.land.root / "data/splits/education"
        exc = pd.read_csv(es / "excluded.csv")
        reasons = set(exc["split"].astype(str))
        self.assertTrue(reasons <= {"excluded_gold_input_overlap",
                                    "excluded_label_conflict",
                                    "excluded_input_duplicate"})
        man = json.loads((es / "manifest.json").read_text(encoding="utf-8"))
        for reason in reasons:
            self.assertEqual(int((exc["split"] == reason).sum()),
                             man["excluded"]["by_reason"].get(reason, 0))

    def test_education_no_test_split_without_trustworthy_labels(self):
        es = self.land.root / "data/splits/education"
        man = json.loads((es / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(man["test_set_decision"]["built"],
                         "在无可信测试集时不得伪造 test 划分")


# ============================================================ G5 可复现性
class G0Reproducibility(_SynthBase):
    """G5 语义：同种子同结果、manifest 哈希一致、分块不影响数值。"""

    def test_split_files_hash_matches_manifest(self):
        for name in ("candidate_cold", "job_cold", "double_cold"):
            d = self.land.root / "data/splits/matching" / name
            man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(man["files"], f"{name}: manifest 未登记文件")
            for f in man["files"]:
                if f["split"] == "manifest":
                    continue
                p = _resolve(self.land.root, f["path"])
                self.assertTrue(p.exists(), f"{name}: {f['path']} 不存在")
                from job_matching.core import sha256_file
                self.assertEqual(sha256_file(p), f["sha256"],
                                 f"{name}: {f['path']} 哈希与 manifest 不一致")

    def test_group_assignment_deterministic(self):
        sizes = self.matches.groupby("candidate_id").size()
        ratios = {"train": 0.8, "validation": 0.1, "test": 0.1}
        from job_matching.split_matching import assign_groups
        a = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold"))
        b = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold"))
        self.assertEqual(a, b)

    def test_group_assignment_changes_with_seed(self):
        sizes = self.matches.groupby("candidate_id").size()
        ratios = {"train": 0.8, "validation": 0.1, "test": 0.1}
        from job_matching.split_matching import assign_groups
        a = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold"))
        b = assign_groups(sizes, ratios, self.c.seed("split_candidate_cold") + 1)
        self.assertNotEqual(a, b)

    def test_candidate_cold_split_reproducible(self):
        proto = self.c.protocol("candidate_cold")
        ratios = {k: float(v) for k, v in proto["ratios"].items()}
        res = build_single_key_protocol(
            self.matches, "candidate_id", ratios,
            self.c.seed(proto["seed_key"]), "candidate_cold",
            self.c.min_group_size_for_ranking)
        pairs = res["_pairs_frame"]
        for s in ("train", "validation", "test"):
            f = pd.read_csv(self.land.root / "data/splits/matching/candidate_cold" /
                            f"{s}.csv")
            saved = set(map(tuple, f[["candidate_id", "job_id"]].astype(str).to_numpy()))
            got = set(map(tuple, pairs.loc[pairs["split"] == s,
                                           ["candidate_id", "job_id"]]
                          .astype(str).to_numpy()))
            self.assertEqual(got, saved, f"candidate_cold/{s} 重算与落盘不一致")

    def test_random_baseline_deterministic(self):
        for seed in (self.c.seed("baseline_random_ranking"),
                     self.c.seed("baseline_random_ranking") + 1):
            self.assertTrue(np.array_equal(random_ranking_scores(1000, seed),
                                           random_ranking_scores(1000, seed)))

    def test_cosine_scores_deterministic_within_tolerance(self):
        d = self.land.root / "data/processed/embeddings"
        cv = np.load(d / "cv_embeddings.npy")
        job = np.load(d / "job_embeddings.npy")
        n = 200
        cv_rows = np.arange(n) % cv.shape[0]
        job_rows = np.arange(n) % job.shape[0]
        a = cosine_scores(cv, job, cv_rows, job_rows, block=32)
        b = cosine_scores(cv, job, cv_rows, job_rows, block=7)
        self.assertTrue(np.allclose(a, b, rtol=0, atol=1e-6))

    def test_embedding_cache_hash_stable(self):
        d = self.land.root / "data/processed/embeddings"
        meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
        from job_matching.core import sha256_file
        for side in ("cv", "job"):
            self.assertEqual(sha256_file(d / f"{side}_embeddings.npy"),
                             meta["sides"][side]["npy_sha256"])

    def test_feature_matrix_shape_and_names_stable(self):
        m = np.load(self.land.root / "data/processed/matching" /
                    "feature_matrix_match_label_strength.npz", allow_pickle=True)
        self.assertEqual(list(m["X"].shape), self.schema["matrix_shape"])
        self.assertEqual([str(x) for x in m["feature_names"].tolist()],
                         self.schema["numeric_feature_columns"])

    def test_rebuilding_features_reproduces_values(self):
        feats, _ = build_pair_features(self.matches, self.resume, self.job)
        self.assertEqual(list(feats.columns), list(self.features.columns))
        for col in NUMERIC_FEATURE_COLUMNS:
            self.assertTrue(np.allclose(feats[col].to_numpy(dtype=float),
                                        self.features[col].to_numpy(dtype=float),
                                        rtol=0, atol=1e-6), f"{col} 重算不一致")


# ============================================================ G6 可加载性
class G0Loadability(_SynthBase):
    """G6 语义：缓存可读、ID 映射一致、数值 ID 不进特征。"""

    def test_numpy_cache_readable_and_finite(self):
        d = self.land.root / "data/processed/embeddings"
        for side in ("cv", "job"):
            a = np.load(d / f"{side}_embeddings.npy", mmap_mode="r")
            self.assertEqual(a.dtype, np.float32)
            self.assertTrue(np.isfinite(np.asarray(a[:8])).all())

    def test_embedding_rows_match_id_map(self):
        d = self.land.root / "data/processed/embeddings"
        for side, id_col, src in (("cv", "candidate_id", "cv"),
                                  ("job", "job_id", "job")):
            m = json.loads((d / f"{side}_id_map.json").read_text(encoding="utf-8"))
            arr = np.load(d / f"{side}_embeddings.npy")
            self.assertEqual(arr.shape[0], len(m["row_to_id"]))
            src_df = self.land.read(f"data/raw/job-resume-matching/{src}.csv")
            self.assertEqual(set(m["id_to_row"]), set(src_df[id_col].astype(str)))

    def test_split_indices_loadable_and_in_range(self):
        n = len(self.matches)
        for name in ("candidate_cold", "job_cold", "double_cold"):
            for s in ("train", "validation", "test"):
                f = pd.read_csv(self.land.root / "data/splits/matching" / name / f"{s}.csv")
                self.assertTrue(f["pair_index"].between(0, n - 1).all())
                self.assertEqual(f["pair_index"].is_monotonic_increasing, True)

    def test_numeric_ids_not_used_as_semantic_features(self):
        id_like = set(self.c.id_like_columns())
        self.assertEqual(id_like & set(self.schema["numeric_feature_columns"]), set())
        self.assertNotIn("candidate_id", self.schema["numeric_feature_columns"])
        self.assertNotIn("job_id", self.schema["numeric_feature_columns"])

    def test_education_inputs_loadable(self):
        self.assertGreater(len(self.edu_in), 0)
        self.assertTrue(self.edu_in["record_key"].is_unique)
        self.assertIn("slot_education_norm", self.edu_in.columns)

    def test_education_multihot_matrix_loadable(self):
        order = LABEL_ORDER
        mat = np.zeros((len(self.edu_lab), len(order)), dtype=np.int8)
        for i, s in enumerate(self.edu_lab["label_multi_hot"].astype(str)):
            self.assertEqual(len(s), len(order))
            mat[i] = [1 if ch == "1" else 0 for ch in s]
        self.assertEqual(mat.shape[1], 6)
        self.assertTrue(set(np.unique(mat)) <= {0, 1})
        self.assertGreater(int(mat.sum()), 0)

    def test_no_nan_in_key_feature_columns(self):
        cols = ["skill_jaccard", "position_token_overlap", "category_match"]
        self.assertFalse(self.features[cols].isna().any().any())


# ============================================================ 负向测试
class G0NegativeDetection(_SynthBase):
    """负向测试：违规数据必须被门禁**抓住**，否则门禁本身不可信。"""

    def test_policy_rejects_derived_score_column(self):
        cols = list(self.features.columns)
        cols.append("final_score")
        res = check_feature_columns("match_label_strength", cols, raise_on_violation=False)
        self.assertFalse(res.ok, "派生评分列混入特征必须被判违规")

    def test_policy_rejects_id_column_as_feature(self):
        cols = list(self.features.columns)
        res = check_feature_columns("match_label_strength", cols, raise_on_violation=False)
        self.assertFalse(res.ok, "ID 列作为特征列必须被判违规")

    def test_policy_rejects_target_column(self):
        cols = [c for c in self.features.columns if c not in ("candidate_id", "job_id")]
        cols.append("label_strength")
        res = check_feature_columns("match_label_strength", cols, raise_on_violation=False)
        self.assertFalse(res.ok, "目标列混入特征必须被判违规")

    def test_detect_indirect_leakage_flags_reconstructable_score(self):
        rng = np.random.default_rng(7)
        n = 400
        x = rng.random(n)
        # 用单一特征线性重建派生评分 -> 必须被判为间接泄漏
        feats = pd.DataFrame({"leaky_feature": x})
        ref = {"final_score": 3.0 * x + 0.5}
        findings = detect_indirect_leakage(feats, ref, "match_label_strength")
        hard = [f for f in findings if f.get("severity") != "warn"]
        self.assertTrue(hard, "特征可线性重建派生评分必须被检出")

    def test_audit_feature_set_flags_violation(self):
        bad = self.features[NUMERIC_FEATURE_COLUMNS].copy()
        bad["final_score"] = self.targets["final_score"].to_numpy()
        ref = {"final_score": self.targets["final_score"].to_numpy(dtype=np.float64)}
        res = audit_feature_set("match_label_strength", bad, ref, raise_on_violation=False)
        self.assertFalse(res.ok, "特征集审计必须拒绝带派生评分的集合")

    def test_split_builder_rejects_bad_ratio_sum(self):
        with self.assertRaises(ValueError):
            build_single_key_protocol(self.matches, "candidate_id",
                                      {"train": 0.5, "validation": 0.5, "test": 0.5},
                                      1, "probe", 2)

    def test_fixture_tree_has_no_real_pii(self):
        """夹具不得包含真实简历原文特征（手机号 / 邮箱 / 身份证号形态）。"""
        import re
        pats = {
            "mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
            "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
            "idcard": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
        }
        offenders = []
        for p in sorted(self.land.root.rglob("*")):
            if not p.is_file() or p.suffix.lower() in (".npy", ".npz"):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for name, rx in pats.items():
                if rx.search(text):
                    offenders.append(f"{p.relative_to(self.land.root)}:{name}")
        self.assertEqual(offenders, [], f"合成夹具疑似含个人信息: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
