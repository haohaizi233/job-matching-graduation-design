# -*- coding: utf-8 -*-
"""验收项 1：Conda 环境隔离与解释器一致性（只读）。

验证 sys.executable / sys.prefix / CONDA_PREFIX 指向同一环境，
pip 属于同一解释器，未误用全局或 base 环境的 Python。
"""
import os
import subprocess
import sys

RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


ENV_NAME = "graduation-design"
ENV_ROOT = os.path.join(os.path.expanduser("~"), "miniconda3", "envs", ENV_NAME)


def main():
    print("=" * 70)
    print("sys.executable :", sys.executable)
    print("sys.prefix     :", sys.prefix)
    print("sys.base_prefix:", sys.base_prefix)
    print("CONDA_PREFIX   :", os.environ.get("CONDA_PREFIX"))
    print("CONDA_DEFAULT_ENV:", os.environ.get("CONDA_DEFAULT_ENV"))

    # 1) 解释器路径来自目标环境
    ok = os.path.normcase(sys.executable).startswith(os.path.normcase(ENV_ROOT))
    record("解释器位于 %s 环境" % ENV_NAME, "PASS" if ok else "FAIL",
           "sys.executable=%s, 期望前缀=%s" % (sys.executable, ENV_ROOT))

    # 2) 前缀一致，不是 base
    ok = (os.path.normcase(sys.prefix) == os.path.normcase(sys.base_prefix) == os.path.normcase(ENV_ROOT))
    record("sys.prefix == sys.base_prefix == 环境根", "PASS" if ok else "FAIL",
           "prefix=%s, base_prefix=%s" % (sys.prefix, sys.base_prefix))

    # 3) CONDA_* 环境变量
    cd = os.environ.get("CONDA_DEFAULT_ENV")
    record("CONDA_DEFAULT_ENV", "PASS" if cd == ENV_NAME else "WARN",
           "CONDA_DEFAULT_ENV=%s" % cd)

    # 4) pip 归属同一解释器
    try:
        out = subprocess.check_output([sys.executable, "-m", "pip", "--version"],
                                      text=True, stderr=subprocess.STDOUT)
        ok = ENV_NAME in out
        record("pip 属于同一环境", "PASS" if ok else "FAIL", out.strip())
    except Exception as e:
        record("pip 属于同一环境", "FAIL", error=str(e))

    # 5) site-packages 归属
    import site
    sps = site.getsitepackages()
    ok = all(ENV_NAME in p for p in sps)
    record("site-packages 隔离", "PASS" if ok else "FAIL", str(sps))

    # 6) 非 base / 非全局 Python
    global_hit = [p for p in sys.path if p and ENV_NAME not in p and ("site-packages" in p or "Anaconda" in p)]
    record("未混入全局 site-packages", "PASS" if not global_hit else "WARN", "额外路径=%s" % global_hit)

    print("=" * 70)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
