# -*- coding: utf-8 -*-
"""人工标注导入与合法性校验（协议 4.3 / 测试场景 5、6）。

校验项（全部必须通过才接受）：
  * pair_id 存在于待标注样本池；
  * 标签值合法（0 / 1 / 2 / unjudgeable）；
  * annotator_id 合法且已登记（机器标识直接拒收）；
  * 同一标注员对同一样本不得有冲突重复记录；
  * unjudgeable 不被强行归类；
  * 不得把模型推理结果当成人工标签（模型输出列拒收）；
  * 不得混用不同版本标注协议。

任何非法输入都记录到 errors 并保留行号；不静默修正、不丢弃错误行。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .schema import (
    ANNOTATION_FIELDS,
    ARBITRATION_FIELDS,
    AnnotationError,
    has_model_output_columns,
    validate_annotation_row,
    validate_arbitration_row,
)


def read_table(path: Path | str) -> tuple[list[dict], list[str]]:
    """读 CSV / JSONL 标注文件。返回 (行列表, 列名列表)。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"标注文件不存在: {path}")
    if path.suffix.lower() == ".jsonl":
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        cols = sorted({k for r in rows for k in r})
        return rows, cols
    df = pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")
    return df.to_dict("records"), [str(c) for c in df.columns]


def validate_annotation_file(path: Path | str, *, known_pairs: set[str],
                             known_annotators: set[str] | None = None,
                             protocol_version: str | None = None) -> dict:
    """校验一份标注文件，返回结构化报告。"""
    from .schema import PROTOCOL_VERSION
    pv = protocol_version or PROTOCOL_VERSION
    path = Path(path)
    rows, columns = read_table(path)
    report = {
        "file": str(path),
        "protocol_version_expected": pv,
        "rows_read": len(rows),
        "columns": columns,
        "rows_valid": [],
        "errors": [],
        "warnings": [],
    }
    banned = has_model_output_columns(columns)
    if banned:
        report["errors"].append({
            "code": "model_output_columns", "row": None,
            "message": f"标注文件包含模型输出/旧评分列，禁止冒充人工标签: {banned}",
        })
        return report

    missing_cols = [c for c in ANNOTATION_FIELDS if c not in columns]
    if missing_cols:
        report["errors"].append({"code": "missing_columns", "row": None,
                                 "message": f"缺少标注字段: {missing_cols}"})
        return report

    seen: dict[tuple[str, str], dict] = {}
    for i, row in enumerate(rows, start=2):  # 第 1 行是表头
        try:
            rec = validate_annotation_row(row, known_pairs=known_pairs,
                                          known_annotators=known_annotators,
                                          protocol_version=pv)
        except AnnotationError as e:
            report["errors"].append({"code": e.code, "row": i, "message": e.message})
            continue
        key = (rec["annotator_id"], rec["pair_id"])
        if key in seen:
            prev = seen[key]
            same = all(prev[f] == rec[f] for f in ("relevance", "confidence", "reason", "evidence"))
            if same:
                report["warnings"].append({
                    "code": "duplicate_identical", "row": i,
                    "message": f"重复的同人同样本记录（内容一致，已去重保留首条）: {key}",
                })
                continue
            report["errors"].append({
                "code": "duplicate_conflict", "row": i,
                "message": f"同人同样本存在冲突记录，禁止自行择一: {key}",
            })
            continue
        seen[key] = rec
        report["rows_valid"].append(rec)

    report["counts"] = {
        "valid": len(report["rows_valid"]),
        "errors": len(report["errors"]),
        "warnings": len(report["warnings"]),
        "annotators": sorted({r["annotator_id"] for r in report["rows_valid"]}),
        "by_relevance": _count_by(report["rows_valid"], "relevance"),
    }
    return report


