# -*- coding: utf-8 -*-
"""研究产物/数据冻结完整性检查（Phase5-1A / A5、A7 门禁证据，只读）。

在 `annotation/freeze.verify_freeze()` 之外补齐三类缺口（不改写冻结模块）：
  1. **规范化 manifest 摘要**：对 manifest 元数据做规范化 JSON 摘要（canonical digest），
     使"清单自身被改写"可被发现（verify_freeze 只校验清单列出的文件哈希）；
  2. **文件清单外新增文件检测**：冻结目录内出现未登记文件时告警；
  3. **路径歧义检测**：manifest 相对路径在项目根 / 清单目录下解析不一致时告警
     （verify_freeze 的多候选解析可能被同名文件混淆）。

能力边界（必须与摘要一起呈现）：
  * 普通哈希用于检测**非预期变化**（拷贝错误、误改、误删）；
  * **不等于**经过可信签名的防恶意篡改机制——攻击者可同时改文件与清单哈希；
  * 因此本检查结果只能表述为"完整性自检通过"，不得表述为"已防篡改"。

输出：reports/phase5-1a/artifact-integrity.json
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.core import sha256_file  # noqa: E402

OUT_DIR = ROOT / "reports" / "phase5-1a"
CAPABILITY_BOUNDARY = (
    "普通哈希完整性自检：可发现非预期变化（误改/误删/清单外新增），"
    "不等于可信签名防篡改；不得据此声称数据已防恶意篡改或已匿名化")


def canonical_digest(manifest: dict) -> str:
    """规范化 manifest 摘要：键排序 + 紧凑分隔符 + UTF-8，稳定可复算。"""
    blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def check_manifest(manifest_path: Path) -> dict:
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return {"manifest": str(manifest_path.relative_to(ROOT)), "ok": False,
                "problems": [f"manifest.json 无法解析: {e}"]}
    base = manifest_path.parent
    problems: list[str] = []
    files_report = []
    listed_names: set[str] = set()
    for key, rec in sorted((manifest.get("files") or {}).items()):
        rel = str(rec.get("path", ""))
        listed_names.add(Path(rel).name)
        candidates = [base / rel, ROOT / rel, base / Path(rel).name]
        existing = [c for c in candidates if c.exists()]
        if not existing:
            problems.append(f"文件缺失: {rel}")
            files_report.append({"key": key, "path": rel, "exists": False, "match": False})
            continue
        primary = existing[0]
        if len(existing) > 1 and len({str(c.resolve()) for c in existing}) > 1:
            problems.append(f"路径歧义: {rel} 在多个位置存在 -> {sorted(str(c) for c in existing)}")
        actual = sha256_file(primary)
        match = (actual == rec.get("sha256"))
        if not match:
            problems.append(f"哈希不匹配: {rel}（expected={rec.get('sha256')} actual={actual}）")
        files_report.append({"key": key, "path": rel, "exists": True, "match": match,
                             "expected": rec.get("sha256"), "actual": actual,
                             "resolved": str(primary.relative_to(ROOT)) if str(primary).startswith(str(ROOT)) else str(primary)})

    # 清单外文件检测（只看 manifest 同级目录，忽略 manifest 自身与操作日志）
    extras = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        if p.name in ("manifest.json", "op_log.jsonl"):
            continue
        if p.name not in listed_names:
            extras.append(str(p.relative_to(ROOT)))
    if extras:
        problems.append(f"冻结目录存在清单外文件 {len(extras)} 个: {extras[:10]}")

    meta = {k: v for k, v in manifest.items() if k != "files"}
    return {
        "manifest": str(manifest_path.relative_to(ROOT)),
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


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 范围：研究产物/数据冻结清单（data/independent_eval/**），
    # 数据管线/特征清单由 scripts/verify_data_integrity.py 另行覆盖，避免重复登记。
    manifests = sorted(ROOT.glob("data/independent_eval/**/manifest*.json"))
    results = [check_manifest(p) for p in manifests]
    out = {
        "generated_by": "scripts/phase5_1a/check_artifact_integrity.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "capability_boundary": CAPABILITY_BOUNDARY,
        "manifests_checked": len(results),
        "manifests_ok": sum(1 for r in results if r.get("ok")),
        "results": results,
    }
    (OUT_DIR / "artifact-integrity.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(f"artifact-integrity: {out['manifests_ok']}/{out['manifests_checked']} OK")
    for r in results:
        if not r.get("ok"):
            print("  !", r["manifest"], r.get("problems"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
