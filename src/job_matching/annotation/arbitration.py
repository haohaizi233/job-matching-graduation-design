# -*- coding: utf-8 -*-
"""双人标注分歧仲裁与最终标签（协议 4.2 / 测试场景 7、8）。

硬性规则：
  * 保留两份原始标注、仲裁记录与最终标签，任何环节不得覆盖原始记录；
  * 只有两人意见不一致的样本进入仲裁；
  * 仲裁结论为 unjudgeable 时，最终标签即 unjudgeable，不得强行归入 0/1/2；
  * 未完成仲裁的样本最终标签为空（pending_arbitration），不进入任何指标。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schema import ANNOTATION_FIELDS, ARBITRATION_FIELDS, FINAL_LABEL_FIELDS

PENDING = "pending_arbitration"
INSUFFICIENT = "insufficient_annotators"


def group_annotations(annotation_rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in annotation_rows:
        out.setdefault(r["pair_id"], []).append(r)
    for pid in out:
        out[pid] = sorted(out[pid], key=lambda x: x["annotator_id"])
    return out


def find_disagreements(annotation_rows: list[dict],
                       annotators: tuple[str, ...] = ("annotator_A", "annotator_B")
                       ) -> list[dict]:
    """检测需要仲裁的样本（两人标签不同，含 unjudgeable vs 数值）。"""
    by_pair = group_annotations(annotation_rows)
    out = []
    for pid in sorted(by_pair):
        rows = [r for r in by_pair[pid] if r["annotator_id"] in annotators]
        labels = {r["annotator_id"]: r["relevance"] for r in rows}
        if len(labels) < 2:
            continue
        vals = [labels[a] for a in annotators if a in labels]
        if len(set(vals)) > 1:
            out.append({
                "pair_id": pid,
                "relevance_a": labels.get(annotators[0], ""),
                "relevance_b": labels.get(annotators[1], ""),
                "reason_a": next((r["reason"] for r in rows
                                  if r["annotator_id"] == annotators[0]), ""),
                "reason_b": next((r["reason"] for r in rows
                                  if r["annotator_id"] == annotators[1]), ""),
                "evidence_a": next((r["evidence"] for r in rows
                                    if r["annotator_id"] == annotators[0]), ""),
                "evidence_b": next((r["evidence"] for r in rows
                                    if r["annotator_id"] == annotators[1]), ""),
            })
    return out


def export_arbitration_sheet(disagreements: list[dict], path: Path | str) -> Path:
    """导出待仲裁样本表（仲裁员填写 final_* 列）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in disagreements:
        rows.append({
            "arbitrator_id": "",
            "pair_id": d["pair_id"],
            "final_relevance": "",
            "final_confidence": "",
            "reason": "",
            "evidence": "",
            "annotation_timestamp": "",
            "protocol_version": "",
            "_relevance_a": d["relevance_a"],
            "_relevance_b": d["relevance_b"],
            "_reason_a": d["reason_a"],
            "_reason_b": d["reason_b"],
        })
    cols = list(ARBITRATION_FIELDS) + ["_relevance_a", "_relevance_b", "_reason_a", "_reason_b"]
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False, encoding="utf-8",
                                            lineterminator="\n")
    return path


def build_final_labels(pairs: list[dict], annotation_rows: list[dict],
                       arbitration_rows: list[dict] | None = None
                       ) -> dict:
    """合成最终标签（保留原始标注）。返回 {final_rows, checks, counts}。"""
    arbitration_rows = arbitration_rows or []
    arb = {r["pair_id"]: r for r in arbitration_rows}
    by_pair = group_annotations(annotation_rows)
    pair_ids = [p["pair_id"] for p in pairs]
    final_rows = []
    checks = {"unjudgeable_forced": [], "missing_final": [], "arbitration_used": 0,
              "both_agree": 0, "pending": 0, "insufficient": 0}

    for pid in pair_ids:
        rows = by_pair.get(pid, [])
        if len(rows) < 2:
            checks["insufficient"] += 1
            checks["missing_final"].append({"pair_id": pid, "reason": INSUFFICIENT})
            final_rows.append(_final_row(pid, None, INSUFFICIENT, rows, None))
            continue
        labels = {r["annotator_id"]: r["relevance"] for r in rows}
        vals = list(labels.values())
        if len(set(vals)) == 1:
            checks["both_agree"] += 1
            # unjudgeable 保护：双方一致判 unjudgeable 时，任何仲裁都不得改成数值标签
            a0 = arb.get(pid)
            if vals[0] == "unjudgeable" and a0 is not None \
                    and a0["final_relevance"] != "unjudgeable":
                checks["unjudgeable_forced"].append({
                    "pair_id": pid,
                    "message": "双方均判 unjudgeable，仲裁却给出数值标签（不予采纳）",
                })
            final_rows.append(_final_row(pid, vals[0], "both_agree", rows, None))
            continue
        a = arb.get(pid)
        if a is None:
            checks["pending"] += 1
            checks["missing_final"].append({"pair_id": pid, "reason": PENDING})
            final_rows.append(_final_row(pid, None, PENDING, rows, None))
            continue
        checks["arbitration_used"] += 1
        fr = _final_row(pid, a["final_relevance"], "arbitration", rows, a)
        final_rows.append(fr)

    counts: dict[str, int] = {}
    for r in final_rows:
        k = str(r["final_relevance"])
        counts[k] = counts.get(k, 0) + 1
    return {"final_rows": final_rows, "checks": checks,
            "label_distribution": dict(sorted(counts.items())),
            "finalized": sum(1 for r in final_rows if r["final_relevance"] not in (None, ""))}


def _final_row(pair_id: str, relevance, source: str, rows: list[dict],
               arb_row: dict | None) -> dict:
    by_id = {r["annotator_id"]: r for r in rows}
    a_id = sorted(by_id)[0] if len(by_id) > 0 else ""
    b_id = sorted(by_id)[1] if len(by_id) > 1 else ""
    base = arb_row or (rows[0] if rows else {})
    return {
        "pair_id": pair_id,
        "final_relevance": relevance,
        "final_source": source,
        "final_confidence": (arb_row or {}).get("final_confidence", ""),
        "annotator_a_id": a_id,
        "annotator_a_relevance": by_id.get(a_id, {}).get("relevance", ""),
        "annotator_b_id": b_id,
        "annotator_b_relevance": by_id.get(b_id, {}).get("relevance", ""),
        "arbitrator_id": (arb_row or {}).get("arbitrator_id", ""),
        "reason": base.get("reason", ""),
        "evidence": base.get("evidence", ""),
        "annotation_timestamp": base.get("annotation_timestamp", ""),
        "protocol_version": base.get("protocol_version", ""),
    }


def write_final_labels(final_rows: list[dict], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(final_rows, columns=list(FINAL_LABEL_FIELDS)).to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n")
    return path


def write_annotations_template(annotator_id: str, pair_ids: list[str],
                               path: Path | str, protocol_version: str) -> Path:
    """双人标注 CSV 模板（空白待填，含协议版本与示例填写要求见 annotation-guidelines）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"annotator_id": annotator_id, "pair_id": pid, "relevance": "",
             "confidence": "", "reason": "", "evidence": "",
             "annotation_timestamp": "", "protocol_version": protocol_version}
            for pid in pair_ids]
    pd.DataFrame(rows, columns=list(ANNOTATION_FIELDS)).to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n")
    return path
