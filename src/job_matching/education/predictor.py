# -*- coding: utf-8 -*-
"""学历规范化推理接口（第四阶段 4.2 第六部分）。

约束：
  * 只依赖模型文件 + 输入文本；**绝不读取任何监督目标字段**（label_* / assistant /
    人工正确结果 等）；
  * 输入做 NFKC 规范化与空值处理；未知表达不崩溃，可回退规则解析；
  * CPU 推理；支持单条与批量；
  * confidence 是**未经校准的模型分数均值**，不代表真实正确概率。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..core import jload, norm_text
from .labels import LABEL_ORDER
from .rules import rule_predict

LEVEL_TOKENS = ("博士", "硕士", "本科", "大专")
TERMINAL_TOKENS = ("学历不限", "学历不明")


class EducationNormalizer:
    """统一学历规范化推理器（支持 tfidf / charcnn 两类模型 + 规则回退）。"""

    def __init__(self, model, model_type: str, model_version: str,
                 thresholds: np.ndarray, tokenizer=None,
                 train_slot_vocab: list[str] | None = None,
                 fallback_to_rules: bool = True):
        self.model = model
        self.model_type = model_type
        self.model_version = model_version
        self.thresholds = np.asarray(thresholds, dtype=np.float64)
        self.tokenizer = tokenizer
        self.train_slot_vocab = set(train_slot_vocab or [])
        self.fallback_to_rules = bool(fallback_to_rules)

    # ---------------- 加载
    @classmethod
    def from_model_dir(cls, model_dir: Path | str,
                       fallback_to_rules: bool = True) -> "EducationNormalizer":
        d = Path(model_dir)
        meta = jload(d / "manifest.json")
        model_type = meta["model_type"]
        if model_type == "tfidf_char_ovr_logreg":
            from .tfidf_model import TfidfEducationModel
            model = TfidfEducationModel.load(d)
            tok = None
        elif model_type == "char_cnn":
            from .neural_model import CharCNN
            from .tokenizer import CharTokenizer
            model, _extra = CharCNN.load(d / "model.pt")
            tok = CharTokenizer.load(d / "tokenizer.json")
        else:
            raise ValueError(f"未知模型类型: {model_type}")
        return cls(model, model_type, meta.get("model_version", d.name),
                   np.asarray(meta["thresholds"], dtype=np.float64),
                   tokenizer=tok,
                   train_slot_vocab=meta.get("train_slot_vocab"),
                   fallback_to_rules=fallback_to_rules)

    # ---------------- 打分
    def _scores(self, texts: list[str]) -> np.ndarray:
        if self.model_type == "tfidf_char_ovr_logreg":
            return self.model.predict_proba(texts)
        import torch
        X = self.tokenizer.transform(texts)
        with torch.no_grad():
            logits = self.model(torch.from_numpy(X))
            return torch.sigmoid(logits).cpu().numpy().astype(np.float64)

    def _to_labels(self, scores: np.ndarray) -> tuple[list[str], dict]:
        """阈值化 + 互斥终态 token 的冲突消解。"""
        picked = [LABEL_ORDER[i] for i in range(len(LABEL_ORDER))
                  if scores[i] >= self.thresholds[i]]
        note = {}
        levels = [t for t in picked if t in LEVEL_TOKENS]
        terminals = [t for t in picked if t in TERMINAL_TOKENS]
        if levels and terminals:
            lv = float(np.mean([scores[LABEL_ORDER.index(t)] for t in levels]))
            tv = float(np.mean([scores[LABEL_ORDER.index(t)] for t in terminals]))
            keep_levels = lv >= tv
            dropped = terminals if keep_levels else levels
            picked = [t for t in picked if t not in dropped]
            note["conflict_resolution"] = {
                "type": "terminal_vs_level",
                "dropped": dropped,
                "rule": "保留平均分数更高的一侧（学历不限/学历不明 为互斥终态 token）",
            }
        t2 = [t for t in picked if t == "学历不限"]
        t3 = [t for t in picked if t == "学历不明"]
        if t2 and t3:
            keep = ("学历不限" if scores[LABEL_ORDER.index("学历不限")] >=
                    scores[LABEL_ORDER.index("学历不明")] else "学历不明")
            drop = "学历不明" if keep == "学历不限" else "学历不限"
            picked = [t for t in picked if t != drop]
            note.setdefault("conflict_resolution", {}).update(
                {"type": "terminal_vs_terminal", "dropped": [drop]})
        picked = [t for t in LABEL_ORDER if t in picked]
        return picked, note

    # ---------------- 单条 / 批量
    def normalize(self, text, fallback_to_rules: bool | None = None) -> dict:
        return self.batch([text], fallback_to_rules=fallback_to_rules)[0]

    def batch(self, texts, fallback_to_rules: bool | None = None) -> list[dict]:
        use_fb = self.fallback_to_rules if fallback_to_rules is None else bool(fallback_to_rules)
        raw_list = ["" if t is None else str(t) for t in texts]
        norm_list = [norm_text(t) for t in raw_list]
        out: list[dict] = []

        # 空输入单独走确定性规则（"学历不明"），不进模型
        idx_model = [i for i, s in enumerate(norm_list) if s]
        scores = (self._scores([norm_list[i] for i in idx_model])
                  if idx_model else np.zeros((0, len(LABEL_ORDER))))
        score_map = {i: scores[k] for k, i in enumerate(idx_model)}

        for i, (raw, s) in enumerate(zip(raw_list, norm_list)):
            rec: dict = {"input": raw, "normalized_input": s,
                         "model_version": self.model_version, "model_type": self.model_type}
            rec["expression_seen_in_train"] = bool(s in self.train_slot_vocab) \
                if self.train_slot_vocab else None
            if not s:
                rec.update({"labels": ["学历不明"], "scores": None, "confidence": None,
                            "fallback_to_rule": True, "rule": "empty_input",
                            "note": {"empty_input": "空输入按标签规范返回 学历不明"}})
                out.append(rec)
                continue
            sc = score_map[i]
            labels, note = self._to_labels(sc)
            rule_used = None
            if not labels and use_fb:
                r = rule_predict(s)
                labels = r["tokens"]
                rule_used = r["rule"]
                note = {**note, "fallback": "rule_predict"}
            elif not labels:
                labels = ["学历不明"]
                rule_used = "no_label_above_threshold"
                note = {**note, "fallback": "no_label_above_threshold"}
            conf = float(np.mean([sc[LABEL_ORDER.index(t)] for t in labels])) if labels else None
            rec.update({
                "labels": labels,
                "scores": {LABEL_ORDER[j]: round(float(sc[j]), 6) for j in range(len(LABEL_ORDER))},
                "confidence": round(conf, 6) if conf is not None else None,
                "confidence_meaning": "模型分数在预测标签上的均值，未经校准，不是真实正确概率",
                "fallback_to_rule": rule_used is not None,
                "rule": rule_used,
                "note": note,
            })
            out.append(rec)
        return out

    def describe(self) -> dict:
        return {"model_type": self.model_type, "model_version": self.model_version,
                "thresholds": {LABEL_ORDER[i]: float(self.thresholds[i])
                               for i in range(len(LABEL_ORDER))},
                "label_order": list(LABEL_ORDER),
                "fallback_to_rules": self.fallback_to_rules}