def validate_arbitration_file(path: Path | str, *, known_pairs: set[str],
                              disputed_pairs: set[str],
                              protocol_version: str | None = None) -> dict:
    """仲裁文件校验：只能仲裁确有分歧的样本。"""
    from .schema import PROTOCOL_VERSION
    pv = protocol_version or PROTOCOL_VERSION
    path = Path(path)
    rows, columns = read_table(path)
    report = {"file": str(path), "rows_read": len(rows), "columns": columns,
              "rows_valid": [], "errors": [], "warnings": []}
    banned = has_model_output_columns(columns)
    if banned:
        report["errors"].append({"code": "model_output_columns", "row": None,
                                 "message": f"仲裁文件包含模型输出列: {banned}"})
        return report
    missing_cols = [c for c in ARBITRATION_FIELDS if c not in columns]
    if missing_cols:
        report["errors"].append({"code": "missing_columns", "row": None,
                                 "message": f"缺少仲裁字段: {missing_cols}"})
        return report
    seen: set[str] = set()
    for i, row in enumerate(rows, start=2):
        try:
            rec = validate_arbitration_row(row, known_pairs=known_pairs, protocol_version=pv)
        except AnnotationError as e:
            report["errors"].append({"code": e.code, "row": i, "message": e.message})
            continue
        if rec["pair_id"] in seen:
            report["errors"].append({"code": "duplicate_conflict", "row": i,
                                     "message": f"同一 pair 重复仲裁: {rec['pair_id']}"})
            continue
        if rec["pair_id"] not in disputed_pairs:
            report["warnings"].append({"code": "arbitration_not_disputed", "row": i,
                                       "message": f"pair {rec['pair_id']} 无分歧却被仲裁（记录保留但标记）"})
        seen.add(rec["pair_id"])
        report["rows_valid"].append(rec)
    report["counts"] = {"valid": len(report["rows_valid"]),
                        "errors": len(report["errors"]),
                        "warnings": len(report["warnings"])}
    return report


def check_unjudgeable_not_forced(final_rows: list[dict],
                                 annotation_rows: list[dict]) -> list[dict]:
    """unjudgeable 不得被强行归类（测试场景 6 的一部分）。

    规则：若双方标注均为 unjudgeable 且没有仲裁记录，最终标签必须是 unjudgeable。
    """
    by_pair: dict[str, list[dict]] = {}
    for r in annotation_rows:
        by_pair.setdefault(r["pair_id"], []).append(r)
    problems = []
    for fin in final_rows:
        anns = by_pair.get(fin["pair_id"], [])
        if len(anns) < 2:
            continue
        all_unj = all(a["relevance"] == "unjudgeable" for a in anns)
        forced_numeric = str(fin.get("final_relevance")) in ("0", "1", "2")
        arbitrated = bool(str(fin.get("arbitrator_id") or "").strip())
        if all_unj and forced_numeric and not arbitrated:
            problems.append({
                "code": "unjudgeable_forced",
                "pair_id": fin["pair_id"],
                "message": "双方均判 unjudgeable 且无仲裁，却被强行归入数值标签",
            })
    return problems


def check_missing_annotations(pairs: list[dict], annotation_rows: list[dict],
                              required_annotators: int = 2) -> dict:
    """缺失人工标注的处理：如实统计，不填补默认标签。"""
    by_pair: dict[str, set[str]] = {}
    for r in annotation_rows:
        by_pair.setdefault(r["pair_id"], set()).add(r["annotator_id"])
    missing = []
    for p in pairs:
        got = len(by_pair.get(p["pair_id"], ()))
        if got < int(required_annotators):
            missing.append({"pair_id": p["pair_id"], "annotations_received": got,
                            "annotations_required": int(required_annotators)})
    return {
        "pairs_total": len(pairs),
        "pairs_fully_annotated": len(pairs) - len(missing),
        "pairs_missing_annotations": len(missing),
        "required_annotators": int(required_annotators),
        "missing_detail": missing[:200],
        "note": "缺失标注只登记不填补；无标注样本不得进入任何指标分母",
    }


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key, ""))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))
