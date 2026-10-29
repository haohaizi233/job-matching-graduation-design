# -*- coding: utf-8 -*-
"""Phase5-1R 产物完整性校验（差异测试证据，R5）。

对以下历史产物计算 SHA-256 并与登记信息/上一轮记录比对：
  * data/raw/**            —— 原始数据（Phase3 输入，绝不允许改动）；
  * models/**              —— Phase4-1 / Phase4-2 模型权重与清单；
  * data/independent_eval/frozen/** —— Gold 冻结产物与阻断记录；
  * 历史评估/测试报告       —— 归档指标是否被本次整改改动。

输出：reports/phase5-1r/artifact-integrity.json
用法：python scripts/phase5_1r/artifact_integrity.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "phase5-1r" / "artifact-integrity.json"

WEIGHT_SUFFIXES = (".pkl", ".pt", ".pth", ".joblib")
HISTORICAL_REPORTS = (
    "reports/model-training/model-tests.json",
    "reports/model-training/results.json",
    "reports/education-training/education-tests.json",
    "reports/phase4-3a/test-results.json",
    "reports/phase4-3a-2/test-results.json",
    "reports/phase5-1/test-results.json",
    "reports/data-quality-gates.json",
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_tree(root: Path, *, suffixes: tuple[str, ...] | None = None) -> dict:
    out: dict[str, dict] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if suffixes and p.suffix.lower() not in suffixes:
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        out[rel] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    return out


def combined_digest(files: dict[str, dict]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(files[rel]["sha256"].encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def manifest_checksum_check() -> list[dict]:
    """用 manifest 登记的 sha256 复核模型权重（不加载权重，避免环境不兼容）。"""
    results = []
    for mp in sorted(ROOT.glob("models/**/manifest.json")):
        try:
            man = json.loads(mp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            results.append({"manifest": str(mp.relative_to(ROOT)).replace("\\", "/"),
                            "readable": False, "error": f"{type(e).__name__}: {e}"})
            continue
        arts = []
        for key in ("artifacts", "files", "weights"):
            if isinstance(man.get(key), list):
                arts.extend(man[key])
        checks = []
        for art in arts:
            if not isinstance(art, dict):
                continue
            name = art.get("path") or art.get("name") or art.get("file")
            want = art.get("sha256")
            if not name or not want:
                continue
            cand = (mp.parent / Path(str(name)).name)
            if not cand.exists():
                checks.append({"artifact": str(name), "status": "missing"})
                continue
            got = sha256_file(cand)
            checks.append({"artifact": cand.name,
                           "status": "match" if got == want else "mismatch",
                           "sha256": got})
        results.append({
            "manifest": str(mp.relative_to(ROOT)).replace("\\", "/"),
            "readable": True, "artifact_checks": checks,
            "all_match": all(c["status"] == "match" for c in checks) if checks else None,
        })
    return results


def git_state() -> dict:
    def run(*args: str) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                               text=True, timeout=60)
            return r.stdout.strip()
        except Exception as e:  # noqa: BLE001
            return f"<git error: {e}>"

    reports_state = {}
    for rel in HISTORICAL_REPORTS:
        out = run("status", "--short", "--", rel)
        reports_state[rel] = out.splitlines()[0].strip() if out else "clean"
    return {
        "head": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "historical_reports_status": reports_state,
    }


def main() -> int:
    raw_files = hash_tree(ROOT / "data" / "raw")
    weight_files = hash_tree(ROOT / "models", suffixes=WEIGHT_SUFFIXES + (".json",))
    frozen_files = hash_tree(ROOT / "data" / "independent_eval" / "frozen")
    out = {
        "generated_by": "scripts/phase5_1r/artifact_integrity.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "purpose": "Phase5-1R 差异测试：历史数据/权重/归档指标完整性证据",
        "data_raw": {"files": len(raw_files),
                     "combined_digest": combined_digest(raw_files),
                     "detail": raw_files},
        "models": {"files": len(weight_files),
                   "combined_digest": combined_digest(weight_files),
                   "manifest_verification": manifest_checksum_check(),
                   "detail": weight_files},
        "frozen_eval": {"files": len(frozen_files),
                        "combined_digest": combined_digest(frozen_files),
                        "detail": frozen_files},
        "git": git_state(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    bad = [m for m in out["models"]["manifest_verification"]
           if m.get("all_match") is False]
    print(f"data_raw files={out['data_raw']['files']} digest={out['data_raw']['combined_digest'][:16]}")
    print(f"models  files={out['models']['files']} digest={out['models']['combined_digest'][:16]} "
          f"manifest_mismatch={len(bad)}")
    print(f"frozen  files={out['frozen_eval']['files']} digest={out['frozen_eval']['combined_digest'][:16]}")
    print(f"-> {OUT.relative_to(ROOT)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
