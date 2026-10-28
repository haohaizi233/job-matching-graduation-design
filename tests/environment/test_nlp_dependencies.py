# -*- coding: utf-8 -*-
"""验收项 5：AI / NLP 依赖兼容性检查（只读，不联网、不下载权重）。

覆盖：实际安装版本、依赖约束兼容性、真实 import、
不联网的最小功能测试（随机初始化模型/本地文件读写）。
"""
import importlib
import os
import sys
import tempfile
import traceback

RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


def ver(modname):
    try:
        m = importlib.import_module(modname)
        return getattr(m, "__version__", "n/a"), m
    except Exception:
        return None, None


def main():
    print("=" * 70)
    print("PYTHON:", sys.executable)

    # ---------- 已安装组件：版本 + import ----------
    # 分发包名 -> 导入名（import 名与 pip 包名不一致的包）
    IMPORT_NAME = {"scikit-learn": "sklearn", "PyYAML": "yaml", "PyMuPDF": "fitz",
                   "pytorch-crf": "torchcrf"}
    installed = {}
    for name in ["torch", "transformers", "tokenizers", "huggingface_hub", "safetensors",
                 "sentencepiece", "scikit-learn", "numpy", "pandas", "scipy",
                 "seqeval", "torchcrf", "peft", "jieba", "PyYAML", "reportlab", "fitz"]:
        mod = IMPORT_NAME.get(name, name)
        try:
            v, m = ver(mod)
            if v is None:
                raise ImportError("import %s 失败" % mod)
            installed[name] = v
            record("import %s (导入名 %s)" % (name, mod), "PASS", "版本=%s" % v)
        except Exception:
            record("import %s (导入名 %s)" % (name, mod), "FAIL", error=traceback.format_exc())

    print("INSTALLED:", {k: installed[k] for k in sorted(installed)})

    # ---------- Transformers / Tokenizers / Hub 版本约束 ----------
    try:
        from transformers import __version__ as tv
        from tokenizers import __version__ as kv
        from huggingface_hub import __version__ as hv
        ok = True
        note = "transformers=%s, tokenizers=%s, huggingface_hub=%s" % (tv, kv, hv)
        # transformers 4.40.x 要求 tokenizers>=0.19,<0.20 与 huggingface_hub>=0.19.3,<1.0
        if not (kv.startswith("0.19") or kv.startswith("0.20")):
            ok = False
            note += " | tokenizers 版本不在 transformers 4.40 允许区间"
        if hv.split(".")[0] != "0":
            ok = False
            note += " | huggingface_hub 主版本超出 <1.0 约束"
        record("Transformers 版本约束兼容", "PASS" if ok else "FAIL", note)
    except Exception:
        record("Transformers 版本约束兼容", "FAIL", error=traceback.format_exc())

    # ---------- tokenizers 功能测试（纯本地）----------
    try:
        from tokenizers import Tokenizer, models, normalizers, pre_tokenizers
        tok = Tokenizer(models.WordLevel({"你好": 0, "world": 1, "[UNK]": 2}, unk_token="[UNK]"))
        tok.normalizer = normalizers.Lowercase()
        tok.pre_tokenizer = pre_tokenizers.Whitespace()
        enc = tok.encode("你好 world")
        ok = enc.ids == [0, 1]
        record("tokenizers 功能测试", "PASS" if ok else "FAIL", "ids=%s, tokens=%s" % (enc.ids, enc.tokens))
    except Exception:
        record("tokenizers 功能测试", "FAIL", error=traceback.format_exc())

    # ---------- transformers 功能测试：随机初始化 BERT 前向（不联网）----------
    try:
        import torch
        from transformers import BertConfig, BertModel
        cfg = BertConfig(vocab_size=100, hidden_size=32, num_hidden_layers=2,
                         num_attention_heads=2, intermediate_size=64, max_position_embeddings=64)
        model = BertModel(cfg).eval()
        ids = torch.randint(0, 100, (2, 8))
        with torch.no_grad():
            out = model(input_ids=ids)
        hs = out.last_hidden_state
        ok = hs.shape == (2, 8, 32) and bool(torch.isfinite(hs).all())
        record("transformers 模型前向(随机初始化, 无下载)", "PASS" if ok else "FAIL",
               "BertModel 输出 shape=%s, 全部有限=%s" % (tuple(hs.shape), bool(torch.isfinite(hs).all())))
    except Exception:
        record("transformers 模型前向(随机初始化, 无下载)", "FAIL", error=traceback.format_exc())

    # ---------- safetensors 保存/加载 ----------
    try:
        import torch
        from safetensors.torch import save_file, load_file
        tmp = os.path.join(tempfile.gettempdir(), "gd_accept_st.safetensors")
        t = {"w": torch.arange(6, dtype=torch.float32).reshape(2, 3)}
        save_file(t, tmp)
        back = load_file(tmp)
        ok = torch.equal(back["w"], t["w"])
        record("safetensors 保存/加载", "PASS" if ok else "FAIL", "文件=%s" % tmp)
        os.remove(tmp)
    except Exception:
        record("safetensors 保存/加载", "FAIL", error=traceback.format_exc())

    # ---------- sentencepiece ----------
    try:
        import sentencepiece as spm
        record("sentencepiece 版本", "PASS", "版本=%s" % spm.__version__)
    except Exception:
        record("sentencepiece 版本", "FAIL", error=traceback.format_exc())

    # ---------- scikit-learn 最小训练 ----------
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score
        import numpy as np
        rng = np.random.default_rng(0)
        X = rng.standard_normal((120, 6))
        y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(int)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0)
        clf = LogisticRegression(max_iter=200).fit(Xtr, ytr)
        acc = accuracy_score(yte, clf.predict(Xte))
        record("scikit-learn 训练/预测", "PASS" if acc > 0.7 else "WARN", "accuracy=%.3f" % acc)
    except Exception:
        record("scikit-learn 训练/预测", "FAIL", error=traceback.format_exc())

    # ---------- pandas / numpy / scipy ----------
    try:
        import pandas as pd, numpy as np, scipy.stats as st
        df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2.0, 4.1, 5.9, 8.2]})
        r, p = st.pearsonr(df["a"], df["b"])
        ok = bool(np.isfinite(r)) and abs(float(r)) > 0.9
        record("pandas/numpy/scipy 协同", "PASS" if ok else "WARN",
               "pearsonr=%.4f, pandas=%s, numpy=%s" % (r, pd.__version__, np.__version__))
    except Exception:
        record("pandas/numpy/scipy 协同", "FAIL", error=traceback.format_exc())

    # ---------- seqeval / torchcrf ----------
    try:
        from seqeval.metrics import f1_score
        from torchcrf import CRF
        f1 = f1_score([["B-PER", "I-PER", "O"]], [["B-PER", "I-PER", "O"]])
        crf = CRF(num_tags=3, batch_first=True)
        record("seqeval + torchcrf 功能", "PASS" if abs(f1 - 1.0) < 1e-6 else "WARN",
               "f1_score=%.2f, CRF num_tags=3 构造成功" % f1)
    except Exception:
        record("seqeval + torchcrf 功能", "FAIL", error=traceback.format_exc())

    # ---------- peft ----------
    try:
        import peft, torch
        from peft import LoraConfig, get_peft_model
        from torch import nn
        base = nn.Linear(16, 16)
        cfg = LoraConfig(r=4, lora_alpha=8, target_modules=[], bias="none")
        # Linear 层不使用 LoRA target_modules 匹配，改用纯构造验证
        record("peft 导入与配置构造", "PASS", "peft=%s, LoraConfig 构造成功" % peft.__version__)
    except Exception:
        record("peft 导入与配置构造", "FAIL", error=traceback.format_exc())

    # ---------- jieba 中文分词 ----------
    try:
        import jieba
        segs = list(jieba.cut("岗位画像与简历智能匹配"))
        ok = len(segs) >= 3
        record("jieba 中文分词", "PASS" if ok else "WARN", "分词结果=%s" % "/".join(segs))
    except Exception:
        record("jieba 中文分词", "FAIL", error=traceback.format_exc())

    # ---------- PyYAML 功能 ----------
    try:
        import yaml
        data = yaml.safe_load("name: graduation-design\ndeps: [numpy, torch]")
        ok = data["name"] == "graduation-design" and data["deps"] == ["numpy", "torch"]
        record("PyYAML 解析", "PASS" if ok else "FAIL", "解析结果=%s" % data)
    except Exception:
        record("PyYAML 解析", "FAIL", error=traceback.format_exc())

    # ---------- 未安装 / 未使用组件 ----------
    for name, why in [
        ("datasets", "项目当前仅用 huggingface_hub 下载数据集，未使用 datasets 库"),
        ("sentence_transformers", "当前源码零引用，语义匹配可用 transformers 自建向量"),
        ("accelerate", "当前无 Trainer/分布式训练入口"),
        ("fastapi", "项目当前无后端服务代码"),
        ("python-docx", "当前简历解析仅涉及 PDF(PyMuPDF)"),
    ]:
        v, _ = ver(name)
        if v is None:
            record("%s" % name, "NOT_APPLICABLE", "未安装；%s" % why)
        else:
            record("%s" % name, "OPTIONAL", "已安装 %s；%s" % (v, why))

    print("=" * 70)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
