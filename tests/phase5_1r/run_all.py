# -*- coding: utf-8 -*-
"""Phase5-1R 整改回归测试运行器（stdlib unittest，与既有测试套件一致）。

用法:
    python tests/phase5_1r/run_all.py            # 全部测试（更新正式全量报告）
    python tests/phase5_1r/run_all.py R5         # 只跑 R5 组（写独立的分组报告）

输出:
    控制台逐项 PASS/FAIL
    全量运行: reports/phase5-1r/test-results.json / test-results.md
             + reports/phase5-1r/positive-flow-validation.json（链路 A/B/C 正向验证摘要）
    分组运行: reports/phase5-1r/test-results-<GROUP>.json / test-results-<GROUP>.md
              （分组运行**不覆盖**正式全量报告）
退出码:
    0 = 全部通过
    1 = 存在 FAIL / ERROR（或聚合一致性断言失败）
    2 = 运行器用法或收集错误（未知分组、0 项测试、模块未产生任何用例等）

分组规则（Phase5-1A 修订）:
    分组**唯一来源**是下方 `TEST_MODULES` 注册表，按“测试用例从哪个模块加载”归属分组，
    与测试类名前缀无关（test_r5_metrics_input 的类名为 R9*，test_r6_e2e_chains
    的类名为 ChainB*/ChainC*，均正确归属 R5/R6）。

纪律：
  * 只用纯合成工程夹具，不写真实 Gold 目录、不生成真实 H2 PASS；
  * 不触碰 data/raw、data/independent_eval/frozen、models/（R1/R2 有前后指纹校验）；
  * 严禁跳过失败测试或降低既有门禁标准。
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

# 稳定的模块映射：module -> group（分组唯一来源）
MODULE_TO_GROUP = {mod: tag for tag, mod, _title in TEST_MODULES}
GROUPS = [tag for tag, _mod, _title in TEST_MODULES]

# 三条端到端正向链路 -> 测试类（用于 positive-flow-validation.json）
CHAIN_GROUPS = {
    "chain_a_gold_freeze_engineering": ["R1FreezeCliChain", "R1PreFreezeGate",
                                        "R1PostFreezeGate"],
    "chain_b_resume_job_recommendation": ["ChainBResumeToRanking"],
    "chain_c_model_error_and_degradation": ["ChainCModelErrorsAndDegradation"],
}


def _walk(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _walk(item)
        else:
            yield item


def _environment_info() -> dict:
    """运行环境元信息（Python 版本 / 平台 / 关键依赖版本 / commit SHA）。"""
    deps = {}
    for name in ("fastapi", "pydantic", "httpx", "uvicorn", "numpy", "scipy",
                 "sklearn", "joblib", "pandas", "torch", "yaml"):
        try:
            mod = __import__(name)
            deps[name] = getattr(mod, "__version__", "unknown")
        except Exception as exc:  # 依赖缺失是合法状态，必须如实记录
            deps[name] = "NOT_INSTALLED(%s)" % type(exc).__name__
    commit, dirty = "UNKNOWN", "UNKNOWN"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
            text=True, timeout=10, check=False).stdout.strip() or "UNKNOWN"
        st = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True,
            text=True, timeout=10, check=False).stdout
        dirty = "dirty" if st.strip() else "clean"
    except Exception:
        pass
    return {
        "python": sys.version.split()[0],
        "python_full": sys.version,
        "platform": platform.platform(),
        "dependencies": deps,
        "commit": commit,
        "worktree": dirty,
    }


def make_result_class(group_map: dict):
    """按“加载时登记的 test.id() -> group”归属分组，与类名无关。"""

    class RecordingResult(unittest.TextTestResult):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.records: list[dict] = []

        def _group_of(self, test) -> str:
            # 唯一分组依据：加载阶段按 TEST_MODULES 登记的映射；无法归属即非法记录
            return group_map.get(test.id(), "UNKNOWN")

        def _add(self, test, status: str, detail: str):
            self.records.append({"group": self._group_of(test),
                                 "module": type(test).__module__,
                                 "class": type(test).__name__,
                                 "test": str(test),
                                 "test_id": test.id(),
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

    return RecordingResult


class RunnerUsageError(Exception):
    """运行器用法 / 收集错误（退出码 2）。"""


def load_suite(only: str):
    """按模块注册表加载测试，同时登记 test.id() -> group。"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    group_map: dict[str, str] = {}
    loaded_modules: list[str] = []
    seen: set[str] = set()
    for tag, mod, _title in TEST_MODULES:
        if only and tag != only:
            continue
        if mod in seen:
            continue
        seen.add(mod)
        loaded = loader.loadTestsFromName(mod)
        module_tests = list(_walk(loaded))
        if not module_tests:
            raise RunnerUsageError(
                f"模块 {mod}（组 {tag}）未产生任何测试用例，禁止以空运行判定 PASS")
        for test in module_tests:
            key = test.id()
            if key in group_map and group_map[key] != tag:
                raise RunnerUsageError(
                    f"测试 {key} 同时归属 {group_map[key]} 与 {tag}，分组注册表冲突")
            group_map[key] = tag
        suite.addTests(module_tests)
        loaded_modules.append(mod)
    return suite, group_map, loaded_modules


