# -*- coding: utf-8 -*-
"""T3 模型训练 / GPU 反向传播 / 保存重载 / 可复现（验收项 4、5、9、15）。

  4. 回归模型（Ridge / HistGradientBoosting）能完成训练和预测。
  5. PyTorch MLP 在 CUDA 上前向、反向传播与参数更新成功（无 GPU 时降级 CPU 并记录）。
  9. 模型保存后重新加载，预测结果一致。
 15. 固定随机种子下重复实验结果一致（成对采样、回归拟合、torch 训练）。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from _util import synthetic_frame

from job_matching.models.base import TorchScorer
from job_matching.models.gradient_boosting import GradientBoostingModel
from job_matching.models.ridge import RidgeModel
from job_matching.training import trainer as T
from job_matching.training.feature_map import FeatureMap
from job_matching.training.pair_sampler import build_preference_pairs


def _xy(seed: int = 11):
    df = synthetic_frame(seed=seed)
    fm = FeatureMap(task="match_ranking")
    fm.fit(df)
    X = fm.transform(df)
    y = df["final_score"].to_numpy(dtype=np.float32)
    return df, fm, X, y


class T3Models(unittest.TestCase):
    # ---- 4. 回归模型训练 + 预测
    def test_regression_models_train_and_predict(self):
        df, fm, X, y = _xy()
        ridge = RidgeModel({"alpha": 1.0})
        ridge.feature_names = list(fm.feature_names_)
        ridge.fit(X, y)
        pred = ridge.predict(X)
        self.assertEqual(pred.shape, (len(df),))
        self.assertTrue(np.isfinite(pred).all())

        gb = GradientBoostingModel({"max_iter": 20, "max_depth": 3, "random_state": 0,
                                    "early_stopping": False})
        gb.feature_names = list(fm.feature_names_)
        gb.fit(X, y)
        pred_gb = gb.predict(X)
        self.assertEqual(pred_gb.shape, (len(df),))
        self.assertTrue(np.isfinite(pred_gb).all())
        self.assertGreater(float(np.std(pred_gb)), 0.0, "GB 预测为常数")

    # ---- 5. MLP GPU（或 CPU）前向 + 反向 + 参数更新
    def test_mlp_forward_backward_updates(self):
        df, fm, X, y = _xy()
        device = T.resolve_device(prefer_gpu=True)
        torch.manual_seed(0)
        net = TorchScorer(X.shape[1])
        before = [p.detach().clone() for p in net.parameters()]

        def val_eval(_model=None):
            return 0.0, {}

        with tempfile.TemporaryDirectory() as td:
            out = T.train_pointwise(net, X, y, val_eval,
                                    {"learning_rate": 1e-2, "weight_decay": 0.0,
                                     "batch_size": 32, "epochs": 3,
                                     "early_stopping_patience": 3},
                                    device, Path(td), seed=0)
            ckpt_saved = Path(out["checkpoint"]).exists()
        self.assertGreaterEqual(out["epochs_run"], 1)
        self.assertTrue(np.isfinite(out["best_value"]) or out["best_value"] == 0.0)
        changed = any(not torch.equal(b, p.detach().cpu())
                      for b, p in zip(before, net.parameters()))
        self.assertTrue(changed, "训练后参数未更新")
        self.assertTrue(ckpt_saved, "checkpoint 未保存")
        if device.type == "cuda":
            dev = next(net.parameters()).device
            self.assertEqual(dev.type, "cuda", "模型参数不在 CUDA 设备上")

    # ---- 9. 保存 / 重载一致
    def test_save_reload_consistency(self):
        df, fm, X, y = _xy()
        ridge = RidgeModel({"alpha": 0.5})
        ridge.feature_names = list(fm.feature_names_)
        ridge.fit(X, y)
        ref = ridge.predict(X)

        torch.manual_seed(0)
        from job_matching.models.mlp import MLPModel
        mlp = MLPModel(X.shape[1], {"hidden": [16, 8], "layernorm": True, "dropout": 0.0},
                       {"epochs": 1}, list(fm.feature_names_))
        ref_mlp = mlp.predict(X)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ridge.save(td / "ridge")
            mlp.save(td / "mlp")
            ridge2 = RidgeModel.load(td / "ridge")
            mlp2 = MLPModel.load(td / "mlp")
            got = ridge2.predict(X)
            got_mlp = mlp2.predict(X)

        self.assertLess(float(np.max(np.abs(ref - got))), 1e-9, "Ridge 重载预测不一致")
        self.assertLess(float(np.max(np.abs(ref_mlp - got_mlp))), 1e-6,
                        "MLP 重载预测不一致")

    # ---- 15. 固定种子重复实验一致
    def test_reproducibility_fixed_seed(self):
        df, fm, X, y = _xy()
        r1 = RidgeModel({"alpha": 1.0}).fit(X, y)
        r2 = RidgeModel({"alpha": 1.0}).fit(X, y)
        self.assertTrue(np.array_equal(r1.predict(X), r2.predict(X)))

        groups = df["candidate_id"].to_numpy()
        scores = df["final_score"].to_numpy()
        p1 = build_preference_pairs(groups, scores, seed=42)
        p2 = build_preference_pairs(groups, scores, seed=42)
        self.assertTrue(np.array_equal(p1.idx_a, p2.idx_a))
        self.assertTrue(np.array_equal(p1.idx_b, p2.idx_b))

        def run_once():
            torch.manual_seed(123)
            net = TorchScorer(X.shape[1])

            def ve(_m=None):
                return 0.0, {}
            with tempfile.TemporaryDirectory() as td:
                T.train_pointwise(net, X, y, ve,
                                  {"learning_rate": 1e-2, "batch_size": 32,
                                   "epochs": 2, "early_stopping_patience": 2},
                                  torch.device("cpu"), Path(td), seed=123)
            return torch.cat([p.detach().flatten() for p in net.parameters()])

        self.assertTrue(torch.allclose(run_once(), run_once(), atol=1e-7),
                        "固定种子下 torch 训练结果不一致")


if __name__ == "__main__":
    unittest.main()
