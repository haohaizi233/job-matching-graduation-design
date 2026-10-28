# -*- coding: utf-8 -*-
"""T4 RankNet 成对偏好（验收项 6、7）。

  6. 偏好对方向正确：a 侧 final_score 严格高于 b 侧，且同一 candidate_id 组内构造。
  7. 同分与近似同分处理正确：|Δscore| < min_score_margin 的对不构造成强偏好。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from _util import synthetic_frame

from job_matching.models.base import TorchScorer
from job_matching.training import trainer as T
from job_matching.training.pair_sampler import build_preference_pairs


def _groups_scores():
    df = synthetic_frame(n_groups=8, per_group=6, seed=5)
    return df["candidate_id"].to_numpy(), df["final_score"].to_numpy()


class T4RankNetPairs(unittest.TestCase):
    def test_preference_direction_and_grouping(self):
        groups, scores = _groups_scores()
        pairs = build_preference_pairs(groups, scores, seed=42,
                                       min_score_margin=0.001)
        self.assertGreater(len(pairs), 0, "没有生成任何偏好对")
        diff = scores[pairs.idx_a] - scores[pairs.idx_b]
        self.assertTrue(np.all(diff >= 0.001 - 1e-12), "存在方向错误的偏好对")
        self.assertTrue(np.array_equal(pairs.score_diff, diff), "score_diff 与索引不一致")
        same_group = groups[pairs.idx_a] == groups[pairs.idx_b]
        self.assertTrue(np.all(same_group), "存在跨候选人的偏好对")

    def test_ties_and_near_ties_dropped(self):
        groups = np.array(["c1"] * 4)
        scores = np.array([0.5, 0.5, 0.5005, 0.9])
        pairs = build_preference_pairs(groups, scores, seed=0, min_score_margin=0.001)
        # 0.5/0.5 完全同分、0.5 与 0.5005 近似同分都不允许构成偏好对
        for a, b in zip(pairs.idx_a, pairs.idx_b):
            self.assertGreaterEqual(scores[a] - scores[b], 0.001 - 1e-12)
            self.assertFalse({int(a), int(b)} <= {0, 1}, "完全同分对被保留")
            self.assertNotIn((int(min(a, b)), int(max(a, b))),
                             [(0, 2), (1, 2)], "近似同分对被保留")
        self.assertGreaterEqual(len(pairs), 2, "显著分差对未生成")
        self.assertGreaterEqual(pairs.stats["near_tie_pairs_dropped"], 1)

    def test_caps_and_empty_group(self):
        rng = np.random.default_rng(0)
        groups = np.array(["big"] * 40 + ["solo"])
        scores = np.concatenate([rng.random(40), [0.5]])
        pairs = build_preference_pairs(groups, scores, seed=1,
                                       max_pairs_per_group=10, max_total_pairs=1000)
        counts = {}
        for g in groups[pairs.idx_a]:
            counts[g] = counts.get(g, 0) + 1
        self.assertLessEqual(counts.get("big", 0), 10, "每组上限未生效")
        self.assertNotIn("solo", counts, "单元素组不应产生偏好对")

        tiny = build_preference_pairs(groups, scores, seed=1, max_total_pairs=5)
        self.assertLessEqual(len(tiny), 5, "总量上限未生效")

    def test_pairwise_loss_pushes_correct_direction(self):
        # loss = softplus(-(sa - sb))：优化后 sa - sb 应增大（a 为偏好更优侧）
        sa = torch.tensor([0.0], requires_grad=True)
        sb = torch.tensor([0.0], requires_grad=True)
        opt = torch.optim.SGD([sa, sb], lr=0.5)
        before = float((sa - sb).detach())
        for _ in range(20):
            opt.zero_grad()
            loss = torch.nn.functional.softplus(-(sa - sb)).mean()
            loss.backward()
            opt.step()
        after = float((sa - sb).detach())
        self.assertGreater(after, before + 1.0, "成对损失未把偏好侧推向更高分")

    def test_train_pairwise_end_to_end(self):
        df = synthetic_frame(n_groups=8, per_group=6, seed=5)
        from job_matching.training.feature_map import FeatureMap
        fm = FeatureMap(task="match_ranking")
        fm.fit(df)
        X = fm.transform(df)
        groups = df["candidate_id"].to_numpy()
        scores = df["final_score"].to_numpy(dtype=np.float64)
        pairs = build_preference_pairs(groups, scores, seed=42)
        device = T.resolve_device(prefer_gpu=True)
        torch.manual_seed(0)
        net = TorchScorer(X.shape[1])
        first = torch.cat([p.detach().flatten() for p in net.parameters()]).clone()

        def val_eval(_m=None):
            return 0.0, {}

        with tempfile.TemporaryDirectory() as td:
            out = T.train_pairwise(net, X, pairs, val_eval,
                                   {"learning_rate": 1e-2, "weight_decay": 0.0,
                                    "pair_batch_size": 32, "epochs": 3,
                                    "early_stopping_patience": 3},
                                   device, Path(td), seed=0)
        self.assertGreaterEqual(out["epochs_run"], 1)
        last = torch.cat([p.detach().flatten().cpu() for p in net.parameters()])
        self.assertFalse(torch.allclose(first, last), "RankNet 参数未更新")
        self.assertTrue(torch.isfinite(last).all(), "RankNet 参数出现 NaN/Inf")


if __name__ == "__main__":
    unittest.main()
