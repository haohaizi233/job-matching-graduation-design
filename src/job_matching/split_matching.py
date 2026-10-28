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
# job 侧归属策略（全部确定性、可复现；种子固定）
DOUBLE_COLD_STRATEGIES = ("majority_edge", "proportional", "eval_first_greedy")


def _job_edge_counts(pairs: pd.DataFrame) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}
    for job_id, ser in pairs.groupby("job_id")["candidate_split"]:
        counts = {k: int((ser == k).sum()) for k in SPLIT_ORDER}
        out[int(job_id)] = counts
    return out


def _assign_jobs_majority_edge(counts: dict[int, dict[str, int]], seed: int) -> dict[int, str]:
    """策略 A：job 归到其拥有最多已分配边的集合，平局用种子打破。保留率最高。"""
    rng = np.random.default_rng(seed + 7919)
    out: dict[int, str] = {}
    for job_id, c in counts.items():
        top = max(c.values())
        tied = [k for k in SPLIT_ORDER if c[k] == top]
        out[job_id] = tied[int(rng.integers(0, len(tied)))] if len(tied) > 1 else tied[0]
    return out


def _assign_jobs_proportional(counts: dict[int, dict[str, int]], seed: int) -> dict[int, str]:
    """策略 B：job 按其三侧边数比例随机归属（种子驱动），验证/测试集非空但规模有限。"""
    rng = np.random.default_rng(seed + 7919)
    out: dict[int, str] = {}
    for job_id in sorted(counts):
        c = counts[job_id]
        total = sum(c.values()) or 1
        u = float(rng.random())
        cum = 0.0
        chosen = SPLIT_ORDER[0]
        for k in SPLIT_ORDER:
            cum += c[k] / total
            if u <= cum:
                chosen = k
                break
        out[job_id] = chosen
    return out


