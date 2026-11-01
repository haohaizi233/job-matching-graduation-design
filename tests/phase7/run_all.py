# -*- coding: utf-8 -*-
"""Phase7 统一测试运行器（stdlib unittest，与 tests/phase6/run_all.py 同风格）。

任务书 12.2 要求的运行证据字段全部登记：
  run_id / git_sha / python_version / dataset_version / model_version /
  execution_command / exit_code / PASS FAIL ERROR SKIP NOT_RUN BLOCKED / evidence_path

用法：
    py -3.13 tests/phase7/run_all.py            # 全部
    py -3.13 tests/phase7/run_all.py prereg      # 只跑模块名含 prereg 的

输出：reports/phase7/11-phase7-regression.{json,md}
退出码：0 = 无 FAIL/ERROR；1 = 存在 FAIL/ERROR
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase7"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase7"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

STATUSES = ("PASS", "FAIL", "ERROR", "SKIP", "NOT_RUN", "BLOCKED")


def discover_modules() -> list[str]:
    return sorted(p.stem for p in HERE.glob("test_*.py") if p.is_file())


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []
        self._start = 0.0

    def startTest(self, test):
        super().startTest(test)
        self._start = time.perf_counter()

    def _elapsed(self) -> float:
        return round((time.perf_counter() - self._start) * 1000.0, 3)

    def _module_of(self, test) -> str:
        return type(test).__module__.split(".")[-1]

    def _add(self, test, status: str, detail: str):
        self.records.append({
            "module": self._module_of(test), "test": str(test),
            "status": status, "ms": self._elapsed(), "detail": detail[-1500:],
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, "PASS", "")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, "SKIP", reason)


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    modules = discover_modules()
    if only:
        modules = [m for m in modules if only in m]

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    load_errors: list[dict] = []
    for mod in modules:
        try:
            suite.addTests(loader.loadTestsFromName(mod))
        except Exception as e:  # noqa: BLE001
            load_errors.append({"module": mod, "error": f"{type(e).__name__}: {e}"})

    t0 = time.time()
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    result = runner.run(suite)
    elapsed = round(time.time() - t0, 3)

    counts = {s: 0 for s in STATUSES}
    for r in result.records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for le in load_errors:
        counts["ERROR"] += 1
        result.records.append({"module": le["module"], "test": f"<import {le['module']}>",
                               "status": "ERROR", "ms": 0.0, "detail": le["error"]})

    ok = counts["FAIL"] == 0 and counts["ERROR"] == 0
    cmd = f"py -3.13 tests/phase7/run_all.py{(' ' + only) if only else ''}"
    payload = {
        "run_id": time.strftime("phase7-reg-%Y%m%d-%H%M%S"),
        "git_sha": _git_sha(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "dataset_version": "none (Phase7 真实 Gold 未建立；测试仅使用合成夹具)",
        "model_version": "n/a（本套件不加载模型权重）",
        "execution_command": cmd,
        "exit_code": 0 if ok else 1,
        "counts": counts,
        "evidence_path": "reports/phase7/11-phase7-regression.json",
        "generated_by": "tests/phase7/run_all.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "modules": modules,
        "tests_run": result.testsRun,
        "seconds": elapsed,
        "ok": ok,
        "load_errors": load_errors,
        "records": result.records,
    }
    (REPORT_DIR / "11-phase7-regression.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase7 纯软件协议测试回归结果",
        "",
        f"- run_id：`{payload['run_id']}`",
        f"- git_sha：`{payload['git_sha']}`",
        f"- python_version：`{payload['python_version']}` / {payload['platform']}"
        "（本地 3.13；GitHub Core CI 固定 3.11，跨版本兼容性以远端 CI 为准）",
        f"- dataset_version：{payload['dataset_version']}",
        f"- model_version：{payload['model_version']}",
        f"- execution_command：`{payload['execution_command']}`",
        f"- exit_code：{payload['exit_code']}",
        f"- 运行用例：{result.testsRun}，耗时 {elapsed}s",
        f"- PASS={counts['PASS']} FAIL={counts['FAIL']} ERROR={counts['ERROR']} "
        f"SKIP={counts['SKIP']} NOT_RUN={counts['NOT_RUN']} BLOCKED={counts['BLOCKED']}",
        f"- 结论：{'全部通过' if ok else '存在 FAIL/ERROR（非零退出）'}",
        "",
        "## 说明",
        "",
        "- 本套件是**纯软件协议测试**（预注册锁定、样本规划确定性、标注工具链演练），",
        "  不依赖真实人工数据，可进入公开 CI；",
        "- 真实人工简历、授权文件与标注原文**不得**进入 GitHub Actions 公开 Runner；",
        "- 本结果不能替代 Phase4-3B / Phase5-x / Phase6 历史回归，也**不构成** H2 通过。",
        "",
        "## 运行模块（确定性顺序）",
        "",
    ]
    for m in modules:
        lines.append(f"- `{m}`")
    lines += ["", "## 逐项结果", "",
              "| 模块 | 用例 | 状态 | 耗时(ms) | 说明 |", "|---|---|---|---|---|"]
    for r in result.records:
        det = (r["detail"] or "").replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(f"| {r['module']} | {r['test']} | {r['status']} | {r['ms']} | {det} |")
    if load_errors:
        lines += ["", "## 模块导入失败（登记，不静默）", ""]
        for le in load_errors:
            lines.append(f"- `{le['module']}`: {le['error']}")
    (REPORT_DIR / "11-phase7-regression.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nPASS={counts['PASS']} FAIL={counts['FAIL']} ERROR={counts['ERROR']} "
          f"SKIP={counts['SKIP']} NOT_RUN={counts['NOT_RUN']} BLOCKED={counts['BLOCKED']}  ({elapsed}s)")
    print(f"wrote {REPORT_DIR / '11-phase7-regression.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
