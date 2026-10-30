# -*- coding: utf-8 -*-
"""历史模型权重完整性检查（Artifact-dependent，只读）。

背景（Phase5-3 / M1 缺陷修复）：
  此前 `tests/phase5_1a/test_a1_a7_gates.py` 的 `test_history_checkpoints_untouched`
  只断言 `models/` 目录存在。该检查有两个问题：
    1. `.gitignore` 忽略 `models/**`，干净 checkout 中 `models/` 必然不存在，
       于是 Core CI（要求全新 checkout 通过）必然失败；
    2. "目录存在" 推不出 "权重未被修改"，无法真正发现权重被改动。
  因此真实权重完整性检查归位到 **Artifact-dependent Validation**，
  并在缺失产物时显式登记 NOT_RUN / BLOCKED，绝不计入 PASS。

状态口径（不得同义替换）：
  PASS              存在 models/ 与冻结基线，且全部权重文件哈希一致      -> 退出码 0
  FAIL              存在 models/ 与基线，但出现哈希不一致 / 基线内文件缺失 -> 退出码 1
  NOT_RUN           models/ 缺失，或尚未建立冻结基线                     -> 退出码 0
  ENV_INCOMPATIBLE  运行环境无法执行检查（如 JM_RUN_ID 缺失）             -> 退出码 2

纪律：
  * NOT_RUN 一律不计入 PASS；没有真实比对就没有 PASS；
  * 不创建伪造 checkpoint、不重训权重、不改写历史产物（本脚本只读 models/）；
  * 基线缺失时只输出"当前清单（diagnostic inventory）"，状态仍是 NOT_RUN，
    因为当前清单无法证明"相对某个时点未被修改"。

命令行：
  --root DIR          权重根（默认 <repo>/models）
  --baseline PATH     冻结基线（默认 configs/history-weights-baseline.json）
  --write-baseline    以当前扫描结果建立/覆盖基线（显式动作，需人工确认时点）
  --out PATH          报告输出（默认 reports/phase5-3/history-weights-integrity.json）
  --run-id ID         运行身份（默认取 JM_RUN_ID）
  --quiet             只输出汇总行

退出码：0 = PASS 或 NOT_RUN；1 = FAIL；2 = ENV_INCOMPATIBLE / 用法错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import run_identity as _ri  # noqa: E402

WEIGHT_SUFFIXES = (".pt", ".pth", ".ckpt", ".pkl", ".joblib", ".bin",
                   ".safetensors", ".onnx", ".h5")
CAPABILITY_BOUNDARY = (
    "普通哈希完整性自检：可发现非预期变化（误改/误删/清单外新增），"
    "不等于可信签名防篡改；不得据此声称权重已防恶意篡改")

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ENV = 2


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: Path) -> dict[str, dict]:
    """扫描权重文件清单（只读）。键为相对 root 的 POSIX 路径。"""
    out: dict[str, dict] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in WEIGHT_SUFFIXES:
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        out[rel] = {"path": rel, "size": p.stat().st_size, "sha256": sha256_file(p)}
    return out


def compare(baseline: dict, current: dict) -> tuple[list[str], list[str], list[str]]:
    """比对基线与当前清单，返回 (changed, missing, extra)。"""
    b, c = baseline.get("files", {}), current
    changed = sorted(k for k in b if k in c and b[k].get("sha256") != c[k]["sha256"])
    missing = sorted(k for k in b if k not in c)
    extra = sorted(k for k in c if k not in b)
    return changed, missing, extra


def decide_status(*, models_exists: bool, has_baseline: bool,
                  changed: list[str], missing: list[str]) -> tuple[str, str]:
    """状态判定（单一事实来源，负向测试直接覆盖此函数）。

    关键约束：**没有基线就不可能 PASS**——因为"未与冻结基线比对"不等于"未被修改"。
    """
    if not models_exists:
        return "NOT_RUN", "models/ 不存在（干净 checkout / 无权重产物）；不计入 PASS"
    if not has_baseline:
        return "NOT_RUN", ("尚未建立权重冻结基线；仅登记当前清单，"
                           "不构成'未被修改'的证据，不计入 PASS")
    if changed or missing:
        return "FAIL", (f"权重完整性不通过：{len(changed)} 个哈希变化、"
                        f"{len(missing)} 个基线内文件缺失")
    return "PASS", "全部权重文件与冻结基线一致"


def build_report(*, status: str, reason: str, root: Path, baseline_path: Path,
                 has_baseline: bool, current: dict, changed: list[str],
                 missing: list[str], extra: list[str], run_id: str) -> dict:
    identity = _ri.build_run_identity(
        ROOT, artifact_count=len(current), status=status,
        extra={"tool": "check_history_weights_integrity",
               "scan_root": str(root),
               "baseline": str(baseline_path),
               "has_baseline": has_baseline})
    identity["run_id"] = run_id
    return {
        "generated_by": "scripts/phase5_1a/check_history_weights_integrity.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "capability_boundary": CAPABILITY_BOUNDARY,
        "status": status,
        "status_reason": reason,
        "scan_root": str(root),
        "models_exists": root.is_dir(),
        "baseline_path": str(baseline_path),
        "has_baseline": has_baseline,
        "weights_scanned": len(current),
        "changed": changed,
        "missing": missing,
        "extra": extra,
        "files": current,
        "run_identity": identity,
    }


def run_check(root: Path, baseline_path: Path, out_path: Path, run_id: str,
              write_baseline: bool = False, quiet: bool = False) -> tuple[int, dict]:
    current = inventory(root)

    if write_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_by": "scripts/phase5_1a/check_history_weights_integrity.py",
            "note": ("历史模型权重完整性基线（只读清单）。仅登记文件哈希，"
                     "不包含权重内容，不是评估协议，不改写任何模型产物。"),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "root": str(root),
            "files": current,
        }
        baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8", newline="\n")
        print(f"已建立权重完整性基线：{baseline_path}（{len(current)} 个权重文件）")
        status, reason = "PASS", f"基线已建立（{len(current)} 个权重文件）"
        has_baseline = True
        changed: list[str] = []
        missing: list[str] = []
        extra: list[str] = []
    else:
        has_baseline = baseline_path.is_file()
        baseline = {}
        if has_baseline:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        changed, missing, extra = compare(baseline, current)
        status, reason = decide_status(models_exists=root.is_dir(), has_baseline=has_baseline,
                                       changed=changed, missing=missing)

    report = build_report(status=status, reason=reason, root=root,
                          baseline_path=baseline_path, has_baseline=has_baseline,
                          current=current, changed=changed, missing=missing,
                          extra=extra, run_id=run_id)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")

    print(f"history-weights-integrity [{status}] "
          f"scanned={len(current)} baseline={'yes' if has_baseline else 'no'} "
          f"changed={len(changed)} missing={len(missing)} extra={len(extra)}")
    print(f"  reason: {reason}")
    if not quiet:
        for k in changed[:10]:
            print(f"  ! 哈希变化: {k}")
        for k in missing[:10]:
            print(f"  ! 基线内缺失: {k}")
    print(f"  run_id={run_id} commit={report['run_identity']['git_commit'][:12]} -> {out_path}")

    return (EXIT_FAIL if status == "FAIL" else EXIT_PASS), report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="历史模型权重完整性检查（Artifact-dependent，只读）")
    ap.add_argument("--root", default=str(ROOT / "models"), help="权重根目录")
    ap.add_argument("--baseline", default=str(ROOT / "configs" / "history-weights-baseline.json"))
    ap.add_argument("--write-baseline", action="store_true", help="以当前扫描结果建立基线")
    ap.add_argument("--out", default=str(ROOT / "reports" / "phase5-3" /
                                         "history-weights-integrity.json"))
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        run_id = args.run_id or _ri.current_run_id_from_env()
    except RuntimeError as e:
        print(f"ENV_INCOMPATIBLE: {e}", file=sys.stderr)
        return EXIT_ENV

    root = Path(args.root).resolve()
    baseline_path = Path(args.baseline).resolve()
    out_path = Path(args.out).resolve()

    code, _ = run_check(root, baseline_path, out_path, run_id,
                        write_baseline=args.write_baseline, quiet=args.quiet)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