def _aggregate(records: list[dict], loaded_modules: list[str]) -> tuple[dict, dict]:
    """按组聚合 + 总计，并做聚合一致性断言。"""
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
            "errors": sum(1 for r in rows if r["status"] == "ERROR"),
            "failures": sum(1 for r in rows if r["status"] == "FAIL"),
        }
    totals = {"tests": len(records),
              "pass": sum(1 for r in records if r["status"] == "PASS"),
              "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
              "skip": sum(1 for r in records if r["status"] == "SKIP"),
              "errors": sum(1 for r in records if r["status"] == "ERROR"),
              "failures": sum(1 for r in records if r["status"] == "FAIL")}
    checks = {
        "sum_groups_total_eq_totals_tests":
            sum(s["total"] for s in summary.values()) == totals["tests"],
        "sum_groups_pass_eq_totals_pass":
            sum(s["pass"] for s in summary.values()) == totals["pass"],
        "sum_groups_fail_eq_totals_fail":
            sum(s["fail"] for s in summary.values()) == totals["fail"],
        "sum_groups_skip_eq_totals_skip":
            sum(s["skip"] for s in summary.values()) == totals["skip"],
        "all_records_have_legal_group":
            all(r["group"] in GROUPS for r in records),
        "all_records_belong_to_loaded_module":
            all(r["group"] == MODULE_TO_GROUP.get(m)
                for r in records for m in [r["module"]]
                if m in MODULE_TO_GROUP),
        "loaded_modules_registered":
            all(m in MODULE_TO_GROUP for m in loaded_modules),
        "no_empty_run": totals["tests"] > 0,
    }
    return summary, {"checks": checks,
                     "ok": all(checks.values())}


