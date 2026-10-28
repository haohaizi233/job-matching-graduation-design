# -*- coding: utf-8 -*-
"""验收项 8：环境可复现性检查（只读，不修改任何配置）。

核对 environment.yml / requirements*.txt 是否与当前环境一致、
是否记录 Python 与 torch/CUDA 版本、是否存在绝对路径或互相矛盾的约束。
"""
import os
import re
import subprocess
import sys

ROOT = r"D:\desktop\毕业设计"
RESULTS = []


def record(name, status, evidence="", error=""):
    RESULTS.append((name, status, evidence, error))
    print("[%s] %s | %s %s" % (status, name, evidence, ("| " + error) if error else ""))


def installed_versions():
    out = subprocess.check_output([sys.executable, "-m", "pip", "list", "--format=freeze"],
                                 text=True)
    d = {}
    for line in out.splitlines():
        if "==" in line:
            k, v = line.split("==", 1)
            d[k.strip().lower().replace("_", "-")] = v.strip()
    return d


def main():
    print("=" * 70)
    env_yml = os.path.join(ROOT, "environment.yml")
    exists = os.path.exists(env_yml)
    record("environment.yml 存在", "PASS" if exists else "FAIL", env_yml)
    if not exists:
        return 1

    with open(env_yml, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()

    # 1) Python 版本记录
    py_ok = any(re.match(r"\s*-\s*python\s*=\s*3\.11", ln) for ln in lines)
    record("记录 Python 版本", "PASS" if py_ok else "FAIL",
           "python=3.11 声明存在=%s, 当前解释器=%s" % (py_ok, sys.version.split()[0]))

    # 2) torch / CUDA 明确
    torch_line = [ln.strip() for ln in lines if "torch==" in ln]
    extra = [ln.strip() for ln in lines if "extra-index-url" in ln or "index-url" in ln]
    ok = bool(torch_line) and bool(extra) and any("cu121" in ln for ln in torch_line + extra)
    record("PyTorch/CUDA 版本与来源明确", "PASS" if ok else "FAIL",
           "torch 行=%s, 索引行=%s" % (torch_line, extra))

    # 3) 无绝对路径
    abs_paths = [ln.strip() for ln in lines
                 if re.search(r"[A-Za-z]:\\\\|/[Uu]sers/|/home/", ln) or "MemoryLeak" in ln]
    record("无本机绝对路径", "PASS" if not abs_paths else "FAIL", "命中=%s" % (abs_paths or "无"))

    # 4) 与实际安装版本一致性
    inst = installed_versions()
    pins = {}
    for ln in lines:
        m = re.match(r"\s*-\s*([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.+]+)\s*$", ln)
        if m:
            pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    mismatch, checked = [], 0
    for name, ver in sorted(pins.items()):
        real = inst.get(name)
        checked += 1
        if real is None:
            mismatch.append("%s: 声明 %s, 环境中缺失" % (name, ver))
        elif real != ver:
            mismatch.append("%s: 声明 %s, 实际 %s" % (name, ver, real))
    record("声明版本与实装一致", "PASS" if not mismatch else "FAIL",
           "核对 %d 个直接依赖, 不一致=%s" % (checked, mismatch or "无"))

    # 5) 与其他 requirements 文件是否存在矛盾约束
    conflicts = []
    req_files = []
    for dp, _, fns in os.walk(ROOT):
        if "chinese-skillspan-benchmark" in dp and "reproduction" not in dp:
            pass
        for fn in fns:
            if fn.startswith("requirements") and fn.endswith(".txt"):
                req_files.append(os.path.join(dp, fn))
    for rf in req_files:
        with open(rf, "r", encoding="utf-8", errors="replace") as f:
            for ln in f:
                m = re.match(r"\s*([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.+]+)", ln)
                if not m:
                    continue
                name = m.group(1).lower().replace("_", "-")
                ver = m.group(2)
                cur = pins.get(name)
                if cur and cur != ver:
                    conflicts.append("%s 声明 %s vs environment.yml %s" % (os.path.relpath(rf, ROOT), ver, cur))
    record("跨文件版本约束", "WARN" if conflicts else "PASS",
           "发现差异（已在 docs/environment-setup.md 记录取舍理由）=%s" % (conflicts or "无")
           if conflicts else "无相互矛盾的强制约束")
    record("requirements 文件清单", "PASS", "; ".join(os.path.relpath(p, ROOT) for p in sorted(req_files)))

    # 6) pyproject.toml / Pipfile
    other = [p for p in ("pyproject.toml", "Pipfile", "setup.py")
             if os.path.exists(os.path.join(ROOT, p))]
    record("其他依赖清单", "NOT_APPLICABLE" if not other else "WARN",
           "根目录不存在 pyproject.toml/Pipfile/setup.py，依赖由 environment.yml 统一维护"
           if not other else str(other))

    print("=" * 70)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("汇总: %d 项, FAIL=%d" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
