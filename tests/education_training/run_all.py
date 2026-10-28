# -*- coding: utf-8 -*-
"""第四阶段 4.2 学历训练/推理测试运行器（stdlib unittest）。

用法:
    python tests/education_training/run_all.py          # 全部
    python tests/education_training/run_all.py E4       # 只跑 E4

输出:
    控制台逐项 PASS/FAIL + reports/education-training/education-tests.json
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
sys.path.insert(0, str(ROOT / "scripts" / "education_training"))
sys.path.insert(0, str(HERE))

TEST_MODULES = [
    ("E1", "test_e1_data_integrity", "原始数据哈希 / 切分互斥 / 金标准隔离"),
    ("E2", "test_e2_labels", "六维标签映射 / 可逆 / 互斥规则"),
    ("E3", "test_e3_fit_scope", "TF-IDF 与字符词表只在 Train 上 fit"),
    ("E4", "test_e4_models", "正反向传播 / 参数更新 / 保存重载 / 可复现"),
    ("E5", "test_e5_inference", "推理接口 / 异常输入 / 无标签依赖"),
    ("E6", "test_e6_experiments", "实验关联 / 4.1 产物保护 / pip check"),
]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _group_of(self, test) -> str:
        m = re.match(r"^E(\d)", type(test).__name__)
        return f"E{m.group(1)}" if m else "E?"

    def _add(self, test, status: str, detail: str):
        self.records.append({"group": self._group_of(test), "test": str(test),
                             "status": status, "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, "PASS", "")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL", self._exc_info_to_string(err, test)[-1500:])

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR", self._exc_info_to_string(err, test)[-1500:])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, "SKIP", reason)


def main() -> int:
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tag, mod, _title in TEST_MODULES:
        if only and tag != only:
            continue
        suite.addTests(loader.loadTestsFromName(mod))

    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)

    records = result.records
    summary = {}
    for tag, mod, title in TEST_MODULES:
        rows = [r for r in records if r["group"] == tag]
        if not rows:
            continue
        summary[tag] = {
            "title": title, "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "skip": sum(1 for r in rows if r["status"] == "SKIP"),
        }
    ok = not (result.failures or result.errors)
    out = {
        "generated_by": "tests/education_training/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds, "ok": ok,
        "totals": {"tests": len(records),
                   "pass": sum(1 for r in records if r["status"] == "PASS"),
                   "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
                   "skip": sum(1 for r in records if r["status"] == "SKIP")},
        "groups": summary, "records": records,
    }
    out_dir = ROOT / "reports" / "education-training"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "education-tests.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"=== 测试完成 {seconds}s | PASS={out['totals']['pass']} "
          f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
