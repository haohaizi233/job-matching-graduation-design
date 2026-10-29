# -*- coding: utf-8 -*-
"""数据集冻结与 SHA-256 复验（协议第九节 / 测试场景 9）。

两级冻结：
  stage="pool"    候选池冻结（无标注也可以），登记来源、哈希、抽样与覆盖度；
  stage="evalset" 正式评估集冻结（必须先完成双人标注 + 仲裁 + 质量检查），
                  生成数据集版本号、标签协议版本号、样本量、来源统计、标签分布、
                  互斥检查结果、文件 SHA-256、冻结时间、来源与人工标注责任记录。

冻结后任何文件变化都会在 verify_freeze 中被检出；禁止静默修改，修改必须升版本号。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from ..core import ensure_dir, jdump, jload, rel, sha256_file, sha256_text
from .schema import PROTOCOL_VERSION


class FreezeError(RuntimeError):
    pass


FREEZE_STAGES = ("pool", "evalset")


def assign_splits(pairs: list[dict], seed: int = 20261211,
                  blind_ratio: float = 0.5) -> list[dict]:
    """按简历分组分配 dev_validation / blind_test（同简历不拆分，确定性）。"""
    resume_ids = sorted({p["resume_id"] for p in pairs})
    rng = np.random.default_rng(int(seed))
    order = list(rng.permutation(len(resume_ids)))
    n_blind = int(round(len(resume_ids) * float(blind_ratio)))
    blind_set = {resume_ids[order[i]] for i in range(min(n_blind, len(order)))}
    out = []
    for p in pairs:
        q = dict(p)
        q["split"] = "blind_test" if p["resume_id"] in blind_set else "dev_validation"
        out.append(q)
    return out


def mutual_exclusivity_checks(pairs: list[dict], final_rows: list[dict] | None = None
                              ) -> dict:
    """互斥/唯一性检查：pair 唯一、resume-job 唯一、split 隔离、最终标签唯一。"""
    pair_ids = [p["pair_id"] for p in pairs]
    resume_by_split: dict[str, set[str]] = {}
    for p in pairs:
        resume_by_split.setdefault(p["split"], set()).add(p["resume_id"])
    splits = sorted(resume_by_split)
    overlap = {}
    for i in range(len(splits)):
        for j in range(i + 1, len(splits)):
            a, b = splits[i], splits[j]
            ov = resume_by_split[a] & resume_by_split[b]
            overlap[f"{a}__{b}"] = len(ov)

    checks = {
        "pair_id_unique": len(pair_ids) == len(set(pair_ids)),
        "pair_id_duplicates": len(pair_ids) - len(set(pair_ids)),
        "resume_job_unique": len({(p["resume_id"], p["job_id"]) for p in pairs}) == len(pairs),
        "split_resume_overlap": overlap,
        "split_isolation_ok": all(v == 0 for v in overlap.values()),
        "splits_present": splits,
    }
    if final_rows is not None:
        fids = [r["pair_id"] for r in final_rows]
        checks["final_label_unique"] = len(fids) == len(set(fids))
        checks["final_label_missing_for_pairs"] = len(set(pair_ids) - set(fids))
        checks["final_label_unknown_pairs"] = len(set(fids) - set(pair_ids))
    return checks


def _file_record(path: Path) -> dict:
    p = Path(path)
    return {"path": rel(p), "bytes": p.stat().st_size, "sha256": sha256_file(p)}


def freeze_dataset(*, stage: str, out_dir: Path | str, pairs_file: Path | str,
                   files: dict[str, Path | str], dataset_version: str,
                   source_stats: dict, label_distribution: dict | None = None,
                   annotation_quality: dict | None = None,
                   responsibility: dict | None = None,
                   protocol_version: str = PROTOCOL_VERSION,
                   extra: dict | None = None) -> dict:
    """冻结数据集并写 manifest.json。不满足条件抛 FreezeError（不静默降级）。"""
    if stage not in FREEZE_STAGES:
        raise FreezeError(f"未知冻结阶段: {stage}")
    out_dir = ensure_dir(out_dir)
    files = {k: Path(v) for k, v in files.items()}
    for k, p in files.items():
        if not p.exists():
            raise FreezeError(f"冻结所需文件缺失: {k} -> {p}")

    if stage == "evalset":
        aq = annotation_quality or {}
        if aq.get("annotation_status") != "complete":
            raise FreezeError(
                "正式评估集冻结被拒绝：annotation_status != complete（人工标注未完成）")
        if aq.get("open_disagreements", 0) > 0:
            raise FreezeError("正式评估集冻结被拒绝：仍有未仲裁的分歧样本")
        if aq.get("unjudgeable_forced", 0) > 0:
            raise FreezeError("正式评估集冻结被拒绝：存在 unjudgeable 被强行归类")
        if not responsibility:
            raise FreezeError("正式评估集冻结被拒绝：缺少数据来源与人工标注责任记录")
        if aq.get("synthetic_pairs_included", 0) > 0:
            raise FreezeError("正式评估集冻结被拒绝：合成样本不得进入人工真值评估集")

    manifest = {
        "generated_by": "src/job_matching/annotation/freeze.py",
        "stage": stage,
        "dataset_version": dataset_version,
        "protocol_version": protocol_version,
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": {k: _file_record(p) for k, p in sorted(files.items())},
        "source_stats": source_stats,
        "label_distribution": label_distribution or {},
        "annotation_quality": annotation_quality or {},
        "responsibility": responsibility or {},
        "mutual_exclusivity": {},
        "extra": extra or {},
        "immutability_note": "冻结后禁止静默修改；任何变更必须生成新的 dataset_version",
    }
    checks_path = files.get("pairs")
    if checks_path is not None:
        import json
        pairs = []
        with open(checks_path, "r", encoding="utf-8") as f:
            if checks_path.suffix.lower() == ".jsonl":
                for line in f:
                    line = line.strip()
                    if line:
                        pairs.append(json.loads(line))
            else:
                import pandas as pd
                pairs = pd.read_csv(checks_path, dtype=str).fillna("").to_dict("records")
        final_rows = None
        if "final_labels" in files:
            import pandas as pd
            final_rows = pd.read_csv(files["final_labels"], dtype=str).fillna("").to_dict("records")
        manifest["mutual_exclusivity"] = mutual_exclusivity_checks(pairs, final_rows)
        manifest["sample_counts"] = {
            "pairs": len(pairs),
            "resumes": len({p["resume_id"] for p in pairs}),
            "jobs": len({p["job_id"] for p in pairs}),
            "synthetic_pairs": sum(1 for p in pairs if str(p.get("is_synthetic")) == "True"),
        }
    manifest["manifest_sha256"] = sha256_text(
        "|".join(f"{k}:{v['sha256']}" for k, v in manifest["files"].items()))
    jdump(manifest, Path(out_dir) / "manifest.json")
    return manifest


def verify_freeze(manifest_path: Path | str) -> dict:
    """复验冻结清单：逐文件重算 SHA-256。"""
    manifest_path = Path(manifest_path)
    manifest = jload(manifest_path)
    base = manifest_path.parent
    results = []
    ok = True
    for key, rec in sorted(manifest.get("files", {}).items()):
        p = base / rec["path"] if not Path(rec["path"]).is_absolute() else Path(rec["path"])
        # manifest 内记录的是相对项目根路径，按项目根解析
        from ..core import ROOT
        cand = [p, ROOT / rec["path"], base / Path(rec["path"]).name]
        actual = None
        found = None
        for c in cand:
            if c.exists():
                found = c
                actual = sha256_file(c)
                break
        match = (actual == rec["sha256"]) if actual is not None else False
        ok = ok and match
        results.append({"key": key, "path": rec["path"], "expected": rec["sha256"],
                        "actual": actual, "exists": found is not None, "match": match})
    return {"manifest": str(manifest_path), "ok": ok, "files": results,
            "dataset_version": manifest.get("dataset_version"),
            "frozen_at": manifest.get("frozen_at"),
            "stage": manifest.get("stage")}
