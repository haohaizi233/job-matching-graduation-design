# -*- coding: utf-8 -*-
"""E4：模型训练链路（正反向传播 / 参数更新 / 保存重载 / 稳定性）。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from _util import SYNTH_TEXTS, synth_multi_hot


def _train_tiny_tfidf():
    from job_matching.education.tfidf_model import TfidfEducationModel
    m = TfidfEducationModel()
    m.fit(SYNTH_TEXTS, synth_multi_hot())
    return m


def _train_tiny_charcnn(seed: int = 7):
    import torch
    from job_matching.education.neural_model import CharCNN
    from job_matching.education.tokenizer import CharTokenizer
    from job_matching.education.trainer import seed_everything, train_neural
    tok = CharTokenizer(max_len=16).fit(SYNTH_TEXTS)
    X = torch.from_numpy(tok.transform(SYNTH_TEXTS))
    Y = torch.from_numpy(synth_multi_hot().astype(np.float32))
    seed_everything(seed)  # 权重初始化也必须受种子控制，否则重复训练不可复现
    model = CharCNN(tok.vocab_size)
    info = train_neural(model, X, Y, X, Y, device=torch.device("cpu"),
                        epochs=3, batch_size=4, lr=5e-3, patience=3, seed=seed)
    return model, tok, info


class E4Models(unittest.TestCase):
    def test_tfidf_train_predict(self):
        m = _train_tiny_tfidf()
        proba = m.predict_proba(["本科及以上", "火星文"])
        self.assertEqual(proba.shape, (2, 6))
        self.assertTrue(np.all((proba >= 0) & (proba <= 1)))

    def test_neural_forward_backward_and_param_update(self):
        import torch
        from job_matching.education.neural_model import CharCNN
        torch.manual_seed(3)
        model = CharCNN(vocab_size=20)
        before = {k: v.detach().clone() for k, v in model.state_dict().items()}
        X = torch.randint(0, 20, (8, 10))
        Y = (torch.rand(8, 6) > 0.5).float()
        opt = torch.optim.AdamW(model.parameters(), lr=1e-2)
        loss_val = None
        for _ in range(5):
            opt.zero_grad()
            loss = torch.nn.functional.binary_cross_entropy_with_logits(model(X), Y)
            loss.backward()
            for p in model.parameters():
                if p.grad is not None:
                    self.assertTrue(bool(torch.isfinite(p.grad).all()), "梯度出现非有限值")
            opt.step()
            loss_val = float(loss)
        self.assertTrue(np.isfinite(loss_val))
        changed = any(not torch.equal(before[k], v)
                      for k, v in model.state_dict().items())
        self.assertTrue(changed, "参数未更新")
        self.assertTrue(bool(torch.isfinite(next(model.parameters())).all()))

    def test_neural_training_record_complete(self):
        _m, _t, info = _train_tiny_charcnn()
        for key in ("history", "best_epoch", "seconds", "n_parameters",
                    "nonfinite_grad_steps", "device"):
            self.assertIn(key, info)
        self.assertEqual(info["nonfinite_grad_steps"], 0)
        self.assertGreaterEqual(len(info["history"]), 1)

    def test_model_save_reload_consistent(self):
        m = _train_tiny_tfidf()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "tfidf"
            m.save(out)
            from job_matching.education.tfidf_model import TfidfEducationModel
            m2 = TfidfEducationModel.load(out)
            a = m.predict_proba(SYNTH_TEXTS)
            b = m2.predict_proba(SYNTH_TEXTS)
            self.assertLess(float(np.abs(a - b).max()), 1e-9)

    def test_charcnn_save_reload_consistent(self):
        import torch
        from job_matching.education.neural_model import CharCNN
        from job_matching.education.tokenizer import CharTokenizer
        model, tok, _ = _train_tiny_charcnn()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "model.pt"
            model.save(p)
            model2, _extra = CharCNN.load(p)
            tok.save(Path(td) / "tokenizer.json")
            tok2 = CharTokenizer.load(Path(td) / "tokenizer.json")
            X = tok2.transform(SYNTH_TEXTS)
            with torch.no_grad():
                a = torch.sigmoid(model(torch.from_numpy(X))).numpy()
                b = torch.sigmoid(model2(torch.from_numpy(X))).numpy()
            self.assertLess(float(np.abs(a - b).max()), 1e-6)

    def test_reproducible_small_training(self):
        import torch
        from job_matching.education.trainer import evaluate_proba
        m1, t1, _ = _train_tiny_charcnn(seed=11)
        m2, t2, _ = _train_tiny_charcnn(seed=11)
        a = evaluate_proba(m1, t1.transform(SYNTH_TEXTS), torch.device("cpu"))
        b = evaluate_proba(m2, t2.transform(SYNTH_TEXTS), torch.device("cpu"))
        self.assertLess(float(np.abs(a - b).max()), 1e-5, "同种子重复训练结果不一致")


if __name__ == "__main__":
    unittest.main()
