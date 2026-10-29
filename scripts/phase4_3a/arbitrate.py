# -*- coding: utf-8 -*-
"""标注仲裁 CLI（任务书第六节 C）。

用法：
  python scripts/phase4_3a/arbitrate.py export    # 导出待仲裁样本表
  python scripts/phase4_3a/arbitrate.py import    # 导入仲裁结果并生成最终标签

原始两份标注永久保留；仲裁结果与最终标签分别落盘，绝不覆盖。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import ANNOT_DIR, IMPORT_DIR, PAIRS_DIR, now, read_jsonl  # noqa: E402

from job_matching.annotation.arbitration import (  # noqa: E402
    build_final_labels, export_arbitration_sheet, find_disagreements,
    write_final_labels,
)
from job_matching.annotation.importer import validate_arbitration_file  # noqa: E402
from job_matching.core import ensure_dir, jdump  # noqa: E402

ARBITRATION_FILE = ANNOT_DIR / "arbitration.csv"
PENDING_FILE = ANNOT_DIR / "arbitration_pending.csv"
FINAL_FILE = ANNOT_DIR / "final_labels.csv"


def load_annotations() -> list[dict]:
    report_path = IMPORT_DIR / "validation_report.json"
    if not report_path.exists():
        return []
    from job_matching.core import jload
    rep = jload(report_path)
    rows = []
    for _who, sub in (rep.get("validation_reports") or {}).items():
        rows.extend(sub.get("rows_valid", []))
    return rows


def load_pairs() -> list[dict]:
    out = []
    for name in ("pairs_v1.jsonl", "pairs_synthetic_v1.jsonl"):
        p = PAIRS_DIR / name
        if p.exists():
            out.extend(read_jsonl(p))
    return out


def run(action: str = "export") -> dict:
    ensure_dir(ANNOT_DIR)
    rows = load_annotations()
    pairs = load_pairs()
    if not rows:
        out = {"generated_by": "scripts/phase4_3a/arbitrate.py", "created_at": now(),
               "action": action, "status": "pending",
               "note": "尚无人工标注记录，仲裁流程待启动"}
        jdump(out, ANNOT_DIR / f"arbitrate_{action}_report.json")
        return out

    disagreements = find_disagreements(rows)
    if action == "export":
        path = export_arbitration_sheet(disagreements, PENDING_FILE)
        out = {"generated_by": "scripts/phase4_3a/arbitrate.py", "created_at": now(),
               "action": "export", "status": "exported",
               "disagreements": len(disagreements),
               "sheet": str(path), "disputed_pairs": [d["pair_id"] for d in disagreements]}
        jdump(out, ANNOT_DIR / "arbitrate_export_report.json")
        return out

    if action != "import":
        raise ValueError(f"未知 action: {action}")

    disputed = {d["pair_id"] for d in disagreements}
    if not ARBITRATION_FILE.exists():
        out = {"generated_by": "scripts/phase4_3a/arbitrate.py", "created_at": now(),
               "action": "import", "status": "pending",
               "note": f"仲裁文件不存在: {ARBITRATION_FILE}"}
        jdump(out, ANNOT_DIR / "arbitrate_import_report.json")
        return out

    rep = validate_arbitration_file(ARBITRATION_FILE, known_pairs={p["pair_id"] for p in pairs},
                                    disputed_pairs=disputed)
    final = build_final_labels(pairs, rows, rep["rows_valid"])
    write_final_labels(final["final_rows"], FINAL_FILE)
    out = {
        "generated_by": "scripts/phase4_3a/arbitrate.py", "created_at": now(),
        "action": "import", "status": "finalized" if not rep["errors"] else "invalid",
        "arbitration_validation": rep,
        "final_labels": str(FINAL_FILE),
        "finalization": final["checks"],
        "label_distribution": final["label_distribution"],
        "finalized_rows": final["finalized"],
        "raw_annotations_preserved": True,
    }
    jdump(out, ANNOT_DIR / "arbitrate_import_report.json")
    return out


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "export"
    res = run(action)
    print(json.dumps({k: v for k, v in res.items()
                      if k in ("action", "status", "disagreements", "finalized_rows")},
                     ensure_ascii=False, indent=2))
