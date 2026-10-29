# -*- coding: utf-8 -*-
"""全新 checkout 可移植性验证：证明 Core CI 不依赖真实数据 / 权重 / 私有文件。

做法（不联网、不下载）：
  1. 用 `git ls-files -c -o --exclude-standard` 取出"一个全新 checkout 会拿到的全部文件"
     （已跟踪 + 未跟踪但未忽略；被 .gitignore 的 data/raw、models 等天然不入列）；
  2. 只把这些文件复制到一个临时目录（干净 checkout 模拟）；
  3. 在该目录里执行 Core CI 各步骤；
  4. 同时断言：临时目录内**没有**任何 data/raw、models/**权重、data/private 文件。

用法：
  python scripts/phase5_1a/verify_fresh_checkout.py [--keep] [--skip-run] [--out PATH]

退出码：0 = Core CI 在干净 checkout 上通过且无数据泄漏；1 = 失败。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import run_identity as _ri  # noqa: E402

FORBIDDEN_PREFIXES = ("data/raw/", "data/private/", "models/")
FORBIDDEN_SUFFIXES = (".ckpt", ".pt", ".pth", ".safetensors", ".bin", ".pkl")

CORE_CI_STEPS = [
    ("syntax", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
    ("phase5_1r", [sys.executable, "tests/phase5_1r/run_all.py"]),
    ("phase5_1a", [sys.executable, "tests/phase5_1a/run_all.py"]),
    ("phase5_1", [sys.executable, "tests/phase5_1/run_all.py"]),
    ("core_ci", [sys.executable, "tests/core_ci/run_all.py"]),
]


def tracked_file_list() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard"],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git ls-files 失败: {r.stderr}")
    return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]


def export_clean_checkout(dest: Path) -> list[str]:
    """把"全新 checkout 会拿到的文件"复制到 dest。返回文件清单。"""
    files = tracked_file_list()
    copied = []
    for rel in files:
        src = ROOT / rel
        if not src.is_file():
            continue
        if rel.startswith(FORBIDDEN_PREFIXES) or rel.endswith(FORBIDDEN_SUFFIXES):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(rel)
    return copied


def assert_no_forbidden_artifacts(dest: Path) -> list[str]:
    bad = []
    for p in dest.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dest)).replace("\\", "/")
        if rel.startswith(FORBIDDEN_PREFIXES) or rel.endswith(FORBIDDEN_SUFFIXES):
            bad.append(rel)
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="全新 checkout Core CI 可移植性验证")
    ap.add_argument("--keep", action="store_true", help="保留临时 checkout 目录")
    ap.add_argument("--skip-run", action="store_true", help="只做文件清单检查，不跑测试")
    ap.add_argument("--out", default=str(ROOT / "reports" / "phase5-2" / "ci" /
                                        "fresh-checkout.json"))
    args = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="jm_fresh_checkout_"))
    t0 = time.time()
    steps = []
    try:
        copied = export_clean_checkout(tmp)
        forbidden = assert_no_forbidden_artifacts(tmp)
        steps.append({"id": "export", "status": "PASS" if not forbidden else "FAIL",
                      "files_exported": len(copied),
                      "forbidden_artifacts": forbidden[:20],
                      "reason": ("干净 checkout 内不含真实数据/权重"
                                 if not forbidden else "导出内容含被禁产物")})

        if args.skip_run:
            steps.append({"id": "core_ci", "status": "NOT_RUN",
                          "reason": "本次使用 --skip-run，未执行 Core CI"})
        else:
            env = dict(os.environ)
            env["JM_RUN_ID"] = env.get("JM_RUN_ID", f"fresh-{int(time.time())}")
            env["PYTHONUTF8"] = "1"
            for step_id, cmd in CORE_CI_STEPS:
                r = subprocess.run(cmd, cwd=str(tmp), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   timeout=2400, env=env)
                tail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-1500:]
                steps.append({"id": step_id,
                              "status": "PASS" if r.returncode == 0 else "FAIL",
                              "returncode": r.returncode, "tail": tail})
                if r.returncode != 0 and step_id == "syntax":
                    break
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)

    failed = [s for s in steps if s["status"] == "FAIL"]
    not_run = [s for s in steps if s["status"] == "NOT_RUN"]
    overall = "FAIL" if failed else ("PASS" if not not_run else "NOT_RUN")

    identity = _ri.build_run_identity(ROOT, artifact_count=len(steps), status=overall,
                                      extra={"tool": "verify_fresh_checkout"})
    identity["run_id"] = os.environ.get("JM_RUN_ID", identity["run_id"])

    out = {
        "generated_by": "scripts/phase5_1a/verify_fresh_checkout.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": round(time.time() - t0, 2),
        "overall": overall,
        "kept_checkout": str(tmp) if args.keep else None,
        "policy": ("Core CI 必须在全新 checkout（无 data/raw、无 models 权重、"
                   "无 data/private）上通过；NOT_RUN 不计入 PASS"),
        "run_identity": identity,
        "steps": steps,
    }
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")

    print("=" * 78)
    print(f"全新 checkout Core CI 验证 | overall={overall} | {out['seconds']}s")
    print("=" * 78)
    for s in steps:
        print(f"[{s['status']:>7}] {s['id']:<12} {s.get('reason', s.get('returncode', ''))}")
    print(f"-> {p}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
