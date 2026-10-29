# -*- coding: utf-8 -*-
"""标注一致性分析 CLI（任务书 4.4）-> reports/phase4-3a/annotation-quality.json。

无双人标注时输出 not_computable 与原因，绝不填充一致性数值。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import IMPORT_DIR, PAIRS_DIR, now, read_jsonl, write_report  # noqa: E402

from job_matching.annotation.agreement import agreement_report  # noqa: E402
from job_matching.annotation.arbitration import (  # noqa: E402
    find_disagreements, group_annotations,
)
from job_matching.annotation.importer import check_missing_annotations  # noqa: E402


def load_valid_rows() -> tuple[list[dict], str]:
    report_path = IMPORT_DIR / "validation_report.json"
    if not report_path.exists():
        return [], "pending"
    from job_matching.core import jload
    rep = jload(report_path)
    rows = []
    for _who, sub in (rep.get("validation_reports") or {}).items():
        rows.extend(sub.get("rows_valid", []))
    return rows, rep.get("annotation_status", "pending")


def run() -> dict:
    rows, status = load_valid_rows()
    pair_meta = {}
    pair_ids = set()
    for name in ("pairs_v1.jsonl", "pairs_synthetic_v1.jsonl"):
        p = PAIRS_DIR / name
        if p.exists():
            for r in read_jsonl(p):
                pair_meta[r["pair_id"]] = {"job_category": r.get("job_category", "UNKNOWN"),
                                           "difficulty_tier": r.get("difficulty_tier", "")}
                pair_ids.add(r["pair_id"])

    rows_a = [r for r in rows if r["annotator_id"] == "annotator_A"]
    rows_b = [r for r in rows if r["annotator_id"] == "annotator_B"]
    report = agreement_report(rows_a, rows_b, pair_meta)

    disagreements = find_disagreements(rows) if rows else []
    missing = check_missing_annotations([{"pair_id": pid} for pid in sorted(pair_ids)],
                                        rows, required_annotators=2) if pair_ids else {
        "pairs_total": 0, "note": "无待标注样本"}

    out = {
        "generated_by": "scripts/phase4_3a/check_agreement.py",
        "created_at": now(),
        "annotation_status": status if status != "validated" else
                             ("complete" if missing.get("pairs_missing_annotations", 0) == 0
                              and not disagreements else "in_progress"),
        "agreement": report,
        "disagreements": {"count": len(disagreements), "pairs": [d["pair_id"] for d in disagreements],
                          "detail": disagreements[:100]},
        "missing_annotations": missing,
        "annotation_counts": {
            "annotator_A": len(rows_a), "annotator_B": len(rows_b),
            "pair_pool": len(pair_ids),
        },
        "unjudgeable_policy": "unjudgeable 不参与 Kappa；双方 unjudgeable 计入独立状态统计",
    }
    write_report("annotation-quality.json", out)
    return out


if __name__ == "__main__":
    res = run()
    print(json.dumps({"annotation_status": res["annotation_status"],
                      "agreement_status": res["agreement"].get("status"),
                      "disagreements": res["disagreements"]["count"]},
                     ensure_ascii=False, indent=2))
