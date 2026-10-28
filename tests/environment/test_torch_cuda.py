# -*- coding: utf-8 -*-
"""验收项 2：PyTorch 与 CUDA 实测（只读，不修改依赖）。

覆盖：版本、CUDA runtime 初始化、设备识别、cuDNN、真实 GPU 矩阵运算、
与 CPU 结果一致性、NaN/Inf 检查、显存占用。
"""
import sys
import time
import traceback

import torch

RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


def main():
    print("=" * 70)
    print("PYTHON      :", sys.executable)
    print("Torch       :", torch.__version__)
    print("Torch CUDA  :", torch.version.cuda)
    print("CUDA avail  :", torch.cuda.is_available())
    record("torch 版本", "PASS" if torch.__version__ == "2.1.2+cu121" else "WARN",
           "torch.__version__=%s" % torch.__version__)
    record("torch CUDA 编译版本", "PASS" if torch.version.cuda else "FAIL",
           "torch.version.cuda=%s" % torch.version.cuda)

    if not torch.cuda.is_available():
        record("CUDA 可用性", "FAIL", "torch.cuda.is_available()=False")
        return 2
    record("CUDA 可用性", "PASS", "torch.cuda.is_available()=True")

    # --- 初始化 / 驱动 / DLL ---
    try:
        torch.cuda.init()
        driver = torch.cuda.current_device()
        name = torch.cuda.get_device_name(0)
        cap = torch.cuda.get_device_capability(0)
        count = torch.cuda.device_count()
        props = torch.cuda.get_device_properties(0)
        print("GPU         :", name)
        print("Capability  :", cap)
        print("Device count:", count)
        print("Total mem   : %.2f GB" % (props.total_memory / 1024 ** 3))
        record("CUDA runtime 初始化", "PASS", "device=%s, capability=%s, count=%d, mem=%.2fGB"
               % (name, cap, count, props.total_memory / 1024 ** 3))
        if "RTX 2050" in name:
            record("GPU 型号识别", "PASS", "NVIDIA GeForce RTX 2050")
        else:
            record("GPU 型号识别", "WARN", "实际识别为 %s" % name)
        if cap < (7, 0):
            record("GPU 计算能力", "WARN", "capability=%s" % (cap,))
        else:
            record("GPU 计算能力", "PASS", "capability=%s" % (cap,))
    except Exception:
        record("CUDA runtime 初始化", "FAIL", error=traceback.format_exc())
        return 2

    # --- cuDNN ---
    try:
        cudnn_ok = torch.backends.cudnn.is_available()
        ver = torch.backends.cudnn.version()
        record("cuDNN 可用性", "PASS" if cudnn_ok else "WARN",
               "cudnn.is_available()=%s, version=%s" % (cudnn_ok, ver))
    except Exception:
        record("cuDNN 可用性", "WARN", error=traceback.format_exc())

    # --- 真实 GPU 计算 ---
    for n in (512, 1024):
        try:
            torch.cuda.reset_peak_memory_stats()
            a_cpu = torch.randn(n, n, dtype=torch.float32)
            b_cpu = torch.randn(n, n, dtype=torch.float32)
            a = a_cpu.cuda()
            b = b_cpu.cuda()
            torch.cuda.synchronize()
            t0 = time.time()
            c = a @ b
            torch.cuda.synchronize()
            dt = time.time() - t0
            c_cpu = c.cpu()
            ref = a_cpu @ b_cpu
            diff = (c_cpu - ref).abs().max().item()
            finite = bool(torch.isfinite(c_cpu).all())
            peak = torch.cuda.max_memory_allocated() / 1024 ** 2
            ok = finite and diff < 1e-2
            record("GPU 矩阵乘法 %dx%d" % (n, n), "PASS" if ok else "FAIL",
                   "耗时=%.3fs, 与CPU最大偏差=%.3e, 全部有限=%s, 显存峰值=%.1fMB"
                   % (dt, diff, finite, peak))
            del a, b, c
            torch.cuda.empty_cache()
        except Exception:
            record("GPU 矩阵乘法 %dx%d" % (n, n), "FAIL", error=traceback.format_exc())

    # --- CUDA->CPU 往返与 dtype 校验 ---
    try:
        x = torch.arange(6, dtype=torch.float32).reshape(2, 3).cuda()
        y = x.cpu().numpy()
        ok = (y.dtype == "float32") and (abs(float(y.sum()) - 15.0) < 1e-6)
        record("CUDA Tensor→NumPy 往返", "PASS" if ok else "FAIL", "dtype=%s, sum=%.1f" % (y.dtype, float(y.sum())))
    except Exception:
        record("CUDA Tensor→NumPy 往返", "FAIL", error=traceback.format_exc())

    print("=" * 70)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