def _write_json(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _render_markdown(out: dict, chains: dict) -> str:
    lines = [
        "# Phase5-1R 整改回归测试报告", "",
        f"- 生成时间：{out['created_at']} ｜ 耗时：{out['seconds']}s ｜ 模式：{out['mode']}",
        f"- 运行模块：{', '.join(out['loaded_modules'])}",
        f"- Python {out['environment']['python']} ｜ commit `{out['environment']['commit']}`"
        f"（{out['environment']['worktree']}）",
        f"- 总计 {out['totals']['tests']} 项：PASS={out['totals']['pass']} "
        f"FAIL={out['totals']['fail']} ERROR={out['totals']['errors']} "
        f"SKIP={out['totals']['skip']} ｜ ok={out['ok']}", "",
        "| 组 | 内容 | 总数 | 通过 | 失败 | 错误 | 跳过 |",
        "|---|---|---|---|---|---|---|",
    ]
    for tag, _mod, _title in TEST_MODULES:
        if tag in out["groups"]:
            s = out["groups"][tag]
            lines.append(f"| {tag} | {s['title']} | {s['total']} | {s['pass']} | "
                         f"{s['failures']} | {s['errors']} | {s['skip']} |")
    lines += ["", "## 聚合一致性断言", "",
              "| 断言 | 结果 |", "|---|---|"]
    for name, ok in out["consistency"]["checks"].items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")
    lines += ["", "## 端到端正向链路", "",
              "| 链路 | 状态 | 通过/总数 |", "|---|---|---|"]
    for chain, info in chains.items():
        lines.append(f"| {chain} | {info['status']} | "
                     f"{info['pass']}/{info['total']} |")
    lines += ["", "说明：R1–R6 覆盖 F-001–F-009 修复回归、正向/异常/边界路径、",
              "模型降级、数据保护与冻结不可变性；全部使用合成夹具；",
              "链路 A 为冻结工程模拟，**不构成真实 H2 PASS**（H2 维持 BLOCKED）。",
              "分组由 TEST_MODULES 注册表确定，与测试类名前缀无关。", ""]
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) > 2:
        print("用法: python tests/phase5_1r/run_all.py [GROUP]", file=sys.stderr)
        return 2
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    if only and only not in GROUPS:
        print(f"未知测试分组 {only!r}；可用分组: {', '.join(GROUPS)}", file=sys.stderr)
        return 2
    try:
        suite, group_map, loaded_modules = load_suite(only)
    except RunnerUsageError as exc:
        print(f"测试收集错误: {exc}", file=sys.stderr)
        return 2

    if not list(_walk(suite)):
        print("收集到 0 项测试，判定为运行器错误（不允许“无测试但 PASS”）",
              file=sys.stderr)
        return 2

    runner = unittest.TextTestRunner(verbosity=2,
                                     resultclass=make_result_class(group_map))
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)

    records = result.records
    if not records:
        print("执行 0 项测试，判定为运行器错误（不允许“无测试但 PASS”）",
              file=sys.stderr)
        return 2

    summary, consistency = _aggregate(records, loaded_modules)
    run_failed = bool(result.failures or result.errors)
    consistency_failed = not consistency["ok"]
    ok = (not run_failed) and (not consistency_failed)

    out = {
        "generated_by": "tests/phase5_1r/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds, "ok": ok,
        "mode": "full" if not only else f"partial:{only}",
        "requested_group": only or None,
        "loaded_modules": loaded_modules,
        "environment": _environment_info(),
        "totals": {"tests": len(records),
                   "pass": sum(1 for r in records if r["status"] == "PASS"),
                   "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
                   "errors": sum(1 for r in records if r["status"] == "ERROR"),
                   "failures": sum(1 for r in records if r["status"] == "FAIL"),
                   "skip": sum(1 for r in records if r["status"] == "SKIP")},
        "groups": summary, "consistency": consistency, "records": records,
    }
    out_dir = ROOT / "reports" / "phase5-1r"
    out_dir.mkdir(parents=True, exist_ok=True)

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

    if only:
        # 部分组运行不得覆盖正式全量报告
        stem = f"test-results-{only}"
    else:
        stem = "test-results"
    _write_json(out_dir / f"{stem}.json", out)
    (out_dir / f"{stem}.md").write_text(_render_markdown(out, chains),
                                        encoding="utf-8", newline="\n")

    if not only:
        positive = {
            "generated_by": "tests/phase5_1r/run_all.py",
            "created_at": out["created_at"],
            "mode": out["mode"],
            "fixture_policy": ("纯合成工程夹具 + 临时隔离目录；只证明软件流程可运行，"
                               "不得作为真实 Gold / 真实 H2 通过证据"),
            "real_h2_status": "BLOCKED（真实中文简历、人工标签与合法盲测集未完成）",
            "chains": chains,
        }
        _write_json(out_dir / "positive-flow-validation.json", positive)

    print(f"=== Phase5-1R 测试完成 {seconds}s | 模式={out['mode']} | "
          f"PASS={out['totals']['pass']} FAIL={out['totals']['fail']} "
          f"ERROR={out['totals']['errors']} SKIP={out['totals']['skip']} "
          f"| ok={ok} ===")
    if consistency_failed:
        bad = [k for k, v in consistency["checks"].items() if not v]
        print(f"!!! 聚合一致性断言失败: {bad}", file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
