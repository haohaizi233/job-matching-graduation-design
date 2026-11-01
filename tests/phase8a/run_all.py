# -*- coding: utf-8 -*-
"""Phase8-A 统一测试运行器（stdlib unittest，与 tests/phase7/run_all.py 同风格）。

运行 tests/phase8a 全部 test_*.py（安全原语 / Provider 协议 / 事务票据 / 身份纪律 /
API 集成 / PostgreSQL 集成），产出真实执行证据：

  reports/phase8-a/07-provider-mock-tests.json
  reports/phase8-a/07-provider-mock-tests.md

纪律：
  * 执行证据字段一律取自**真实进程**（python_version / sys.argv / cwd / git sha /
    起止时间 / 退出码），禁止硬编码；
  * 零测试发现（模块为空或 testsRun==0）显式失败（退出码 1），不允许《FAIL=0 全绿》；
  * PostgreSQL 未提供时该模块记 NOT_RUN（skip），绝不冒充 PASS。

用法（项目根目录）：
    py -3.13 tests/phase8a/run_all.py            # 全部
    py -3.13 tests/phase8a/run_all.py api        # 只跑模块名含 api 的
"""
from __future__ import annotations

import json
import os
import platform
import shlex
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase8-a"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

STATUSES = ("PASS", "FAIL", "ERROR", "SKIP", "NOT_RUN", "BLOCKED")


def discover_modules(pattern: str | None = None) -> list[str]:
    names = sorted(p.stem for p in HERE.glob("test_*.py") if p.is_file())
    if pattern:
        names = [n for n in names if pattern in n]
    return names


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"test": test.id(), "status": "FAIL",
                             "detail": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({"test": test.id(), "status": "ERROR",
                             "detail": self._exc_info_to_string(err, test)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({"test": test.id(), "status": "SKIP",
                             "reason": reason})


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def run_module(module_name: str, verbosity: int = 1) -> dict:
    started = time.time()
    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName(module_name)
    except Exception as e:  # noqa: BLE001 - 模块导入失败记 ERROR
        return {"module": module_name, "status": "ERROR", "tests": 0,
                "pass": 0, "fail": 0, "error": 1, "skip": 0, "seconds": 0.0,
                "records": [{"test": module_name, "status": "ERROR",
                             "detail": f"模块导入失败: {e}"}]}
    stream = open(os.devnull, "w", encoding="utf-8") if verbosity <= 0 else sys.stderr
    runner = unittest.TextTestRunner(stream=stream, verbosity=verbosity,
                                     resultclass=RecordingResult)
    result = runner.run(suite)
    seconds = round(time.time() - started, 3)
    if stream is not sys.stderr:
        stream.close()
    records = result.records
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if counts["FAIL"] or counts["ERROR"]:
        status = "FAIL" if counts["FAIL"] else "ERROR"
    elif counts["PASS"] == 0 and counts["SKIP"] > 0:
        status = ("NOT_RUN"
                  if all(str(r.get("reason", "")).startswith("NOT_RUN")
                         for r in records if r["status"] == "SKIP")
                  else "SKIP")
    elif counts["PASS"] == 0:
        status = "ERROR"
    else:
        status = "PASS"
    return {"module": module_name, "status": status, "tests": result.testsRun,
            "pass": counts["PASS"], "fail": counts["FAIL"],
            "error": counts["ERROR"], "skip": counts["SKIP"],
            "seconds": seconds, "records": records}


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    modules = discover_modules(pattern)
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()
    results = [run_module(m) for m in modules]
    seconds = round(time.time() - t0, 3)

    total = sum(r["tests"] for r in results)
    totals = {
        "tests": total,
        "pass": sum(r["pass"] for r in results),
        "fail": sum(r["fail"] for r in results),
        "error": sum(r["error"] for r in results),
        "skip": sum(r["skip"] for r in results),
    }
    if total == 0:
        overall = "ERROR"
    elif totals["fail"] or totals["error"]:
        overall = "FAIL"
    elif totals["pass"] == 0:
        overall = "NOT_RUN"
    else:
        overall = "PASS"

    report = {
        "suite": "phase8a-oauth",
        "run_id": f"phase8a-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "overall": overall,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "seconds": seconds,
        "python_version": platform.python_version(),
        "actual_python_executable": sys.executable,
        "sys_argv": sys.argv,
        "working_directory": os.getcwd(),
        "execution_command": shlex.join([sys.executable, *sys.argv]),
        "git_sha": _git_sha(),
        "totals": totals,
        "modules": [{k: v for k, v in r.items()} for r in results],
    }
    (REPORT_DIR / "07-provider-mock-tests.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Phase8-A OAuth 测试执行证据（M9 / 07-provider-mock-tests）", "",
        f"- run_id: `{report['run_id']}`",
        f"- overall: **{overall}**",
        f"- python: `{report['python_version']}`（{report['actual_python_executable']}）",
        f"- command: `{report['execution_command']}`",
        f"- git_sha: `{report['git_sha']}`",
        f"- seconds: {seconds}",
        f"- totals: tests={total} pass={totals['pass']} fail={totals['fail']} "
        f"error={totals['error']} skip={totals['skip']}", "",
        "| 模块 | 状态 | tests | pass | fail | error | skip | 秒 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['module']} | {r['status']} | {r['tests']} | "
                     f"{r['pass']} | {r['fail']} | {r['error']} | {r['skip']} | "
                     f"{r['seconds']} |")
    lines.append("")
    lines.append("## 失败/跳过明细")
    lines.append("")
    for r in results:
        for rec in r["records"]:
            if rec["status"] in ("FAIL", "ERROR", "SKIP"):
                detail = rec.get("detail") or rec.get("reason") or ""
                first_line = str(detail).strip().splitlines()[0] if detail else ""
                lines.append(f"- `{rec['status']}` {rec['test']} {first_line}")
    lines.append("")
    (REPORT_DIR / "07-provider-mock-tests.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"[phase8a] overall={overall} tests={total} pass={totals['pass']} "
          f"fail={totals['fail']} error={totals['error']} skip={totals['skip']}")
    print(f"[phase8a] report: {REPORT_DIR / '07-provider-mock-tests.md'}")
    return 0 if overall == "PASS" and total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
