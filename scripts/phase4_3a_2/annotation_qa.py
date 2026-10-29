# -*- coding: utf-8 -*-
"""双人标注 QA：导入校验、独立性、一致性、仲裁、最终标签（Phase4-3A-2 模块 D）。

流程：
  1. 读取两位标注员的填写文件（data/private/annotations_raw/annotations_<id>.csv）；
  2. importer 校验（pair 存在、标签合法、协议版本一致、无模型输出列、无冲突重复）；
  3. blind_guard 独立性检查（同一人不得冒充两名标注员）；
  4. agreement 一致性（一致率 / Kappa / Weighted Kappa，样本不足输出 not_computable）；
  5. 分歧 -> 仲裁表（保留双方原始标签与理由）-> 仲裁校验 -> build_final_labels
     （unjudgeable 保护：不得强行归入数值标签）；
  6. 产出 annotation-progress.json / agreement-results.json。

用法：
  python scripts/phase4_3a_2/annotation_qa.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    ANNOTATOR_A, ANNOTATOR_B, ANNOT_DIR, ARBITRATOR, PAIRS_REAL_V2, PRIVATE_ANNOT_DIR,
    now, read_jsonl, write_report,
)

from job_matching.annotation import agreement as agreement_mod  # noqa: E402
from job_matching.annotation import arbitration as arbitration_mod  # noqa: E402
from job_matching.annotation import blind_guard  # noqa: E402
from job_matching.annotation import importer as importer_mod  # noqa: E402
from job_matching.core import ROOT, ensure_dir, jdump  # noqa: E402

ANNOTATORS = (ANNOTATOR_A, ANNOTATOR_B)


def _annotation_path(annotator: str) -> Path:
    return PRIVATE_ANNOT_DIR / f"annotations_{annotator}.csv"


def load_valid_annotations(pairs: list[dict]) -> tuple[dict, dict]:
    """逐文件校验标注记录。返回 ({annotator: rows_valid}, {annotator: 校验报告})。"""
    known_pairs = {str(p["pair_id"]) for p in pairs}
    rows_by: dict[str, list[dict]] = {}
    reports: dict[str, dict] = {}
    for annotator in ANNOTATORS:
        path = _annotation_path(annotator)
        if not path.exists():
            rows_by[annotator] = []
            reports[annotator] = {"file": str(path), "status": "file_missing",
                                  "rows_read": 0, "errors": [], "counts": {"valid": 0}}
            continue
        rep = importer_mod.validate_annotation_file(
            path, known_pairs=known_pairs,
            known_annotators={ANNOTATOR_A, ANNOTATOR_B})
        rep["status"] = "validated"
        rows_by[annotator] = rep["rows_valid"]
        reports[annotator] = rep
    return rows_by, reports


def run() -> dict:
    pairs = read_jsonl(PAIRS_REAL_V2) if PAIRS_REAL_V2.exists() else []
    pair_meta = {str(p["pair_id"]): {"job_category": p.get("job_category", "UNKNOWN")}
                 for p in pairs}
    rows_by, import_reports = load_valid_annotations(pairs)
    rows_a, rows_b = rows_by[ANNOTATOR_A], rows_by[ANNOTATOR_B]
    all_rows = rows_a + rows_b

    independence = blind_guard.check_annotator_independence(rows_a, rows_b)
    agr = agreement_mod.agreement_report(rows_a, rows_b, pair_meta=pair_meta)

    disagreements = arbitration_mod.find_disagreements(all_rows,
                                                       annotators=ANNOTATORS)
    disputed_ids = {d["pair_id"] for d in disagreements}

    # 仲裁文件：已填 -> 校验；未填且有分歧 -> 导出待仲裁表（保留双方原始标签与理由）
    arb_path = PRIVATE_ANNOT_DIR / "arbitration_filled.csv"
    arb_rows: list[dict] = []
    arb_report: dict
    if arb_path.exists():
        arb_report = importer_mod.validate_arbitration_file(
            arb_path, known_pairs={str(p["pair_id"]) for p in pairs},
            disputed_pairs=disputed_ids)
        arb_report["status"] = "validated"
        arb_rows = arb_report["rows_valid"]
    else:
        pending_path = None
        if disagreements:
            ensure_dir(PRIVATE_ANNOT_DIR)
            pending_path = str(arbitration_mod.export_arbitration_sheet(
                disagreements, PRIVATE_ANNOT_DIR / "arbitration_pending.csv"
            ).relative_to(ROOT)).replace("\\", "/")
        arb_report = {"status": "waiting_arbitration" if disagreements else "no_disagreements",
                      "file": None, "pending_sheet": pending_path,
                      "rows_read": 0, "rows_valid": [], "errors": []}

    built = arbitration_mod.build_final_labels(pairs, all_rows, arb_rows)
    final_rows = built["final_rows"]
    forced_problems = importer_mod.check_unjudgeable_not_forced(final_rows, all_rows)
    independence_final = blind_guard.check_final_label_independence(final_rows)

    final_file = ANNOT_DIR / "final_labels.csv"
    ensure_dir(ANNOT_DIR)
    arbitration_mod.write_final_labels(final_rows, final_file)

    missing = importer_mod.check_missing_annotations(pairs, all_rows, required_annotators=2)
    dual_complete = (missing["pairs_missing_annotations"] == 0 and len(pairs) > 0)
    open_disagreements = len(disputed_ids) - sum(1 for r in arb_rows if r["pair_id"] in disputed_ids)

    if not pairs:
        status = "waiting_real_pairs"
    elif dual_complete and open_disagreements == 0 and not forced_problems:
        status = "complete"
    elif all_rows:
        status = "in_progress"
    else:
        status = "waiting_external_annotation"

    unjudgeable_rows = [r for r in all_rows if r.get("relevance") == "unjudgeable"]
    progress = {
        "generated_by": "scripts/phase4_3a_2/annotation_qa.py",
        "created_at": now(),
        "annotation_status": status,
        "pairs_total": len(pairs),
        "annotations_received": {
            ANNOTATOR_A: len(rows_a),
            ANNOTATOR_B: len(rows_b),
            "total": len(all_rows),
        },
        "pairs_fully_annotated": missing["pairs_fully_annotated"],
        "pairs_missing_annotations": missing["pairs_missing_annotations"],
        "required_annotators": 2,
        "missing_detail_sample": missing["missing_detail"][:50],
        "unjudgeable_annotations": len(unjudgeable_rows),
        "unjudgeable_policy": "unjudgeable 是独立状态，不得自动设为 0，不参与 Kappa",
        "disagreements_total": len(disagreements),
        "open_disagreements": open_disagreements,
        "arbitration": {
            "status": arb_report.get("status"),
            "rows_valid": len(arb_rows),
            "pending_sheet": arb_report.get("pending_sheet"),
            "arbitrator": ARBITRATOR,
            "records_keep_original_labels": True,
        },
        "unjudgeable_forced_problems": forced_problems,
        "independence": independence,
        "note": ("真实人工标注未开始" if status in ("waiting_real_pairs", "waiting_external_annotation")
                 else "标注进行中；缺失标注只登记不填补"),
    }
    write_report("annotation-progress.json", progress)

    agreement_results = {
        "generated_by": "scripts/phase4_3a_2/annotation_qa.py",
        "created_at": now(),
        "annotation_status": status,
        "import_reports": {k: {"file": v.get("file"), "status": v.get("status"),
                               "rows_read": v.get("rows_read"),
                               "counts": v.get("counts", {}),
                               "errors": v.get("errors", [])}
                           for k, v in import_reports.items()},
        "independence_check": independence,
        "agreement": agr,
        "disagreements": {
            "count": len(disagreements),
            "open": open_disagreements,
            "detail": disagreements[:200],
            "policy": "分歧必须仲裁；不隐藏、不平均、不静默覆盖",
        },
        "arbitration": {
            "status": arb_report.get("status"),
            "rows_valid": len(arb_rows),
            "errors": arb_report.get("errors", []),
            "warnings": arb_report.get("warnings", []),
        },
        "final_labels": {
            "file": str(final_file.relative_to(ROOT)).replace("\\", "/"),
            "counts": built["label_distribution"],
            "finalized": built["finalized"],
            "checks": built["checks"],
            "unjudgeable_forced": forced_problems,
            "independence_violations": independence_final,
        },
        "quality_target": {
            "weighted_kappa_target": 0.60,
            "note": ("0.60 是初步质量目标，不是通过线；不得为追求阈值修改标签。"
                     "一致性不足时应分析指南歧义/题目不可判/理解差异，必要时修订指南"
                     "并版本化后重新独立标注"),
        },
    }
    write_report("agreement-results.json", agreement_results)
    print(json.dumps({"annotation_status": status,
                      "pairs_total": len(pairs),
                      "annotations_received": len(all_rows),
                      "pairs_fully_annotated": missing["pairs_fully_annotated"],
                      "disagreements": len(disagreements),
                      "open_disagreements": open_disagreements,
                      "agreement_status": agr.get("status"),
                      "raw_agreement": (agr.get("raw_agreement") or {}).get("value"),
                      "weighted_kappa_linear": (agr.get("weighted_kappa_linear") or {}).get("value")},
                     ensure_ascii=False, indent=2))
    return progress


if __name__ == "__main__":
    run()
