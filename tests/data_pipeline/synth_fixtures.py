# -*- coding: utf-8 -*-
"""合成数据夹具生成器：为"无真实数据的 Core CI"提供临时数据景观。

为什么需要它（Phase5-2 / Batch 0）：
  `tests/data_pipeline/` 的 G1~G7 门禁大多依赖 data/raw、data/processed 等
  **不入库的真实数据**。在全新 checkout 上直接跑必然大面积失败。
  与其"跳过失败并宣称全部通过"，不如把**门禁逻辑本身**放到一套临时合成数据上验证：
    * 特征构造、泄漏防护、切分互斥、可复现性、可加载性 全部走**生产代码**；
    * 数据是合成的，不含任何真实简历 / 真人信息；
    * 测试跑完即删，绝不写入 data/、models/、reports/ 的历史基线。

硬约束：
  * 只写入调用方给定的临时根目录（默认 tempfile.mkdtemp）；
  * 绝不修改 data/raw/、models/、历史实验结果；
  * 绝不联网、不下载任何数据集；
  * 合成样本不得混入正式 Gold 评估集（本模块产物只在临时目录存在）。

用法：
    from synth_fixtures import SynthLandscape
    with SynthLandscape() as land:
        land.root        # 临时数据根
        land.cfg         # 绑定到该根的 Config
        ...
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from job_matching import config as _config  # noqa: E402
from job_matching.core import sha256_file, write_csv  # noqa: E402
from job_matching.pair_features import (NUMERIC_FEATURE_COLUMNS,  # noqa: E402
                                        build_pair_features)
from job_matching.split_matching import build_all_protocols, save_protocol  # noqa: E402

LABEL_STRENGTH = ["weak_positive", "medium_positive", "strong_positive"]
LABEL_ORDINAL = {"weak_positive": 1, "medium_positive": 2, "strong_positive": 3}
SKILL_POOL = ["java", "javascript", "spring boot", "python", "sql", "c++",
              "docker", "react", "vue", "linux", "mysql", "redis"]
CATEGORY_POOL = ["后端开发", "前端开发", "数据分析", "测试开发"]
TITLE_POOL = ["java开发工程师", "前端开发工程师", "数据分析师", "测试开发工程师"]
LABEL_ORDER = ["博士", "硕士", "本科", "大专", "学历不限", "学历不明"]


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _skills(rng: np.random.Generator, k: int) -> list[str]:
    idx = rng.choice(len(SKILL_POOL), size=k, replace=False)
    return sorted(SKILL_POOL[i] for i in idx)


def _resolve(base: Path, p: str) -> Path:
    """manifest 里的 path 可能是相对项目根，也可能是绝对路径，统一解析。"""
    cand = Path(p)
    if cand.is_absolute() and cand.exists():
        return cand
    for root in (base, ROOT):
        q = root / p
        if q.exists():
            return q
    return base / Path(p).name


class SynthLandscape:
    """一次性合成数据景观（上下文管理器，退出时清理）。"""

    def __init__(self, root: Path | None = None, *,
                 n_candidates: int = 60, n_jobs: int = 40,
                 n_pairs: int = 260, seed: int = 20261028,
                 keep: bool = False):
        self._own_dir = root is None
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="jm_synth_"))
        self.n_candidates = int(n_candidates)
        self.n_jobs = int(n_jobs)
        self.n_pairs = int(n_pairs)
        self.seed = int(seed)
        self.keep = keep
        self._prev_env = os.environ.get("JM_DATA_ROOT")
        self.cfg = None
        self.manifest: dict = {}

    # ---------------- 上下文管理
    def __enter__(self) -> "SynthLandscape":
        self.build()
        return self

    def __exit__(self, *exc) -> bool:
        os.environ.pop("JM_DATA_ROOT", None)
        if self._prev_env is not None:
            os.environ["JM_DATA_ROOT"] = self._prev_env
        _config.reset_config()
        if self._own_dir and not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)
        return False

    # ---------------- 生成
    def build(self) -> dict:
        rng = _rng(self.seed)
        self.root.mkdir(parents=True, exist_ok=True)

        # --- 实体
        cand_ids = [f"C{i:04d}" for i in range(1, self.n_candidates + 1)]
        job_ids = list(range(1, self.n_jobs + 1))

        resume_rows = []
        for cid in cand_ids:
            cat = CATEGORY_POOL[int(rng.integers(0, len(CATEGORY_POOL)))]
            ti = CATEGORY_POOL.index(cat)
            resume_rows.append({
                "candidate_id": cid,
                "skills_canonical_json": json.dumps(_skills(rng, int(rng.integers(2, 6))),
                                                   ensure_ascii=False),
                "target_position_norm": TITLE_POOL[ti],
                "inferred_category": cat,
                "years_experience": float(rng.integers(0, 9)),
            })
        resume_norm = pd.DataFrame(resume_rows)

        job_rows = []
        for jid in job_ids:
            cat = CATEGORY_POOL[int(rng.integers(0, len(CATEGORY_POOL)))]
            ti = CATEGORY_POOL.index(cat)
            job_rows.append({
                "job_id": int(jid),
                "job_title_norm": TITLE_POOL[ti],
                "category": cat,
                "skills_canonical_json": json.dumps(_skills(rng, int(rng.integers(2, 6))),
                                                   ensure_ascii=False),
            })
        job_norm = pd.DataFrame(job_rows)

        # --- 匹配对（合成，无真实简历/JD 原文）
        seen: set[tuple[str, int]] = set()
        pairs: list[tuple[str, int]] = []
        guard = 0
        while len(pairs) < self.n_pairs and guard < self.n_pairs * 40:
            guard += 1
            cid = cand_ids[int(rng.integers(0, len(cand_ids)))]
            jid = int(job_ids[int(rng.integers(0, len(job_ids)))])
            if (cid, jid) in seen:
                continue
            seen.add((cid, jid))
            pairs.append((cid, jid))
        pairs.sort(key=lambda t: (t[0], t[1]))

        labels = [LABEL_STRENGTH[int(rng.integers(0, 3))] for _ in pairs]
        matches = pd.DataFrame({
            "candidate_id": [p[0] for p in pairs],
            "job_id": np.asarray([p[1] for p in pairs], dtype="int64"),
            "label_strength": labels,
            "label_ordinal": [LABEL_ORDINAL[x] for x in labels],
            "final_score": rng.random(len(pairs)).round(6),
            "candidate_rank": np.arange(1, len(pairs) + 1, dtype="int64"),
            "candidate_rank_pct": rng.random(len(pairs)).round(6),
        })

        # --- 落盘：raw / interim
        raw_dir = self.root / "data" / "raw" / "job-resume-matching"
        raw_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"candidate_id": cand_ids,
                      "resume_chars": rng.integers(200, 4000, len(cand_ids))}).to_csv(
            raw_dir / "cv.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
        pd.DataFrame({"job_id": job_ids,
                      "job_title": [TITLE_POOL[CATEGORY_POOL.index(r["category"])]
                                    for r in job_rows],
                      "category": [r["category"] for r in job_rows]}).to_csv(
            raw_dir / "job.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
        matches.to_csv(raw_dir / "matches.csv", index=False, encoding="utf-8-sig",
                       lineterminator="\n")

        interim = self.root / "data" / "interim" / "matching"
        interim.mkdir(parents=True, exist_ok=True)
        write_csv(resume_norm, interim / "resume_normalized.csv")
        write_csv(job_norm, interim / "job_normalized.csv")

        # --- 特征（生产代码构造）
        feats, feat_stats = build_pair_features(matches, resume_norm, job_norm)
        proc = self.root / "data" / "processed" / "matching"
        proc.mkdir(parents=True, exist_ok=True)
        write_csv(feats, proc / "features_pairs.csv")
        write_csv(matches, proc / "targets_pairs.csv")

        schema = {
            "numeric_feature_columns": NUMERIC_FEATURE_COLUMNS,
            "all_feature_columns": [c for c in feats.columns
                                    if c not in ("candidate_id", "job_id")],
            "matrix_shape": [int(len(feats)), int(len(NUMERIC_FEATURE_COLUMNS))],
            "derived_score_columns_used": [],
        }
        (proc / "feature_schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        np.savez(proc / "feature_matrix_match_label_strength.npz",
                 X=feats[NUMERIC_FEATURE_COLUMNS].to_numpy(dtype=np.float32),
                 feature_names=np.asarray(NUMERIC_FEATURE_COLUMNS, dtype=object))

        # --- 向量缓存 + ID 映射
        emb = self.root / "data" / "processed" / "embeddings"
        emb.mkdir(parents=True, exist_ok=True)
        cv_vec = rng.standard_normal((len(cand_ids), 768)).astype(np.float32)
        job_vec = rng.standard_normal((len(job_ids), 768)).astype(np.float32)
        np.save(emb / "cv_embeddings.npy", cv_vec)
        np.save(emb / "job_embeddings.npy", job_vec)
        for side, ids in (("cv", cand_ids), ("job", [str(j) for j in job_ids])):
            idmap = {"id_to_row": {str(v): i for i, v in enumerate(ids)},
                     "row_to_id": {str(i): str(v) for i, v in enumerate(ids)}}
            (emb / f"{side}_id_map.json").write_text(
                json.dumps(idmap, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8", newline="\n")
        meta = {
            "sides": {
                "cv": {"npy_sha256": sha256_file(emb / "cv_embeddings.npy"),
                       "rows": len(cand_ids), "dim": 768},
                "job": {"npy_sha256": sha256_file(emb / "job_embeddings.npy"),
                        "rows": len(job_ids), "dim": 768},
            },
            "limitations": ["合成向量，仅供门禁逻辑自检；冷启动编码来源未评估"],
        }
        (emb / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8", newline="\n")

        # --- 切分（生产代码：build_all_protocols -> save_protocol）
        os.environ["JM_DATA_ROOT"] = str(self.root)
        _config.reset_config()
        self.cfg = _config.get_config()
        build_all_protocols(matches, self.cfg)

        # --- 学历侧
        self._build_education(rng)

        self.manifest = {
            "root": str(self.root),
            "n_candidates": len(cand_ids),
            "n_jobs": len(job_ids),
            "n_pairs": len(pairs),
            "seed": self.seed,
            "synthetic": True,
            "note": "合成夹具：不含任何真实简历 / 真人信息；不得混入 Gold 评估集",
        }
        return self.manifest

    # ---------------- 学历侧
    def _build_education(self, rng: np.random.Generator) -> None:
        proc = self.root / "data" / "processed" / "education"
        proc.mkdir(parents=True, exist_ok=True)
        split_dir = self.root / "data" / "splits" / "education"
        split_dir.mkdir(parents=True, exist_ok=True)

        n = 120
        rows = []
        for i in range(n):
            k = int(rng.integers(1, 4))
            toks = sorted({LABEL_ORDER[j] for j in rng.integers(0, 6, k)})
            mh = "".join("1" if lab in toks else "0" for lab in LABEL_ORDER)
            rows.append({
                "record_key": f"E{i:05d}",
                "user_hash": f"h{i:05d}",
                "user_norm": f"synthetic_slot_{i}",
                "slot_education_norm": "本科及以上",
                "user_len": 20,
                "label_multi_hot": mh,
                "label_tokens_json": json.dumps(toks, ensure_ascii=False),
                "label_status": "ok",
                "unresolved_tokens_json": "[]",
                "label_provenance": "pseudo_online",
            })
        edu_lab = pd.DataFrame(rows)
        # 泄漏防护：特征列只进 inputs，标签表不得携带特征列（G3 语义）
        label_cols = ["record_key", "user_hash", "label_multi_hot", "label_tokens_json",
                      "label_status", "unresolved_tokens_json", "label_provenance"]
        edu_in = edu_lab[["record_key", "user_norm", "slot_education_norm", "user_len"]].copy()
        write_csv(edu_in, proc / "education_inputs.csv")
        write_csv(edu_lab[label_cols], proc / "education_labels.csv")

        # 切分：train/validation/pseudo + gold_holdout + excluded（全部合成）
        gold_n = 40
        gold = edu_lab.iloc[:gold_n].copy()
        gold["label_provenance"] = "human_gold"
        rest = edu_lab.iloc[gold_n:].copy()
        n_val = max(1, len(rest) // 5)
        val = rest.iloc[:n_val].copy()
        train = rest.iloc[n_val:].copy()
        excluded = pd.DataFrame([{
            "record_key": "EX0001", "user_hash": "hex0001",
            "label_provenance": "pseudo_online",
            "split": "excluded_label_conflict",
        }, {
            "record_key": "EX0002", "user_hash": "hex0002",
            "label_provenance": "pseudo_online",
            "split": "excluded_input_duplicate",
        }])
        files = []
        for name, frame in (("train", train), ("validation", val),
                            ("gold_holdout", gold), ("excluded", excluded)):
            write_csv(frame, split_dir / f"{name}.csv")
            files.append({"split": name, "path": str(split_dir / f"{name}.csv"),
                          "rows": int(len(frame)), "sha256": sha256_file(split_dir / f"{name}.csv")})
        manifest = {
            "generated_by": "tests/data_pipeline/synth_fixtures.py",
            "synthetic": True,
            "files": files,
            "excluded": {"by_reason": {"excluded_label_conflict": 1,
                                       "excluded_input_duplicate": 1}},
            "test_set_decision": {"built": False,
                                  "reason": "无可信测试标签，不伪造 test 划分"},
            "splits": {name: {"rows": int(len(f))} for name, f in
                       (("train", train), ("validation", val), ("gold_holdout", gold))},
        }
        (split_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")

    # ---------------- 便捷读取
    def read(self, relpath: str, **kw) -> pd.DataFrame:
        return pd.read_csv(self.root / relpath, encoding="utf-8", low_memory=False, **kw)


def build_in(root: Path, **kw) -> SynthLandscape:
    land = SynthLandscape(root=root, **kw)
    land.build()
    return land