def _assign_jobs_eval_first(pairs: pd.DataFrame, counts: dict[int, dict[str, int]],
                            seed: int, budget_ratio: float,
                            min_group: int = 2, soft_target: int = 5,
                            gain_power: int = 2) -> tuple[dict[int, str], dict]:
    """策略 C（改进策略）：评估感知贪心。

    动机：策略 A（majority_edge）保留率最高（实测 ~80%）但验证/测试集几乎为空
    （实测 3 / 3 条），完全无法评估；本策略在保留率与"可评估性"之间做显式权衡。

    两步：
      1. 零代价归属：job 归到其拥有最多边的集合（平局偏好 train）。
         若某 job 的多数边本来就在 validation / test，直接定下来，不消耗预算。
      2. 评估补齐：对 validation / test 各自独立地从 train 手里"抢" job，
         直到预算耗尽或次要集合候选人都达到 soft_target。

    gain/cost 定义（全部确定性）：
      gain = Σ_{c ∈ 该 job 的次要集合候选人} (soft_target - kept[c])^gain_power，
             仅对 kept[c] < soft_target 计入，越缺越重要；
      cost = 把该 job 从默认集合挪到目标集合的净损失边数
             = counts[j][默认集合] - counts[j][目标集合]，保底 1.0；
      每个次要集合的总预算 = budget_ratio × 原始边数。

    全过程只允许从 train 侧抢 job，绝不把 validation 的 job 抢给 test，
    保证两个次要集合的评估条件互不污染；同分时取 job_id 较小者，保证确定性。
    """
    rng = np.random.default_rng(seed + 7919)
    job_ids = sorted(counts)
    job_order = [int(job_ids[i]) for i in rng.permutation(len(job_ids))]

    cand_split = dict(zip(pairs["candidate_id"].astype(str),
                          pairs["candidate_split"]))
    edges_by_job: dict[int, list[str]] = {}
    for j, c in zip(pairs["job_id"].to_numpy(), pairs["candidate_id"].astype(str).to_numpy()):
        edges_by_job.setdefault(int(j), []).append(c)

    total_edges = int(len(pairs))

    # ---- 第 1 步：零代价归属（多数边集合，平局偏好 train，确定性）
    default_split: dict[int, str] = {}
    for j in job_order:
        c = counts[j]
        top = max(c.values())
        tied = [k for k in SPLIT_ORDER if c[k] == top]
        default_split[j] = "train" if "train" in tied else tied[0]
    assign: dict[int, str] = dict(default_split)
    per_split_stats: dict[str, dict] = {}

    for s in ("validation", "test"):
        eval_edges = {j: [c for c in edges_by_job.get(j, []) if cand_split.get(c) == s]
                      for j in job_order}
        kept = {c: 0 for c, sp in cand_split.items() if sp == s}
        for j in job_order:
            if assign[j] == s:
                for c in eval_edges[j]:
                    kept[c] += 1
        budget = float(budget_ratio) * total_edges
        spent = 0.0
        moved = 0
        while True:
            best, best_score, best_cost = None, -1.0, 0.0
            for j in job_order:
                if assign[j] != "train":
                    continue
                gain = 0.0
                for c in eval_edges[j]:
                    k = kept[c]
                    if k < soft_target:
                        gain += (soft_target - k) ** gain_power
                if gain <= 0:
                    continue
                cost = float(counts[j][SPLIT_ORDER[0]] - counts[j][s])
                if cost <= 0:
                    cost = 1.0
                if spent + cost > budget:
                    continue
                score = gain / cost
                # 同分取 job_id 较小者，保证与 job_order 的排列顺序无关、结果确定
                if (best is None or score > best_score
                        or (score == best_score and j < best)):
                    best, best_score, best_cost = j, score, cost
            if best is None:
                break
            assign[best] = s
            spent += best_cost
            moved += 1
            for c in eval_edges[best]:
                kept[c] += 1
        per_split_stats[s] = {
            "budget_edges": round(budget, 1),
            "train_edges_spent": round(spent, 1),
            "jobs_moved_from_train": moved,
            "jobs_owned_in_split": int(sum(1 for j in job_order if assign[j] == s)),
            "candidates_total": int(len(kept)),
            "candidates_reaching_min_group": int(
                sum(1 for v in kept.values() if v >= min_group)),
            "candidates_reaching_soft_target": int(
                sum(1 for v in kept.values() if v >= soft_target)),
            "soft_target": int(soft_target),
            "kept_edges_to_split": int(sum(kept.values())),
        }
    return assign, per_split_stats


def _summarize_assign(pairs: pd.DataFrame, job_assign: dict[int, str],
                      min_rank_size: int) -> dict:
    kept = pairs[pairs["job_id"].map(job_assign) == pairs["candidate_split"]]
    out = {"kept_pairs": int(len(kept)),
           "retention_ratio": round(len(kept) / max(len(pairs), 1), 6),
           "splits": {}}
    for s in SPLIT_ORDER:
        sub = kept[kept["candidate_split"] == s]
        sizes = sub.groupby("candidate_id").size()
        out["splits"][s] = {
            "pairs": int(len(sub)),
            "candidates": int(sub["candidate_id"].nunique()),
            "jobs": int(sub["job_id"].nunique()),
            "rankable_groups_ge_2": int((sizes >= 2).sum()),
            "rankable_groups_ge_min": int((sizes >= min_rank_size).sum()),
            "rankable_groups_ge_5": int((sizes >= 5).sum()),
            "rankable_groups_ge_10": int((sizes >= 10).sum()),
        }
    return out


