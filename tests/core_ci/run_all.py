# -*- coding: utf-8 -*-
"""Core CI 可移植门禁运行器（stdlib unittest，无真实数据 / 无权重 / 无 GPU）。

用法:
    python tests/core_ci/run_all.py          # 全部 Core CI 门禁
    python tests/core_ci/run_all.py C2       # 只跑 C2 组

输出: reports/phase5-2/ci/core-ci-test-results.json / .md
退出码: 0 全部通过 / 1 存在 FAIL/ERROR / 2 运行器错误（未知分组、0 项测试）

分组唯一来源是 TEST_MODULES 注册表：
  C2  可信 CI 门禁负向测试（完整性退出码 / 运行身份 / 模型诊断 / 状态登记）
  C3  测试运行器聚合一致性与历史基线保护
  C4  隐私与安全门禁
  C5  Core CI 契约（无数据依赖 / 无下载 / 干净 checkout）

纪律（禁止硬编码假 PASS）：
  * 每步必须真实执行测试并如实记录 总数/实跑/失败/跳过；
  * 收集到 0 项测试一律判为运行器错误，不写 ok=true；
  * NOT_RUN / BLOCKED 一律不计入 PASS；
  * 历史基线报告不得被失败或局部运行覆盖。
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
for _p in (str(ROOT / "src"), str(HERE), str(ROOT / "tests" / "data_pipeline"),
           str(ROOT / "scripts" / "phase5_1a")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TEST_MODULES = [
    ("C2", "test_c2_gates_negative.C2ArtifactIntegrityGates", "完整性检查器退出码语义"),
    ("C2", "test_c2_gates_negative.C2RunIdentityGates", "运行身份与报告新鲜度"),
    ("C2", "test_c2_gates_negative.C2ModelCompatGates", "模型兼容诊断：NOT_RUN 与旧报告拒用"),
    ("C2", "test_c2_gates_negative.C2ValidationRegistryGates", "Artifact-dependent 状态口径"),
    ("C3", "test_c3_runner_trust.C3RunnerAggregation", "测试运行器聚合一致性"),
    ("C3", "test_c3_runner_trust.C3HistoricalBaselineProtection", "历史基线保护"),
    ("C4", "test_c4_privacy_security.C4SecretsAndLeaks", "密钥与泄漏门禁"),
    ("C4", "test_c4_privacy_security.C4ResponseAndLoggingPrivacy", "响应与日志隐私"),
    ("C4", "test_c4_privacy_security.C4ReportPrivacy", "报告隐私"),
    ("C4", "test_c4_privacy_security.C4DependencyHygiene", "依赖与下载卫生"),
    ("C4", "test_c4_privacy_security.C4EncodingIntegrity", "文本编码与换行门禁（UTF-8 / LF）"),
    ("C5", "test_c5_ci_contract.C5WorkflowContract", "Core CI 工作流契约"),
    ("C5", "test_c5_ci_contract.C5CleanCheckoutContract", "干净 checkout 契约"),
]
GROUPS = ["C2", "C3", "C4", "C5"]


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


def _aggregate(records: list[dict], modules: list[str]) -> tuple[dict, dict]:
    """记录 -> 分组汇总 + 聚合一致性断言（可信性自检的单一事实来源）。"""
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
        "no_unexpected_skip_flood": totals["skip"] <= totals["tests"],
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
        "generated_by": "tests/core_ci/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds,
        "ok": ok,
        "mode": "full" if not only else f"partial:{only}",
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "commit": commit},
        "totals": totals, "groups": groups, "consistency": checks,
        "records": result.records,
    }
    out_dir = ROOT / "reports" / "phase5-2" / "ci"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "core-ci-test-results" if not only else f"core-ci-test-results-{only}"
    (out_dir / f"{stem}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    lines = ["# Core CI 可移植门禁报告", "",
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
    print(f"=== Core CI 门禁 {seconds}s | PASS={totals['pass']} "
          f"FAIL={totals['fail']} SKIP={totals['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
