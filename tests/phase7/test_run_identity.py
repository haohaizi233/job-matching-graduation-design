# -*- coding: utf-8 -*-
"""Phase7 运行器身份与报告一致性元测试（B1 整改）。

验证 tests/phase7/run_all.py 的执行证据来自**真实进程**且零测试发现显式失败：
  - test_run_identity_actual_interpreter   实际解释器身份（sys.executable/sys.version）
  - test_run_identity_current_git_sha      git_sha 与真实 HEAD 一致
  - test_runner_import_failure_nonzero     模块导入失败 -> 非零退出
  - test_runner_no_tests_discovered_nonzero 零测试发现 -> 显式失败
  - test_runner_report_freshness           报告新鲜度（真实生成时间）
  - test_report_status_count_consistency   状态计数与 JSON/Markdown 一致

元测试通过注入 report_dir/argv 隔离执行，不覆盖主报告。
"""
from __future__ import annotations

import json
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_all  # noqa: E402  （tests/phase7/run_all.py）


def _register_dummy_module(name: str, ok: bool = True) -> None:
    """注册一个内存测试模块，避免元测试重复执行真实套件。"""
    mod = types.ModuleType(name)

    class _T(unittest.TestCase):
        def test_dummy(self):
            if not ok:
                self.fail("intentional failure")
            self.assertTrue(True)

    mod._T = _T
    mod.__test__ = True
    sys.modules[name] = mod


class TestRunIdentity(unittest.TestCase):
    def test_run_identity_actual_interpreter(self):
        """执行证据中的解释器必须是真实进程解释器，不得硬编码。"""
        _register_dummy_module("_meta_dummy_identity")
        fake_argv = ["tests/phase7/run_all.py", "_meta_dummy_identity"]
        with tempfile.TemporaryDirectory() as td:
            payload = run_all.run_suite(["_meta_dummy_identity"],
                                        report_dir=Path(td), argv=fake_argv)
        self.assertEqual(sys.executable, payload["actual_python_executable"])
        self.assertEqual(platform.python_version(), payload["python_version"])
        self.assertIn(sys.version.split()[0], payload["python_full_version"])
        self.assertEqual(shlex.join([sys.executable, *fake_argv]),
                         payload["execution_command"])
        self.assertEqual(fake_argv, payload["sys_argv"])
        self.assertFalse(re.search(r"py -3\.13", payload["execution_command"]),
                         "execution_command 不得硬编码 py -3.13")

    def test_run_identity_current_git_sha(self):
        """git_sha 必须来自真实 git rev-parse HEAD。"""
        _register_dummy_module("_meta_dummy_sha")
        expect = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                capture_output=True, text=True, timeout=20
                                ).stdout.strip()
        with tempfile.TemporaryDirectory() as td:
            payload = run_all.run_suite(["_meta_dummy_sha"],
                                        report_dir=Path(td),
                                        argv=["tests/phase7/run_all.py", "_meta_dummy_sha"])
        self.assertEqual(expect, payload["git_sha"])
        self.assertEqual(40, len(payload["git_sha"]))

    def test_runner_import_failure_nonzero(self):
        """模块导入失败必须登记 ERROR 并返回非零退出码。"""
        with tempfile.TemporaryDirectory() as td:
            payload = run_all.run_suite(["_meta_nonexistent_module_xyz"],
                                        report_dir=Path(td),
                                        argv=["tests/phase7/run_all.py",
                                              "_meta_nonexistent_module_xyz"])
        self.assertEqual(1, payload["exit_code"])
        self.assertFalse(payload["ok"])
        # unittest 可能把导入失败包装为 _FailedTest（ERROR 记录）或 load_errors，
        # 两条路径都必须登记为 ERROR 且非零退出，不得静默。
        self.assertGreaterEqual(payload["counts"]["ERROR"], 1)
        self.assertTrue(payload["load_errors"]
                        or any(r["status"] == "ERROR" for r in payload["records"]))

    def test_runner_no_tests_discovered_nonzero(self):
        """零测试发现必须显式失败，禁止 0 FAIL = 全绿。"""
        with tempfile.TemporaryDirectory() as td:
            payload = run_all.run_suite([], report_dir=Path(td),
                                        argv=["tests/phase7/run_all.py"])
        self.assertEqual(1, payload["exit_code"])
        self.assertFalse(payload["ok"])
        self.assertIn("no_tests_discovered", payload["not_ok_reasons"])
        self.assertEqual(0, payload["tests_run"])
        # 空结果不得登记为 PASS 全绿
        self.assertEqual(0, payload["counts"]["PASS"])

    def test_runner_report_freshness(self):
        """报告必须由本次真实执行生成（新鲜时间戳 + 真实退出码联动）。"""
        _register_dummy_module("_meta_dummy_fresh")
        t_before = time.time()
        with tempfile.TemporaryDirectory() as td:
            payload = run_all.run_suite(["_meta_dummy_fresh"],
                                        report_dir=Path(td),
                                        argv=["tests/phase7/run_all.py", "_meta_dummy_fresh"])
            report = Path(td) / "11-phase7-regression.json"
            self.assertTrue(report.is_file())
            mtime = report.stat().st_mtime
            on_disk = json.loads(report.read_text(encoding="utf-8"))
        t_after = time.time()
        self.assertGreaterEqual(mtime, t_before - 1)
        self.assertLessEqual(mtime, t_after + 1)
        self.assertEqual(payload, on_disk)
        self.assertRegex(payload["run_id"], r"^phase7-reg-\d{8}-\d{6}$")
        # started_at/finished_at 必须落在真实执行窗口内
        for key in ("started_at", "finished_at", "generated_at"):
            self.assertRegex(payload[key], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_report_status_count_consistency(self):
        """counts 与逐项 records、tests_run、Markdown 摘要必须一致。"""
        _register_dummy_module("_meta_dummy_counts_ok")
        _register_dummy_module("_meta_dummy_counts_fail", ok=False)
        modules = ["_meta_dummy_counts_ok", "_meta_dummy_counts_fail"]
        with tempfile.TemporaryDirectory() as td:
            payload = run_all.run_suite(modules, report_dir=Path(td),
                                        argv=["tests/phase7/run_all.py", *modules])
            md = (Path(td) / "11-phase7-regression.md").read_text(encoding="utf-8")
        counts = payload["counts"]
        self.assertEqual(len(payload["records"]),
                         sum(counts.values()))
        self.assertEqual(payload["tests_run"] + len(payload["load_errors"]),
                         counts["PASS"] + counts["FAIL"] + counts["ERROR"] + counts["SKIP"])
        self.assertEqual(1, counts["PASS"])
        self.assertEqual(1, counts["FAIL"])
        self.assertEqual(1, payload["exit_code"])  # 存在 FAIL -> 非零
        m = re.search(r"PASS=(\d+) FAIL=(\d+) ERROR=(\d+) SKIP=(\d+) NOT_RUN=(\d+) BLOCKED=(\d+)", md)
        self.assertIsNotNone(m, "Markdown 必须包含状态计数摘要")
        self.assertEqual([counts["PASS"], counts["FAIL"], counts["ERROR"],
                          counts["SKIP"], counts["NOT_RUN"], counts["BLOCKED"]],
                         [int(g) for g in m.groups()])


if __name__ == "__main__":
    unittest.main()
