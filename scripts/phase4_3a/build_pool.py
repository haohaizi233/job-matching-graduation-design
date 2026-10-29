# -*- coding: utf-8 -*-
"""候选样本池构建 CLI（任务书第六节 A）。

产出（data/independent_eval/）：
  pool/job_pool_v1.jsonl            中文岗位候选池（去重 + 分层采样）
  pairs/pairs_v1.jsonl              真实简历-岗位配对（当前依赖简历导入，可能为空）
  pairs/pairs_synthetic_v1.jsonl    合成测试池（is_synthetic=true，永不进人工真值）
  annotation/templates/*.csv        双人标注模板 + 仲裁模板
  pool/pool_manifest_v1.json        抽样策略、覆盖度、来源与哈希清单
  frozen/pool_v1/manifest.json      候选池冻结清单（stage=pool）

用法：
  python scripts/phase4_3a/build_pool.py [--jobs 150] [--seed 20261210]
      [--synthetic 8] [--resumes <csv>] [--allow-all-df]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    ANNOTATOR_A, ANNOTATOR_B, ANNOT_DIR, EVAL_DATA_DIR, FROZEN_DIR, PAIRS_DIR,
    POOL_DIR, TEMPLATE_DIR, file_record, now, write_jsonl,
)

from job_matching.annotation import pool as pool_mod  # noqa: E402
from job_matching.annotation.arbitration import write_annotations_template  # noqa: E402
from job_matching.annotation.freeze import freeze_dataset  # noqa: E402
from job_matching.annotation.schema import ARBITRATION_FIELDS, PROTOCOL_VERSION  # noqa: E402
from job_matching.core import ROOT, dataset_version as make_dataset_version, ensure_dir  # noqa: E402

RESUME_IMPORT_CANDIDATES = (
    "data/independent_eval/resume_pool/resumes.csv",
)


def _dataset_version_for_sources(sources: list[str]) -> str:
    hashes = {}
    for rel_path in sources:
        p = ROOT / rel_path
        if p.exists():
            from job_matching.core import sha256_file
            hashes[rel_path] = sha256_file(p)
    return make_dataset_version(hashes) if hashes else "dv-empty"


def load_real_resumes(resume_file: str | None) -> tuple[list[dict], dict]:
    if resume_file:
        return pool_mod.load_resume_file(ROOT / resume_file, source_name=Path(resume_file).stem)
    for cand in RESUME_IMPORT_CANDIDATES:
        p = ROOT / cand
        if p.exists():
            return pool_mod.load_resume_file(p, source_name=Path(cand).stem)
    return [], {"source": None, "rows": 0,
                "note": "未找到经授权的中文简历导入文件（data/independent_eval/resume_pool/resumes.csv）"}


def run(jobs: int = 150, seed: int = 20261210, synthetic: int = 8,
        resume_file: str | None = None, allow_all_df: bool = False) -> dict:
    ensure_dir(POOL_DIR)
    ensure_dir(PAIRS_DIR)
    ensure_dir(TEMPLATE_DIR)

    job_pool, job_stats = pool_mod.build_job_pool(n_target=jobs, seed=seed,
                                                  allow_all_df=allow_all_df)
    job_file = POOL_DIR / "job_pool_v1.jsonl"
    write_jsonl(job_pool, job_file)

    real_resumes, resume_info = load_real_resumes(resume_file)
    syn_resumes = pool_mod.make_synthetic_resumes(n=synthetic, seed=seed) if synthetic else []

    real_pairs, real_stats = pool_mod.build_pairs(real_resumes, job_pool, seed=seed) \
        if real_resumes else ([], {"pairs_built": 0, "tier_counts": {},
                                   "note": "无真实中文简历 -> 真实配对数 0（数据缺口）"})
    syn_pairs, syn_stats = pool_mod.build_pairs(syn_resumes, job_pool, seed=seed + 1) \
        if syn_resumes else ([], {"pairs_built": 0, "tier_counts": {}})

    dv = _dataset_version_for_sources([
        "data/raw/job-education/annotated/2w_0716_eval.csv",
        "data/raw/job-education/default/test/2w_0716.csv",
    ])
    for p in real_pairs + syn_pairs:
        p["dataset_version"] = dv

    real_file = PAIRS_DIR / "pairs_v1.jsonl"
    syn_file = PAIRS_DIR / "pairs_synthetic_v1.jsonl"
    pool_mod.write_pool(real_pairs, real_file)
    pool_mod.write_pool(syn_pairs, syn_file)

    # 模板：覆盖当前配对池（真实 + 合成），冻结门禁会阻止合成样本进入人工真值
    all_pair_ids = [p["pair_id"] for p in real_pairs + syn_pairs]
    tpl_a = write_annotations_template(ANNOTATOR_A, all_pair_ids,
                                       TEMPLATE_DIR / "annotations_A.csv", PROTOCOL_VERSION)
    tpl_b = write_annotations_template(ANNOTATOR_B, all_pair_ids,
                                       TEMPLATE_DIR / "annotations_B.csv", PROTOCOL_VERSION)
    arb_tpl = TEMPLATE_DIR / "arbitration.csv"
    import pandas as pd
    pd.DataFrame([], columns=list(ARBITRATION_FIELDS)).to_csv(
        arb_tpl, index=False, encoding="utf-8", lineterminator="\n")

    coverage = pool_mod.coverage_report(real_pairs + syn_pairs, job_stats, {
        "tier_counts": _merge_tiers(real_stats, syn_stats)})
    files = {
        "job_pool": file_record(job_file),
        "pairs_real": file_record(real_file),
        "pairs_synthetic": file_record(syn_file),
        "template_annotations_a": file_record(tpl_a),
        "template_annotations_b": file_record(tpl_b),
        "template_arbitration": file_record(arb_tpl),
    }
    manifest = pool_mod.pool_manifest(real_pairs + syn_pairs, job_stats, {
        "real": real_stats, "synthetic": syn_stats, "resume_import": resume_info,
    }, coverage, files, dv)
    manifest["created_at"] = now()
    manifest["synthetic_policy"] = ("is_synthetic=true / eligible_for_gold=false；"
                                    "合成样本只用于验证标注-评估流水线，绝不冒充人工真值")
    from job_matching.core import jdump
    manifest_file = POOL_DIR / "pool_manifest_v1.json"
    jdump(manifest, manifest_file)

    frozen = freeze_dataset(
        stage="pool", out_dir=FROZEN_DIR / "pool_v1", pairs_file=real_file,
        files={"pairs": real_file, "pairs_synthetic": syn_file, "job_pool": job_file,
               "pool_manifest": manifest_file},
        dataset_version=dv, source_stats=job_stats,
        label_distribution={"unlabeled": len(real_pairs) + len(syn_pairs)},
        responsibility={"data_sources": job_stats.get("license_status"),
                        "annotation_status": "pending",
                        "note": "候选池冻结不含人工标签；正式评估集冻结需 G2 条件"},
        extra={"pool_manifest": str(manifest_file.relative_to(ROOT)).replace("\\", "/")})

    return {
        "job_pool": {"file": str(job_file.relative_to(ROOT)), "jobs": len(job_pool),
                     "stats": job_stats},
        "pairs_real": {"file": str(real_file.relative_to(ROOT)), "pairs": len(real_pairs),
                       "stats": real_stats},
        "pairs_synthetic": {"file": str(syn_file.relative_to(ROOT)), "pairs": len(syn_pairs),
                            "stats": syn_stats},
        "templates": [str(tpl_a.relative_to(ROOT)), str(tpl_b.relative_to(ROOT)),
                      str(arb_tpl.relative_to(ROOT))],
        "dataset_version": dv,
        "coverage": coverage,
        "pool_freeze": {"stage": frozen["stage"], "dataset_version": frozen["dataset_version"],
                        "manifest": str((FROZEN_DIR / 'pool_v1' / 'manifest.json').relative_to(ROOT))},
    }


def _merge_tiers(a: dict, b: dict) -> dict:
    out = {}
    for src in (a.get("tier_counts", {}), b.get("tier_counts", {})):
        for k, v in src.items():
            out[k] = out.get(k, 0) + int(v)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261210)
    ap.add_argument("--synthetic", type=int, default=8)
    ap.add_argument("--resumes", type=str, default=None)
    ap.add_argument("--allow-all-df", action="store_true")
    args = ap.parse_args()
    result = run(jobs=args.jobs, seed=args.seed, synthetic=args.synthetic,
                 resume_file=args.resumes, allow_all_df=args.allow_all_df)
    print(json.dumps({k: v for k, v in result.items() if k != "coverage"},
                     ensure_ascii=False, indent=2))
