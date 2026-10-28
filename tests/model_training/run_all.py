# -*- coding: utf-8 -*-
"""第四阶段 4.1 模型训练/推理测试运行器（stdlib unittest，不引入 pytest）。

用法:
    python tests/model_training/run_all.py            # 全部测试
    python tests/model_training/run_all.py T4         # 只跑 T4

输出:
    控制台逐项 PASS/FAIL + reports/model-training/model-tests.json
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
sys.path.insert(0, str(ROOT / "scripts" / "model_training"))
sys.path.insert(0, str(HERE))

TEST_MODULES = [
    ("T1", "test_t1_feature_policy", "特征黑名单 / 无标签依赖"),
    ("T2", "test_t2_split_protocol", "切分不变 / 协议合规 / 不碰 test"),
    ("T3", "test_t3_models", "模型训练 / GPU 反传 / 重载 / 可复现"),
    ("T4", "test_t4_ranknet_pairs", "RankNet 偏好对方向与同分处理"),
    ("T5", "test_t5_inference", "独立推理与稳定排序"),
    ("T6", "test_t6_integrity_privacy", "原始数据哈希 / 日志隐私"),
]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _group_of(self, test) -> str:
        m = re.match(r"^T(\d)", type(test).__name__)
        return f"T{m.group(1)}" if m else "T?"

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
            "title": title,
            "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "skip": sum(1 for r in rows if r["status"] == "SKIP"),
        }
    ok = not (result.failures or result.errors)
    out = {
        "generated_by": "tests/model_training/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds,
        "ok": ok,
        "totals": {"tests": len(records),
                   "pass": sum(1 for r in records if r["status"] == "PASS"),
                   "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
                   "skip": sum(1 for r in records if r["status"] == "SKIP")},
        "groups": summary,
        "records": records,
    }
    out_dir = ROOT / "reports" / "model-training"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "model-tests.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"=== 测试完成 {seconds}s | PASS={out['totals']['pass']} "
          f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
