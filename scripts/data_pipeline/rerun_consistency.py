# -*- coding: utf-8 -*-
"""重复执行一致性取证（验收项 P3-12）。

用法：
    python scripts/data_pipeline/rerun_consistency.py snapshot   # 记录当前产物指纹
    python scripts/data_pipeline/rerun_consistency.py compare    # 与上次快照比对并落盘结论

比对对象是**确定性产物**（切分索引、特征表、目标表、特征矩阵、学历输入/标签、
Embedding 数组与 ID 映射），以及 Baseline 指标数值（剔除 created_at / seconds 等
时间字段）。manifest.json 自带 created_at，其文件哈希必然变化，故只比对其登记的
文件哈希与统计量，不比对 manifest 文件本身。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401
from job_matching.config import get_config  # noqa: E402
from job_matching.core import ROOT, jdump, sha256_file  # noqa: E402

SNAPSHOT = ROOT / "reports" / "phase3-reproducibility-snapshot.json"
RESULT = ROOT / "reports" / "phase3-reproducibility-rerun.json"

# 时间类字段：重复执行必然不同，不参与一致性判定
TIME_KEYS = {"created_at", "finished_at", "started_at", "seconds", "build_seconds",
             "elapsed_seconds", "generated_at"}


def _artifact_files(cfg) -> list[Path]:
    files: list[Path] = []
    for key in ("splits_matching", "splits_education"):
        d = cfg.out(key)
        if d.exists():
            files += sorted(p for p in d.rglob("*.csv"))
            files += sorted(p for p in d.rglob("manifest.json"))
    for key in ("processed_matching", "processed_education", "processed_embeddings"):
        d = cfg.out(key)
        if d.exists():
            files += sorted(p for p in d.rglob("*") if p.is_file())
    return [f for f in files if f.is_file()]


def _strip_time(o):
    if isinstance(o, dict):
        return {k: _strip_time(v) for k, v in o.items() if k not in TIME_KEYS}
    if isinstance(o, list):
        return [_strip_time(v) for v in o]
    return o


def _manifest_payload(manifest: dict) -> dict:
    """只保留确定性内容：文件哈希、行数、切分统计。"""
    keep = {}
    for k in ("seed", "ratios", "group_key", "splits", "excluded", "overlap_check",
              "coverage", "files", "gold_isolation", "duplicate_analysis",
              "test_set_decision"):
        if k in manifest:
            keep[k] = _strip_time(manifest[k])
    return keep


def snapshot() -> dict:
    cfg = get_config()
    files = {}
    for f in _artifact_files(cfg):
        key = str(f.relative_to(ROOT)).replace("\\", "/")
        if key.endswith("manifest.json"):
            files[key] = _manifest_payload(json.loads(f.read_text("utf-8")))
        else:
            files[key] = sha256_file(f)
    payload = {
        "generated_by": "scripts/data_pipeline/rerun_consistency.py snapshot",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": files,
    }
    jdump(payload, SNAPSHOT)
    print(f"[snapshot] 记录 {len(files)} 个产物指纹 -> {SNAPSHOT.relative_to(ROOT)}")
    return payload


def compare() -> dict:
    cfg = get_config()
    if not SNAPSHOT.exists():
        raise SystemExit("缺少快照文件，请先执行 snapshot")
    before = json.loads(SNAPSHOT.read_text("utf-8"))
    now = snapshot()
    diffs = []
    keys = sorted(set(before["files"]) | set(now["files"]))
    for k in keys:
        a, b = before["files"].get(k), now["files"].get(k)
        if a != b:
            diffs.append({"artifact": k, "changed": True})
    baseline = ROOT / "reports" / "baselines" / "baseline-results.json"
    baseline_note = "-"
    if baseline.exists():
        raw = json.loads(baseline.read_text("utf-8"))
        base_key = "baseline_metrics"
        cur = _strip_time({"matching": raw.get("matching"),
                           "education": raw.get("education")})
        prev = before["files"].get(base_key)
        if prev is None:
            now["files"][base_key] = cur
            baseline_note = "本次首次登记 Baseline 指标指纹"
        elif prev != cur:
            diffs.append({"artifact": base_key, "changed": True})
            baseline_note = "Baseline 指标与上次运行不一致"
        else:
            baseline_note = "Baseline 指标与上次运行逐值一致（剔除时间字段）"
        jdump(now, SNAPSHOT)

    ok = not diffs
    out = {
        "generated_by": "scripts/data_pipeline/rerun_consistency.py compare",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ok": ok,
        "artifacts_compared": len(keys),
        "differences": diffs,
        "baseline_metrics": baseline_note,
        "summary": (f"比对 {len(keys)} 个确定性产物（切分索引 / 特征表 / 目标表 / 特征矩阵 / "
                    f"学历输入与标签 / Embedding 数组与 ID 映射 / manifest 统计量），"
                    f"差异 {len(diffs)} 个；{baseline_note}。"),
    }
    jdump(out, RESULT)
    print(f"[compare] 差异 {len(diffs)} 个 -> {RESULT.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if mode == "snapshot":
        snapshot()
    elif mode == "compare":
        compare()
    else:
        raise SystemExit("用法: rerun_consistency.py [snapshot|compare]")
