# -*- coding: utf-8 -*-
"""历史模型兼容性诊断（Phase5-1A / A4 门禁证据）。

只读诊断：**不重训、不改写、不移动**任何历史 checkpoint。

Phase5-2 / Batch 0 修复（此前 CI 用 `|| true` + 只检查报告存在，旧报告可冒充本次成功）：
  * 每次运行写入**运行身份**（run_id / git_commit / execution_time / python_version /
    dependency_versions / artifact_count / status）；
  * 消费方必须用 scripts/phase5_1a/verify_run_freshness.py 校验身份，
    run_id 或 git_commit 不匹配即拒绝采信（见 run_identity.assert_report_fresh）；
  * 扫描到 0 个 checkpoint 时显式 NOT_RUN，不得写成 PASS；
  * 运行异常时返回 ENV_INCOMPATIBLE / FAIL，且**不生成**可被误读为成功的新报告。

输出：
  --out 指定路径（默认 reports/phase5-1a/model-compatibility.json）
  同时写出 <stem>.md 兼容性矩阵

分类口径（与 service/model_registry.classify_load_failure 一致）：
  loaded            —— 当前运行环境可加载并可用
  loaded_with_version_warning —— 可加载但存在依赖版本漂移警告
  env_incompatible  —— 历史 checkpoint 依赖旧版依赖栈（如旧 scikit-learn 反序列化失败）
  artifact_missing  —— 权重文件缺失
  artifact_corrupt  —— 权重文件损坏 / 加载逻辑失败
  skipped           —— 无权重文件或未登记加载方式

运行 status 口径：
  PASS              扫描到 checkpoint 且完成诊断（结论好坏不影响"诊断已执行"）
  NOT_RUN           未扫描到任何 checkpoint（没有可诊断对象）
  ENV_INCOMPATIBLE  运行环境缺少诊断必需能力（如 import 失败）
  FAIL              诊断过程自身异常

能力边界：普通哈希/加载检查只能证明"当前环境能否加载"，不能证明模型效果；
效果验收仍受 H2 BLOCKED 约束。
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import run_identity as _ri  # noqa: E402

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ENV = 2


def runtime_env() -> dict:
    return _ri.dependency_versions(("numpy", "pandas", "sklearn", "joblib", "torch"))


def try_load_weights(path: Path) -> tuple[str, str]:
    """尝试反序列化权重。返回 (状态, 说明)。"""
    if not path.exists():
        return "artifact_missing", f"权重文件不存在: {path.name}"
    try:
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            if path.suffix == ".pkl":
                try:
                    import joblib
                    joblib.load(path)
                except Exception:
                    with open(path, "rb") as f:
                        pickle.load(f)
            elif path.suffix == ".pt":
                import torch
                torch.load(path, map_location="cpu", weights_only=False)
            else:
                return "skipped", f"未登记加载方式: {path.suffix}"
        drift = [str(w.category.__name__) for w in caught
                 if "Version" in w.category.__name__ or "Inconsistent" in str(w.message)]
        if drift:
            return "loaded_with_version_warning", (
                "可加载，但存在依赖版本漂移警告（如 scikit-learn 反序列化版本不一致）；"
                "输出不保证与训练时逐位一致，正式口径需在 Legacy 兼容环境复核")
        return "loaded", "当前环境可加载"
    except Exception as e:  # noqa: BLE001
        from job_matching.service.model_registry import classify_load_failure
        kind, why = classify_load_failure(e)
        if kind == "env_incompatible":
            return "env_incompatible", why
        return "artifact_corrupt", why


def scan(root: Path) -> list[dict]:
    rows: list[dict] = []
    for manifest in sorted(root.glob("models/**/manifest.json")):
        run_dir = manifest.parent
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            rows.append({"run_dir": str(run_dir.relative_to(root)),
                         "status": "artifact_corrupt",
                         "note": f"manifest.json 无法解析: {e}"})
            continue
        weights = [p for p in sorted(run_dir.glob("model.*")) if p.is_file()]
        if not weights:
            rows.append({"run_dir": str(run_dir.relative_to(root)),
                         "model_name": meta.get("model_name"),
                         "status": "skipped", "note": "目录内无 model.* 权重文件"})
            continue
        status, note = try_load_weights(weights[0])
        recorded = (meta.get("environment") or {})
        current = runtime_env()
        drift = {k: {"trained_with": recorded.get(k), "current": current.get(k)}
                 for k in sorted(set(recorded) | {"python", "sklearn", "numpy",
                                                  "pandas", "torch"})
                 if k in recorded or k in current}
        rows.append({
            "run_dir": str(run_dir.relative_to(root)),
            "model_name": meta.get("model_name"),
            "protocol": meta.get("protocol"),
            "run_id": meta.get("run_id"),
            "weight_file": weights[0].name,
            "weight_bytes": weights[0].stat().st_size,
            "status": status,
            "note": note,
            "training_environment": recorded,
            "environment_drift": drift,
            "dataset_version": meta.get("dataset_version"),
            "created_at": meta.get("created_at"),
        })
    return rows


def build_markdown(out: dict) -> list[str]:
    summary = out["summary"]
    ident = out["run_identity"]
    lines = ["# 历史模型兼容性矩阵（Phase5-1A）", "",
             f"- 生成时间：{out['created_at']}",
             f"- 运行身份：run_id=`{ident['run_id']}` / commit=`{ident['git_commit']}`",
             f"- 运行状态：**{ident['status']}**（{out['status_reason']}）",
             f"- 运行环境：Python {ident['python_version']} / "
             f"sklearn {ident['dependency_versions'].get('sklearn')} / "
             f"numpy {ident['dependency_versions'].get('numpy')} / "
             f"pandas {ident['dependency_versions'].get('pandas')} / "
             f"torch {ident['dependency_versions'].get('torch')}",
             f"- 扫描产物数：{ident['artifact_count']}",
             f"- 汇总：{summary}", "",
             "| 模型目录 | 模型 | 状态 | 训练环境 | 说明 |",
             "|---|---|---|---|---|"]
    for r in out["models"]:
        env = r.get("training_environment") or {}
        env_str = (f"py{env.get('python', '?')} / sklearn{env.get('sklearn', '?')}"
                   if env else "未记录")
        lines.append(f"| {r['run_dir']} | {r.get('model_name', '')} | {r['status']} | "
                     f"{env_str} | {r.get('note', '')} |")
    lines += ["", "说明：`env_incompatible` 表示历史 checkpoint 与当前依赖栈不兼容，",
              "需要 Legacy Model Compatibility Environment 复现（Conda/venv 隔离，不引入微服务）；",
              "历史权重一律不动；本矩阵不代表任何模型效果验收结论（H2 维持 BLOCKED）。",
              "",
              "可信性：消费方必须先用 `scripts/phase5_1a/verify_run_freshness.py` 校验",
              "`run_identity.run_id` 与 `git_commit`，不匹配即视为旧报告，不得采信。", ""]
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="历史模型兼容性诊断（只读，带运行身份）")
    ap.add_argument("--root", default=str(ROOT), help="扫描根目录")
    ap.add_argument("--out", default=str(ROOT / "reports" / "phase5-1a" /
                                        "model-compatibility.json"))
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    try:
        run_id = args.run_id or _ri.current_run_id_from_env()
    except RuntimeError as e:
        print(f"ENV_INCOMPATIBLE: {e}", file=sys.stderr)
        return EXIT_ENV

    root = Path(args.root).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 关键可信性动作：先把既有报告移开，避免"本次失败 + 旧报告残留"被误读成本次成功。
    stale = out_path.with_suffix(out_path.suffix + ".stale")
    if out_path.exists():
        out_path.replace(stale)

    try:
        rows = scan(root)
    except Exception as e:  # noqa: BLE001 - 诊断自身异常必须显式失败
        print(f"FAIL: 模型兼容诊断执行异常，未生成新报告: {type(e).__name__}: {e}",
              file=sys.stderr)
        return EXIT_FAIL

    summary: dict[str, int] = {}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    if rows:
        status = "PASS"
        reason = f"完成 {len(rows)} 个 checkpoint 的兼容性诊断"
    else:
        status = "NOT_RUN"
        reason = ("未扫描到任何模型 checkpoint（models/**/manifest.json 为空）；"
                  "显式记为 NOT_RUN，不得计入 PASS。模型实际兼容诊断属"
                  "Artifact-dependent Validation，需在具备权重的环境执行")

    identity = _ri.build_run_identity(root, artifact_count=len(rows), status=status,
                                      extra={"tool": "diagnose_model_compat"})
    identity["run_id"] = run_id

    out = {
        "generated_by": "scripts/phase5_1a/diagnose_model_compat.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": status,
        "status_reason": reason,
        "run_identity": identity,
        "runtime_environment": runtime_env(),
        "policy": ("只读诊断；不重训、不改写历史 checkpoint；"
                   "env_incompatible 属环境问题，不得记为权重缺失或模型业务失败；"
                   "无 checkpoint 时记 NOT_RUN，不得记 PASS"),
        "summary": summary,
        "models": rows,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    out_path.with_suffix(".md").write_text("\n".join(build_markdown(out)),
                                           encoding="utf-8", newline="\n")
    stale.unlink(missing_ok=True)

    print(f"model-compatibility [{status}] {summary} | {reason}")
    print(f"  run_id={run_id} commit={identity['git_commit'][:12]} -> {out_path}")
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
