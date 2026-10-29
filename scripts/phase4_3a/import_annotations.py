# -*- coding: utf-8 -*-
"""人工标注导入与校验 CLI（任务书第六节 B）。

用法：
  python scripts/phase4_3a/import_annotations.py [--a <csv>] [--b <csv>]

默认读取 data/independent_eval/annotation/imports/{annotations_A,annotations_B}.csv；
不存在时如实报告 annotation_status=pending，不伪造标注。
校验报告写入 data/independent_eval/annotation/imports/validation_report.json。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import ANNOT_DIR, IMPORT_DIR, PAIRS_DIR, now, read_jsonl, write_report  # noqa: E402

from job_matching.annotation.importer import (  # noqa: E402
    check_missing_annotations, validate_annotation_file,
)
from job_matching.core import ensure_dir, jdump  # noqa: E402

DEFAULT_FILES = {
    "annotator_A": "data/independent_eval/annotation/imports/annotations_A.csv",
    "annotator_B": "data/independent_eval/annotation/imports/annotations_B.csv",
}


def known_pair_ids() -> set[str]:
    ids: set[str] = set()
    for name in ("pairs_v1.jsonl", "pairs_synthetic_v1.jsonl"):
        p = PAIRS_DIR / name
        if p.exists():
            ids |= {r["pair_id"] for r in read_jsonl(p)}
    return ids


def run(files: dict[str, str] | None = None) -> dict:
    ensure_dir(IMPORT_DIR)
    files = dict(files or DEFAULT_FILES)
    pair_ids = known_pair_ids()
    reports = {}
    all_rows: list[dict] = []
    present = {}
    for annotator, rel_path in files.items():
        p = Path(rel_path)
        p = p if p.is_absolute() else (Path(__file__).resolve().parents[2] / rel_path)
        if not p.exists():
            present[annotator] = False
            continue
        present[annotator] = True
        rep = validate_annotation_file(p, known_pairs=pair_ids,
                                       known_annotators={annotator})
        reports[annotator] = rep
        all_rows.extend(rep["rows_valid"])

    status = "pending"
    if all(present.values()) and all(r["counts"]["errors"] == 0 for r in reports.values()):
        status = "validated"
    elif any(present.values()):
        status = "invalid"

    missing = check_missing_annotations(
        [{"pair_id": pid} for pid in sorted(pair_ids)], all_rows, required_annotators=2) \
        if pair_ids else {"pairs_total": 0, "note": "无待标注样本"}

    out = {
        "generated_by": "scripts/phase4_3a/import_annotations.py",
        "created_at": now(),
        "annotation_status": status,
        "files_present": present,
        "pair_pool_size": len(pair_ids),
        "validation_reports": reports,
        "missing_annotations": missing,
        "rows_valid_total": len(all_rows),
    }
    jdump(out, IMPORT_DIR / "validation_report.json")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=str, default=None)
    ap.add_argument("--b", type=str, default=None)
    args = ap.parse_args()
    files = dict(DEFAULT_FILES)
    if args.a:
        files["annotator_A"] = args.a
    if args.b:
        files["annotator_B"] = args.b
    res = run(files)
    print(json.dumps({"annotation_status": res["annotation_status"],
                      "rows_valid_total": res["rows_valid_total"],
                      "missing": res["missing_annotations"].get("pairs_missing_annotations")},
                     ensure_ascii=False, indent=2))
