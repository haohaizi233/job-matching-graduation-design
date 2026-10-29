# -*- coding: utf-8 -*-
"""正式 Gold 评估集冻结（Phase4-3A-2 模块 E / Phase5-1R F-001、F-003、F-004）。

流程（两阶段门禁，消除「未冻结 -> 不过门禁 -> 不能冻结」的循环依赖）：
  1. 汇总事实（真实简历/配对规模、双人标注、标注独立性、仲裁、授权、泄漏、合成混入）；
  2. **Pre-freeze Gate**（gold_gate.evaluate_precheck, strict）：只检查冻结前置条件，
     不要求任何冻结哈希/切分结果；任一不满足 -> freeze_blocked.json（绝不虚构补数）；
  3. 按简历 ID 组级切分 dev_validation / blind_test（默认 70/30，seed 固定）：
     * 同一简历的配对绝不跨集合；
     * 岗位盲测不合格（与训练语料/历史 Gold 重合）的配对不进 blind_test，
       若其简历被分到 blind_test 则该配对整体排除（quarantined_out）；
     * 合成配对一律排除出人工真值评估集；
  4. freeze_dataset(stage=evalset) 在暂存目录生成 manifest（来源/许可清单、标签分布、
     双标注与仲裁统计、SHA-256），校验通过后原子发布；
  5. verify_freeze 复验哈希 -> freeze-verification.json；
  6. **Post-freeze Gate**（gold_gate.evaluate_postcheck, strict）：切分隔离、pair 唯一、
     最终标签一一对应、文件完整、SHA-256、数据集版本、来源记录；
  7. h2_status = evaluate_g2_status（前置 + 后置 + 真实规模）。

状态字段（唯一口径）：
  precheck_passed / split_validated / freeze_written / freeze_verified / h2_status

工程夹具模式（--fixture-mode，必须配合 PHASE4_3A_2_WORKSPACE 隔离目录）：
  * 只验证冻结**软件流程**能够成功运行，不需要真实简历；
  * 一律输出 h2_status=blocked + fixture_mode=true，绝不产生真实 H2 PASS；
  * 拒绝指向真实数据/模型目录的工作区（workspace_guard）。

用法：
  python scripts/phase4_3a_2/freeze_gold.py [--seed 20261213] [--blind-ratio 0.3] [--job-isolated]
  python scripts/phase4_3a_2/freeze_gold.py verify --manifest <path>
  python scripts/phase4_3a_2/freeze_gold.py --fixture-mode   # 仅限隔离工作区
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    ANNOTATOR_A, ANNOTATOR_B, ANNOT_DIR, ARBITRATOR, DOCS_DIR, FROZEN_DIR,
    IS_FIXTURE_WORKSPACE, PAIRS_REAL_V2, POOL_DIR, PRIVATE_ANNOT_DIR, REPORT_DIR,
    ensure_workspace_safe, now, read_jsonl, write_report,
)

from job_matching.annotation import gold_gate  # noqa: E402
from job_matching.annotation.freeze import (  # noqa: E402
    FreezeError, assign_splits, freeze_dataset, verify_freeze,
)
from job_matching.core import ensure_dir, fix_stdio, jdump, rel  # noqa: E402

fix_stdio()   # Windows 控制台强制 UTF-8（避免中文报告乱码）

EVALSET_DIR = FROZEN_DIR / "evalset_v2"
EVALSET_VERSION = "evalset-v2"

_FIXTURE_NOTE = (
    "工程夹具模式：本结果只证明冻结软件流程可运行，"
    "不构成真实 Gold，不产生真实 H2 PASS，不得计入正式数据数量")


def _jload_if(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _source_license_ok(source_audit: dict) -> bool:
    """数据来源与使用许可准入（复用 source-audit.json 的 admission_checklist）。"""
    items = list(source_audit.get("admission_checklist") or [])
    if not items:
        return False
    bad = [it for it in items
           if str(it.get("status", "")).lower() not in ("ok", "partial")]
    return not bad and not source_audit.get("unresolved_blocking_findings")


def collect_facts(min_real_pairs: int) -> dict:
    """汇总门禁事实（前置 + 后置分阶段回填）。"""
    manifest = _jload_if(REPORT_DIR / "real-pair-manifest.json")
    progress = _jload_if(REPORT_DIR / "annotation-progress.json")
    agreement = _jload_if(REPORT_DIR / "agreement-results.json")
    leakage = _jload_if(REPORT_DIR / "leakage-check.json")
    intake = _jload_if(REPORT_DIR / "resume-intake-audit.json")
    source_audit = _jload_if(REPORT_DIR / "source-audit.json")

    real_resumes = int((manifest.get("resume_intake") or {}).get("records_real", 0)
                       or intake.get("accepted_real_gold", 0) or 0)
    pairs = read_jsonl(PAIRS_REAL_V2) if PAIRS_REAL_V2.exists() else []
    real_pairs = len([p for p in pairs if not bool(p.get("is_synthetic"))])
    final_checks = (agreement.get("final_labels") or {}).get("checks", {})
    unjudgeable_forced = len(final_checks.get("unjudgeable_forced", [])
                             or (agreement.get("final_labels") or {}).get("unjudgeable_forced", []) or [])
    assessment = progress.get("status_assessment") or {}
    independence = progress.get("independence") or {}
    independence_status = str(independence.get("status", "") or "")
    arbitration_status = str((progress.get("arbitration") or {}).get("status", "") or "")

    blocking_findings = list(leakage.get("unresolved_blocking_findings", []) or [])
    blocking_findings += [f"标注:{b}" for b in (assessment.get("blocking") or [])]

    facts = {
        # ---- 冻结前置（Pre-freeze Gate）
        "consent_complete": bool(real_resumes > 0
                                 and intake.get("consent_complete", True)),
        "source_license_ok": _source_license_ok(source_audit),
        "real_resumes": real_resumes,
        "real_pairs": real_pairs,
        "dual_annotation_complete": progress.get("annotation_status") == "complete",
        "annotator_independence_ok": independence_status in ("ok", "not_applicable"),
        "open_disagreements": int(progress.get("open_disagreements", 0) or 0),
        "arbitration_status": arbitration_status,
        "unjudgeable_forced": int(unjudgeable_forced),
        "blocking_findings": blocking_findings,
        "synthetic_pairs_included": 0,   # 合成配对在 plan_splits 一律排除，回填复核
        # ---- 冻结后置（Post-freeze Gate，切分/冻结后回填）
        "split_isolation_ok": False,
        "freeze_written": False,
        "freeze_verified": False,
        # ---- 兼容历史 facts 契约
        "synthetic_pairs": int((manifest.get("resume_intake") or {})
                               .get("records_synthetic_excluded", 0) or 0),
        "min_real_pairs": min_real_pairs,
        "independence_status": independence_status,
    }
    return {"facts": facts, "pairs": pairs, "progress": progress,
            "agreement": agreement, "source_audit": source_audit,
            "leakage": leakage, "intake": intake}


def plan_splits(pairs: list[dict], seed: int, blind_ratio: float) -> tuple[list[dict], list[dict], dict]:
    """按简历 ID 组级切分（70/30）。返回 (frozen_pairs, excluded_pairs, split_info)。

    盲测合格判定：
      * 配对 blind_eligible 不为 False（岗位与训练语料/历史 Gold 重合的配对禁入盲测）；
      * 简历是否进 blind_test 由 assign_splits（确定性、按简历分组）决定。
    被排除配对（其简历进 blind_test 但配对盲测不合格 / 合成配对）整体出评估集，记录原因。
    """
    synthetic = [p for p in pairs if bool(p.get("is_synthetic"))]
    real = [p for p in pairs if not bool(p.get("is_synthetic"))]
    eligible = [p for p in real if p.get("blind_eligible", True)]
    ineligible = [p for p in real if not p.get("blind_eligible", True)]
    assigned = assign_splits(eligible, seed=int(seed), blind_ratio=float(blind_ratio))
    blind_resumes = {p["resume_id"] for p in assigned if p["split"] == gold_gate.SPLIT_BLIND}

    frozen: list[dict] = []
    excluded: list[dict] = []
    for p in assigned:
        frozen.append(dict(p))
    for p in ineligible:
        q = dict(p)
        if q.get("resume_id") in blind_resumes:
            q["split"] = "quarantined_out"
            q["exclusion_reason"] = ("该配对岗位与训练语料/历史 Gold 重合，禁入 blind_test；"
                                     "其简历已分入 blind_test，为保持简历级隔离该配对整体排除")
            excluded.append(q)
        else:
            q["split"] = gold_gate.SPLIT_DEV
            q["exclusion_reason"] = ""
            frozen.append(q)
    for p in synthetic:
        q = dict(p)
        q["split"] = "quarantined_out"
        q["exclusion_reason"] = "合成配对不得进入人工真值评估集（不计入真实 Gold 数量）"
        excluded.append(q)

    strict_pairs = [p for p in real if p.get("strict_unseen_jd_eligible", True)]
    split_info = {
        "seed": int(seed), "blind_ratio": float(blind_ratio),
        "policy": "resume_id 组级切分（同一简历的配对不拆分）",
        "resumes_dev": sorted({p["resume_id"] for p in frozen
                               if p["split"] == gold_gate.SPLIT_DEV}),
        "resumes_blind": sorted(blind_resumes),
        "pairs_dev": sum(1 for p in frozen if p["split"] == gold_gate.SPLIT_DEV),
        "pairs_blind": sum(1 for p in frozen if p["split"] == gold_gate.SPLIT_BLIND),
        "pairs_excluded": len(excluded),
        "synthetic_pairs_excluded": len(synthetic),
        "exclusion_policy": ("盲测不合格配对若属于 blind 简历则整体排除；"
                             "属于 dev 简历的保留在 dev_validation（dev 允许见过数据）；"
                             "合成配对一律排除"),
        "strict_unseen_jd_variant": {
            "pairs_eligible": len(strict_pairs),
            "resumes_eligible": len({p["resume_id"] for p in strict_pairs}),
            "usable": len(strict_pairs) > 0,
            "note": ("要求『模型完全未见过岗位文本』的任务只能使用 strict_unseen_jd_eligible=true "
                     "的配对；若为 0，该类任务不能使用本评估集（需另行采集岗位）"),
        },
    }
    return frozen, excluded, split_info


def _blocked_out(reasons: list[str], *, facts: dict, stage: str,
                 extra: dict | None = None, fixture_mode: bool = False) -> dict:
    """统一的冻结拒绝产出（freeze_blocked.json + freeze-verification.json）。"""
    pre = gold_gate.evaluate_precheck(facts, min_real_pairs=int(facts.get("min_real_pairs")
                                                               or gold_gate.H2_MIN_REAL_PAIRS),
                                      strict=True)
    out = {
        "stage": "evalset", "status": "blocked", "blocked_stage": stage,
        "created_at": now(),
        "reasons": reasons,
        "precheck_passed": pre["precheck_passed"],
        "split_validated": bool(facts.get("split_isolation_ok", False)),
        "freeze_written": False,
        "freeze_verified": False,
        "h2_status": "blocked",
        "precheck": pre,
        "facts": facts,
        "fixture_mode": bool(fixture_mode),
        "blind_protection": gold_gate.check_blind_status(freeze_verified=False,
                                                        blind_claimed_pass=False),
        "note": ("未满足冻结条件：评估集不允许冻结，更不允许虚构人工数据补齐。"
                 "blind_test 在冻结与哈希复验完成前不得标记正式通过"),
    }
    if fixture_mode:
        out["note"] = _FIXTURE_NOTE + "；" + out["note"]
    out.update(extra or {})
    ensure_dir(EVALSET_DIR)
    jdump(out, EVALSET_DIR / "freeze_blocked.json")
    write_report("freeze-verification.json", {
        "generated_by": "scripts/phase4_3a_2/freeze_gold.py",
        "created_at": now(),
        "status": "blocked", "blocked_stage": stage,
        "reasons": reasons,
        "precheck_passed": pre["precheck_passed"],
        "split_validated": out["split_validated"],
        "freeze_written": False,
        "freeze_verified": False,
        "h2_status": "blocked",
        "precheck": pre,
        "facts": facts,
        "fixture_mode": bool(fixture_mode),
        "hash_verification": "not_applicable（未冻结）",
        "blind_protection": out["blind_protection"],
    })
    return out


def run(seed: int = 20261213, blind_ratio: float = 0.3,
        min_real_pairs: int = 300, job_isolated: bool = False,
        fixture_mode: bool = False) -> dict:
    ensure_workspace_safe()
    fixture_mode = bool(fixture_mode or IS_FIXTURE_WORKSPACE)
    ctx = collect_facts(min_real_pairs)
    facts, pairs, progress, agreement = (ctx["facts"], ctx["pairs"],
                                         ctx["progress"], ctx["agreement"])

    # ---------------- Pre-freeze Gate（冻结前置，不要求冻结哈希）
    pre = gold_gate.evaluate_precheck(facts, min_real_pairs=min_real_pairs, strict=True)
    if not pre["precheck_passed"]:
        return _blocked_out(list(pre["reasons"]), facts=facts, stage="pre_freeze",
                            extra={"precheck": pre}, fixture_mode=fixture_mode)

    # ---------------- 切分（组级隔离）+ 合成排除
    frozen_pairs, excluded_pairs, split_info = plan_splits(pairs, seed, blind_ratio)
    facts["synthetic_pairs_included"] = sum(1 for p in frozen_pairs
                                            if bool(p.get("is_synthetic")))
    if facts["synthetic_pairs_included"] > 0:   # pragma: no cover - plan_splits 已排除
        return _blocked_out(["合成配对混入人工真值评估集"], facts=facts,
                            stage="pre_freeze", fixture_mode=fixture_mode)
    split_check = gold_gate.check_split_isolation(frozen_pairs, job_isolated=job_isolated)
    facts["split_isolation_ok"] = bool(split_check["ok"])
    if not split_check["ok"]:
        return _blocked_out(["dev_validation / blind_test 分组隔离检查未通过"],
                            facts=facts, stage="split",
                            extra={"split_check": split_check}, fixture_mode=fixture_mode)

    # ---------------- 冻结（暂存目录 -> 校验 -> 原子发布）
    staging = EVALSET_DIR.parent / (EVALSET_DIR.name + ".staging")
    if staging.exists():
        import shutil
        shutil.rmtree(staging)
    ensure_dir(staging)
    pairs_file = staging / "pairs_frozen.jsonl"
    with open(pairs_file, "w", encoding="utf-8", newline="\n") as f:
        for p in sorted(frozen_pairs, key=lambda x: str(x["pair_id"])):
            f.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
    excluded_file = staging / "excluded_pairs.jsonl"
    with open(excluded_file, "w", encoding="utf-8", newline="\n") as f:
        for p in sorted(excluded_pairs, key=lambda x: str(x["pair_id"])):
            f.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")

    split_lists = {
        "policy": split_info["policy"],
        "seed": split_info["seed"], "blind_ratio": split_info["blind_ratio"],
        "dev_validation_pairs": sorted(p["pair_id"] for p in frozen_pairs
                                       if p["split"] == gold_gate.SPLIT_DEV),
        "blind_test_pairs": sorted(p["pair_id"] for p in frozen_pairs
                                   if p["split"] == gold_gate.SPLIT_BLIND),
        "dev_validation_resumes": split_info["resumes_dev"],
        "blind_test_resumes": split_info["resumes_blind"],
        "excluded_pairs": [{"pair_id": p["pair_id"], "reason": p.get("exclusion_reason")}
                           for p in excluded_pairs],
    }
    split_file = staging / "split_lists.json"
    jdump(split_lists, split_file)

    final_file = ANNOT_DIR / "final_labels.csv"
    labels = []
    if final_file.exists():
        labels = _load_csv(final_file)
    label_dist: dict[str, int] = {}
    for r in labels:
        k = str(r.get("final_relevance", ""))
        label_dist[k] = label_dist.get(k, 0) + 1

    files = {
        "pairs": pairs_file,
        "excluded_pairs": excluded_file,
        "split_lists": split_file,
        "final_labels": final_file,
        "annotations_a": PRIVATE_ANNOT_DIR / f"annotations_{ANNOTATOR_A}.csv",
        "annotations_b": PRIVATE_ANNOT_DIR / f"annotations_{ANNOTATOR_B}.csv",
        "job_pool_v2": POOL_DIR / "job_pool_v2.jsonl",
        "source_audit": REPORT_DIR / "source-audit.json",
        "consent_template": DOCS_DIR / "evaluation" / "consent-template.md",
        "annotation_guidelines": DOCS_DIR / "evaluation" / "annotation-guidelines.md",
    }
    # F-003：仲裁文件按仲裁状态登记，无分歧不得强制要求人工仲裁文件
    arbitration_status = str((progress.get("arbitration") or {}).get("status", "") or "")
    arbitration_file = PRIVATE_ANNOT_DIR / "arbitration_filled.csv"
    arbitration_required = arbitration_status == "completed"
    arbitration_registered = arbitration_required and arbitration_file.exists()
    if arbitration_registered:
        files["arbitration"] = arbitration_file
    arbitration_manifest_note = {
        "arbitration_status": arbitration_status or "not_reported",
        "arbitration_file_registered": bool(arbitration_registered),
        "reason": (
            "无分歧样本（arbitration_status=not_required）：协议不要求人工仲裁文件，"
            "冻结 manifest 明确登记『无仲裁记录』的原因" if not arbitration_required
            else "存在分歧且仲裁已完成：仲裁记录随评估集一起冻结"),
        "arbitration_file": rel(arbitration_file) if arbitration_file.exists() else None,
    }

    responsibility = {
        "annotators": [ANNOTATOR_A, ANNOTATOR_B],
        "arbitrator": ARBITRATOR,
        "data_sources": "见 source-audit.json（job-education apache-2.0；"
                        "all_df/英文简历已隔离）",
        "consent_records": "data/private/consent/consent_records.csv（不入库，逐条可核）",
        "protocol_version": "phase4-3a-annotation-v1",
        "human_labeling_statement": "全部标签由人工双盲标注 + 仲裁产生，无生成式 AI 标签",
    }

    try:
        manifest = freeze_dataset(
            stage="evalset", out_dir=EVALSET_DIR, pairs_file=pairs_file,
            files=files, dataset_version=EVALSET_VERSION,
            work_dir=staging,
            path_map={k: EVALSET_DIR / Path(v).name
                      for k, v in files.items()
                      if Path(v).parent == staging},
            source_stats={
                "pairs_frozen": len(frozen_pairs),
                "pairs_excluded": len(excluded_pairs),
                "real_resumes": facts["real_resumes"],
                "split": {"dev_validation": split_info["pairs_dev"],
                          "blind_test": split_info["pairs_blind"]},
                "job_adjudication": "见 job-candidate-audit.json",
            },
            label_distribution=dict(sorted(label_dist.items())),
            annotation_quality={
                "annotation_status": progress.get("annotation_status"),
                "open_disagreements": facts["open_disagreements"],
                "unjudgeable_forced": facts["unjudgeable_forced"],
                "arbitration_status": arbitration_status or "not_reported",
                "synthetic_pairs_included": 0,
                "agreement": agreement.get("agreement", {}),
            },
            responsibility=responsibility,
            extra={
                "cold_start_protocol": (
                    "本次切分仅按 resume_id 组级隔离（简历冷启动）；"
                    "如需岗位冷启动/双冷启动，必须按 job_id 严格隔离另行建协议，"
                    "不得把只按简历隔离的结果称为双冷启动"),
                "blind_protection_policy": (
                    "blind_test 仅在模型/特征/参数冻结后一次性执行；"
                    "不得用 blind_test 调参、选算法、反复查看或替换不利样本"),
                "split_info": split_info,
                "arbitration_manifest": arbitration_manifest_note,
                "fixture_mode": bool(fixture_mode),
                "fixture_note": _FIXTURE_NOTE if fixture_mode else "",
            })
    except FreezeError as e:
        facts["freeze_written"] = False
        return _blocked_out([str(e)], facts=facts, stage="freeze_write",
                            fixture_mode=fixture_mode)

    facts["freeze_written"] = True
    verification = verify_freeze(EVALSET_DIR / "manifest.json")
    facts["freeze_verified"] = bool(verification["ok"])

    # ---- 回填 Post-freeze Gate 事实（唯一口径：manifest 互斥检查 + 哈希复验 + 来源记录）
    mx = manifest.get("mutual_exclusivity") or {}
    facts.update({
        "pair_id_unique": bool(mx.get("pair_id_unique", False)),
        "resume_job_unique": bool(mx.get("resume_job_unique", False)),
        "final_labels_complete": mx.get("final_label_missing_for_pairs", 1) == 0,
        "final_labels_unique": bool(mx.get("final_label_unique", False)),
        "final_label_pairs_known": mx.get("final_label_unknown_pairs", 1) == 0,
        "files_complete": bool(verification["files"]) and all(
            f.get("exists") for f in verification["files"]),
        "sha256_ok": bool(verification["ok"]),
        "dataset_version_ok": bool(manifest.get("dataset_version")),
        "provenance_complete": bool(responsibility) and bool(manifest.get("source_stats")),
    })

    # ---------------- Post-freeze Gate（冻结后验证）
    post = gold_gate.evaluate_postcheck(facts, strict=True)
    g2 = gold_gate.evaluate_g2_status(facts, min_real_pairs=min_real_pairs, strict=True)
    h2_status = g2["status"]
    h2_reasons = list(g2["reasons"])
    if fixture_mode:
        h2_status = "blocked"
        h2_reasons.append(_FIXTURE_NOTE)

    verification_report = {
        "generated_by": "scripts/phase4_3a_2/freeze_gold.py",
        "created_at": now(),
        "status": ("frozen" if verification["ok"] and post["postcheck_passed"]
                   else "verification_failed"),
        "dataset_version": manifest["dataset_version"],
        "stage": "evalset",
        "manifest": rel(EVALSET_DIR / "manifest.json"),
        "manifest_sha256": manifest.get("manifest_sha256"),
        "files_verified": verification["files"],
        "hash_verification_ok": verification["ok"],
        "sample_counts": manifest.get("sample_counts", {}),
        "mutual_exclusivity": manifest.get("mutual_exclusivity", {}),
        "split_info": split_info,
        "split_isolation": split_check,
        "arbitration": arbitration_manifest_note,
        "precheck_passed": pre["precheck_passed"],
        "split_validated": bool(split_check["ok"]),
        "freeze_written": True,
        "freeze_verified": bool(verification["ok"]),
        "postcheck": post,
        "h2_status": h2_status,
        "h2_reasons": h2_reasons,
        "h2_gate": g2,
        "fixture_mode": bool(fixture_mode),
        "blind_protection": gold_gate.check_blind_status(
            freeze_verified=bool(verification["ok"]), blind_claimed_pass=False),
        "reverify_command": ("python scripts/phase4_3a_2/freeze_gold.py verify "
                             f"--manifest {rel(EVALSET_DIR / 'manifest.json')}"),
    }
    write_report("freeze-verification.json", verification_report)
    out = {"stage": "evalset", "status": verification_report["status"],
           "dataset_version": manifest["dataset_version"],
           "hash_verification_ok": verification["ok"],
           "precheck_passed": pre["precheck_passed"],
           "split_validated": bool(split_check["ok"]),
           "freeze_written": True,
           "freeze_verified": bool(verification["ok"]),
           "postcheck_passed": post["postcheck_passed"],
           "h2_status": h2_status,
           "h2_reasons": h2_reasons,
           "fixture_mode": bool(fixture_mode),
           "split_info": split_info}
    return out


def _load_csv(path: Path) -> list[dict]:
    import pandas as pd
    return pd.read_csv(path, dtype=str).fillna("").to_dict("records")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="freeze")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--seed", type=int, default=20261213)
    ap.add_argument("--blind-ratio", type=float, default=0.3)
    ap.add_argument("--min-real-pairs", type=int, default=300)
    ap.add_argument("--job-isolated", action="store_true",
                    help="岗位冷启动协议：额外按 job_id 隔离（与简历隔离结果分开命名）")
    ap.add_argument("--fixture-mode", action="store_true",
                    help="工程夹具模式：只验证冻结软件流程，必须配合 "
                         f"{'PHASE4_3A_2_WORKSPACE' if True else ''} 隔离目录；"
                         "绝不产生真实 H2 PASS")
    args = ap.parse_args()
    if args.action == "verify":
        if not args.manifest:
            print(json.dumps({"error": "verify 需要 --manifest"}, ensure_ascii=False))
            return 2
        res = verify_freeze(args.manifest)
    else:
        if args.fixture_mode and not IS_FIXTURE_WORKSPACE:
            print(json.dumps({
                "error": "--fixture-mode 必须配合 PHASE4_3A_2_WORKSPACE 隔离工作区使用，"
                         "禁止在真实工作区跑工程夹具（防止模拟结果污染真实 Gold 产物）"},
                ensure_ascii=False))
            return 2
        res = run(seed=args.seed, blind_ratio=args.blind_ratio,
                  min_real_pairs=args.min_real_pairs, job_isolated=args.job_isolated,
                  fixture_mode=args.fixture_mode)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
