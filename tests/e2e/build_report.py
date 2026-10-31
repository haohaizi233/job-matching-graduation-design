# -*- coding: utf-8 -*-
"""将 Playwright JSON 原始结果转换为 Phase5-3 E2E 验收报告。

输入：frontend/e2e/.artifacts/e2e-raw.json（playwright json reporter 输出）
输出：reports/phase5-3/e2e-results.json + reports/phase5-3/e2e-results.md

纪律：只做**格式转换与汇总**，不修改任何测试状态；缺场景记 NOT_RUN，失败保留原始错误摘要。
用法（项目根目录）：
  py -3.13 tests/e2e/build_report.py
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "frontend" / "e2e" / ".artifacts" / "e2e-raw.json"
OUT_DIR = ROOT / "reports" / "phase5-3"

SCENARIOS: dict[str, str] = {
    "E01": "注册、登录、退出",
    "E02": "上传简历与解析",
    "E03": "简历解析失败及重试",
    "E04": "画像修改、确认、版本历史",
    "E05": "岗位查询、筛选与详情",
    "E06": "发起推荐与解释展示",
    "E07": "推荐历史与 CSV 导出",
    "E08": "反馈提交与状态回显",
    "E09": "未认证及 Token 失效",
    "E10": "多用户数据隔离",
    "E11": "空数据、网络错误与 API 失败",
    "E12": "页面刷新与基础响应式检查",
}


def walk_specs(suite: dict, out: list[dict], file_prefix: str) -> None:
    for spec in suite.get("specs") or []:
        file_path = spec.get("file") or file_prefix
        for case in spec.get("tests") or []:
            results = case.get("results") or []
            result = results[-1] if results else {}
            errors = [
                str((err.get("message") or "").strip())[:500]
                for err in (result.get("errors") or [])
            ]
            out.append(
                {
                    "file": file_path,
                    "title": spec.get("title") or case.get("title") or "",
                    "status": (result.get("status") or case.get("status") or "unknown").upper(),
                    "expected_status": case.get("expectedStatus", "passed"),
                    "duration_ms": int(result.get("duration") or 0),
                    "errors": errors,
                    "steps": [
                        {"title": s.get("title"), "status": s.get("status")}
                        for s in (result.get("steps") or [])
                        if s.get("category") == "test.step"
                    ],
                }
            )
    for child in suite.get("suites") or []:
        walk_specs(child, out, file_prefix)


def scenario_of(title: str, file_path: str) -> str:
    # 文件名前缀优先（e01-*.spec.ts / e12-*.spec.ts），标题中的 E0x 仅作兜底
    base = Path(file_path).name
    m = re.match(r"e(\d{2})[-_]", base)
    if m:
        return f"E{m.group(1)}"
    m = re.search(r"\bE(0[1-9]|1[0-2])\b", title, re.I)
    return f"E{m.group(1)}" if m else ""


def main() -> int:
    if not RAW.exists():
        print(f"NOT_RUN: 缺少 Playwright 原始结果 {RAW}", file=sys.stderr)
        return 2
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    cases: list[dict] = []
    for suite in raw.get("suites") or []:
        walk_specs(suite, cases, suite.get("file") or "")

    by_scenario: dict[str, list[dict]] = {k: [] for k in SCENARIOS}
    for case in cases:
        sid = scenario_of(case["title"], case["file"])
        if sid in by_scenario:
            by_scenario[sid].append(case)

    scenarios = []
    for sid, title in SCENARIOS.items():
        items = by_scenario[sid]
        if not items:
            status = "NOT_RUN"
        elif all(i["status"] == "PASSED" and i["expected_status"] == "passed" for i in items):
            status = "PASS"
        else:
            status = "FAIL"
        scenarios.append({"id": sid, "title": title, "status": status, "tests": items})

    totals = {
        "tests": len(cases),
        "pass": sum(1 for c in cases if c["status"] == "PASSED"),
        "fail": sum(1 for c in cases if c["status"] not in ("PASSED", "SKIPPED")),
        "skip": sum(1 for c in cases if c["status"] == "SKIPPED"),
        "duration_ms": sum(c["duration_ms"] for c in cases),
    }
    report = {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": os.environ.get("JM_RUN_ID", ""),
        "raw_source": str(RAW.relative_to(ROOT)).replace("\\", "/"),
        "environment": {
            "base_url": os.environ.get("JM_E2E_BASE_URL", "http://127.0.0.1:5173"),
            "backend": "tests/e2e/serve_backend.py（隔离 sqlite + 隔离存储）",
            "fixtures": "tests/e2e/fixtures.py（全部合成数据 is_synthetic）",
            "playwright": raw.get("config", {}).get("version", ""),
        },
        "totals": totals,
        "scenarios": scenarios,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "e2e-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = []
    md.append("# Phase5-3 浏览器 E2E 验收结果")
    md.append("")
    md.append(f"- 生成时间：{report['generated_at']}")
    md.append(f"- Run ID：`{report['run_id'] or '（未设置）'}`")
    md.append(f"- 原始结果：`{report['raw_source']}`")
    md.append("- 环境：真实 Chromium + 真实前后端（隔离测试库 tests/e2e/.runtime/），夹具全部为合成数据")
    md.append("")
    md.append(
        f"**汇总：{totals['tests']} 个用例 / PASS {totals['pass']} / "
        f"FAIL {totals['fail']} / SKIP {totals['skip']} / "
        f"耗时 {totals['duration_ms'] / 1000:.1f}s**"
    )
    md.append("")
    md.append("## 场景覆盖（任务书 E01–E12）")
    md.append("")
    md.append("| 编号 | 场景 | 状态 | 用例 | 证据（用例） |")
    md.append("|---|---|---|---|---|")
    for s in scenarios:
        names = "<br>".join(f"`{Path(t['file']).name}::{t['title']}`" for t in s["tests"]) or "—"
        md.append(f"| {s['id']} | {s['title']} | {s['status']} | {len(s['tests'])} | {names} |")
    md.append("")
    failures = [c for c in cases if c["status"] != "PASSED"]
    md.append("## 失败与错误明细" if failures else "## 失败与错误明细（无）")
    md.append("")
    for c in failures:
        md.append(f"### ❌ `{Path(c['file']).name}::{c['title']}`（{c['status']}）")
        md.append("")
        for err in c["errors"] or ["（无错误文本）"]:
            md.append("```text")
            md.append(err)
            md.append("```")
        md.append("")
    md.append("## 用例耗时")
    md.append("")
    md.append("| 用例 | 状态 | 耗时 |")
    md.append("|---|---|---|")
    for c in cases:
        md.append(
            f"| `{Path(c['file']).name}::{c['title']}` | {c['status']} | {c['duration_ms'] / 1000:.1f}s |"
        )
    md.append("")
    (OUT_DIR / "e2e-results.md").write_text("\n".join(md), encoding="utf-8")

    print(f"wrote {OUT_DIR / 'e2e-results.json'}")
    print(f"wrote {OUT_DIR / 'e2e-results.md'}")
    print(f"totals: {totals}")
    return 0 if totals["fail"] == 0 and totals["tests"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
