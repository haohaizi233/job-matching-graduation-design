# -*- coding: utf-8 -*-
"""Phase6 统一测试运行器（stdlib unittest，与 tests/phase4_3b/run_all.py 同风格）。

任务（R6.1）：
  * 自动发现 tests/phase6 下全部用例（test_*.py），确定性（字典序）运行顺序；
  * 逐项记录真实结果与执行耗时；不静默吞异常；
  * 输出 JSON / Markdown；正确统计 PASS/FAIL/ERROR/SKIP；
  * 测试失败必须非零退出；
  * 可在 Python 3.13 本地执行；跨环境不兼容明确报告（记录解释器版本）。

用法:
    py -3.13 tests/phase6/run_all.py            # 全部
    py -3.13 tests/phase6/run_all.py reranker   # 只跑模块名含 reranker 的

输出: reports/phase6-r/06-phase6-regression.{json,md}
退出码: 0 = 无 FAIL/ERROR；1 = 存在 FAIL/ERROR
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase6-r"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def discover_modules() -> list[str]:
    """确定性发现 test_*.py（字典序），返回模块名（不含扩展名）。"""
    mods = sorted(p.stem for p in HERE.glob("test_*.py") if p.is_file())
    return mods


class RecordingResult(unittest.TextTestResult):
    """逐项记录结果 + 耗时；不吞异常（addFailure/addError 均落盘）。"""

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
        except Exception as e:  # noqa: BLE001 —— 模块导入失败必须登记，不静默
            load_errors.append({"module": mod, "error": f"{type(e).__name__}: {e}"})

    t0 = time.time()
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    result = runner.run(suite)
    elapsed = round(time.time() - t0, 3)

    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for r in result.records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for le in load_errors:
        counts["ERROR"] += 1
        result.records.append({"module": le["module"], "test": f"<import {le['module']}>",
                               "status": "ERROR", "ms": 0.0, "detail": le["error"]})

    ok = counts["FAIL"] == 0 and counts["ERROR"] == 0
    payload = {
        "generated_by": "tests/phase6/run_all.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "modules": modules,
        "counts": counts,
        "tests_run": result.testsRun,
        "seconds": elapsed,
        "ok": ok,
        "load_errors": load_errors,
        "records": result.records,
    }
    (REPORT_DIR / "06-phase6-regression.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase6 统一回归结果",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 解释器：Python {payload['python']} / {payload['platform']}"
        "（本地 3.13；GitHub Core CI 固定 3.11，跨版本兼容性需另行验证）",
        f"- 运行用例：{result.testsRun}，耗时 {elapsed}s",
        f"- PASS={counts['PASS']} FAIL={counts['FAIL']} "
        f"ERROR={counts['ERROR']} SKIP={counts['SKIP']}",
        f"- 结论：{'全部通过' if ok else '存在 FAIL/ERROR（非零退出）'}",
        "",
        "## 运行模块（确定性顺序）",
        "",
    ]
    for m in modules:
        lines.append(f"- `{m}`")
    lines += [
        "",
        "## 逐项结果",
        "",
        "| 模块 | 用例 | 状态 | 耗时(ms) | 说明 |",
        "|---|---|---|---|---|",
    ]
    for r in result.records:
        det = (r["detail"] or "").replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(f"| {r['module']} | {r['test']} | {r['status']} | {r['ms']} | {det} |")
    if load_errors:
        lines += ["", "## 模块导入失败（登记，不静默）", ""]
        for le in load_errors:
            lines.append(f"- `{le['module']}`: {le['error']}")
    (REPORT_DIR / "06-phase6-regression.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nPASS={counts['PASS']} FAIL={counts['FAIL']} "
          f"ERROR={counts['ERROR']} SKIP={counts['SKIP']}  ({elapsed}s)")
    print(f"wrote {REPORT_DIR / '06-phase6-regression.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
