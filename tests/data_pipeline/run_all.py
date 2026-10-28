# -*- coding: utf-8 -*-
"""数据质量门禁测试运行器（stdlib unittest，不引入 pytest 等新依赖）。

用法：
    python tests/data_pipeline/run_all.py            # 全部门禁
    python tests/data_pipeline/run_all.py G3         # 只跑 G3

输出：
    控制台逐项 PASS/FAIL + reports/data-quality-gates.json
    退出码：0 = 全部通过；1 = 存在 FAIL
"""
from __future__ import annotations

import json
import re
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "data_pipeline"))
sys.path.insert(0, str(HERE))

GATE_MODULES = [
    ("G1", "test_g1_raw_unchanged"),
    ("G2", "test_g2_schema_constraints"),
    ("G3", "test_g3_leakage_guard"),
    ("G4", "test_g4_split_disjoint"),
    ("G5", "test_g5_reproducibility"),
    ("G6", "test_g6_loadability"),
    ("G7", "test_g7_resource_guard"),
]

GATE_TITLES = {
    "G1": "原始数据不变",
    "G2": "字段约束",
    "G3": "目标泄漏防护",
    "G4": "切分互斥",
    "G5": "结果可复现性",
    "G6": "数据可加载",
    "G7": "资源约束",
}


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _gate_of(self, test) -> str:
        m = re.match(r"^G(\d)", type(test).__name__)
        return f"G{m.group(1)}" if m else "G?"

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"gate": self._gate_of(test), "test": str(test),
                             "status": "PASS", "detail": ""})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"gate": self._gate_of(test), "test": str(test),
                             "status": "FAIL",
                             "detail": self._exc_info_to_string(err, test)[-1500:]})

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({"gate": self._gate_of(test), "test": str(test),
                             "status": "ERROR",
                             "detail": self._exc_info_to_string(err, test)[-1500:]})


def main() -> int:
    only = sys.argv[1].upper() if len(sys.argv) > 1 else None
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for gate, mod in GATE_MODULES:
        if only and gate != only:
            continue
        suite.addTests(loader.loadTestsFromName(mod))

    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    t0 = time.time()
    result = runner.run(suite)
    elapsed = round(time.time() - t0, 2)

    by_gate: dict[str, dict] = {}
    for gate in GATE_TITLES:
        recs = [r for r in result.records if r["gate"] == gate]
        if not recs:
            continue
        by_gate[gate] = {
            "title": GATE_TITLES[gate],
            "total": len(recs),
            "passed": sum(1 for r in recs if r["status"] == "PASS"),
            "failed": sum(1 for r in recs if r["status"] != "PASS"),
            "ok": all(r["status"] == "PASS" for r in recs),
            "tests": recs,
        }

    payload = {
        "generated_by": "tests/data_pipeline/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_seconds": elapsed,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "ok": result.wasSuccessful(),
        "gates": by_gate,
    }
    out = ROOT / "reports" / "data-quality-gates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print("\n" + "=" * 72)
    for gate, info in by_gate.items():
        mark = "PASS" if info["ok"] else "FAIL"
        print(f"[{mark}] {gate} {info['title']}: {info['passed']}/{info['total']} 通过")
    print("=" * 72)
    print(f"总计 {result.testsRun} 项，失败 {len(result.failures)}，错误 {len(result.errors)}"
          f"，耗时 {elapsed}s -> {out}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
