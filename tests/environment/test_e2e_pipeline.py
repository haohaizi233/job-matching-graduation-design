# -*- coding: utf-8 -*-
"""验收项 7：最小端到端训练链路冒烟测试（使用真实数据的小样本，只读）。

链路：真实 CSV 读取 → 预处理/特征转换 → Tensor → CUDA → 前向 → Loss → 反向 → 更新。

字段含义严格依据根目录 README.md 的数据字典，不做任何字段含义猜测：
  matches.csv: semantic_score / skill_score / position_score / category_score /
               experience_score / education_score  (特征)
               label_strength: weak_positive=0 / medium_positive=1 / strong_positive=2 (标签)
本测试仅验证基础设施可用性，不代表业务模型已通过验收。
"""
import os
import sys
import time
import traceback

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ROOT = r"D:\desktop\毕业设计"
RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


FEATS = ["semantic_score", "skill_score", "position_score",
         "category_score", "experience_score", "education_score"]
LABEL_MAP = {"weak_positive": 0, "medium_positive": 1, "strong_positive": 2}


def main():
    print("=" * 70)
    print("PYTHON :", sys.executable)
    if not torch.cuda.is_available():
        record("端到端链路", "SKIP", "CUDA 不可用")
        return 2

    try:
        # ---- 1. 真实数据读取（小样本）----
        path = os.path.join(ROOT, "data", "raw", "job-resume-matching", "matches.csv")
        df = pd.read_csv(path, nrows=512, encoding="utf-8-sig")
        record("1 真实 CSV 读取", "PASS", "%s, shape=%s" % (path, df.shape))

        # ---- 2. 预处理 / 特征转换（字段含义来自 README 数据字典）----
        x_np = df[FEATS].to_numpy(dtype=np.float32)
        y_np = df["label_strength"].map(LABEL_MAP).to_numpy(dtype=np.int64)
        finite = bool(np.isfinite(x_np).all()) and not np.isnan(y_np).any()
        record("2 预处理/特征转换", "PASS" if finite else "FAIL",
               "特征矩阵=%s, 标签取值=%s, 全部有限=%s"
               % (x_np.shape, sorted(set(y_np.tolist())), finite))

        # ---- 3. Tensor → CUDA ----
        device = torch.device("cuda:0")
        x = torch.from_numpy(x_np).to(device)
        y = torch.from_numpy(y_np).to(device)
        record("3 Tensor→CUDA", "PASS" if (x.is_cuda and y.is_cuda) else "FAIL",
               "x=%s, y=%s" % (tuple(x.shape), tuple(y.shape)))

        # ---- 4. 模型 / 优化器 ----
        model = nn.Sequential(
            nn.Linear(len(FEATS), 32), nn.ReLU(), nn.Linear(32, 3)
        ).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-2)
        loss_fn = nn.CrossEntropyLoss()

        # ---- 5. 训练 20 步 ----
        steps, losses = 20, []
        t0 = time.time()
        for _ in range(steps):
            opt.zero_grad(set_to_none=True)
            logits = model(x)
            loss = loss_fn(logits, y)
            loss.backward()
            opt.step()
            torch.cuda.synchronize()
            losses.append(float(loss.detach().cpu()))
        elapsed = time.time() - t0
        peak = torch.cuda.max_memory_allocated() / 1024 ** 2

        finite_ok = all(np.isfinite(losses))
        improved = losses[-1] < losses[0]
        params_ok = all(bool(torch.isfinite(p).all()) for p in model.parameters())
        record("4 模型前向+Loss", "PASS", "loss.shape=%s" % (tuple(loss_fn(model(x), y).shape) or "scalar",))
        record("5 反向传播+参数更新 %d 步" % steps,
               "PASS" if (finite_ok and improved and params_ok) else "FAIL",
               "loss: %.6f -> %.6f, 耗时=%.3fs, 显存峰值=%.2fMB, 全部有限=%s"
               % (losses[0], losses[-1], elapsed, peak, finite_ok))

        # ---- 6. 推理一致性 ----
        with torch.no_grad():
            pred = model(x).argmax(dim=1)
        acc = float((pred == y).float().mean().cpu())
        record("6 前向推理", "PASS" if acc > 0.3 else "WARN",
               "训练后训练集准确率=%.3f（仅用于链路验证，不作为模型指标）" % acc)

    except Exception:
        record("端到端链路", "FAIL", error=traceback.format_exc())

    print("=" * 70)
    print("声明: 本测试为基础设施冒烟测试，使用 matches.csv 前 512 行真实数据,")
    print("      仅验证 数据→张量→CUDA→训练 全链路可用，不代表正式业务模型通过验收。")
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
