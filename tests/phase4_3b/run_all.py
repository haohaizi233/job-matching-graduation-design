# -*- coding: utf-8 -*-
"""Phase4-3B 机器学习研究测试运行器（stdlib unittest，与 tests/phase4_3a 同风格）。

用法:
    python tests/phase4_3b/run_all.py            # 全部测试
    python tests/phase4_3b/run_all.py P5         # 只跑 P5

输出:
    控制台逐项 PASS/FAIL + reports/phase4-3b/test-results.json
    退出码 0 = 全部通过，1 = 存在 FAIL
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
sys.path.insert(0, str(ROOT / "scripts" / "phase4_3b"))
sys.path.insert(0, str(HERE))

TEST_MODULES = [
    ("P1", "test_p1_dataset_protocol", "数据集协议 / 代理标签边界 / Gold 门禁语义"),
    ("P2", "test_p2_split_leakage", "切分互斥 / 文本哈希重叠 / 归一化与负采样泄漏"),
    ("P3", "test_p3_model_registry", "模型登记 / checkpoint 真实存在 / 缺失与不兼容处理"),
    ("P4", "test_p4_retrieval_baseline", "TF-IDF / BM25 召回基线行为"),
    ("P5", "test_p5_embedding_contract", "TextEncoder 契约：空文本 / 截断 / 批量 / 可复现"),
    ("P6", "test_p6_reranker_contract", "精排契约：批量 / 截断 / 缺模型显式失败"),
    ("P7", "test_p7_feature_fusion", "硬/软约束、可解释明细、权重来源登记"),
    ("P8", "test_p8_evaluation_metrics", "排序指标正确性 / 小样本与空样本 / 指标适用性"),
    ("P9", "test_p9_reproducibility", "同输入同输出 / 固定种子 / 推理不改权重"),
    ("P10", "test_p10_privacy_guards", "日志与导出不落简历原文 / 冻结数据不可修改"),
]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _group_of(self, test) -> str:
        m = re.match(r"^P(\d+)", type(test).__name__)
        return f"P{m.group(1)}" if m else "P?"

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
    only = sys.argv[1] if len(sys.argv) > 1 else None
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for group, module, _desc in TEST_MODULES:
        if only and group != only:
            continue
        suite.addTests(loader.loadTestsFromName(module))

    t0 = time.time()
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    result = runner.run(suite)
    elapsed = round(time.time() - t0, 3)

    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for r in result.records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    out_dir = ROOT / "reports" / "phase4-3b"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "tests/phase4_3b/run_all.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "groups": [{"group": g, "module": m, "description": d} for g, m, d in TEST_MODULES],
        "counts": counts,
        "tests_run": result.testsRun,
        "seconds": elapsed,
        "ok": counts["FAIL"] == 0 and counts["ERROR"] == 0,
        "records": result.records,
    }
    with open(out_dir / "test-results.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = [
        "# Phase4-3B 测试结果",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 运行用例：{result.testsRun}，耗时 {elapsed}s",
        f"- PASS={counts['PASS']} FAIL={counts['FAIL']} ERROR={counts['ERROR']} SKIP={counts['SKIP']}",
        "",
        "| 组 | 模块 | 说明 |",
        "|---|---|---|",
    ]
    for g, m, d in TEST_MODULES:
        lines.append(f"| {g} | `{m}` | {d} |")
    with open(out_dir / "test-results.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nPASS={counts['PASS']} FAIL={counts['FAIL']} "
          f"ERROR={counts['ERROR']} SKIP={counts['SKIP']}  ({elapsed}s)")
    print(f"wrote {out_dir / 'test-results.json'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
