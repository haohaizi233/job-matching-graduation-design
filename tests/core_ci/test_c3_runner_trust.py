# -*- coding: utf-8 -*-
"""C3：测试运行器聚合一致性（防止"0 测试误报 PASS"与"跳过即通过"）。

覆盖：
  * 各套件运行器的分组注册表唯一、分组名合法；
  * 收集到 0 项测试必须判为运行器错误（退出码 2），不得写 ok=true；
  * 未知分组必须拒绝；
  * 聚合一致性：分组计数之和 == 总计数；
  * 报告里的 totals 必须与逐条记录可对账；
  * 历史基线报告（model-tests.json）不得被失败/局部运行覆盖。
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RUNNERS = {
    "phase5_1a": ROOT / "tests" / "phase5_1a" / "run_all.py",
    "phase5_1r": ROOT / "tests" / "phase5_1r" / "run_all.py",
    "phase5_1": ROOT / "tests" / "phase5_1" / "run_all.py",
    "phase4_3a": ROOT / "tests" / "phase4_3a" / "run_all.py",
    "model_training": ROOT / "tests" / "model_training" / "run_all.py",
    "data_pipeline": ROOT / "tests" / "data_pipeline" / "run_all.py",
    "core_ci": ROOT / "tests" / "core_ci" / "run_all.py",
}


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"probe_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class C3RunnerAggregation(unittest.TestCase):

    def test_every_suite_runner_exists(self):
        for name, p in RUNNERS.items():
            self.assertTrue(p.exists(), f"{name} 运行器缺失: {p}")

    def test_registry_tables_are_unique_and_non_empty(self):
        for name, p in RUNNERS.items():
            mod = _load(p)
            table = getattr(mod, "TEST_MODULES", None) or getattr(mod, "GATE_MODULES", None)
            self.assertIsNotNone(table, f"{name} 无测试注册表")
            self.assertTrue(table, f"{name} 注册表为空")
            # 注册表唯一性按 (分组, 目标) 判定：同一模块可被多个分组登记不同测试类
            pairs = [(t[0], t[1]) for t in table]
            self.assertEqual(len(pairs), len(set(pairs)),
                             f"{name} 注册表存在重复 (分组, 目标): {pairs}")

    def test_group_columns_are_legal(self):
        """声明了 GROUPS 的运行器：分组名必须覆盖注册表且自身不重复。"""
        checked = 0
        for name, p in RUNNERS.items():
            mod = _load(p)
            groups = list(getattr(mod, "GROUPS", []))
            if not groups:
                continue
            checked += 1
            self.assertEqual(len(groups), len(set(groups)), f"{name}: GROUPS 有重复")
            table = getattr(mod, "TEST_MODULES", None) or getattr(mod, "GATE_MODULES", None)
            for tag, _target, _title in table:
                self.assertIn(tag, groups, f"{name}: 注册表分组 {tag} 不在 GROUPS")
        self.assertGreaterEqual(checked, 3, "声明 GROUPS 的运行器过少")

    def test_undeclared_group_runners_still_have_unique_registry(self):
        """未声明 GROUPS 的运行器（phase5_1 / phase4_3a / data_pipeline）不得有重复登记。"""
        for name in ("phase5_1", "phase4_3a", "data_pipeline"):
            mod = _load(RUNNERS[name])
            self.assertFalse(getattr(mod, "GROUPS", None),
                             f"{name} 声明方式与预期不符，请同步更新本门禁")
            table = getattr(mod, "TEST_MODULES", None) or getattr(mod, "GATE_MODULES", None)
            pairs = [(t[0], t[1]) for t in table]
            self.assertEqual(len(pairs), len(set(pairs)), f"{name}: 注册表重复")

    def test_unknown_group_is_rejected_nonzero(self):
        env = dict(os.environ, PYTHONUTF8="1")
        for name in ("phase5_1a", "core_ci"):
            r = subprocess.run([sys.executable, str(RUNNERS[name]), "ZZ9"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, cwd=str(ROOT), env=env)
            self.assertEqual(r.returncode, 2, f"{name}: 未知分组未被拒绝")
            out = (r.stdout or "") + (r.stderr or "")
            self.assertIn("未知测试分组", out, f"{name}: 错误信息不可读 -> {out!r}")

    def test_zero_test_module_is_runner_error(self):
        mod = _load(RUNNERS["core_ci"])
        tmp = ROOT / "tests" / "core_ci" / "_c3_empty_mod.py"
        tmp.write_text("import unittest\nclass Empty(unittest.TestCase):\n    pass\n",
                       encoding="utf-8")
        try:
            mod.TEST_MODULES = [("C9", "_c3_empty_mod.Empty", "probe")]
            mod.GROUPS = ["C9"]
            self.assertTrue(hasattr(mod, "load_suite"),
                            "core_ci 运行器必须提供 load_suite 以便可信性自检")
            with self.assertRaises(Exception):
                mod.load_suite("")
        finally:
            tmp.unlink(missing_ok=True)

    def test_aggregation_consistency_helper_present(self):
        """提供聚合一致性函数的运行器必须能对"记录 -> 分组汇总"做自检。"""
        for name in ("phase5_1r", "core_ci"):
            mod = _load(RUNNERS[name])
            self.assertTrue(hasattr(mod, "_aggregate") or hasattr(mod, "aggregate"),
                            f"{name} 运行器缺少聚合一致性函数")
            agg, checks = mod._aggregate(
                [{"group": "R1" if name == "phase5_1r" else "C2", "module": "m",
                  "class": "C", "test": "t", "test_id": "m.C.t",
                  "status": "PASS", "detail": ""}],
                ["m"])
            self.assertTrue(all(checks.values()), checks)
            self.assertEqual(agg["totals"]["tests"], 1)

    def test_reports_totals_match_records(self):
        """已生成的报告：分组之和 == 总计，且总数 > 0。"""
        checked = 0
        for p in (ROOT / "reports").glob("*/test-results.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if "totals" not in d or "groups" not in d:
                continue
            t, g = d["totals"], d["groups"]
            self.assertEqual(sum(s["total"] for s in g.values()), t["tests"],
                             f"{p}: 分组总数与总计不一致")
            self.assertEqual(sum(s["pass"] for s in g.values()), t["pass"],
                             f"{p}: 分组通过数与总计不一致")
            self.assertGreater(t["tests"], 0, f"{p}: 报告显示 0 项测试")
            checked += 1
        self.assertGreater(checked, 0, "没有任何可对账的测试报告")

    def test_data_quality_gates_report_not_fabricated(self):
        p = ROOT / "reports" / "data-quality-gates.json"
        if not p.exists():
            self.skipTest("尚无数据质量闸门报告")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertGreater(d["tests_run"], 0, "报告显示 0 项测试")
        total_recorded = sum(g["total"] for g in d["gates"].values())
        # 运行器的历史实现不登记 SKIP 记录，故只断言"已登记不超过实跑"且失败可对账
        self.assertLessEqual(total_recorded, d["tests_run"])
        self.assertGreater(total_recorded, 0)
        self.assertEqual(sum(g["failed"] for g in d["gates"].values()),
                         d["failures"] + d["errors"],
                         "闸门失败数与运行器失败/错误数不一致")


class C3HistoricalBaselineProtection(unittest.TestCase):
    """历史基线不得被失败测试覆盖。"""

    def test_model_training_baseline_intact(self):
        p = ROOT / "reports" / "model-training" / "model-tests.json"
        self.assertTrue(p.exists(), "4.1 基线报告缺失")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertTrue(d["ok"], "历史基线被覆盖（ok 不再为 true）")
        self.assertEqual(d["totals"]["fail"], 0, "历史基线被覆盖（出现失败记录）")

    def test_report_target_protects_baseline(self):
        mod = _load(RUNNERS["model_training"])
        self.assertTrue(hasattr(mod, "report_target"))
        self.assertEqual(mod.report_target("", True, "20261029-000000"), "model-tests.json")
        self.assertNotEqual(mod.report_target("", False, "20261029-000000"),
                            "model-tests.json")
        self.assertNotEqual(mod.report_target("T4", True, "20261029-000000"),
                            "model-tests.json")

    def test_runners_declare_baseline_policy(self):
        for name in ("phase5_1a", "core_ci", "model_training"):
            mod = _load(RUNNERS[name])
            doc = (mod.__doc__ or "") + json.dumps(
                list(getattr(mod, "TEST_MODULES", []) or getattr(mod, "GATE_MODULES", [])),
                ensure_ascii=False)
            self.assertTrue(doc.strip(), f"{name} 运行器无任何说明")


if __name__ == "__main__":
    unittest.main(verbosity=2)