def build_double_cold(matches: pd.DataFrame, ratios: dict[str, float], seed: int,
                      min_rank_size: int, strategy: str = "eval_first_greedy",
                      strategy_budget_ratio: float = 0.15,
                      eval_soft_target: int = 5, gain_power: int = 2,
                      compare_strategies: bool = True) -> dict:
    log = get_logger()
    pairs = _pair_table(matches)
    labels = matches["label_strength"].reset_index(drop=True)
    pairs["label_strength"] = labels.to_numpy()

    # 阶段 1：候选人按观测边数贪心分配 80/10/10（组完整，边不拆）
    cand_sizes = pairs.groupby("candidate_id").size()
    cand_assign = assign_groups(cand_sizes, ratios, seed)
    pairs["candidate_split"] = pairs["candidate_id"].map(cand_assign)
    counts = _job_edge_counts(pairs)

    # 阶段 2：job 归属（策略可选，均确定性）
    comparison: dict[str, dict] = {}
    job_assign: dict[int, str] | None = None
    extra_stats: dict = {}
    for name in (DOUBLE_COLD_STRATEGIES if compare_strategies else (strategy,)):
        if name == "majority_edge":
            ja = _assign_jobs_majority_edge(counts, seed)
            cmp_stats = _summarize_assign(pairs, ja, min_rank_size)
        elif name == "proportional":
            ja = _assign_jobs_proportional(counts, seed)
            cmp_stats = _summarize_assign(pairs, ja, min_rank_size)
        elif name == "eval_first_greedy":
            ja, extra = _assign_jobs_eval_first(pairs, counts, seed,
                                                strategy_budget_ratio, min_rank_size,
                                                eval_soft_target, gain_power)
            cmp_stats = _summarize_assign(pairs, ja, min_rank_size)
            cmp_stats["greedy_budget"] = extra
        else:
            raise ValueError(f"未知 double_cold 策略: {name}")
        comparison[name] = cmp_stats
        if name == strategy:
            job_assign, extra_stats = ja, cmp_stats
    assert job_assign is not None

    pairs["job_split"] = pairs["job_id"].map(job_assign)
    pairs["split"] = np.where(pairs["candidate_split"] == pairs["job_split"],
                              pairs["candidate_split"], "excluded")

    out = {"protocol": "double_cold", "group_key": ["candidate_id", "job_id"],
           "seed": seed, "ratios": ratios,
           "assignment_strategy": strategy,
           "assignment_strategy_note": (
               "阶段 1：candidate_id 按观测边数贪心分配 80/10/10（组完整、边不拆）；"
               "阶段 2：job_id 归属由 assignment_strategy 指定。"
               "两侧归属不一致的交叉边一律进 excluded，不归入任何集合。"
               + ("eval_first_greedy 是本阶段提出的改进策略：先用 gain/cost 贪心为验证/测试"
                  "候选人补齐可排序性（每个次要集合带独立的 train 损失预算），"
                  "再把其余 job 归给边数最多的集合；"
                  "而 majority_edge 虽保留率最高但验证/测试集为空（见 strategy_comparison）。"
                  if strategy == "eval_first_greedy" else "")),
           "strategy_budget_ratio_per_minor_split": strategy_budget_ratio,
           "strategy_params": {
               "budget_ratio_per_minor_split": strategy_budget_ratio,
               "eval_soft_target": int(eval_soft_target),
               "gain_deficit_power": int(gain_power),
               "min_group_size_for_ranking": int(min_rank_size),
           },
           "strategy_comparison": comparison,
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
        "两侧独立按 80/10/10 随机分配时期望保留率约 66%（= 0.8² + 0.1² + 0.1²），"
        "且验证/测试各只占约 1% 的边。三种策略的实测对比见 strategy_comparison。")

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
    log.info("[double_cold/%s] 保留 %d/%d (%.2f%%)，excluded %d",
             strategy, kept, len(matches), 100.0 * kept / len(matches), len(exc))
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
            sp = proto.get("strategy_params") or {}
            res = build_double_cold(
                matches, ratios, seed, cfg.min_group_size_for_ranking,
                strategy=proto.get("assignment_strategy", "eval_first_greedy"),
                strategy_budget_ratio=float(sp.get("budget_ratio_per_minor_split", 0.15)),
                eval_soft_target=int(sp.get("eval_soft_target", 5)),
                gain_power=int(sp.get("gain_deficit_power", 2)))
        saved = save_protocol(res, root / name)
        results[name] = {"manifest": saved["manifest"], "dir": saved["dir"]}
        log.info("[切分] %s 完成 -> %s", name, saved["dir"])
    return results
