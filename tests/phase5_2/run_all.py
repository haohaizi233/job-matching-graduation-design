# -*- coding: utf-8 -*-
"""Phase5-2 端到端测试运行器（stdlib unittest；合成夹具，无真实简历/无真人信息）。

用法:
    python tests/phase5_2/run_all.py          # 全部
    python tests/phase5_2/run_all.py T3       # 只跑 T3 组

输出: reports/phase5-2/test-results.json / .md
退出码: 0 全部通过 / 1 存在 FAIL/ERROR / 2 运行器错误（未知分组、0 项测试）

分组唯一来源是 TEST_MODULES 注册表：
  T1  数据库 Schema/约束/索引/迁移/事务（B1）
  T2  认证与权限链路 A（B2）
  T3  简历与画像链路 B（B3）
  T4  岗位与推荐闭环链路 C（B4）
  T5  数据隔离链路 D（B2/B6）
  T6  异常事务链路 E（B4/B6）
  T7  PostgreSQL 集成（B1；无 PG 环境显式 NOT_RUN/skip，不计 PASS）

纪律（禁止硬编码假 PASS）：
  * 每步真实执行测试并如实记录 总数/实跑/失败/跳过；
  * 收集到 0 项测试一律判为运行器错误（退出码 2）；
  * skip（NOT_RUN / ENV_INCOMPATIBLE）不计入 PASS；
  * 部分运行写独立报告，不覆盖全量报告。
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
    ("T1", "test_t1_database.T1MigrationGates", "数据库 Schema/约束/迁移/事务"),
    ("T2", "test_t2_auth.T2AuthChain", "认证与权限（链路A）"),
    ("T3", "test_t3_profile.T3ResumeAndProfile", "简历与画像（链路B）"),
    ("T4", "test_t4_jobs_reco.T4JobsAndRecommendations", "岗位与推荐闭环（链路C）"),
    ("T5", "test_t5_isolation.T5DataIsolation", "数据隔离（链路D）"),
    ("T6", "test_t6_failures.T6FailureTransactions", "异常事务（链路E）"),
    ("T7", "test_t7_pg_integration.T7PostgreSQLIntegration", "PostgreSQL 集成"),
]
GROUPS = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]


def _walk(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _walk(item)
        else:
            yield item


def load_suite(only: str = ""):
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


def _aggregate(records: list[dict], modules: list[str]) -> tuple[dict, dict]:
    """记录 -> 分组汇总 + 聚合一致性断言（与 core_ci 运行器同口径）。"""
    groups: dict[str, dict] = {}
    for tag in GROUPS:
        rows = [r for r in records if r["group"] == tag]
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
    totals = {"tests": len(records),
              "pass": sum(1 for r in records if r["status"] == "PASS"),
              "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
              "skip": sum(1 for r in records if r["status"] == "SKIP")}
    checks = {
        "sum_groups_total_eq_totals_tests":
            sum(g["total"] for g in groups.values()) == totals["tests"],
        "sum_groups_pass_eq_totals_pass":
            sum(g["pass"] for g in groups.values()) == totals["pass"],
        "all_records_have_legal_group":
            all(r["group"] in GROUPS for r in records),
        "no_empty_run": totals["tests"] > 0,
        "modules_registered_non_empty": bool(modules),
    }
    return {"groups": groups, "totals": totals}, checks


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
        super().addSuccess(test)
        self._add(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL", self._exc_info_to_string(err, test)[-1200:])

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR", self._exc_info_to_string(err, test)[-1200:])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, "SKIP", reason)


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

    modules = [t[1] for t in TEST_MODULES if not only or t[0] == only]
    agg, checks = _aggregate(result.records, modules)
    groups, totals = agg["groups"], agg["totals"]
    ok = (not (result.failures or result.errors)) and all(checks.values())

    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = "UNKNOWN"

    out = {
        "generated_by": "tests/phase5_2/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds,
        "ok": ok,
        "mode": "full" if not only else f"partial:{only}",
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "commit": commit},
        "totals": totals, "groups": groups, "consistency": checks,
        "records": result.records,
    }
    out_dir = ROOT / "reports" / "phase5-2"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "test-results" if not only else f"test-results-{only}"
    (out_dir / f"{stem}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    lines = ["# Phase5-2 端到端测试报告", "",
             f"- 生成时间：{out['created_at']} ｜ 模式：{out['mode']} ｜ 耗时 {seconds}s",
             f"- 总计 {totals['tests']} 项：PASS={totals['pass']} FAIL={totals['fail']} "
             f"SKIP={totals['skip']} ｜ ok={ok}",
             "- SKIP = NOT_RUN / ENV_INCOMPATIBLE，**不计入 PASS**；"
             "全部夹具为合成数据，不代表真实中文招聘场景模型效果。", "",
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
    print(f"=== Phase5-2 端到端 {seconds}s | PASS={totals['pass']} "
          f"FAIL={totals['fail']} SKIP={totals['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
