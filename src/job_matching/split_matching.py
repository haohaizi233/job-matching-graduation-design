# -*- coding: utf-8 -*-
"""人岗匹配数据的可信切分（第三阶段 3.2.1，验收项 P3-06/07/08）。

三套协议：
  A. Candidate Cold-start  —— candidate_id 分组互斥
  B. Job Cold-start        —— job_id 分组互斥
  C. Double Cold-start     —— candidate_id 与 job_id 双侧互斥，交叉边进 excluded

全部随机过程由 configs/data_pipeline.yaml 的固定种子驱动，可重复执行。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from .core import (PIPELINE_VERSION, get_logger, jdump, rel, sha256_file)

SPLIT_ORDER = ["train", "validation", "test"]


# ------------------------------------------------------------------ 组分配
def assign_groups(group_sizes: pd.Series, ratios: dict[str, float],
                  seed: int) -> dict[str, str]:
    """把完整分组分配到 train/validation/test，保证组内所有记录同集合。

    策略：种子洗牌 + 相对缺口贪心。确定性：相同输入与种子必得相同结果。
    """
    total = float(group_sizes.sum())
    if total <= 0:
        raise ValueError("group_sizes 总和必须为正")
    keys = SPLIT_ORDER
    targets = {k: ratios[k] * total for k in keys}
    if abs(sum(targets.values()) - total) > 1e-6:
        raise ValueError(f"划分比例之和必须为 1，实际 {sum(ratios.values())}")

    ids = list(group_sizes.index)
    rng = np.random.default_rng(seed)
    order = [ids[i] for i in rng.permutation(len(ids))]

    current = {k: 0.0 for k in keys}
    assign: dict[str, str] = {}
    sizes = group_sizes.to_dict()
    for g in order:
        best_key, best_val = keys[0], -np.inf
        for idx, k in enumerate(keys):
            t = targets[k]
            val = ((t - current[k]) / t) if t > 0 else 0.0
            if val > best_val:
                best_key, best_val = k, val
        assign[g] = best_key
        current[best_key] += float(sizes[g])
    return assign


def _pair_table(matches: pd.DataFrame) -> pd.DataFrame:
    """规范 pair 索引：按 matches.csv 原始行序编号，可精确定位回原始数据。"""
    t = matches[["candidate_id", "job_id"]].copy()
    t["candidate_id"] = t["candidate_id"].astype(str)
    t["job_id"] = t["job_id"].astype("int64")
    t.insert(0, "pair_index", np.arange(len(t), dtype=np.int64))
    return t


def _label_stats(sub: pd.DataFrame, labels: pd.Series) -> dict:
    if len(sub) == 0:
        return {"pairs": 0}
    vc = labels.loc[sub.index].value_counts().to_dict()
    return {
        "pairs": int(len(sub)),
        "candidates": int(sub["candidate_id"].nunique()),
        "jobs": int(sub["job_id"].nunique()),
        "label_distribution": {str(k): int(v) for k, v in vc.items()},
    }


def _rankable_groups(sub: pd.DataFrame, key: str, min_size: int) -> dict:
    sizes = sub.groupby(key).size()
    return {
        "groups_total": int(len(sizes)),
        "groups_size_ge_2": int((sizes >= 2).sum()),
        "groups_size_ge_min": int((sizes >= min_size).sum()),
        "groups_size_eq_1": int((sizes == 1).sum()),
        "size_min": int(sizes.min()) if len(sizes) else 0,
        "size_median": float(sizes.median()) if len(sizes) else 0.0,
        "size_max": int(sizes.max()) if len(sizes) else 0,
    }


# ------------------------------------------------------------------ 协议 A/B
def build_single_key_protocol(matches: pd.DataFrame, group_key: str,
                              ratios: dict[str, float], seed: int,
                              protocol_name: str, min_rank_size: int) -> dict:
    pairs = _pair_table(matches)
    labels = matches["label_strength"].reset_index(drop=True)
    sizes = pairs.groupby(group_key).size()
    assign = assign_groups(sizes, ratios, seed)
    pairs["split"] = pairs[group_key].map(assign)
    pairs["label_strength"] = labels.to_numpy()

    out = {"protocol": protocol_name, "group_key": group_key, "seed": seed,
           "ratios": ratios, "splits": {}, "excluded": {"pairs": 0}}
    for s in SPLIT_ORDER:
        sub = pairs[pairs["split"] == s]
        st = _label_stats(sub, labels)
        st.update(_rankable_groups(sub, group_key, min_rank_size))
        out["splits"][s] = st

    # 互斥性检查
    sets = {s: set(pairs.loc[pairs["split"] == s, group_key]) for s in SPLIT_ORDER}
    c_sets = {s: set(pairs.loc[pairs["split"] == s, "candidate_id"]) for s in SPLIT_ORDER}
    j_sets = {s: set(pairs.loc[pairs["split"] == s, "job_id"]) for s in SPLIT_ORDER}
    p_sets = {s: set(map(tuple, pairs.loc[pairs["split"] == s, ["candidate_id", "job_id"]]
                         .to_numpy())) for s in SPLIT_ORDER}

    def pairwise(a):
        return {f"{x}&{y}": len(a[x] & a[y])
                for i, x in enumerate(SPLIT_ORDER) for y in SPLIT_ORDER[i + 1:]}

    out["overlap_check"] = {
        "candidate_overlap": pairwise(c_sets),
        "job_overlap": pairwise(j_sets),
        "pair_overlap": pairwise(p_sets),
        "group_key_overlap": pairwise(sets),
    }
    out["coverage"] = {
        "raw_pairs": int(len(matches)),
        "assigned_pairs": int(len(pairs)),
        "coverage_ratio": 1.0,
    }
    out["_pairs_frame"] = pairs
    return out


# ------------------------------------------------------------------ 协议 C
def build_double_cold(matches: pd.DataFrame, ratios: dict[str, float], seed: int,
                      min_rank_size: int) -> dict:
    log = get_logger()
    pairs = _pair_table(matches)
    labels = matches["label_strength"].reset_index(drop=True)
    pairs["label_strength"] = labels.to_numpy()

    # 阶段 1：候选人按观测边数贪心分配 80/10/10
    cand_sizes = pairs.groupby("candidate_id").size()
    cand_assign = assign_groups(cand_sizes, ratios, seed)
    pairs["candidate_split"] = pairs["candidate_id"].map(cand_assign)

    # 阶段 2：岗位分配到其拥有最多已分配边的那个集合，平局用种子打破
    rng = np.random.default_rng(seed + 7919)
    job_assign: dict[int, str] = {}
    grouped = pairs.groupby("job_id")["candidate_split"]
    for job_id, ser in grouped:
        counts = {k: int((ser == k).sum()) for k in SPLIT_ORDER}
        top = max(counts.values())
        tied = [k for k in SPLIT_ORDER if counts[k] == top]
        job_assign[int(job_id)] = tied[int(rng.integers(0, len(tied)))] if len(tied) > 1 else tied[0]
    pairs["job_split"] = pairs["job_id"].map(job_assign)
    pairs["split"] = np.where(pairs["candidate_split"] == pairs["job_split"],
                              pairs["candidate_split"], "excluded")

    out = {"protocol": "double_cold", "group_key": ["candidate_id", "job_id"],
           "seed": seed, "ratios": ratios,
           "assignment_strategy": "majority_edge",
           "assignment_strategy_note": (
               "阶段 1：candidate_id 按观测边数贪心分配 80/10/10；"
               "阶段 2：job_id 分配到其拥有最多已分配边的集合，平局由固定种子打破。"
               "两侧归属不一致的交叉边一律进 excluded，不归入任何集合。"),
           "splits": {}, "excluded": {}}

    for s in SPLIT_ORDER:
        sub = pairs[pairs["split"] == s]
        st = _label_stats(sub, labels)
        st.update(_rankable_groups(sub, "candidate_id", min_rank_size))
        st["jobs"] = int(sub["job_id"].nunique())
        st["job_rankable_groups"] = _rankable_groups(sub, "job_id", min_rank_size)
        out["splits"][s] = st

    exc = pairs[pairs["split"] == "excluded"]
    out["excluded"] = {
        "pairs": int(len(exc)),
        "candidates": int(exc["candidate_id"].nunique()),
        "jobs": int(exc["job_id"].nunique()),
        "label_distribution": exc["label_strength"].value_counts().to_dict(),
    }

    kept = len(pairs) - len(exc)
    out["coverage"] = {
        "raw_pairs": int(len(matches)),
        "assigned_pairs": int(kept),
        "excluded_pairs": int(len(exc)),
        "retention_ratio": round(kept / len(matches), 6),
        "drop_ratio": round(len(exc) / len(matches), 6),
    }

    # 对照：若两侧独立随机 80/10/10，理论保留率 = 0.8^2 + 0.1^2 + 0.1^2
    naive_expected = sum(r ** 2 for r in ratios.values())
    out["naive_independent_expected_retention"] = round(naive_expected, 6)
    out["naive_independent_note"] = (
        "两侧独立按 80/10/10 分配时期望保留率仅 66%，会造成 validation/test 各约 1% 边、"
        "组内可排序样本严重不足；本实现改用 majority_edge 策略在保持双侧互斥的前提下提升保留率。")

    # 互斥性检查
    c_sets = {s: set(pairs.loc[pairs["split"] == s, "candidate_id"]) for s in SPLIT_ORDER}
    j_sets = {s: set(pairs.loc[pairs["split"] == s, "job_id"]) for s in SPLIT_ORDER}
    p_sets = {s: set(map(tuple, pairs.loc[pairs["split"] == s, ["candidate_id", "job_id"]]
                         .to_numpy())) for s in SPLIT_ORDER}

    def pairwise(a):
        return {f"{x}&{y}": len(a[x] & a[y])
                for i, x in enumerate(SPLIT_ORDER) for y in SPLIT_ORDER[i + 1:]}

    out["overlap_check"] = {
        "candidate_overlap": pairwise(c_sets),
        "job_overlap": pairwise(j_sets),
        "pair_overlap": pairwise(p_sets),
        "excluded_kept_in_any_split": 0,
    }
    out["_pairs_frame"] = pairs
    log.info("[double_cold] 保留 %d/%d (%.2f%%)，excluded %d",
             kept, len(matches), 100.0 * kept / len(matches), len(exc))
    return out


# ------------------------------------------------------------------ 落盘
def save_protocol(result: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs: pd.DataFrame = result.pop("_pairs_frame")
    files = []
    for s in SPLIT_ORDER + ["excluded"]:
        sub = pairs[pairs["split"] == s][["pair_index", "candidate_id", "job_id"]]
        sub = sub.sort_values("pair_index", kind="mergesort").reset_index(drop=True)
        p = out_dir / f"{s}.csv"
        sub.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")
        files.append({"split": s, "path": rel(p), "rows": int(len(sub)),
                      "sha256": sha256_file(p)})

    manifest = {k: v for k, v in result.items()}
    manifest.update({
        "generated_by": "src/job_matching/split_matching.py",
        "pipeline_version": PIPELINE_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": files,
    })
    jdump(manifest, out_dir / "manifest.json")
    files.append({"split": "manifest", "path": rel(out_dir / "manifest.json"),
                  "sha256": sha256_file(out_dir / "manifest.json")})
    return {"dir": rel(out_dir), "files": files, "manifest": manifest}


def build_all_protocols(matches: pd.DataFrame, cfg) -> dict:
    log = get_logger()
    results = {}
    root = cfg.out("splits_matching")

    for name in ("candidate_cold", "job_cold", "double_cold"):
        proto = cfg.protocol(name)
        seed = cfg.seed(proto["seed_key"])
        ratios = {k: float(v) for k, v in proto["ratios"].items()}
        if name == "candidate_cold":
            res = build_single_key_protocol(matches, "candidate_id", ratios, seed,
                                            name, cfg.min_group_size_for_ranking)
        elif name == "job_cold":
            res = build_single_key_protocol(matches, "job_id", ratios, seed,
                                            name, cfg.min_group_size_for_ranking)
        else:
            res = build_double_cold(matches, ratios, seed, cfg.min_group_size_for_ranking)
        saved = save_protocol(res, root / name)
        results[name] = {"manifest": saved["manifest"], "dir": saved["dir"]}
        log.info("[切分] %s 完成 -> %s", name, saved["dir"])
    return results
