# -*- coding: utf-8 -*-
"""Phase7 统一测试运行器（stdlib unittest，与 tests/phase6/run_all.py 同风格）。

运行身份（B1 整改）：所有执行证据字段一律取自**真实进程**，禁止硬编码：
  - python_version      -> platform.python_version() / sys.version
  - actual_python_executable -> sys.executable
  - sys_argv            -> sys.argv（真实命令参数）
  - working_directory   -> os.getcwd()
  - execution_command   -> shlex.join([sys.executable, *sys.argv])
  - git_sha             -> 真实 git rev-parse HEAD（失败显式 UNKNOWN）
  - started_at/finished_at/seconds/exit_code -> 真实运行时间与退出码

其余登记字段：run_id / dataset_version / model_version /
PASS FAIL ERROR SKIP NOT_RUN BLOCKED / evidence_path。

零测试发现（模块为空或 testsRun==0）**显式失败**（退出码 1），
不允许「0 FAIL = 全绿」。模块导入失败计入 ERROR 并退出非零。

用法：
    python tests/phase7/run_all.py            # 全部
    python tests/phase7/run_all.py prereg     # 只跑模块名含 prereg 的

输出：reports/phase7/11-phase7-regression.{json,md}
退出码：0 = 无 FAIL/ERROR 且实际执行了测试；否则 1
"""
from __future__ import annotations

import json
import os
import platform
import shlex
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase7"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase7"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

STATUSES = ("PASS", "FAIL", "ERROR", "SKIP", "NOT_RUN", "BLOCKED")


