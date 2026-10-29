# -*- coding: utf-8 -*-
"""数据集冻结 CLI（任务书第六节 D）。

用法：
  python scripts/phase4_3a/freeze_dataset.py --stage pool
  python scripts/phase4_3a/freeze_dataset.py --stage evalset
  python scripts/phase4_3a/freeze_dataset.py verify --manifest <path>

evalset 冻结必须满足：双人标注完成、分歧全部仲裁、无 unjudgeable 强行归类、
无合成样本混入、有数据来源与人工标注责任记录；否则显式拒绝（FreezeError）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import ANNOT_DIR, FROZEN_DIR, PAIRS_DIR, POOL_DIR, now, read_jsonl  # noqa: E402

from job_matching.annotation.freeze import FreezeError, freeze_dataset, verify_freeze  # noqa: E402
from job_matching.core import ROOT, ensure_dir, jdump, jload  # noqa: E402


def _annotation_quality() -> dict:
    q_path = ROOT / "reports" / "phase4-3a" / "annotation-quality.json"
    if not q_path.exists():
        return {"annotation_status": "pending"}
    q = jload(q_path)
    final_checks = {}
    import_report = ANNOT_DIR / "arbitrate_import_report.json"
    if import_report.exists():
        final_checks = jload(import_report).get("finalization", {})
    return {
        "annotation_status": q.get("annotation_status", "pending"),
        "open_disagreements": q.get("disagreements", {}).get("count", 0),
        "unjudgeable_forced": len(final_checks.get("unjudgeable_forced", []) or []),
        "synthetic_pairs_included": 0,
        "agreement": q.get("agreement", {}),
    }


def run(stage: str = "evalset") -> dict:
    pairs_file = PAIRS_DIR / "pairs_v1.jsonl"
    final_file = ANNOT_DIR / "final_labels.csv"
    manifest_file = FROZEN_DIR / "evalset_v1" / "manifest.json"

    if stage == "pool":
        manifest = freeze_dataset(
            stage="pool", out_dir=FROZEN_DIR / "pool_v1", pairs_file=pairs_file,
            files={"pairs": pairs_file, "job_pool": POOL_DIR / "job_pool_v1.jsonl"},
            dataset_version="pool-v1", source_stats={"note": "见 pool_manifest_v1.json"},
            responsibility={"annotation_status": "pending"})
        return {"stage": "pool", "status": "frozen",
                "manifest": str((FROZEN_DIR / 'pool_v1' / 'manifest.json'))}

    aq = _annotation_quality()
    pairs = read_jsonl(pairs_file) if pairs_file.exists() else []
    labels = []
    if final_file.exists():
        import pandas as pd
        labels = pd.read_csv(final_file, dtype=str).fillna("").to_dict("records")
    synthetic_in = sum(1 for p in pairs if str(p.get("is_synthetic")) == "True")
    try:
        manifest = freeze_dataset(
            stage="evalset", out_dir=FROZEN_DIR / "evalset_v1",
            pairs_file=pairs_file,
            files={"pairs": pairs_file, "final_labels": final_file,
                   "annotations_a": ANNOT_DIR / "imports" / "annotations_A.csv",
                   "annotations_b": ANNOT_DIR / "imports" / "annotations_B.csv",
                   "arbitration": ANNOT_DIR / "arbitration.csv"},
            dataset_version="evalset-v1",
            source_stats={"pairs": len(pairs), "labels": len(labels)},
            label_distribution=_label_dist(labels),
            annotation_quality={**aq, "synthetic_pairs_included": synthetic_in},
            responsibility={"annotators": ["annotator_A", "annotator_B"],
                            "arbitrator": "arbitrator_1",
                            "data_sources": "data/raw/job-education (apache-2.0)",
                            "protocol_version": "phase4-3a-annotation-v1"})
        return {"stage": "evalset", "status": "frozen",
                "manifest": str(manifest_file.relative_to(ROOT)).replace("\\", "/"),
                "dataset_version": manifest["dataset_version"]}
    except FreezeError as e:
        out = {"stage": "evalset", "status": "blocked", "reason": str(e),
               "annotation_quality": aq,
               "created_at": now(),
               "note": "未满足冻结条件：评估集不允许冻结，更不允许静默修改"}
        ensure_dir(FROZEN_DIR / "evalset_v1")
        jdump(out, FROZEN_DIR / "evalset_v1" / "freeze_blocked.json")
        return out


def _label_dist(labels: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in labels:
        k = str(r.get("final_relevance", ""))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="freeze")
    ap.add_argument("--stage", type=str, default="evalset")
    ap.add_argument("--manifest", type=str, default=None)
    args = ap.parse_args()
    if args.action == "verify":
        res = verify_freeze(args.manifest)
    else:
        res = run(args.stage)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
