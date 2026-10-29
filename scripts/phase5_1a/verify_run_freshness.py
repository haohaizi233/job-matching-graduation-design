# -*- coding: utf-8 -*-
"""报告新鲜度校验器：拒绝采信"旧报告冒充本次运行"（Phase5-2 / Batch 0 核心可信门禁）。

问题回顾：
  此前 CI 的模型兼容步骤是 `diagnose_model_compat.py || true`，随后只检查
  `reports/phase5-1a/model-compatibility.json` **是否存在**。由于该文件已提交在仓库里，
  任何一次诊断失败/跳过，旧报告都会被当成"本次通过"。

本脚本是**消费侧**强制点：读取报告 -> 校验 run_identity -> 只有身份匹配才允许结论被采信。

用法：
  python scripts/phase5_1a/verify_run_freshness.py REPORT [REPORT ...] \
      --expect-run-id $JM_RUN_ID --expect-commit $(git rev-parse HEAD)

退出码：
  0  全部报告身份新鲜，且状态被登记为合法状态
  1  存在过期 / 缺失 / 身份不匹配的报告（**必须让 CI 失败**）
  2  用法错误

注意：
  * 本脚本只做"身份 + 状态口径"校验，不重新执行业务检查；
  * NOT_RUN / BLOCKED / ENV_INCOMPATIBLE 会被如实登记，**不计入 PASS**；
    是否放行由调用方用 --allow-status 显式声明，缺省只放行 PASS。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_identity as _ri  # noqa: E402


def verify_one(path: Path, expect_run_id: str | None, expect_commit: str | None,
               max_age: int | None, allow_status: set[str]) -> dict:
    """校验单个报告，返回结构化结论（不抛异常）。"""
    rec: dict = {"report": str(path), "ok": False}
    if not path.exists():
        rec.update(status="FAIL", reason="报告不存在；不得用历史报告或空文件冒充成功")
        return rec
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        rec.update(status="FAIL", reason=f"报告不可解析: {e}")
        return rec

    try:
        ident = _ri.assert_report_fresh(
            data, expect_run_id=expect_run_id, expect_commit=expect_commit,
            max_age_seconds=max_age, source=str(path))
    except _ri.StaleReportError as e:
        rec.update(status="FAIL", reason=str(e))
        return rec

    status = ident["status"]
    rec.update(status=status, run_id=ident["run_id"], git_commit=ident["git_commit"],
               execution_time=ident["execution_time"], artifact_count=ident.get("artifact_count"))
    if status not in allow_status:
        rec.update(ok=False,
                   reason=(f"报告状态 {status} 不在允许集合 {sorted(allow_status)}；"
                           f"NOT_RUN/BLOCKED/ENV_INCOMPATIBLE 不得计入 PASS"))
        return rec
    rec.update(ok=True, reason=f"身份新鲜（run_id={ident['run_id']}），状态 {status} 被允许")
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="校验报告运行身份，拒绝采信旧报告")
    ap.add_argument("reports", nargs="+", help="待校验的 JSON 报告路径")
    ap.add_argument("--expect-run-id", default=None,
                    help="期望 run_id（默认取 JM_RUN_ID）")
    ap.add_argument("--expect-commit", default=None,
                    help="期望 git commit（默认取当前 HEAD）")
    ap.add_argument("--max-age-seconds", type=int, default=None)
    ap.add_argument("--allow-status", default="PASS",
                    help="逗号分隔的可放行状态（默认仅 PASS）")
    args = ap.parse_args(argv)

    if not args.reports:
        print("用法错误：必须指定至少一个报告路径", file=sys.stderr)
        return 2

    expect_run_id = args.expect_run_id
    if expect_run_id is None:
        try:
            expect_run_id = _ri.current_run_id_from_env()
        except RuntimeError as e:
            print(f"用法错误: {e}", file=sys.stderr)
            return 2

    expect_commit = args.expect_commit
    if expect_commit is None:
        commit, _ = _ri.git_head(Path.cwd())
        expect_commit = commit

    allow = {s.strip().upper() for s in args.allow_status.split(",") if s.strip()}
    illegal = allow - set(_ri.STATUSES)
    if illegal:
        print(f"用法错误：未登记状态 {sorted(illegal)}", file=sys.stderr)
        return 2

    results = [verify_one(Path(p), expect_run_id, expect_commit,
                          args.max_age_seconds, allow) for p in args.reports]
    ok = all(r["ok"] for r in results)
    for r in results:
        mark = "OK  " if r["ok"] else "FAIL"
        print(f"[{mark}] {r['report']} :: {r['status']} :: {r['reason']}")

    summary = {
        "generated_by": "scripts/phase5_1a/verify_run_freshness.py",
        "expect_run_id": expect_run_id,
        "expect_commit": expect_commit,
        "allow_status": sorted(allow),
        "ok": ok,
        "results": results,
        "not_passing": [r["report"] for r in results if r["status"] != "PASS"],
    }
    out = Path("reports/phase5-2/ci/report-freshness.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"report-freshness: ok={ok} 未达PASS的报告={len(summary['not_passing'])} -> {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
