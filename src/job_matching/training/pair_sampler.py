# -*- coding: utf-8 -*-
"""RankNet 成对偏好样本构造（第四阶段 4.1 / 七、成对样本构造）。

规则（全部确定性、可复现）：
  * 只在 Train 内构造；组 = candidate_id（同一候选人的已观测岗位）；
  * 偏好方向来自代理排序标签 final_score（原评分系统派生，不是用户真实偏好）：
      job_A > job_B  <=>  final_score_A - final_score_B >= min_score_margin
  * |Δfinal_score| < min_score_margin 的近似同分对直接丢弃，不构造强偏好；
  * 每组全配对后按上限 max_pairs_per_group 用固定种子无放回抽样，
    防止单个高频候选人主导训练；总量再受 max_total_pairs 截断；
  * 不跨候选人组构造偏好对；不把未观测组合当负例。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PreferencePairs:
    idx_a: np.ndarray            # 偏好更优一侧（final_score 更高）的行号
    idx_b: np.ndarray            # 偏好更弱一侧的行号
    score_diff: np.ndarray       # final_score_a - final_score_b（>= min_score_margin）
    group_id: np.ndarray         # 每对所属 candidate_id
    stats: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.idx_a.size)

    def batches(self, batch_size: int, rng: np.random.Generator):
        n = len(self)
        order = rng.permutation(n)
        for s in range(0, n, batch_size):
            take = order[s:s + batch_size]
            yield self.idx_a[take], self.idx_b[take], self.score_diff[take]


def build_preference_pairs(group_ids, scores, seed: int,
                           min_score_margin: float = 0.001,
                           max_pairs_per_group: int = 64,
                           max_total_pairs: int = 400000) -> PreferencePairs:
    groups = np.asarray(group_ids)
    s = np.asarray(scores, dtype=np.float64)
    if groups.shape[0] != s.shape[0]:
        raise ValueError("group_ids 与 scores 长度不一致")
    if np.isnan(s).any():
        raise ValueError("scores 含 NaN")

    rng = np.random.default_rng(seed)
    order_groups = sorted(set(groups.tolist()))       # 确定性处理顺序
    pos = {g: i for i, g in enumerate(order_groups)}

    a_list: list[np.ndarray] = []
    b_list: list[np.ndarray] = []
    d_list: list[np.ndarray] = []
    g_list: list[np.ndarray] = []
    per_group_pairs: list[int] = []
    dropped_ties = 0
    truncated = False

    for g in order_groups:
        idx = np.where(groups == g)[0]
        n = idx.size
        if n < 2:
            continue
        # 组内按 final_score 降序（同分保持原始行序，稳定）
        local = idx[np.lexsort((idx, -s[idx]))]
        sv = s[local]
        diff = sv[:, None] - sv[None, :]
        iu, ju = np.where(np.triu(diff >= min_score_margin, k=1))
        dropped_ties += int(np.triu((np.abs(diff) < min_score_margin) & (diff != 0), k=1).sum())
        if iu.size == 0:
            continue
        pairs_a = local[iu]
        pairs_b = local[ju]
        pairs_d = diff[iu, ju]
        if pairs_a.size > max_pairs_per_group:
            pick = rng.choice(pairs_a.size, size=max_pairs_per_group, replace=False)
            pick.sort()
            pairs_a, pairs_b, pairs_d = pairs_a[pick], pairs_b[pick], pairs_d[pick]
        if max_total_pairs and sum(per_group_pairs) + pairs_a.size > max_total_pairs:
            remain = max_total_pairs - sum(per_group_pairs)
            if remain <= 0:
                truncated = True
                break
            pairs_a, pairs_b, pairs_d = pairs_a[:remain], pairs_b[:remain], pairs_d[:remain]
            truncated = True
        a_list.append(pairs_a)
        b_list.append(pairs_b)
        d_list.append(pairs_d)
        g_list.append(np.full(pairs_a.size, pos[g], dtype=np.int32))
        per_group_pairs.append(int(pairs_a.size))

    if not a_list:
        return PreferencePairs(idx_a=np.zeros(0, np.int64), idx_b=np.zeros(0, np.int64),
                               score_diff=np.zeros(0), group_id=np.zeros(0, np.int32),
                               stats={"pairs": 0, "note": "没有满足最小分差的偏好对"})

    idx_a = np.concatenate(a_list).astype(np.int64)
    idx_b = np.concatenate(b_list).astype(np.int64)
    diff_arr = np.concatenate(d_list).astype(np.float64)
    gid = np.concatenate(g_list)

    # ---- 完整性自检：偏好方向必须正确（A 的分数显著高于 B）
    if not bool(np.all(diff_arr >= min_score_margin - 1e-12)):
        raise AssertionError("偏好对方向错误：存在 final_score_a - final_score_b < min_score_margin")
    if not bool(np.all(s[idx_a] - s[idx_b] >= min_score_margin - 1e-12)):
        raise AssertionError("偏好对索引与分数不一致")

    counts = np.asarray(per_group_pairs, dtype=np.int64)
    stats = {
        "strategy": "group_all_pairs_then_cap",
        "seed": int(seed),
        "min_score_margin": float(min_score_margin),
        "max_pairs_per_group": int(max_pairs_per_group),
        "max_total_pairs": int(max_total_pairs),
        "groups_total": int(len(order_groups)),
        "groups_with_pairs": int(len(per_group_pairs)),
        "groups_skipped_size_1": int(sum(1 for g in order_groups if (groups == g).sum() < 2)),
        "near_tie_pairs_dropped": int(dropped_ties),
        "pairs_total": int(idx_a.size),
        "pairs_truncated_by_total_cap": bool(truncated),
        "pairs_per_group": {
            "min": int(counts.min()) if counts.size else 0,
            "median": float(np.median(counts)) if counts.size else 0.0,
            "mean": round(float(counts.mean()), 3) if counts.size else 0.0,
            "max": int(counts.max()) if counts.size else 0,
        },
        "max_group_share": round(float(counts.max() / idx_a.size), 6) if idx_a.size else 0.0,
        "score_diff": {
            "min": round(float(diff_arr.min()), 6),
            "median": round(float(np.median(diff_arr)), 6),
            "mean": round(float(diff_arr.mean()), 6),
            "max": round(float(diff_arr.max()), 6),
        },
        "direction_check": "passed（全部偏好对满足 final_score_a - final_score_b >= min_score_margin）",
    }
    return PreferencePairs(idx_a=idx_a, idx_b=idx_b, score_diff=diff_arr, group_id=gid,
                           stats=stats)
