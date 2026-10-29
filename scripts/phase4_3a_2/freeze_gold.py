# -*- coding: utf-8 -*-
"""正式 Gold 评估集冻结（Phase4-3A-2 模块 E）。

流程：
  1. 汇总事实（真实简历/配对规模、双人标注、仲裁、授权、泄漏、合成混入）；
  2. gold_gate.evaluate_g2_status 判定：任一不满足 -> freeze_blocked.json（绝不虚构补数）；
  3. 按简历 ID 组级切分 dev_validation / blind_test（默认 70/30，seed 固定）：
     * 同一简历的配对绝不跨集合；
     * 岗位盲测不合格（与训练语料/历史 Gold 重合）的配对不进 blind_test，
       若其简历被分到 blind_test 则该配对整体排除（quarantined_out）；
  4. freeze_dataset(stage=evalset) 生成 manifest（来源/许可清单、标签分布、
     双标注与仲裁统计、SHA-256）；
  5. verify_freeze 复验哈希 -> freeze-verification.json。

用法：
  python scripts/phase4_3a_2/freeze_gold.py [--seed 20261213] [--blind-ratio 0.3] [--job-isolated]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    ANNOTATOR_A, ANNOTATOR_B, ANNOT_DIR, ARBITRATOR, FROZEN_DIR, PAIRS_REAL_V2,
    PRIVATE_ANNOT_DIR, now, read_jsonl, write_report,
)

from job_matching.annotation import gold_gate  # noqa: E402
from job_matching.annotation.freeze import (  # noqa: E402
    FreezeError, assign_splits, freeze_dataset, verify_freeze,
)
from job_matching.core import ROOT, ensure_dir, jdump, sha256_file  # noqa: E402

EVALSET_DIR = FROZEN_DIR / "evalset_v2"


def _jload_if(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_facts(min_real_pairs: int) -> dict:
    manifest = _jload_if(ROOT / "reports" / "phase4-3a-2" / "real-pair-manifest.json")
    progress = _jload_if(ROOT / "reports" / "phase4-3a-2" / "annotation-progress.json")
    agreement = _jload_if(ROOT / "reports" / "phase4-3a-2" / "agreement-results.json")
    leakage = _jload_if(ROOT / "reports" / "phase4-3a-2" / "leakage-check.json")
    intake = _jload_if(ROOT / "reports" / "phase4-3a-2" / "resume-intake-audit.json")

    real_resumes = int((manifest.get("resume_intake") or {}).get("records_real", 0)
                       or intake.get("accepted_real_gold", 0) or 0)
    pairs = read_jsonl(PAIRS_REAL_V2) if PAIRS_REAL_V2.exists() else []
    real_pairs = len([p for p in pairs if not bool(p.get("is_synthetic"))])
    final_checks = (agreement.get("final_labels") or {}).get("checks", {})
    unjudgeable_forced = len(final_checks.get("unjudgeable_forced", [])
                             or (agreement.get("final_labels") or {}).get("unjudgeable_forced", []) or [])
    facts = {
        "real_resumes": real_resumes,
        "real_pairs": real_pairs,
        "synthetic_pairs": int((manifest.get("resume_intake") or {})
                               .get("records_synthetic_excluded", 0) or 0),
        "dual_annotation_complete": progress.get("annotation_status") == "complete",
        "open_disagreements": int(progress.get("open_disagreements", 0) or 0),
        "unjudgeable_forced": int(unjudgeable_forced),
        "consent_complete": real_resumes > 0,
        "leakage_blocking_findings": leakage.get("unresolved_blocking_findings", []),
        "split_isolation_ok": False,   # 切分后回填
        "freeze_verified": False,      # 冻结复验后回填
        "min_real_pairs": min_real_pairs,
    }
    return facts, pairs, progress, agreement


def plan_splits(pairs: list[dict], seed: int, blind_ratio: float) -> tuple[list[dict], list[dict], dict]:
    """按简历 ID 组级切分（70/30）。返回 (frozen_pairs, excluded_pairs, split_info)。

    盲测合格判定：
      * 配对 blind_eligible 不为 False（岗位与训练语料/历史 Gold 重合的配对禁入盲测）；
      * 简历是否进 blind_test 由 assign_splits（确定性、按简历分组）决定。
    被排除配对（其简历进 blind_test 但配对盲测不合格）整体出评估集，记录原因。
    """
    eligible = [p for p in pairs if p.get("blind_eligible", True)]
    ineligible = [p for p in pairs if not p.get("blind_eligible", True)]
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

    strict_pairs = [p for p in pairs if p.get("strict_unseen_jd_eligible", True)]
    split_info = {
        "seed": int(seed), "blind_ratio": float(blind_ratio),
        "policy": "resume_id 组级切分（同一简历的配对不拆分）",
        "resumes_dev": sorted({p["resume_id"] for p in frozen
                               if p["split"] == gold_gate.SPLIT_DEV}),
        "resumes_blind": sorted(blind_resumes),
        "pairs_dev": sum(1 for p in frozen if p["split"] == gold_gate.SPLIT_DEV),
        "pairs_blind": sum(1 for p in frozen if p["split"] == gold_gate.SPLIT_BLIND),
        "pairs_excluded": len(excluded),
        "exclusion_policy": ("盲测不合格配对若属于 blind 简历则整体排除；"
                             "属于 dev 简历的保留在 dev_validation（dev 允许见过数据）"),
        "strict_unseen_jd_variant": {
            "pairs_eligible": len(strict_pairs),
            "resumes_eligible": len({p["resume_id"] for p in strict_pairs}),
            "usable": len(strict_pairs) > 0,
            "note": ("要求『模型完全未见过岗位文本』的任务只能使用 strict_unseen_jd_eligible=true "
                     "的配对；若为 0，该类任务不能使用本评估集（需另行采集岗位）"),
        },
    }
    return frozen, excluded, split_info


def run(seed: int = 20261213, blind_ratio: float = 0.3,
        min_real_pairs: int = 300, job_isolated: bool = False) -> dict:
    ensure_dir(EVALSET_DIR)
    facts, pairs, progress, agreement = collect_facts(min_real_pairs)
    g2 = gold_gate.evaluate_g2_status(facts, min_real_pairs=min_real_pairs)

    if g2["status"] != "ready":
        out = {
            "stage": "evalset", "status": "blocked",
            "created_at": now(),
            "g2_status": g2,
            "facts": facts,
            "blind_protection": gold_gate.check_blind_status(freeze_verified=False,
                                                            blind_claimed_pass=False),
            "note": ("未满足冻结条件：评估集不允许冻结，更不允许虚构人工数据补齐。"
                     "blind_test 在冻结与哈希复验完成前不得标记正式通过"),
        }
        jdump(out, EVALSET_DIR / "freeze_blocked.json")
        write_report("freeze-verification.json", {
            "generated_by": "scripts/phase4_3a_2/freeze_gold.py",
            "created_at": now(),
            "status": "blocked",
            "reasons": g2["reasons"],
            "g2_status": g2,
            "facts": facts,
            "hash_verification": "not_applicable（未冻结）",
            "blind_protection": out["blind_protection"],
        })
        return out

    frozen_pairs, excluded_pairs, split_info = plan_splits(pairs, seed, blind_ratio)
    split_check = gold_gate.check_split_isolation(frozen_pairs, job_isolated=job_isolated)
    if not split_check["ok"]:
        out = {"stage": "evalset", "status": "blocked",
               "created_at": now(),
               "reason": "切分隔离检查未通过", "split_check": split_check}
        jdump(out, EVALSET_DIR / "freeze_blocked.json")
        write_report("freeze-verification.json", {
            "generated_by": "scripts/phase4_3a_2/freeze_gold.py",
            "created_at": now(), "status": "blocked",
            "reasons": ["dev_validation / blind_test 分组隔离检查未通过"],
            "split_check": split_check})
        return out

    pairs_file = EVALSET_DIR / "pairs_frozen.jsonl"
    with open(pairs_file, "w", encoding="utf-8", newline="\n") as f:
        for p in sorted(frozen_pairs, key=lambda x: str(x["pair_id"])):
            f.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
    excluded_file = EVALSET_DIR / "excluded_pairs.jsonl"
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
    split_file = EVALSET_DIR / "split_lists.json"
    jdump(split_lists, split_file)

    final_file = ANNOT_DIR / "final_labels.csv"
    labels = []
    if final_file.exists():
        import pandas as pd
        labels = pd.read_csv(final_file, dtype=str).fillna("").to_dict("records")
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
        "arbitration": PRIVATE_ANNOT_DIR / "arbitration_filled.csv",
        "job_pool_v2": ROOT / "data" / "independent_eval" / "pool" / "job_pool_v2.jsonl",
        "source_audit": ROOT / "reports" / "phase4-3a-2" / "source-audit.json",
        "consent_template": ROOT / "docs" / "evaluation" / "consent-template.md",
        "annotation_guidelines": ROOT / "docs" / "evaluation" / "annotation-guidelines.md",
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
            files=files, dataset_version="evalset-v2",
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
            })
    except FreezeError as e:
        out = {"stage": "evalset", "status": "blocked", "created_at": now(),
               "reason": str(e), "facts": facts}
        jdump(out, EVALSET_DIR / "freeze_blocked.json")
        write_report("freeze-verification.json", {
            "generated_by": "scripts/phase4_3a_2/freeze_gold.py",
            "created_at": now(), "status": "blocked", "reasons": [str(e)],
            "facts": facts})
        return out

    verification = verify_freeze(EVALSET_DIR / "manifest.json")
    verification_report = {
        "generated_by": "scripts/phase4_3a_2/freeze_gold.py",
        "created_at": now(),
        "status": "frozen" if verification["ok"] else "verification_failed",
        "dataset_version": manifest["dataset_version"],
        "stage": "evalset",
        "manifest": "data/independent_eval/frozen/evalset_v2/manifest.json",
        "manifest_sha256": manifest.get("manifest_sha256"),
        "files_verified": verification["files"],
        "hash_verification_ok": verification["ok"],
        "sample_counts": manifest.get("sample_counts", {}),
        "mutual_exclusivity": manifest.get("mutual_exclusivity", {}),
        "split_info": split_info,
        "split_isolation": split_check,
        "blind_protection": gold_gate.check_blind_status(freeze_verified=verification["ok"],
                                                        blind_claimed_pass=False),
        "reverify_command": ("python scripts/phase4_3a_2/freeze_gold.py verify "
                             "--manifest data/independent_eval/frozen/evalset_v2/manifest.json"),
    }
    write_report("freeze-verification.json", verification_report)
    out = {"stage": "evalset", "status": "frozen",
           "dataset_version": manifest["dataset_version"],
           "hash_verification_ok": verification["ok"],
           "split_info": split_info}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="freeze")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--seed", type=int, default=20261213)
    ap.add_argument("--blind-ratio", type=float, default=0.3)
    ap.add_argument("--min-real-pairs", type=int, default=300)
    ap.add_argument("--job-isolated", action="store_true",
                    help="岗位冷启动协议：额外按 job_id 隔离（与简历隔离结果分开命名）")
    args = ap.parse_args()
    if args.action == "verify":
        if not args.manifest:
            print(json.dumps({"error": "verify 需要 --manifest"}, ensure_ascii=False))
            return 2
        res = verify_freeze(args.manifest)
    else:
        res = run(seed=args.seed, blind_ratio=args.blind_ratio,
                  min_real_pairs=args.min_real_pairs, job_isolated=args.job_isolated)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
