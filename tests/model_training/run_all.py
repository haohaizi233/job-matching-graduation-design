# -*- coding: utf-8 -*-
"""第四阶段 4.1 模型训练/推理测试运行器（stdlib unittest，不引入 pytest）。

用法:
    python tests/model_training/run_all.py            # 全部测试
    python tests/model_training/run_all.py T4         # 只跑 T4

输出:
    控制台逐项 PASS/FAIL
    * 正式基线报告 reports/model-training/model-tests.json
      **只在「全量运行且全部通过」时更新**（它是 Phase4-1 历史验收产物，
      被 tests/education_training/test_e6_experiments.py 与
      scripts/phase5_1r/artifact_integrity.py 登记保护）；
    * 其它运行（部分组 / 有 FAIL / 有 ERROR）写诊断报告
      reports/model-training/model-tests-run-<时间戳>.json，**不覆盖历史基线**。
      在非训练环境（如 Serving 环境）重跑时旧 checkpoint 可能因
      scikit-learn 版本漂移无法反序列化（T5 setUpClass ERROR），
      这属于环境不兼容，不得通过覆盖基线报告"抹掉"历史结果。

退出码:
    0 = 全部通过（且已更新基线报告）
    1 = 存在 FAIL / ERROR（诊断报告已落盘，基线报告保持不动）
    2 = 运行器用法或收集错误（未知分组、0 项测试）

分组规则（Phase5-1A 修订，与 tests/phase5_1r/run_all.py 一致）:
    分组唯一来源是 TEST_MODULES 注册表（按加载模块归属），与测试类名前缀无关。
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
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
MODULE_TO_GROUP = {mod: tag for tag, mod, _title in TEST_MODULES}
GROUPS = [tag for tag, _mod, _title in TEST_MODULES]

BASELINE_NAME = "model-tests.json"
OUT_DIR = ROOT / "reports" / "model-training"


class RunnerUsageError(Exception):
    """运行器用法 / 收集错误（退出码 2）。"""


def _walk(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _walk(item)
        else:
            yield item


def make_result_class(group_map: dict):
    """按加载阶段登记的 test.id() -> group 归属分组，与类名无关。"""

    class RecordingResult(unittest.TextTestResult):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.records: list[dict] = []

        def _add(self, test, status: str, detail: str):
            self.records.append({"group": group_map.get(test.id(), "UNKNOWN"),
                                 "test": str(test), "test_id": test.id(),
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


def report_target(only: str, ok: bool, stamp: str) -> str:
    """决定报告文件名：只有「全量 + 全通过」才允许写正式基线。

    纯函数，便于单测锁定"失败/部分运行不得覆盖历史基线"的语义。
    """
    if ok and not only:
        return BASELINE_NAME
    stem = "model-tests" + (f"-{only}" if only else "") + f"-run-{stamp}"
    return f"{stem}.json"


def load_suite(only: str):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    group_map: dict[str, str] = {}
    seen: set[str] = set()
    for tag, mod, _title in TEST_MODULES:
        if only and tag != only:
            continue
        if mod in seen:
            continue
        seen.add(mod)
        tests = list(_walk(loader.loadTestsFromName(mod)))
        if not tests:
            raise RunnerUsageError(f"模块 {mod}（组 {tag}）未产生任何测试用例")
        for t in tests:
            group_map[t.id()] = tag
        suite.addTests(tests)
    return suite, group_map


def _environment_info() -> dict:
    deps = {}
    for name in ("numpy", "scipy", "sklearn", "joblib", "pandas", "torch", "yaml"):
        try:
            mod = __import__(name)
            deps[name] = getattr(mod, "__version__", "unknown")
        except Exception as exc:
            deps[name] = "NOT_INSTALLED(%s)" % type(exc).__name__
    commit = "UNKNOWN"
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                capture_output=True, text=True,
                                timeout=10, check=False).stdout.strip() or "UNKNOWN"
    except Exception:
        pass
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "dependencies": deps, "commit": commit}


def main() -> int:
    if len(sys.argv) > 2:
        print("用法: python tests/model_training/run_all.py [GROUP]", file=sys.stderr)
        return 2
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    if only and only not in GROUPS:
        print(f"未知测试分组 {only!r}；可用分组: {', '.join(GROUPS)}", file=sys.stderr)
        return 2
    try:
        suite, group_map = load_suite(only)
    except RunnerUsageError as exc:
        print(f"测试收集错误: {exc}", file=sys.stderr)
        return 2
    if not list(_walk(suite)):
        print("收集到 0 项测试，判定为运行器错误（不允许“无测试但 PASS”）", file=sys.stderr)
        return 2

    runner = unittest.TextTestRunner(verbosity=2, resultclass=make_result_class(group_map))
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)
    records = result.records
    if not records:
        print("执行 0 项测试，判定为运行器错误（不允许“无测试但 PASS”）", file=sys.stderr)
        return 2

    summary = {}
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
        }
    ok = not (result.failures or result.errors)
    consistency_ok = (
        sum(s["total"] for s in summary.values()) == len(records)
        and all(r["group"] in GROUPS for r in records)
    )
    out = {
        "generated_by": "tests/model_training/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds,
        "ok": ok,
        "mode": "full" if not only else f"partial:{only}",
        "environment": _environment_info(),
        "totals": {"tests": len(records),
                   "pass": sum(1 for r in records if r["status"] == "PASS"),
                   "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
                   "skip": sum(1 for r in records if r["status"] == "SKIP")},
        "groups": summary,
        "consistency_ok": consistency_ok,
        "records": records,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = report_target(only, ok and consistency_ok, stamp)
    with open(OUT_DIR / name, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if name == BASELINE_NAME:
        print(f"（全量通过，已更新基线报告 {name}）")
    else:
        print(f"（本次运行未全量通过/非全量，结果写入诊断报告 {name}；"
              f"历史基线 {BASELINE_NAME} 保持不变）", file=sys.stderr)
    print(f"=== 测试完成 {seconds}s | PASS={out['totals']['pass']} "
          f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} | ok={ok} ===")
    return 0 if ok and consistency_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
