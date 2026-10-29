# -*- coding: utf-8 -*-
"""研究产物/数据冻结完整性检查（Phase5-1A / A5、A7 门禁证据，只读）。

在 `annotation/freeze.verify_freeze()` 之外补齐三类缺口（不改写冻结模块）：
  1. **规范化 manifest 摘要**：对 manifest 元数据做规范化 JSON 摘要（canonical digest），
     使"清单自身被改写"可被发现（verify_freeze 只校验清单列出的文件哈希）；
  2. **文件清单外新增文件检测**：冻结目录内出现未登记文件时告警；
  3. **路径歧义检测**：manifest 相对路径在项目根 / 清单目录下解析不一致时告警。

状态口径（Phase5-2 / Batch 0 修复，此前 main() 恒返回 0 是可信性缺陷）：
  PASS              存在 manifest 且全部检查通过              -> 退出码 0
  FAIL              manifest 内容错误 / 文件缺失 / 哈希不匹配   -> 退出码 1
  FAIL              要求必须存在 manifest 但扫描结果为 0        -> 退出码 1
  NOT_RUN           非必需 artifact 校验且没有产物              -> 退出码 0
                    （**必须显式记为 NOT_RUN，绝不计入 PASS**）
  ENV_INCOMPATIBLE  运行环境无法执行检查（如缺依赖）            -> 退出码 2

命令行：
  --root DIR             扫描根（默认项目根；合成夹具自检时指向临时目录）
  --glob PATTERN         manifest 匹配模式（默认 data/independent_eval/**/manifest*.json）
  --require-manifest     本次为"必需"校验：扫描到 0 份 manifest 即 FAIL
  --out PATH             报告输出路径（默认 reports/phase5-1a/artifact-integrity.json）
  --run-id ID            运行身份 ID（默认取 JM_RUN_ID）
  --quiet                只输出汇总行

退出码：0=PASS 或 NOT_RUN；1=FAIL；2=ENV_INCOMPATIBLE / 用法错误。

能力边界（必须与摘要一起呈现）：
  * 普通哈希用于检测**非预期变化**（拷贝错误、误改、误删）；
  * **不等于**经过可信签名的防恶意篡改机制——攻击者可同时改文件与清单哈希；
  * 因此本检查结果只能表述为"完整性自检通过"，不得表述为"已防篡改"。
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

from job_matching.core import sha256_file  # noqa: E402

import run_identity as _ri  # noqa: E402

DEFAULT_GLOB = "data/independent_eval/**/manifest*.json"
CAPABILITY_BOUNDARY = (
    "普通哈希完整性自检：可发现非预期变化（误改/误删/清单外新增），"
    "不等于可信签名防篡改；不得据此声称数据已防恶意篡改或已匿名化")

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ENV = 2


def canonical_digest(manifest: dict) -> str:
    """规范化 manifest 摘要：键排序 + 紧凑分隔符 + UTF-8，稳定可复算。"""
    blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _rel(p: Path, base: Path) -> str:
    for cand in (base, ROOT):
        try:
            return str(p.relative_to(cand)).replace("\\", "/")
        except ValueError:
            continue
    return str(p).replace("\\", "/")


def check_manifest(manifest_path: Path, base_root: Path) -> dict:
    """检查单份 manifest。返回结构化结论（含 problems / ok）。"""
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"manifest": _rel(manifest_path, base_root), "ok": False,
                "problems": [f"manifest.json 无法解析: {e}"]}
    base = manifest_path.parent
    problems: list[str] = []
    files_report = []
    listed_names: set[str] = set()
    for key, rec in sorted((manifest.get("files") or {}).items()):
        rel = str(rec.get("path", ""))
        listed_names.add(Path(rel).name)
        candidates = [base / rel, base_root / rel, base / Path(rel).name]
        existing = [c for c in candidates if c.exists()]
        if not existing:
            problems.append(f"文件缺失: {rel}")
            files_report.append({"key": key, "path": rel, "exists": False, "match": False})
            continue
        primary = existing[0]
        if len({str(c.resolve()) for c in existing}) > 1:
            problems.append(f"路径歧义: {rel} 在多个位置存在 -> "
                            f"{sorted(str(c) for c in existing)}")
        actual = sha256_file(primary)
        match = (actual == rec.get("sha256"))
        if not match:
            problems.append(f"哈希不匹配: {rel}（expected={rec.get('sha256')} actual={actual}）")
        files_report.append({
            "key": key, "path": rel, "exists": True, "match": match,
            "expected": rec.get("sha256"), "actual": actual,
            "resolved": _rel(primary, base_root)})

    extras = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if p.name in ("manifest.json", "op_log.jsonl"):
            continue
        if p.name not in listed_names:
            extras.append(_rel(p, base_root))
    if extras:
        problems.append(f"冻结目录存在清单外文件 {len(extras)} 个: {extras[:10]}")

    meta = {k: v for k, v in manifest.items() if k != "files"}
    return {
        "manifest": _rel(manifest_path, base_root),
        "stage": manifest.get("stage"),
        "dataset_version": manifest.get("dataset_version"),
        "frozen_at": manifest.get("frozen_at"),
        "canonical_manifest_digest": canonical_digest(manifest),
        "metadata_digest": canonical_digest(meta),
        "metadata_fields": sorted(meta),
        "files_listed": len(files_report),
        "files_ok": sum(1 for f in files_report if f.get("match")),
        "unlisted_files": extras,
        "files": files_report,
        "problems": problems,
        "ok": not problems,
    }


def decide_status(*, require_manifest: bool, manifest_count: int,
                  bad_count: int) -> tuple[str, str]:
    """状态判定（单一事实来源，负向测试直接覆盖此函数）。"""
    if manifest_count == 0:
        if require_manifest:
            return "FAIL", ("要求必须存在 manifest，但扫描结果为 0；"
                            "不得用历史报告或空跑冒充通过")
        return "NOT_RUN", "非必需 artifact 校验且没有产物；显式记为 NOT_RUN，不计入 PASS"
    if bad_count:
        return "FAIL", f"{bad_count}/{manifest_count} 份 manifest 存在完整性问题"
    return "PASS", f"{manifest_count} 份 manifest 全部完整"


def run_check(root: Path, pattern: str, require_manifest: bool,
              out_path: Path | None, run_id: str, quiet: bool = False) -> tuple[int, dict]:
    manifests = sorted(root.glob(pattern))
    results = [check_manifest(p, root) for p in manifests]
    bad = sum(1 for r in results if not r.get("ok"))
    status, reason = decide_status(require_manifest=require_manifest,
                                   manifest_count=len(results), bad_count=bad)

    identity = _ri.build_run_identity(ROOT, artifact_count=len(results),
                                      status=status,
                                      extra={"scan_root": str(root),
                                             "scan_glob": pattern,
                                             "require_manifest": require_manifest,
                                             "tool": "check_artifact_integrity"})
    identity["run_id"] = run_id
    out = {
        "generated_by": "scripts/phase5_1a/check_artifact_integrity.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "capability_boundary": CAPABILITY_BOUNDARY,
        "status": status,
        "status_reason": reason,
        "require_manifest": require_manifest,
        "manifests_checked": len(results),
        "manifests_ok": sum(1 for r in results if r.get("ok")),
        "run_identity": identity,
        "results": results,
    }

    target = out_path or (ROOT / "reports" / "phase5-1a" / "artifact-integrity.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")

    mark = {"PASS": "PASS", "FAIL": "FAIL", "NOT_RUN": "NOT_RUN"}[status]
    print(f"artifact-integrity [{mark}] {out['manifests_ok']}/{out['manifests_checked']} OK"
          f" | {reason}")
    if not quiet:
        for r in results:
            if not r.get("ok"):
                print("  !", r["manifest"], r.get("problems"))
    print(f"  run_id={run_id} commit={identity['git_commit'][:12]} -> {target}")

    if status == "FAIL":
        return EXIT_FAIL, out
    return EXIT_PASS, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究产物/数据冻结完整性检查（只读）")
    ap.add_argument("--root", default=str(ROOT), help="扫描根目录")
    ap.add_argument("--glob", default=DEFAULT_GLOB, help="manifest 匹配模式")
    ap.add_argument("--require-manifest", action="store_true",
                    help="必需校验：扫描到 0 份 manifest 即判定 FAIL")
    ap.add_argument("--out", default=None, help="报告输出路径")
    ap.add_argument("--run-id", default=None, help="运行身份 ID（默认取 JM_RUN_ID）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        run_id = args.run_id or _ri.current_run_id_from_env()
    except RuntimeError as e:
        print(f"ENV_INCOMPATIBLE: {e}", file=sys.stderr)
        return EXIT_ENV

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"FAIL: 扫描根不存在: {root}", file=sys.stderr)
        return EXIT_FAIL

    out_path = Path(args.out).resolve() if args.out else None
    code, _ = run_check(root, args.glob, args.require_manifest, out_path, run_id,
                        quiet=args.quiet)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
