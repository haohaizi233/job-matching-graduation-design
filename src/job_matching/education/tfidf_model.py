# -*- coding: utf-8 -*-
"""Model A：字符级 TF-IDF + One-vs-Rest Logistic Regression（多标签）。

设计要点：
  * TF-IDF 只在 Train 上 fit（验证/金标准只 transform）；
  * OvR 用 6 个独立 LogisticRegression 实现，等价于 One-vs-Rest，且可精确控制
    样本权重与每标签阈值；
  * 阈值不固定 0.5，只允许在合法 Validation 上选择（见 trainer.select_thresholds）。
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from .labels import LABEL_ORDER


class TfidfEducationModel:
    def __init__(self, ngram_min: int = 1, ngram_max: int = 3, C: float = 1.0,
                 max_iter: int = 1000, min_df: int = 1,
                 class_weight: str | None = None):
        self.params = {"ngram_min": int(ngram_min), "ngram_max": int(ngram_max),
                       "C": float(C), "max_iter": int(max_iter),
                       "min_df": int(min_df), "class_weight": class_weight}
        self.vectorizer = TfidfVectorizer(analyzer="char",
                                          ngram_range=(int(ngram_min), int(ngram_max)),
                                          min_df=int(min_df))
        self.clfs: list[LogisticRegression] = []
        self.thresholds: np.ndarray = np.full(len(LABEL_ORDER), 0.5)
        self.fitted = False

    # ---------------- 训练
    def fit(self, texts, Y: np.ndarray, sample_weight: np.ndarray | None = None) -> "TfidfEducationModel":
        Y = np.asarray(Y).astype(int)
        if Y.shape[1] != len(LABEL_ORDER):
            raise ValueError(f"标签列数 {Y.shape[1]} != {len(LABEL_ORDER)}")
        X = self.vectorizer.fit_transform([str(t) for t in texts])
        self.clfs = []
        for i in range(Y.shape[1]):
            clf = LogisticRegression(C=self.params["C"], max_iter=self.params["max_iter"],
                                     class_weight=self.params["class_weight"],
                                     solver="liblinear")
            y = Y[:, i]
            if len(set(y.tolist())) < 2:
                # 单类标签无法拟合 LR：退化为常数概率模型（占位，保持接口一致）
                self.clfs.append(("constant", None, float(y[0])))
                continue
            if sample_weight is not None:
                clf.fit(X, y, sample_weight=np.asarray(sample_weight, dtype=np.float64))
            else:
                clf.fit(X, y)
            self.clfs.append(("lr", clf, None))
        self.fitted = True
        return self

    # ---------------- 推理
    def predict_proba(self, texts) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("模型尚未训练")
        X = self.vectorizer.transform([str(t) for t in texts])
        out = np.zeros((X.shape[0], len(LABEL_ORDER)), dtype=np.float64)
        for i, item in enumerate(self.clfs):
            kind, clf, const = item
            if kind == "constant":
                out[:, i] = float(const)
            else:
                out[:, i] = clf.predict_proba(X)[:, 1]
        return out

    def predict(self, texts, thresholds: np.ndarray | None = None) -> np.ndarray:
        th = self.thresholds if thresholds is None else np.asarray(thresholds, dtype=np.float64)
        proba = self.predict_proba(texts)
        return (proba >= th.reshape(1, -1)).astype(np.int8)

    # ---------------- 持久化
    def save(self, out_dir: Path) -> dict:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / "model.pkl"
        with open(model_path, "wb") as f:
            pickle.dump({"params": self.params, "vectorizer": self.vectorizer,
                         "clfs": self.clfs,
                         "thresholds": self.thresholds.tolist(),
                         "label_order": list(LABEL_ORDER)}, f)
        return {"model_file": str(model_path.name), "bytes": model_path.stat().st_size}

    @classmethod
    def load(cls, out_dir: Path) -> "TfidfEducationModel":
        with open(Path(out_dir) / "model.pkl", "rb") as f:
            d = pickle.load(f)
        obj = cls(**d["params"])
        obj.vectorizer = d["vectorizer"]
        obj.clfs = d["clfs"]
        obj.thresholds = np.asarray(d["thresholds"], dtype=np.float64)
        obj.fitted = True
        return obj

    # ---------------- 说明
    def describe(self) -> dict:
        n_feat = (len(self.vectorizer.vocabulary_) if getattr(self.vectorizer, "vocabulary_", None)
                  else 0)
        n_par = sum(int(np.prod(c.coef_.shape)) + int(np.prod(c.intercept_.shape))
                    for kind, c, _ in self.clfs if kind == "lr")
        return {"model_type": "tfidf_char_ovr_logreg", **self.params,
                "n_tfidf_features": int(n_feat), "n_parameters": int(n_par),
                "thresholds": {LABEL_ORDER[i]: float(self.thresholds[i])
                               for i in range(len(LABEL_ORDER))}}