def discover_modules() -> list[str]:
    return sorted(p.stem for p in HERE.glob("test_*.py") if p.is_file())


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []
        self._start = 0.0

    def startTest(self, test):
        super().startTest(test)
        self._start = time.perf_counter()

    def _elapsed(self) -> float:
        return round((time.perf_counter() - self._start) * 1000.0, 3)

    def _module_of(self, test) -> str:
        return type(test).__module__.split(".")[-1]

    def _add(self, test, status: str, detail: str):
        self.records.append({
            "module": self._module_of(test), "test": str(test),
            "status": status, "ms": self._elapsed(), "detail": detail[-1500:],
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, "PASS", "")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, "SKIP", reason)


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def run_suite(modules: list[str], report_dir: Path | None = None,
              argv: list[str] | None = None) -> dict:
    """真实执行测试套件并写回证据，返回 payload（含真实退出码）。

    report_dir/argv 可注入以便元测试隔离验证；默认取真实进程身份。
    """
    report_dir = Path(report_dir) if report_dir else REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    argv = list(argv) if argv is not None else list(sys.argv)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    load_errors: list[dict] = []
    for mod in modules:
        try:
            suite.addTests(loader.loadTestsFromName(mod))
        except Exception as e:  # noqa: BLE001
            load_errors.append({"module": mod, "error": f"{type(e).__name__}: {e}"})

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    t0 = time.time()
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    result = runner.run(suite)
    elapsed = round(time.time() - t0, 3)
    finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    counts = {s: 0 for s in STATUSES}
    for r in result.records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for le in load_errors:
        counts["ERROR"] += 1
        result.records.append({"module": le["module"], "test": f"<import {le['module']}>",
                               "status": "ERROR", "ms": 0.0, "detail": le["error"]})

    reasons: list[str] = []
    if counts["FAIL"] or counts["ERROR"]:
        reasons.append("fail_or_error")
    if result.testsRun == 0:
        # 零测试发现显式失败：「0 FAIL = 全绿」是伪造绿灯。
        reasons.append("no_tests_discovered")
    if not modules:
        reasons.append("no_modules_matched")
    ok = not reasons
    exit_code = 0 if ok else 1

    real_argv = list(argv)
    execution_command = shlex.join([sys.executable, *real_argv])
    payload = {
        "run_id": time.strftime("phase7-reg-%Y%m%d-%H%M%S"),
        "git_sha": _git_sha(),
        # ---- 真实进程身份（禁止硬编码）----
        "python_version": platform.python_version(),
        "python_full_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "actual_python_executable": sys.executable,
        "sys_argv": real_argv,
        "working_directory": os.getcwd(),
        "execution_command": execution_command,
        "platform": platform.platform(),
        "node_version": "n/a（Python 套件；前端 Node 版本见 frontend-ci 证据）",
        # ---- 运行时间与退出码（真实）----
        "started_at": started_at,
        "finished_at": finished_at,
        "seconds": elapsed,
        "exit_code": exit_code,
        # ---- 语义登记 ----
        "dataset_version": "none (Phase7 真实 Gold 未建立；测试仅使用合成夹具)",
        "model_version": "n/a（本套件不加载模型权重）",
        "counts": counts,
        "evidence_path": "reports/phase7/11-phase7-regression.json",
        "generated_by": "tests/phase7/run_all.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "modules": modules,
        "tests_run": result.testsRun,
        "ok": ok,
        "not_ok_reasons": reasons,
        "load_errors": load_errors,
        "records": result.records,
    }
    (report_dir / "11-phase7-regression.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Phase7 纯软件协议测试回归结果",
        "",
        f"- run_id：`{payload['run_id']}`",
        f"- git_sha：`{payload['git_sha']}`",
        f"- python_version：`{payload['python_version']}`（{payload['python_implementation']}）",
        f"- actual_python_executable：`{payload['actual_python_executable']}`",
        f"- sys_argv：`{shlex.join(real_argv)}`",
        f"- working_directory：`{payload['working_directory']}`",
        f"- platform：{payload['platform']}",
        f"- dataset_version：{payload['dataset_version']}",
        f"- model_version：{payload['model_version']}",
        f"- execution_command：`{payload['execution_command']}`",
        f"- started_at / finished_at：{started_at} / {finished_at}（耗时 {elapsed}s）",
        f"- exit_code：{exit_code}",
        f"- 运行用例：{result.testsRun}",
        f"- PASS={counts['PASS']} FAIL={counts['FAIL']} ERROR={counts['ERROR']} "
        f"SKIP={counts['SKIP']} NOT_RUN={counts['NOT_RUN']} BLOCKED={counts['BLOCKED']}",
        f"- 结论：{'全部通过' if ok else '未通过：' + ','.join(reasons)}",
        "",
        "## 说明",
        "",
        "- 本套件是**纯软件协议测试**（预注册锁定、样本规划确定性、标注工具链演练、",
        "  模型哈希门禁、盲测状态机），不依赖真实人工数据，可进入公开 CI；",
        "- 真实人工简历、授权文件与标注原文**不得**进入 GitHub Actions 公开 Runner；",
        "- 本结果不能替代 Phase4-3B / Phase5-x / Phase6 历史回归，也**不构成** H2 通过；",
        "- 运行身份字段取自真实进程（sys.executable / sys.argv / os.getcwd()），",
        "  CI 与本地分别登记实际环境，禁止手工伪造执行命令。",
        "",
        "## 运行模块（确定性顺序）",
        "",
    ]
    for m in modules:
        lines.append(f"- `{m}`")
    lines += ["", "## 逐项结果", "",
              "| 模块 | 用例 | 状态 | 耗时(ms) | 说明 |", "|---|---|---|---|---|"]
    for r in result.records:
        det = (r["detail"] or "").replace("|", "\\|").replace("\n", " ")[:120]
        lines.append(f"| {r['module']} | {r['test']} | {r['status']} | {r['ms']} | {det} |")
    if load_errors:
        lines += ["", "## 模块导入失败（登记，不静默）", ""]
        for le in load_errors:
            lines.append(f"- `{le['module']}`: {le['error']}")
    (report_dir / "11-phase7-regression.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nPASS={counts['PASS']} FAIL={counts['FAIL']} ERROR={counts['ERROR']} "
          f"SKIP={counts['SKIP']} NOT_RUN={counts['NOT_RUN']} BLOCKED={counts['BLOCKED']}  ({elapsed}s)")
    print(f"exit_code={exit_code}" + ("" if ok else f" not_ok_reasons={reasons}"))
    print(f"wrote {report_dir / '11-phase7-regression.json'}")
    return payload


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv
    only = argv[1] if len(argv) > 1 else None
    modules = discover_modules()
    if only:
        modules = [m for m in modules if only in m]
    payload = run_suite(modules, argv=argv)
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
