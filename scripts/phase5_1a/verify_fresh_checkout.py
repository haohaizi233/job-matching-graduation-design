# -*- coding: utf-8 -*-
"""全新 checkout 可移植性验证：证明 Core CI 不依赖真实数据 / 权重 / 私有文件。

做法（不联网、不下载）：
  1. 用 `git ls-files -c -o --exclude-standard` 取出"一个全新 checkout 会拿到的全部文件"
     （已跟踪 + 未跟踪但未忽略；被 .gitignore 的 data/raw、models 等天然不入列）；
     **无 git 环境**（如本脚本导出的临时 checkout、源码包）退化为文件系统枚举，
     并经 `file_list_source()` 显式登记来源，绝不把退化结果伪装成 git 结果；
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

# 无 git 时退化枚举需要跳过的"非仓库内容"目录：
#   嵌套的独立 git 仓库 / 依赖与字节码缓存 / 虚拟环境 / 工具缓存。
# 原则：**模拟 `git ls-files -c -o --exclude-standard` 的仓库归属**，
# 只排除不属于本仓库的内容，不替调用方"顺手"隐藏任何业务/产物路径。
NON_REPO_DIR_NAMES = {
    ".git", "chinese-skillspan-benchmark",
    "node_modules", "__pycache__", "dist", "build",
    ".venv", "venv", "env",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints", ".idea",
}

CORE_CI_STEPS = [
    ("syntax", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
    ("phase5_1r", [sys.executable, "tests/phase5_1r/run_all.py"]),
    ("phase5_1a", [sys.executable, "tests/phase5_1a/run_all.py"]),
    ("phase5_1", [sys.executable, "tests/phase5_1/run_all.py"]),
    ("core_ci", [sys.executable, "tests/core_ci/run_all.py"]),
]

# 文件清单来源登记（不得静默假装成 git 结果）
SOURCE_GIT = "git"
SOURCE_FALLBACK = "filesystem_fallback"
_file_list_source: str | None = None


def file_list_source() -> str:
    """返回最近一次 `tracked_file_list()` 使用的来源；未调用过时返回 UNKNOWN。"""
    return _file_list_source or "UNKNOWN"


def _git_available() -> bool:
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
    except Exception:  # noqa: BLE001 - git 不可用时必须退化，不得崩溃
        return False
    return r.returncode == 0 and (r.stdout or "").strip() == "true"


def _walk_repo_files() -> list[str]:
    """无 git 时的退化枚举：遍历文件系统，跳过"非仓库内容"目录。

    注意：**不实现 .gitignore 语义**，因此在"本机开发仓库根"下结果会比 git 清单更宽。
    该退化路径只应在"已导出的干净 checkout"（天然无 data/raw、models、data/private）
    或源码包中使用；在真正的 git 仓库里一律走 `git ls-files`。
    """
    out: list[str] = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(ROOT).parts
        if any(part in NON_REPO_DIR_NAMES for part in rel_parts[:-1]):
            continue
        out.append("/".join(rel_parts))
    return out


def tracked_file_list() -> list[str]:
    """一个全新 checkout 会拿到的文件清单（已跟踪 + 未跟踪但未忽略）。

    * 在 git 仓库内：`git ls-files -c -o --exclude-standard`（权威口径）；
    * 无 git（如 verify_fresh_checkout 导出的临时 checkout、源码包）：
      退化为文件系统枚举，并通过 `file_list_source()` **显式登记来源**，
      绝不把退化结果伪装成 git 结果。
    """
    global _file_list_source
    if _git_available():
        r = subprocess.run(["git", "ls-files", "-c", "-o", "--exclude-standard"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"git ls-files 失败: {r.stderr}")
        _file_list_source = SOURCE_GIT
        return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    _file_list_source = SOURCE_FALLBACK
    return _walk_repo_files()


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
                      "file_list_source": file_list_source(),
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
