# -*- coding: utf-8 -*-
"""Phase5-1R 整改回归测试运行器（stdlib unittest，与既有测试套件一致）。

用法:
    python tests/phase5_1r/run_all.py            # 全部测试
    python tests/phase5_1r/run_all.py R2         # 只跑 R2 组

输出:
    控制台逐项 PASS/FAIL + reports/phase5-1r/test-results.json / test-results.md
    + reports/phase5-1r/positive-flow-validation.json（链路 A/B/C 正向验证摘要）
退出码: 0 = 全部通过，1 = 存在 FAIL/ERROR

纪律：
  * 只用纯合成工程夹具，不写真实 Gold 目录、不生成真实 H2 PASS；
  * 不触碰 data/raw、data/independent_eval/frozen、models/（R1/R2 有前后指纹校验）；
  * 严禁跳过失败测试或降低既有门禁标准。
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
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TEST_MODULES = [
    ("R1", "test_r1_gold_freeze",
     "Gold 冻结循环门禁修复（F-001，兼 F-003/F-004 CLI 链路）"),
    ("R2", "test_r2_annotation_quality",
     "标注独立性 / 仲裁 / 完成状态门禁（F-002、F-003）"),
    ("R3", "test_r3_business_constraints",
     "毕业届别 / 工作经验约束判定（F-005、F-006）"),
    ("R4", "test_r4_api_boundary",
     "API 边界与安全加固（F-007）"),
    ("R5", "test_r5_metrics_input",
     "独立评估输入物化与非法输入拒绝（F-009）"),
    ("R6", "test_r6_e2e_chains",
     "端到端正向链路 B 简历岗位推荐 / 链路 C 模型错误与降级"),
]

# 三条端到端正向链路 -> 测试类（用于 positive-flow-validation.json）
CHAIN_GROUPS = {
    "chain_a_gold_freeze_engineering": ["R1FreezeCliChain", "R1PreFreezeGate",
                                        "R1PostFreezeGate"],
    "chain_b_resume_job_recommendation": ["ChainBResumeToRanking"],
    "chain_c_model_error_and_degradation": ["ChainCModelErrorsAndDegradation"],
}


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _group_of(self, test) -> str:
        m = re.match(r"^(R\d+)", type(test).__name__)
        return m.group(1) if m else "R?"

    def _add(self, test, status: str, detail: str):
        self.records.append({"group": self._group_of(test),
                             "class": type(test).__name__,
                             "test": str(test), "status": status, "detail": detail})

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


def _filter_suite(suite: unittest.TestSuite, tag: str) -> unittest.TestSuite:
    out = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            out.addTests(_filter_suite(test, tag))
        elif type(test).__name__.upper().startswith(tag):
            out.addTest(test)
    return out


def main() -> int:
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    seen: set[str] = set()
    for tag, mod, _title in TEST_MODULES:
        if only and tag != only:
            continue
        if mod in seen:
            continue
        seen.add(mod)
        loaded = loader.loadTestsFromName(mod)
        suite.addTests(_filter_suite(loaded, tag) if only else loaded)

    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)

    records = result.records
    summary: dict[str, dict] = {}
    for tag, mod, title in TEST_MODULES:
        rows = [r for r in records if r["group"] == tag]
        if not rows:
            continue
        summary[tag] = {
            "title": title, "module": mod,
            "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "skip": sum(1 for r in rows if r["status"] == "SKIP"),
        }
    ok = not (result.failures or result.errors)
    out = {
        "generated_by": "tests/phase5_1r/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds, "ok": ok,
        "totals": {"tests": len(records),
                   "pass": sum(1 for r in records if r["status"] == "PASS"),
                   "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
                   "skip": sum(1 for r in records if r["status"] == "SKIP")},
        "groups": summary, "records": records,
    }
    out_dir = ROOT / "reports" / "phase5-1r"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "test-results.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- 三条端到端正向链路摘要（链路 A 工程模拟，不得表述为真实 H2 PASS）
    chains = {}
    for chain, classes in CHAIN_GROUPS.items():
        rows = [r for r in records if r["class"] in classes]
        chains[chain] = {
            "test_classes": classes,
            "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "status": ("PASS" if rows and all(r["status"] == "PASS" for r in rows)
                       else ("FAIL" if any(r["status"] in ("FAIL", "ERROR")
                                           for r in rows) else "NOT_RUN")),
        }
    positive = {
        "generated_by": "tests/phase5_1r/run_all.py",
        "created_at": out["created_at"],
        "fixture_policy": ("纯合成工程夹具 + 临时隔离目录；只证明软件流程可运行，"
                           "不得作为真实 Gold / 真实 H2 通过证据"),
        "real_h2_status": "BLOCKED（真实中文简历、人工标签与合法盲测集未完成）",
        "chains": chains,
    }
    with open(out_dir / "positive-flow-validation.json", "w", encoding="utf-8",
              newline="\n") as f:
        json.dump(positive, f, ensure_ascii=False, indent=2)
        f.write("\n")

    lines = [
        "# Phase5-1R 整改回归测试报告", "",
        f"- 生成时间：{out['created_at']} ｜ 耗时：{seconds}s",
        f"- 总计 {out['totals']['tests']} 项：PASS={out['totals']['pass']} "
        f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} ｜ ok={ok}", "",
        "| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |",
        "|---|---|---|---|---|---|",
    ]
    for tag, mod, title in TEST_MODULES:
        if tag in summary:
            s = summary[tag]
            lines.append(f"| {tag} | {s['title']} | {s['total']} | {s['pass']} | "
                         f"{s['fail']} | {s['skip']} |")
    lines += ["", "## 端到端正向链路", "",
              "| 链路 | 状态 | 通过/总数 |", "|---|---|---|"]
    for chain, info in chains.items():
        lines.append(f"| {chain} | {info['status']} | "
                     f"{info['pass']}/{info['total']} |")
    lines += ["", "说明：R1–R6 覆盖 F-001–F-009 修复回归、正向/异常/边界路径、",
              "模型降级、数据保护与冻结不可变性；全部使用合成夹具；",
              "链路 A 为冻结工程模拟，**不构成真实 H2 PASS**（H2 维持 BLOCKED）。", ""]
    (out_dir / "test-results.md").write_text("\n".join(lines), encoding="utf-8",
                                             newline="\n")
    print(f"=== Phase5-1R 测试完成 {seconds}s | PASS={out['totals']['pass']} "
          f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
