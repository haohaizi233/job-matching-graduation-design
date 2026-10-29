# -*- coding: utf-8 -*-
"""历史模型兼容性诊断（Phase5-1A / A4 门禁证据）。

只读诊断：**不重训、不改写、不移动**任何历史 checkpoint。

输出：
  reports/phase5-1a/model-compatibility.json   —— 逐模型加载结果与环境差异
  reports/phase5-1a/model-compatibility.md     —— 兼容性矩阵

分类口径（与 service/model_registry.classify_load_failure 一致）：
  loaded            —— 当前运行环境可加载并可用
  env_incompatible  —— 历史 checkpoint 依赖旧版依赖栈（如旧 scikit-learn 反序列化失败）
  artifact_missing  —— 权重文件缺失
  artifact_corrupt  —— 权重文件损坏 / 加载逻辑失败
  skipped           —— 无权重文件或未登记加载方式

能力边界：普通哈希/加载检查只能证明"当前环境能否加载"，不能证明模型效果；
效果验收仍受 H2 BLOCKED 约束。
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.service.model_registry import classify_load_failure  # noqa: E402

OUT_DIR = ROOT / "reports" / "phase5-1a"


def runtime_env() -> dict:
    env = {"python": sys.version.split()[0]}
    for name, mod in (("numpy", "numpy"), ("pandas", "pandas"), ("sklearn", "sklearn"),
                      ("joblib", "joblib"), ("torch", "torch")):
        try:
            m = __import__(mod)
            env[name] = getattr(m, "__version__", "unknown")
        except Exception as e:  # 缺失也要如实记录
            env[name] = f"NOT_INSTALLED({type(e).__name__})"
    return env


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
    except Exception as e:
        kind, why = classify_load_failure(e)
        if kind == "env_incompatible":
            return "env_incompatible", why
        return "artifact_corrupt", why


def scan() -> list[dict]:
    rows: list[dict] = []
    for manifest in sorted(ROOT.glob("models/**/manifest.json")):
        run_dir = manifest.parent
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as e:
            rows.append({"run_dir": str(run_dir.relative_to(ROOT)),
                         "status": "artifact_corrupt",
                         "note": f"manifest.json 无法解析: {e}"})
            continue
        weights = [p for p in sorted(run_dir.glob("model.*")) if p.is_file()]
        if not weights:
            rows.append({"run_dir": str(run_dir.relative_to(ROOT)),
                         "model_name": meta.get("model_name"),
                         "status": "skipped", "note": "目录内无 model.* 权重文件"})
            continue
        status, note = try_load_weights(weights[0])
        recorded = (meta.get("environment") or {})
        current = runtime_env()
        drift = {k: {"trained_with": recorded.get(k), "current": current.get(k)}
                 for k in sorted(set(recorded) | {"python", "sklearn", "numpy", "pandas", "torch"})
                 if k in recorded or k in current}
        rows.append({
            "run_dir": str(run_dir.relative_to(ROOT)),
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = scan()
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    out = {
        "generated_by": "scripts/phase5_1a/diagnose_model_compat.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runtime_environment": runtime_env(),
        "policy": ("只读诊断；不重训、不改写历史 checkpoint；"
                   "env_incompatible 属环境问题，不得记为权重缺失或模型业务失败"),
        "summary": summary,
        "models": rows,
    }
    (OUT_DIR / "model-compatibility.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    lines = ["# 历史模型兼容性矩阵（Phase5-1A）", "",
             f"- 生成时间：{out['created_at']}",
             f"- 运行环境：Python {out['runtime_environment']['python']} / "
             f"sklearn {out['runtime_environment']['sklearn']} / "
             f"numpy {out['runtime_environment']['numpy']} / "
             f"pandas {out['runtime_environment']['pandas']} / "
             f"torch {out['runtime_environment']['torch']}",
             f"- 汇总：{summary}", "",
             "| 模型目录 | 模型 | 状态 | 训练环境 | 说明 |",
             "|---|---|---|---|---|"]
    for r in rows:
        env = r.get("training_environment") or {}
        env_str = (f"py{env.get('python', '?')} / sklearn{env.get('sklearn', '?')}"
                   if env else "未记录")
        lines.append(f"| {r['run_dir']} | {r.get('model_name', '')} | {r['status']} | "
                     f"{env_str} | {r.get('note', '')} |")
    lines += ["", "说明：`env_incompatible` 表示历史 checkpoint 与当前依赖栈不兼容，",
              "需要 Legacy Model Compatibility Environment 复现（Conda/venv 隔离，不引入微服务）；",
              "历史权重一律不动；本矩阵不代表任何模型效果验收结论（H2 维持 BLOCKED）。", ""]
    (OUT_DIR / "model-compatibility.md").write_text("\n".join(lines),
                                                    encoding="utf-8", newline="\n")
    print("model-compatibility:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
