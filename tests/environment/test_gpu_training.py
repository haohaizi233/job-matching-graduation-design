# -*- coding: utf-8 -*-
"""验收项 3：真实 GPU 模型训练冒烟测试（只读，不触碰真实数据集）。

覆盖：MLP 构建、数据与模型置于 CUDA、AdamW、前向/反向/step、
连续 40 步训练、参数更新、梯度有限性、NaN/Inf、CUDA 同步、显存峰值。
"""
import sys
import time
import traceback

import torch
import torch.nn as nn

RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


def main():
    if not torch.cuda.is_available():
        record("GPU 训练链路", "SKIP", "CUDA 不可用")
        return 2

    device = torch.device("cuda:0")
    torch.cuda.reset_peak_memory_stats()
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)

    steps = 40
    batch, dim, hidden, n_class = 64, 32, 64, 4

    # ---- 模拟数据（独立验收代码，不使用业务数据集）----
    x = torch.randn(batch, dim, device=device)
    w_true = torch.randn(dim, n_class, device=device)
    y = (x @ w_true).argmax(dim=1)

    model = nn.Sequential(
        nn.Linear(dim, hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, n_class),
    ).to(device)

    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    on_cuda = all(p.is_cuda for p in model.parameters())
    data_cuda = x.is_cuda and y.is_cuda
    record("模型与数据置于 CUDA", "PASS" if (on_cuda and data_cuda) else "FAIL",
           "参数在CUDA=%s, 输入/标签在CUDA=%s, device=%s" % (on_cuda, data_cuda, device))

    # ---- 记录初始参数快照 ----
    first_param = next(model.parameters())
    snapshot0 = first_param.detach().clone()

    losses, grad_finite, param_changed = [], True, False
    nan_inf = False
    t0 = time.time()
    try:
        for step in range(1, steps + 1):
            opt.zero_grad(set_to_none=True)
            logits = model(x)                      # 前向
            loss = loss_fn(logits, y)              # loss
            loss.backward()                        # 反向

            # 梯度检查
            for p in model.parameters():
                if p.grad is not None:
                    if not bool(torch.isfinite(p.grad).all()):
                        grad_finite = False
                    if not bool(torch.isfinite(p.grad).all().item()):
                        grad_finite = False

            opt.step()                             # 参数更新
            torch.cuda.synchronize()

            lv = float(loss.detach().cpu())
            losses.append(lv)
            if not (lv == lv) or lv in (float("inf"), float("-inf")):
                nan_inf = True
        ok_loop = True
    except Exception:
        ok_loop = False
        record("训练循环", "FAIL", error=traceback.format_exc())

    torch.cuda.synchronize()
    elapsed = time.time() - t0
    peak = torch.cuda.max_memory_allocated() / 1024 ** 2

    if ok_loop:
        param_changed = bool((first_param.detach() - snapshot0).abs().max().item() > 0)
        all_finite_params = all(bool(torch.isfinite(p).all()) for p in model.parameters())

        record("前向/反向/优化器 step 连续 %d 步" % steps, "PASS",
               "循环正常结束, 耗时=%.3fs" % elapsed)
        record("Loss 数值", "PASS" if not nan_inf else "FAIL",
               "初始=%.6f, 最终=%.6f, 最小=%.6f, 最大=%.6f"
               % (losses[0], losses[-1], min(losses), max(losses)))
        record("梯度有限性", "PASS" if grad_finite else "FAIL",
               "所有步骤梯度均有限=%s" % grad_finite)
        record("参数确实更新", "PASS" if param_changed else "FAIL",
               "首个参数最大变化=%.6e" % float((first_param.detach() - snapshot0).abs().max()))
        record("参数无 NaN/Inf", "PASS" if all_finite_params else "FAIL",
               "全部参数有限=%s" % all_finite_params)
        record("CUDA 同步", "PASS", "torch.cuda.synchronize() 成功")
        record("显存峰值", "PASS", "%.2f MB" % peak)

        # loss 是否整体下降（仅供参考，不作为判定依据）
        trend = sum(losses[-5:]) / 5.0 < sum(losses[:5]) / 5.0
        record("Loss 总体趋势(参考)", "PASS" if trend else "WARN",
               "前5步均值=%.6f, 后5步均值=%.6f, 单步严格单调=%s"
               % (sum(losses[:5]) / 5.0, sum(losses[-5:]) / 5.0,
                  all(losses[i + 1] <= losses[i] for i in range(len(losses) - 1))))

        print("LOSS_TRACE:", ", ".join("%.4f" % v for v in losses))

    print("=" * 70)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
