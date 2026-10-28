# -*- coding: utf-8 -*-
"""验收项 4：NumPy 与 PyTorch 双向转换与 ABI 兼容性（只读）。

覆盖 torch.tensor(numpy)、torch.from_numpy、tensor.numpy()、
NumPy→CUDA Tensor→CPU NumPy 全链路，以及 dtype/数值一致性。
"""
import sys
import traceback

import numpy as np
import torch

RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


def main():
    print("=" * 70)
    print("NumPy:", np.__version__)
    print("Torch:", torch.__version__)
    record("版本", "PASS", "numpy=%s torch=%s" % (np.__version__, torch.__version__))

    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    # 1) torch.tensor(numpy_array)
    try:
        t = torch.tensor(arr)
        ok = t.dtype == torch.float32 and torch.allclose(t, torch.tensor([1.0, 2.0, 3.0]))
        record("torch.tensor(numpy_array)", "PASS" if ok else "FAIL",
               "dtype=%s, values=%s" % (t.dtype, t.tolist()))
    except Exception:
        record("torch.tensor(numpy_array)", "FAIL", error=traceback.format_exc())

    # 2) torch.from_numpy
    try:
        t2 = torch.from_numpy(arr)
        ok = t2.dtype == torch.float32 and abs(float(t2.sum()) - 6.0) < 1e-6
        record("torch.from_numpy()", "PASS" if ok else "FAIL", "dtype=%s, sum=%.1f" % (t2.dtype, float(t2.sum())))
    except Exception:
        record("torch.from_numpy()", "FAIL", error=traceback.format_exc())

    # 3) tensor.numpy()
    try:
        back = t2.numpy()
        ok = back.dtype == np.float32 and np.allclose(back, arr)
        record("tensor.numpy()", "PASS" if ok else "FAIL", "dtype=%s, values=%s" % (back.dtype, back.tolist()))
    except Exception:
        record("tensor.numpy()", "FAIL", error=traceback.format_exc())

    # 4) 多 dtype 覆盖
    try:
        bad = []
        for dt in (np.float16, np.float32, np.float64, np.int32, np.int64, np.bool_):
            a = np.arange(5).astype(dt)
            t = torch.from_numpy(a)
            if t.numpy().tolist() != a.tolist():
                bad.append(str(dt))
        record("多 dtype 双向转换", "PASS" if not bad else "FAIL",
               "float16/32/64, int32/64, bool_" + ("；异常: %s" % bad if bad else " 全部一致"))
    except Exception:
        record("多 dtype 双向转换", "FAIL", error=traceback.format_exc())

    # 5) NumPy -> CUDA Tensor -> CPU NumPy
    if torch.cuda.is_available():
        try:
            a = np.random.default_rng(0).standard_normal((256, 256)).astype(np.float32)
            t = torch.from_numpy(a).cuda()
            torch.cuda.synchronize()
            back = t.cpu().numpy()
            diff = float(np.abs(back - a).max())
            ok = back.dtype == np.float32 and diff == 0.0 and bool(np.isfinite(back).all())
            record("NumPy→CUDA→NumPy 全链路", "PASS" if ok else "FAIL",
                   "dtype=%s, 最大偏差=%.3e, 全部有限=%s" % (back.dtype, diff, bool(np.isfinite(back).all())))
        except Exception:
            record("NumPy→CUDA→NumPy 全链路", "FAIL", error=traceback.format_exc())
    else:
        record("NumPy→CUDA→NumPy 全链路", "SKIP", "CUDA 不可用")

    # 6) torch._C._ARRAY_API / ABI 信号
    try:
        import numpy.core._multiarray_umath as _m  # noqa: F401
        record("NumPy C 扩展加载", "PASS", "_multiarray_umath 可加载")
    except Exception:
        record("NumPy C 扩展加载", "FAIL", error=traceback.format_exc())

    print("=" * 70)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
