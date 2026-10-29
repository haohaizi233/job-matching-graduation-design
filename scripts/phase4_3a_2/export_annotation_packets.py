# -*- coding: utf-8 -*-
"""盲标注材料导出（Phase4-3A-2 模块 D）。

从真实配对池导出**去标识化标注视图**（按白名单），双人各一份互不可见：
  * 只含去标识化简历 + JD + 标注辅助字段；
  * 模型预测 / 旧评分 / 抽样难度层 / pair 来源 / split / 他人答案 一律不出现；
  * 导出前过 PII 检查（pii.check_export）与列名门禁（blind_guard.check_packet_columns），
    违规直接报错，不静默导出。

用法：
  python scripts/phase4_3a_2/export_annotation_packets.py

产物：
  data/independent_eval/annotation/packets/packet_<annotator>.csv
  data/independent_eval/annotation/packets/packet_manifest.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    ANNOTATOR_A, ANNOTATOR_B, PACKET_DIR, PAIRS_REAL_V2, now, read_jsonl, write_report,
)

from job_matching.annotation import blind_guard  # noqa: E402
from job_matching.annotation.pii import check_export  # noqa: E402
from job_matching.annotation.schema import (  # noqa: E402
    ANNOTATION_FIELDS, PROTOCOL_VERSION,
)
from job_matching.core import ensure_dir, jdump, sha256_file  # noqa: E402

ANNOTATORS = (ANNOTATOR_A, ANNOTATOR_B)
TEXT_FIELDS = ("resume_text", "job_text")


def build_packet_rows(pairs: list[dict], annotator_id: str) -> tuple[list[dict], list[str]]:
    """构建单个标注员的标注包行；任何盲标/PII 违规直接抛错。"""
    rows = []
    for p in pairs:
        view = blind_guard.build_annotation_view(p)
        problems = check_export(view, TEXT_FIELDS,
                                allowed_columns=list(blind_guard.ANNOTATION_VIEW_COLUMNS))
        if problems:
            raise ValueError(f"标注包导出被拒（pair={p.get('pair_id')}）: {'；'.join(problems)}")
        row = dict(view)
        row.update({
            "annotator_id": annotator_id,
            "relevance": "",
            "confidence": "",
            "reason": "",
            "evidence": "",
            "annotation_timestamp": "",
            "protocol_version": PROTOCOL_VERSION,
        })
        rows.append(row)
    columns = list(blind_guard.ANNOTATION_VIEW_COLUMNS) + list(ANNOTATION_FIELDS)[1:]
    bad = blind_guard.check_packet_columns(columns)
    if bad:
        raise ValueError(f"标注包列名违规，拒绝导出: {'；'.join(bad)}")
    return rows, columns


def main() -> int:
    pairs = read_jsonl(PAIRS_REAL_V2) if PAIRS_REAL_V2.exists() else []
    ensure_dir(PACKET_DIR)

    if not pairs:
        manifest = {
            "generated_by": "scripts/phase4_3a_2/export_annotation_packets.py",
            "created_at": now(),
            "status": "waiting_real_pairs",
            "reason": "真实配对 0 组：无可标注对象（真实简历收集未完成）",
            "pairs": 0,
            "annotators": list(ANNOTATORS),
            "blindness_gates": {
                "view_columns": list(blind_guard.ANNOTATION_VIEW_COLUMNS),
                "hidden_columns": list(blind_guard._VIEW_HIDDEN_COLUMNS),
                "model_output_columns_blocked": True,
                "pii_export_check": "pii.check_export（文本残留 + 字段名白名单）",
            },
        }
        jdump(manifest, PACKET_DIR / "packet_manifest.json")
        write_report("annotation-progress.json", {
            "generated_by": "scripts/phase4_3a_2/export_annotation_packets.py",
            "created_at": now(),
            "annotation_status": "waiting_real_pairs",
            "pairs_total": 0, "pairs_fully_annotated": 0,
            "note": "等待真实简历-岗位配对生成后导出标注材料",
        })
        print(json.dumps({"status": "waiting_real_pairs", "pairs": 0}, ensure_ascii=False, indent=2))
        return 0

    written = []
    for annotator in ANNOTATORS:
        rows, columns = build_packet_rows(pairs, annotator)
        path = PACKET_DIR / f"packet_{annotator}.csv"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in columns})
        written.append({"annotator": annotator, "file": str(path.name),
                        "rows": len(rows), "sha256": sha256_file(path)})

    manifest = {
        "generated_by": "scripts/phase4_3a_2/export_annotation_packets.py",
        "created_at": now(),
        "status": "packets_exported",
        "pairs": len(pairs),
        "packets": written,
        "annotators": list(ANNOTATORS),
        "blinding": {
            "per_annotator_file": True,
            "annotator_cannot_see": ["模型预测与旧评分（final_score/label_strength/candidate_rank 等）",
                                     "抽样难度层 difficulty_tier 与 pair_provenance",
                                     "split / eligible_for_gold / is_synthetic",
                                     "另一位标注员的答案"],
            "view_columns": list(blind_guard.ANNOTATION_VIEW_COLUMNS),
        },
        "fill_in_rules": "见 docs/evaluation/phase4-3a-2-annotation-plan.md 与 annotation-guidelines.md",
    }
    jdump(manifest, PACKET_DIR / "packet_manifest.json")

    write_report("annotation-progress.json", {
        "generated_by": "scripts/phase4_3a_2/export_annotation_packets.py",
        "created_at": now(),
        "annotation_status": "in_progress" if pairs else "waiting_real_pairs",
        "pairs_total": len(pairs),
        "pairs_fully_annotated": 0,
        "packets_exported": [w["file"] for w in written],
        "note": "标注材料已导出；等待标注员独立填写（imports 由 annotation_qa.py 处理）",
    })
    print(json.dumps({"status": "packets_exported", "pairs": len(pairs),
                      "packets": [w["file"] for w in written]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
