# -*- coding: utf-8 -*-
"""Phase5-1A 门禁自检运行器（stdlib unittest）。

用法:
    python tests/phase5_1a/run_all.py          # 全部门禁自检
    python tests/phase5_1a/run_all.py A2       # 只跑 A2 组

输出: reports/phase5-1a/test-results.json / test-results.md
退出码: 0 全部通过 / 1 存在 FAIL/ERROR / 2 运行器错误（未知分组、0 项测试）

分组唯一来源是 TEST_MODULES 注册表（按测试类归属登记），与类名前缀无关。
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
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TEST_MODULES = [
    ("A1", "test_a1_a7_gates.A1RunnerTrust", "测试可信性：分组 / 0 测试 / 聚合一致性"),
    ("A2", "test_a1_a7_gates.A2DependencyDirection", "架构边界：依赖方向守卫"),
    ("A2", "test_a1_a7_gates.A2SharedRules", "架构边界：共用规则单一实现与兼容层"),
    ("A4", "test_a1_a7_gates.A4ModelErrorTaxonomy", "模型兼容：加载失败分类与历史权重保护"),
    ("A6", "test_a1_a7_gates.A6HistoricalBaseline", "测试回归：历史基线保护与旧套件运行器可信性"),
    ("A7", "test_a1_a7_gates.A7ConfigAndDocs", "文档交付：配置默认值与部署安全声明"),
]
GROUPS = ["A1", "A2", "A4", "A6", "A7"]


def _walk(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _walk(item)
        else:
            yield item


def load_suite(only: str):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    group_map: dict[str, str] = {}
    seen: set[str] = set()
    for tag, target, _title in TEST_MODULES:
        if only and tag != only:
            continue
        if target in seen:
            continue
        seen.add(target)
        tests = list(_walk(loader.loadTestsFromName(target)))
        if not tests:
            raise ValueError(f"目标 {target}（组 {tag}）未产生任何测试用例")
        for t in tests:
            group_map[t.id()] = tag
        suite.addTests(tests)
    return suite, group_map


class _Recording(unittest.TextTestResult):
    group_map: dict = {}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records = []

    def _add(self, test, status, detail=""):
        self.records.append({"group": self.group_map.get(test.id(), "UNKNOWN"),
                             "class": type(test).__name__, "test_id": test.id(),
                             "status": status, "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test); self._add(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL", self._exc_info_to_string(err, test)[-1200:])

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR", self._exc_info_to_string(err, test)[-1200:])

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._add(test, "SKIP", reason)


def main() -> int:
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    if only and only not in GROUPS:
        print(f"未知测试分组 {only!r}；可用分组: {', '.join(GROUPS)}", file=sys.stderr)
        return 2
    try:
        suite, group_map = load_suite(only)
    except ValueError as e:
        print(f"测试收集错误: {e}", file=sys.stderr)
        return 2
    if not list(_walk(suite)):
        print("收集到 0 项测试，判定为运行器错误", file=sys.stderr)
        return 2

    _Recording.group_map = group_map
    runner = unittest.TextTestRunner(verbosity=2, resultclass=_Recording)
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)
    if not result.records:
        print("执行 0 项测试，判定为运行器错误", file=sys.stderr)
        return 2

    groups = {}
    for tag in GROUPS:
        rows = [r for r in result.records if r["group"] == tag]
        if not rows:
            continue
        title = next(t for tg, _target, t in TEST_MODULES if tg == tag)
        groups[tag] = {
            "title": title,
            "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "skip": sum(1 for r in rows if r["status"] == "SKIP"),
        }
    totals = {"tests": len(result.records),
              "pass": sum(1 for r in result.records if r["status"] == "PASS"),
              "fail": sum(1 for r in result.records if r["status"] in ("FAIL", "ERROR")),
              "skip": sum(1 for r in result.records if r["status"] == "SKIP")}
    checks = {
        "sum_groups_total_eq_totals_tests":
            sum(g["total"] for g in groups.values()) == totals["tests"],
        "sum_groups_pass_eq_totals_pass":
            sum(g["pass"] for g in groups.values()) == totals["pass"],
        "all_records_have_legal_group":
            all(r["group"] in GROUPS for r in result.records),
        "no_empty_run": totals["tests"] > 0,
    }
    ok = (not (result.failures or result.errors)) and all(checks.values())
    out = {
        "generated_by": "tests/phase5_1a/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds, "ok": ok, "mode": "full" if not only else f"partial:{only}",
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                                 capture_output=True, text=True,
                                                 timeout=10).stdout.strip()},
        "totals": totals, "groups": groups, "consistency": checks,
        "records": result.records,
    }
    out_dir = ROOT / "reports" / "phase5-1a"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "test-results" if not only else f"test-results-{only}"
    (out_dir / f"{stem}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8", newline="\n")
    lines = ["# Phase5-1A 门禁自检报告", "",
             f"- 生成时间：{out['created_at']} ｜ 模式：{out['mode']}",
             f"- 总计 {totals['tests']} 项：PASS={totals['pass']} FAIL={totals['fail']} "
             f"SKIP={totals['skip']} ｜ ok={ok}", "",
             "| 组 | 内容 | 总数 | 通过 | 失败 | 跳过 |", "|---|---|---|---|---|---|"]
    for tag in GROUPS:
        if tag in groups:
            g = groups[tag]
            lines.append(f"| {tag} | {g['title']} | {g['total']} | {g['pass']} | "
                         f"{g['fail']} | {g['skip']} |")
    lines += ["", "## 聚合一致性断言", "", "| 断言 | 结果 |", "|---|---|"]
    for k, v in checks.items():
        lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    lines.append("")
    (out_dir / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"=== Phase5-1A 门禁自检 {seconds}s | PASS={totals['pass']} "
          f"FAIL={totals['fail']} SKIP={totals['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
