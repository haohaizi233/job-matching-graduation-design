# -*- coding: utf-8 -*-
"""P7-2：双人独立盲标注工作流完整演练（隔离合成夹具）。

**性质声明（必须先读）**
  * 本脚本用**合成**人岗配对（is_synthetic=true / eligible_for_gold=false）与
    **机械确定性**标签（固定种子 PRNG，与任何模型输出无关）演练标注工具链；
  * 演练中出现的 "标注员" 是脚本生成的**测试夹具记录**，不是真人；
  * 演练产物**不得**计为真实人工标注、**不得**进入 Gold、**不得**写入真实数据目录；
  * 因此本报告只能证明「工具链可操作」，不能证明「H2 已完成」。

安全边界（硬性，负向测试覆盖）：
  * 隔离工作区若与 data/private / data/independent_eval 的真实目录存在包含关系 → 直接拒绝执行；
  * 演练产出的 CSV 全部落在隔离工作区内。

演练覆盖（任务书 6.3 逐项）：
  1. 独立导出          independent_export
  2. 标注保存          annotation_save
  3. 断点续标          resume_partial_annotation
  4. 输入字段检查      required_field_check
  5. 非法标签拒绝      illegal_label_rejected
  6. 同人冒充两标注员  same_person_two_annotators_rejected
  7. 镜像答案异常检测  mirrored_answer_detection
  8. 隐私残留扫描      privacy_residual_scan
  9. 标注进度统计      annotation_progress_stats
  +  仲裁流程          arbitration_flow
  +  一致性统计        agreement_metrics（drill-only）
  +  无真实数据拒冻结  freeze_refused_without_real_data

输出：reports/phase7/annotation-drill.{json,md}
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as p7common  # noqa: E402
from common import ROOT, report_path, write_json  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from job_matching.annotation import (  # noqa: E402
    agreement, arbitration, blind_guard, completion, gold_gate, importer,
)
from job_matching.annotation.pii import check_export  # noqa: E402
from job_matching.annotation.schema import (  # noqa: E402
    ANNOTATION_FIELDS, AnnotationError, PROTOCOL_VERSION, validate_annotation_row,
)
from job_matching.core import ensure_dir, sha256_file  # noqa: E402

DRILL_SEED = 20261031
ANNOTATOR_A = "DrillAnnotatorA"
ANNOTATOR_B = "DrillAnnotatorB"
ARBITRATOR = "DrillArbitrator"
#: 演练标签取值；与协议一致但**由 PRNG 机械生成**，不是人的判断
LABELS = ("0", "1", "2", "unjudgeable")

TEXT_FIELDS = ("resume_text", "job_text")

_DRILL_WATERMARK = (
    "【演练夹具 SYNTHETIC DRILL FIXTURE】本行文本由 scripts/phase7/annotation_drill.py "
    "按固定种子机械生成，非真实简历、非真实岗位、非人工标注。"
)


# ------------------------------------------------------------------ 合成夹具
def _synthetic_pairs(n: int = 12) -> list[dict]:
    """确定性合成配对（is_synthetic=true / eligible_for_gold=false）。"""
    tiers = ("high_skill_overlap", "medium_skill_overlap", "same_direction_diff_duties",
             "hard_requirement_gap", "cross_category_negative")
    cats = ("INFORMATION-TECHNOLOGY", "FINANCE", "HR")
    out = []
    for i in range(n):
        rid = f"resume_synth_{i:02d}"
        jid = f"job_synth_{i:02d}"
        resume_text = (f"{_DRILL_WATERMARK} 合成简历 S{i:02d}："
                       f"掌握 Python / SQL / 数据分析，参与过 {cats[i % 3]} 方向的课程项目。")
        job_text = (f"{_DRILL_WATERMARK} 合成岗位 J{i:02d}："
                    f"负责 {cats[i % 3]} 相关工作，要求熟悉 Python 与数据处理。")
        from job_matching.annotation.pool import pair_content_hash, make_pair_id
        ch = pair_content_hash(resume_text, job_text)
        out.append({
            "pair_id": make_pair_id(ch),
            "resume_id": rid, "job_id": jid,
            "resume_source": "synthetic:phase7-drill", "job_source": "synthetic:phase7-drill",
            "resume_text": resume_text, "job_text": job_text,
            "job_category": cats[i % 3], "job_category_source": "synthetic_fixture",
            "language": "zh",
            "graduation_cohort": "2027", "employment_type": "校招",
            "required_skills": ["Python", "SQL"], "preferred_skills": ["数据可视化"],
            "education_requirement": {"raw": "本科及以上", "tokens": ["本科"]},
            "experience_requirement": {"raw": "不限", "years_min": None, "years_max": None},
            "city": "合成市", "salary_expectation": "",
            "resume_target_position": "数据分析师", "resume_skills": ["Python", "SQL"],
            "resume_education_level": "本科", "resume_years_experience": 0.0,
            "job_title": f"合成岗位 J{i:02d}",
            "difficulty_tier": tiers[i % len(tiers)],
            "content_hash": ch, "dataset_version": "drill-synth-v1",
            "is_synthetic": True, "pair_provenance": "synthetic_fixture",
            "eligible_for_gold": False, "split": "",
        })
    return out


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def _annotation_row(pair_id: str, annotator_id: str, rng: random.Random,
                    *, relevance: str | None = None, stamp: str = "2026-10-31T10:00:00") -> dict:
    rel = relevance if relevance is not None else rng.choice(LABELS)
    conf = rng.choice(("high", "medium", "low"))
    return {
        "annotator_id": annotator_id,
        "pair_id": pair_id,
        "relevance": rel,
        "confidence": conf,
        "reason": f"演练理由（机械生成，依据编号 {rng.randint(1, 5)}）",
        "evidence": f"演练证据片段（合成文本，非真实简历）#{rng.randint(1000, 9999)}",
        "annotation_timestamp": stamp,
        "protocol_version": PROTOCOL_VERSION,
    }


# ------------------------------------------------------------------ 逐项演练
def drill_independent_export(pairs: list[dict], ws: Path) -> dict:
    """能力 1：独立导出（盲化视图 + 列门禁 + PII 导出检查）。"""
    cols = list(blind_guard.ANNOTATION_VIEW_COLUMNS) + list(ANNOTATION_FIELDS)[1:]
    problems = blind_guard.check_packet_columns(cols)
    if problems:
        return {"status": "FAIL", "detail": f"标注包列名违规: {problems}"}
    files = {}
    for annotator in (ANNOTATOR_A, ANNOTATOR_B):
        rows = []
        for p in pairs:
            view = blind_guard.build_annotation_view(p)
            bad = check_export(view, TEXT_FIELDS,
                               allowed_columns=list(blind_guard.ANNOTATION_VIEW_COLUMNS))
            if bad:
                return {"status": "FAIL", "detail": f"导出被 PII/白名单门禁拒绝: {bad}"}
            row = dict(view)
            row.update({k: "" for k in ANNOTATION_FIELDS[2:6]})
            row["annotation_timestamp"] = ""
            row["protocol_version"] = PROTOCOL_VERSION
            rows.append(row)
        path = ws / "packets" / f"packet_{annotator}.csv"
        _write_csv(path, rows, cols)
        files[annotator] = {"path": path.name, "rows": len(rows), "sha256": sha256_file(path)}
    hidden_leak = [c for c in cols if c in blind_guard._VIEW_HIDDEN_COLUMNS]
    return {
        "status": "PASS",
        "detail": "两人各一份独立标注包；列白名单通过；无模型预测/难度层/split/他人答案列",
        "files": files,
        "hidden_columns_leaked": hidden_leak,
    }


def drill_annotation_save_and_resume(pairs: list[dict], ws: Path) -> dict:
    """能力 2/3：标注保存 + 断点续标。"""
    rng = random.Random(DRILL_SEED + 1)
    order = [p["pair_id"] for p in pairs]
    half = order[: len(order) // 2]
    # 阶段一：只标一半（模拟中断）
    rows_a_half = [_annotation_row(pid, ANNOTATOR_A, rng) for pid in half]
    path_a = ws / "imports" / "annotations_DrillAnnotatorA.csv"
    _write_csv(path_a, rows_a_half, list(ANNOTATION_FIELDS))
    missing_half = importer.check_missing_annotations(pairs, rows_a_half)
    # 阶段二：续标剩余
    rows_a_rest = [_annotation_row(pid, ANNOTATOR_A, random.Random(DRILL_SEED + 2)) for pid in order[len(half):]]
    rows_a = rows_a_half + rows_a_rest
    _write_csv(path_a, rows_a, list(ANNOTATION_FIELDS))
    rep = importer.validate_annotation_file(path_a, known_pairs=set(order),
                                            known_annotators={ANNOTATOR_A})
    missing_full = importer.check_missing_annotations(pairs, rows_a, required_annotators=1)
    ok = (not rep["errors"]) and missing_full["pairs_missing_annotations"] == 0
    return {
        "status": "PASS" if ok else "FAIL",
        "detail": "先标一半 → 中断 → 续标剩余，导入校验通过且无遗漏",
        "half_stage_missing": missing_half,
        "full_stage_missing": missing_full,
        "rows_saved": len(rows_a),
        "import_errors": rep["errors"],
    }


def drill_required_field_check(pairs: list[dict], ws: Path) -> dict:
    """能力 4：输入字段检查（缺列必须拒收）。"""
    order = {p["pair_id"] for p in pairs}
    bad_path = ws / "imports" / "annotations_missing_fields.csv"
    _write_csv(bad_path, [{"annotator_id": ANNOTATOR_A, "pair_id": pairs[0]["pair_id"],
                           "relevance": "1"}], ["annotator_id", "pair_id", "relevance"])
    rep = importer.validate_annotation_file(bad_path, known_pairs=order,
                                            known_annotators={ANNOTATOR_A})
    codes = [e["code"] for e in rep["errors"]]
    return {"status": "PASS" if "missing_columns" in codes else "FAIL",
            "detail": f"缺列文件被拒收，错误码={codes}", "errors": rep["errors"]}


def drill_illegal_label(pairs: list[dict], ws: Path) -> dict:
    """能力 5：非法标签拒绝。"""
    order = {p["pair_id"] for p in pairs}
    path = ws / "imports" / "annotations_illegal_label.csv"
    rows = [_annotation_row(pairs[0]["pair_id"], ANNOTATOR_A, random.Random(1), relevance="3")]
    _write_csv(path, rows, list(ANNOTATION_FIELDS))
    rep = importer.validate_annotation_file(path, known_pairs=order, known_annotators={ANNOTATOR_A})
    codes = [e["code"] for e in rep["errors"]]
    # 机器标识标注员也必须拒绝
    path2 = ws / "imports" / "annotations_machine_id.csv"
    r2 = _annotation_row(pairs[0]["pair_id"], "gpt_annotator", random.Random(2))
    _write_csv(path2, [r2], list(ANNOTATION_FIELDS))
    rep2 = importer.validate_annotation_file(path2, known_pairs=order)
    codes2 = [e["code"] for e in rep2["errors"]]
    ok = any(c not in ("missing_columns", "model_output_columns") for c in codes) and bool(codes2)
    return {"status": "PASS" if ok else "FAIL",
            "detail": f"非法标签错误码={codes}；机器标识标注员错误码={codes2}",
            "illegal_label_errors": rep["errors"], "machine_id_errors": rep2["errors"]}


def drill_same_person_two_annotators(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """能力 6：同一人员冒充两个标注员必须被拒。"""
    dup = [dict(r, annotator_id=ANNOTATOR_A) for r in rows_b]
    res = blind_guard.check_annotator_independence(rows_a, dup)
    codes = [v["code"] for v in res["violations"]]
    return {"status": "PASS" if "shared_annotator_id" in codes else "FAIL",
            "detail": f"同一 annotator_id 出现在两份标注中，检测到 {codes}",
            "violations": res["violations"]}


def drill_mirror_detection(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """能力 7：镜像答案异常检测。"""
    # 7a 全表镜像
    mirrored = [dict(r, annotator_id=ANNOTATOR_B) for r in rows_a]
    res_full = blind_guard.check_annotator_independence(rows_a, mirrored)
    codes_full = [v["code"] for v in res_full["violations"]]
    # 7b 真实独立（随机标签）应不报镜像
    res_ind = blind_guard.check_annotator_independence(rows_a, rows_b)
    codes_ind = [v["code"] for v in res_ind["violations"]]
    ok = "mirrored_annotations" in codes_full and "mirrored_annotations" not in codes_ind
    return {"status": "PASS" if ok else "FAIL",
            "detail": f"全表镜像检出={codes_full}；独立标注未误报={codes_ind}",
            "full_mirror": res_full, "independent": res_ind}


def drill_privacy_residual(pairs: list[dict]) -> dict:
    """能力 8：隐私残留扫描（注入真实形态 PII 必须被拦）。"""
    clean = blind_guard.build_annotation_view(pairs[0])
    ok_clean = not check_export(clean, TEXT_FIELDS,
                                allowed_columns=list(blind_guard.ANNOTATION_VIEW_COLUMNS))
    dirty = dict(clean)
    dirty["resume_text"] = clean["resume_text"] + " 联系方式 13800138000 邮箱 fake.user@example.com"
    hits = check_export(dirty, TEXT_FIELDS,
                        allowed_columns=list(blind_guard.ANNOTATION_VIEW_COLUMNS))
    ok = ok_clean and bool(hits)
    return {"status": "PASS" if ok else "FAIL",
            "detail": f"干净合成文本通过={ok_clean}；注入手机号/邮箱后被拦截={bool(hits)}",
            "injected_findings": list(hits)[:5]}


def drill_progress_stats(pairs: list[dict], rows_a: list[dict], rows_b: list[dict]) -> dict:
    """能力 9：标注进度统计。"""
    st = completion.assess_annotation_completion(
        pairs=pairs,
        rows_by_annotator={ANNOTATOR_A: rows_a, ANNOTATOR_B: rows_b},
        independence=blind_guard.check_annotator_independence(rows_a, rows_b),
    )
    return {"status": "PASS" if isinstance(st, dict) else "FAIL",
            "detail": f"进度统计可计算：annotation_status={st.get('annotation_status')}",
            "stats": st}


def drill_arbitration(pairs: list[dict], rows_a: list[dict], rows_b: list[dict], ws: Path) -> dict:
    """仲裁流程：分歧 → 仲裁表 → 最终标签（保留双方原始记录）。"""
    all_rows = list(rows_a) + list(rows_b)
    disagreements = arbitration.find_disagreements(all_rows, annotators=(ANNOTATOR_A, ANNOTATOR_B))
    sheet = ws / "arbitration" / "arbitration.csv"
    if disagreements:
        arbitration.export_arbitration_sheet(disagreements, sheet)
    arb_rows = []
    for d in disagreements:
        arb_rows.append({
            "arbitrator_id": ARBITRATOR, "pair_id": d["pair_id"],
            "final_relevance": "1", "final_confidence": "medium",
            "reason": "演练仲裁理由（机械判定，非真人仲裁）",
            "evidence": "演练仲裁证据（合成文本）",
            "annotation_timestamp": "2026-10-31T11:00:00",
            "protocol_version": PROTOCOL_VERSION,
        })
    if arb_rows:
        _write_csv(ws / "arbitration" / "arbitration_filled.csv", arb_rows,
                   ["arbitrator_id", "pair_id", "final_relevance", "final_confidence",
                    "reason", "evidence", "annotation_timestamp", "protocol_version"])
    built = arbitration.build_final_labels(pairs, all_rows, arb_rows)
    final_rows = built["final_rows"]
    integrity = completion.check_final_label_integrity(pairs, final_rows)
    kept_a = sum(1 for r in final_rows if r.get("annotator_a_relevance") not in ("", None))
    kept_b = sum(1 for r in final_rows if r.get("annotator_b_relevance") not in ("", None))
    ok = len(final_rows) == len(pairs) and kept_a == len(pairs) and kept_b == len(pairs)
    return {"status": "PASS" if ok else "FAIL",
            "detail": f"分歧 {len(disagreements)} 组 → 最终标签 {len(final_rows)} 条，"
                      f"双方原始结论均保留（A={kept_a}, B={kept_b}）",
            "disagreements": len(disagreements),
            "final_labels": len(final_rows),
            "integrity": integrity,
            "note": "演练仲裁由脚本机械判定，绝不是人类仲裁结论，不构成 Gold"}


def drill_agreement(rows_a: list[dict], rows_b: list[dict]) -> dict:
    rep = agreement.agreement_report(rows_a, rows_b)
    return {"status": "PASS",
            "detail": "一致性统计代码可运行；数值来自合成夹具，不代表任何真实标注质量",
            "caveat": "COMPUTED_ON_DRILL_FIXTURE_ONLY",
            "report": rep}


def drill_freeze_refusal(pairs: list[dict]) -> dict:
    """无合法真实数据时必须拒绝冻结（Gold 门禁状态驱动）。"""
    facts = {
        "real_resumes": 0, "real_pairs": 0, "synthetic_pairs": len(pairs),
        "synthetic_pairs_included": 0, "min_real_pairs": gold_gate.H2_MIN_REAL_PAIRS,
        "consent_complete": False, "dual_annotation_complete": False,
        "arbitration_status": "not_required", "open_disagreements": 0,
        "annotator_independence_ok": True, "independence_status": "not_applicable",
        "source_license_ok": False, "split_isolation_ok": False,
        "unjudgeable_forced": 0, "blocking_findings": [],
        "freeze_written": False, "freeze_verified": False,
    }
    pre = gold_gate.evaluate_precheck(facts, min_real_pairs=gold_gate.H2_MIN_REAL_PAIRS)
    ok = (pre.get("status") == "blocked") and not pre.get("precheck_passed")
    return {"status": "PASS" if ok else "FAIL",
            "detail": f"precheck status={pre.get('status')} passed={pre.get('precheck_passed')}",
            "reasons": pre.get("reasons", [])}


def drill_workspace_guard(ws: Path) -> dict:
    """负向测试：工作区落在真实数据目录内必须拒绝；生产根与临时目录允许。"""
    import importlib
    import os

    def would_refuse(target: Path) -> bool:
        old = os.environ.get(p7common.WORKSPACE_ENV)
        os.environ[p7common.WORKSPACE_ENV] = str(target)
        importlib.reload(p7common)
        try:
            p7common.ensure_workspace_safe()
            return False
        except RuntimeError:
            return True
        finally:
            if old is None:
                os.environ.pop(p7common.WORKSPACE_ENV, None)
            else:
                os.environ[p7common.WORKSPACE_ENV] = old
            importlib.reload(p7common)

    must_refuse = [ROOT / "data" / "private", ROOT / "data" / "private" / "resumes",
                   ROOT / "data" / "independent_eval" / "frozen"]
    must_allow = [ROOT.resolve(), ws]
    bad = [str(p) for p in must_refuse if not would_refuse(p)]
    bad += [str(p) for p in must_allow if would_refuse(p)]
    return {
        "status": "PASS" if not bad else "FAIL",
        "detail": ("真实数据目录（data/private、data/independent_eval/frozen）均拒绝执行；"
                   "项目根（生产工作区）与隔离临时目录允许"),
        "unexpected": bad,
    }


# ------------------------------------------------------------------ 主流程
def run_drill(workspace: Path | None = None) -> dict:
    own_ws = workspace is None
    ws = Path(workspace or tempfile.mkdtemp(prefix="phase7-drill-")).resolve()
    ensure_dir(ws)
    try:
        p7common.ensure_workspace_safe()
        pairs = _synthetic_pairs(12)
        order = {p["pair_id"] for p in pairs}

        checks: dict[str, dict] = {}
        checks["workspace_guard"] = drill_workspace_guard(ws)

        exp = drill_independent_export(pairs, ws)
        checks["independent_export"] = exp

        save = drill_annotation_save_and_resume(pairs, ws)
        checks["annotation_save"] = {"status": save["status"], "detail": save["detail"],
                                     "rows_saved": save["rows_saved"]}
        checks["resume_partial_annotation"] = {
            "status": save["status"],
            "detail": "断点续标：半程中断后可继续，最终无遗漏",
            "half_stage_missing": save["half_stage_missing"],
            "full_stage_missing": save["full_stage_missing"],
        }

        checks["required_field_check"] = drill_required_field_check(pairs, ws)
        checks["illegal_label_rejected"] = drill_illegal_label(pairs, ws)
        checks["privacy_residual_scan"] = drill_privacy_residual(pairs)

        # 生成两份真实形态的演练标注（PRNG，非模型输出）
        rng_a, rng_b = random.Random(DRILL_SEED + 11), random.Random(DRILL_SEED + 22)
        rows_a = [_annotation_row(p["pair_id"], ANNOTATOR_A, rng_a) for p in pairs]
        rows_b = [_annotation_row(p["pair_id"], ANNOTATOR_B, rng_b) for p in pairs]
        # 让一部分样本产生分歧（仍为机械生成）
        for i in range(0, len(rows_b), 3):
            rows_b[i]["relevance"] = LABELS[(LABELS.index(rows_a[i]["relevance"]) + 1) % len(LABELS)]

        path_a = ws / "imports" / f"annotations_{ANNOTATOR_A}.csv"
        path_b = ws / "imports" / f"annotations_{ANNOTATOR_B}.csv"
        _write_csv(path_a, rows_a, list(ANNOTATION_FIELDS))
        _write_csv(path_b, rows_b, list(ANNOTATION_FIELDS))
        rep_a = importer.validate_annotation_file(path_a, known_pairs=order,
                                                  known_annotators={ANNOTATOR_A})
        rep_b = importer.validate_annotation_file(path_b, known_pairs=order,
                                                  known_annotators={ANNOTATOR_B})
        checks["annotation_import_valid"] = {
            "status": "PASS" if (not rep_a["errors"] and not rep_b["errors"]) else "FAIL",
            "detail": f"A 有效 {rep_a['counts']['valid']} 行 / B 有效 {rep_b['counts']['valid']} 行",
            "errors": rep_a["errors"] + rep_b["errors"],
        }

        checks["same_person_two_annotators_rejected"] = drill_same_person_two_annotators(rows_a, rows_b)
        checks["mirrored_answer_detection"] = drill_mirror_detection(rows_a, rows_b)
        checks["annotation_progress_stats"] = drill_progress_stats(pairs, rows_a, rows_b)
        checks["arbitration_flow"] = drill_arbitration(pairs, rows_a, rows_b, ws)
        checks["agreement_metrics"] = drill_agreement(rows_a, rows_b)
        checks["freeze_refused_without_real_data"] = drill_freeze_refusal(pairs)

        # 合成数据不得进入 Gold
        real_gold = gold_gate.count_real_gold(pairs)
        checks["synthetic_not_gold"] = {
            "status": "PASS" if real_gold.get("real_gold_records", real_gold.get("real_gold", 0)) == 0 else "FAIL",
            "detail": f"合成配对经 is_real_gold_record 计数 = {real_gold}",
            "count_real_gold": real_gold,
        }

        names = list(checks)
        n_pass = sum(1 for k in names if checks[k]["status"] == "PASS")
        n_fail = sum(1 for k in names if checks[k]["status"] == "FAIL")
        return {
            "artifact": "phase7-annotation-drill",
            "generated_at": "2026-10-31T22:40:00+08:00",
            "drill_only": True,
            "status": "PASS" if n_fail == 0 else "FAIL",
            "nature": (
                "工具链演练：合成夹具 + 机械标签（固定种子 PRNG，与模型输出无关）。"
                "演练中的 '标注员' 不是真人，本结果不计为真实人工标注，不解除 H2 阻断。"
            ),
            "workspace": str(ws) if not own_ws else "<temp>",
            "fixture": {"pairs": len(pairs), "is_synthetic": True, "eligible_for_gold": False,
                        "seed": DRILL_SEED},
            "protocol_version": PROTOCOL_VERSION,
            "checks": checks,
            "summary": {"total": len(names), "pass": n_pass, "fail": n_fail,
                        "failed": [k for k in names if checks[k]["status"] == "FAIL"]},
            "discipline": [
                "不伪造真实简历：夹具全部为合成文本并带水印声明",
                "不让 AI 冒充人工标注员：标签由 PRNG 机械生成，标注员 ID 带 Drill 前缀",
                "不把演练结果当作 Gold：synthetic_not_gold 负向校验保证",
                "不触碰 data/private 与 data/independent_eval 真实对象",
            ],
        }
    finally:
        if own_ws and ws.exists():
            shutil.rmtree(ws, ignore_errors=True)


def _md(payload: dict) -> str:
    L = ["# P7-2 双人盲标注工作流演练（隔离合成夹具）", "",
         f"- 生成时间：{payload['generated_at']}",
         f"- 状态：`{payload['status']}`（{payload['summary']['pass']}/{payload['summary']['total']} 通过）",
         f"- **性质**：{payload['nature']}",
         f"- 协议版本：`{payload['protocol_version']}`",
         f"- 夹具：{payload['fixture']['pairs']} 个合成配对，seed={payload['fixture']['seed']}", "",
         "## 逐项验收（任务书 6.3）", "",
         "| # | 能力 | 结果 | 说明 |", "|---|---|---|---|"]
    names = {
        "workspace_guard": "隔离工作区安全边界（负向）",
        "independent_export": "独立导出（盲化）",
        "annotation_save": "标注保存",
        "resume_partial_annotation": "断点续标",
        "required_field_check": "输入字段检查",
        "illegal_label_rejected": "非法标签拒绝",
        "privacy_residual_scan": "隐私残留扫描",
        "annotation_import_valid": "标注文件导入校验",
        "same_person_two_annotators_rejected": "同人冒充两个标注员拒绝",
        "mirrored_answer_detection": "镜像答案异常检测",
        "annotation_progress_stats": "标注进度统计",
        "arbitration_flow": "仲裁流程",
        "agreement_metrics": "一致性统计（drill-only）",
        "freeze_refused_without_real_data": "无真实数据拒绝冻结",
        "synthetic_not_gold": "合成数据不得进入 Gold",
    }
    for i, (k, v) in enumerate(payload["checks"].items(), 1):
        L.append(f"| {i} | {names.get(k, k)} | `{v['status']}` | {v.get('detail','')} |")
    L += ["", "## 结论", ""]
    if payload["status"] == "PASS":
        L.append("标注工具链在隔离合成夹具上完整可操作：导出、保存、续标、校验、独立性、"
                 "隐私扫描、仲裁与进度统计全部按预期工作。")
    else:
        L.append(f"存在失败项：{payload['summary']['failed']}，工具链尚未完全就绪。")
    L += ["",
          "**但演练通过 ≠ 真实人工标注完成**：当前真实配对 0、标注员 0、H2 仍为 BLOCKED。"
          "解除阻断必须由两名真实人类标注员在授权真实数据上独立标注并经人类仲裁。", "",
          "## 纪律声明", ""]
    L += [f"- {d}" for d in payload["discipline"]]
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase7 盲标注工具链演练（合成夹具）")
    ap.add_argument("--workspace", default=None, help="隔离工作区目录（默认临时目录，用完删除）")
    ap.add_argument("--keep", action="store_true", help="保留演练工作区以便人工核查")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve() if args.workspace else None
    payload = run_drill(ws if args.keep else None)
    out = write_json(report_path("reports", "phase7", "annotation-drill.json"), payload)
    md = report_path("reports", "phase7", "annotation-drill.md")
    md.write_text(_md(payload), encoding="utf-8")
    print(f"[{payload['status']}] 演练 {payload['summary']['pass']}/{payload['summary']['total']} 通过"
          f"（失败: {payload['summary']['failed']}）")
    print(f"  报告: {out}\n        {md}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
