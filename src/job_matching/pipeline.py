# -*- coding: utf-8 -*-
"""第三阶段数据流水线编排。

步骤（run_all.py 按序执行，任一关键步骤失败立即停止）：
  1. check_raw_integrity   原始数据哈希基线核对（G1 前置）
  2. validate_schema       四个 Schema 的实际校验
  3. normalize_data        简历 / 岗位 / 学历 / 风险表规范化
  4. build_embeddings      768 维向量缓存 + 数值一致性校验
  5. build_features        pair 特征 + 目标/输入物理隔离 + 泄漏审计
  6. build_splits          三种匹配协议 + 学历重新划分
  7. run_baselines         零训练 Baseline（匹配 + 学历）
  8. run_gates             数据质量门禁 G1-G7
  9. write_reports         报告生成
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import core
from .core import (PIPELINE_VERSION, ROOT, RunContext, dataset_version, get_logger,
                   jdump, rel, sha256_file)
from .config import get_config
from .schema import (EDUCATION_SCHEMA, JOB_SCHEMA, MATCH_SCHEMA, RESUME_SCHEMA,
                     validate_frame)

RAW_HASH_BASELINE = {
    "data/raw/job-resume-matching/cv.csv":
        "67c81a4761516113dbebcd8c6acc1b692c4b20e54341187ff864d2d637099640",
    "data/raw/job-resume-matching/job.csv":
        "301a382ebec72d574817cc3d4b9ee34cf08e7f8ecdfa3d373142767fe4f9f789",
    "data/raw/job-resume-matching/matches.csv":
        "4ae60b5b134146235148557268c5e04f1fc5e7579b73c4ab59cb01073bce3338",
    "data/raw/other/all_df.csv/all_df.csv":
        "1375b216c20743f571ff8bd9ff654f5cfe82dd0304f0b3d763ecc62acb41ef5f",
    "data/raw/job-education/default/train/19w_0701.csv":
        "c9daaed533f8aa72600ad24c9f4ef3227f2a42bacc63dfeac4418ec04d41d98a",
    "data/raw/job-education/default/validation/4w_0708.csv":
        "f5b7c9b056e804d28076359da8d04b189f24b0da323e8c2bbf12704714295829",
    "data/raw/job-education/default/test/2w_0716.csv":
        "8a3be09a319a5b644b482054773252efbbc664852582d33c53cbf7b1cbeea39c",
    "data/raw/job-education/annotated/2w_0716_eval.csv":
        "b831ff788c44d86fdc28f4675593be5e9c0ab3cb5ee39a5a6aa0fc4feec437f2",
}


# ================================================================ 1. 原始完整性
def step_check_raw_integrity() -> dict:
    log = get_logger()
    cfg = get_config()
    rows = []
    all_ok = True
    for rel_path, expect in RAW_HASH_BASELINE.items():
        p = ROOT / rel_path
        actual = sha256_file(p)
        ok = actual == expect
        all_ok = all_ok and ok
        rows.append({"path": rel_path, "expected": expect, "actual": actual,
                     "bytes": p.stat().st_size, "ok": ok})
        log.info("[G1] %s %s", "OK " if ok else "FAIL", rel_path)
    if not all_ok:
        raise RuntimeError("原始数据哈希与第二阶段基线不一致，必须立即停止")
    return {"ok": True, "files": rows,
            "dataset_version": dataset_version({r["path"]: r["actual"] for r in rows})}


# ================================================================ 2. Schema 校验
def _validate_csv_chunked(path: Path, schema, chunksize: int = 20000,
                          usecols=None) -> dict:
    agg: dict = {"schema": schema.name, "path": rel(path), "chunks": 0,
                 "rows": 0, "issues": [], "ok": True}
    counter: dict[tuple, dict] = {}
    first_chunk_meta = None
    for chunk in pd.read_csv(path, chunksize=chunksize, encoding="utf-8-sig",
                             low_memory=False, usecols=usecols):
        res = validate_frame(chunk, schema, check_values=True)
        if first_chunk_meta is None:
            first_chunk_meta = res
        agg["chunks"] += 1
        agg["rows"] += res["rows"]
        for iss in res["issues"]:
            key = (iss.get("code"), iss.get("field"), json.dumps(iss.get("values"), ensure_ascii=False)
                   if iss.get("values") is not None else "")
            if key not in counter:
                counter[key] = dict(iss)
                counter[key]["count"] = int(iss.get("count", 0) or 0)
            else:
                counter[key]["count"] += int(iss.get("count", 0) or 0)
    agg["issues"] = list(counter.values())
    agg["hard_issue_count"] = sum(1 for i in agg["issues"]
                                 if i.get("severity") != "warn")
    agg["ok"] = agg["hard_issue_count"] == 0
    agg["columns"] = first_chunk_meta and sorted(
        set(pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns))
    return agg


def step_validate_schema() -> dict:
    cfg = get_config()
    log = get_logger()
    from .schema import EDUCATION_EXPECTED_COLUMNS
    out = {"generated_by": "step_validate_schema", "checks": []}

    specs = [
        (cfg.src("matching", "cv"), RESUME_SCHEMA, None),
        (cfg.src("matching", "job"), JOB_SCHEMA, None),
        (cfg.src("matching", "matches"), MATCH_SCHEMA, None),
        (cfg.src("education", "train"), EDUCATION_SCHEMA, "default"),
        (cfg.src("education", "validation"), EDUCATION_SCHEMA, "default"),
        (cfg.src("education", "test"), EDUCATION_SCHEMA, "default"),
        (cfg.src("education", "annotated"), EDUCATION_SCHEMA, "annotated"),
    ]
    for path, schema, variant in specs:
        res = _validate_csv_chunked(path, schema, cfg.csv_chunk_rows)
        if variant:
            expect = set(EDUCATION_EXPECTED_COLUMNS[variant])
            actual = set(res.get("columns") or [])
            res["variant"] = variant
            res["column_set_ok"] = (actual == expect)
            if actual != expect:
                res["issues"].append({
                    "code": "COLUMN_SET_MISMATCH", "severity": "warn",
                    "missing": sorted(expect - actual), "extra": sorted(actual - expect)})
        out["checks"].append(res)
        log.info("[Schema] %s (%s%s): rows=%d hard_issues=%d ok=%s",
                 rel(path), schema.name,
                 f"/{variant}" if variant else "", res["rows"],
                 res["hard_issue_count"], res["ok"])
    out["ok"] = all(c["ok"] for c in out["checks"])
    out["column_set_ok"] = all(c.get("column_set_ok", True) for c in out["checks"])
    jdump(out, get_config().path("reports") / "phase3-schema-validation.json")
    return out


# ================================================================ 3. 规范化
def step_normalize_data() -> dict:
    from .education_data import build_education_table
    from .preprocess_job import normalize_job
    from .preprocess_resume import normalize_resume
    from .preprocess_risk import normalize_risk

    cfg = get_config()
    log = get_logger()
    summary: dict = {"generated_by": "step_normalize_data",
                     "pipeline_version": PIPELINE_VERSION}

    # 简历
    r_df, r_stats = normalize_resume(cfg.src("matching", "cv"))
    p = cfg.out("interim_matching") / "resume_normalized.csv"
    core.write_csv(r_df, p, cfg.float_format)
    summary["resume"] = {**r_stats, "output": rel(p), "sha256": sha256_file(p),
                         "bytes": p.stat().st_size}
    log.info("[规范化] 简历 %d 行 -> %s", len(r_df), rel(p))

    # 岗位
    j_df, j_stats = normalize_job(cfg.src("matching", "job"))
    p = cfg.out("interim_matching") / "job_normalized.csv"
    core.write_csv(j_df, p, cfg.float_format)
    summary["job"] = {**j_stats, "output": rel(p), "sha256": sha256_file(p),
                      "bytes": p.stat().st_size}
    log.info("[规范化] 岗位 %d 行 -> %s", len(j_df), rel(p))

    # 学历
    e_df, e_stats = build_education_table(cfg)
    p = cfg.out("interim_education") / "education_normalized.csv"
    core.write_csv(e_df, p, cfg.float_format)
    summary["education"] = {**e_stats, "output": rel(p), "sha256": sha256_file(p),
                            "bytes": p.stat().st_size,
                            "label_status_counts": e_df["label_status"].value_counts().to_dict(),
                            "label_token_counts": _token_counts(e_df)}
    log.info("[规范化] 学历 %d 行 -> %s", len(e_df), rel(p))

    # 风险
    k_df, k_stats = normalize_risk(cfg.src("risk", "all_df"))
    p = cfg.out("interim_risk") / "risk_normalized.csv"
    core.write_csv(k_df, p, cfg.float_format)
    summary["risk"] = {**k_stats, "output": rel(p), "sha256": sha256_file(p),
                       "bytes": p.stat().st_size}
    log.info("[规范化] 风险 %d 行 -> %s", len(k_df), rel(p))

    summary["dataset_version"] = _dataset_version_now()
    jdump(summary, cfg.path("reports") / "phase3-preprocessing-summary.json")
    return summary


def _token_counts(e_df: pd.DataFrame) -> dict:
    from .preprocess_education import normalize_label
    counts: dict[str, int] = {}
    for raw in e_df["label_raw"].astype(str):
        for t in normalize_label(raw)["tokens"]:
            counts[t] = counts.get(t, 0) + 1
    return counts


def _dataset_version_now() -> str:
    return dataset_version({k: v for k, v in RAW_HASH_BASELINE.items()})


# ================================================================ 4. Embedding
def step_build_embeddings() -> dict:
    from .embeddings import build_embedding_cache, verify_embedding_cache
    cfg = get_config()
    out_dir = cfg.out("processed_embeddings")
    meta = build_embedding_cache(cfg.src("matching", "cv"), cfg.src("matching", "job"),
                                 out_dir, _dataset_version_now())
    ver = verify_embedding_cache(out_dir, cfg.src("matching", "cv"),
                                 cfg.src("matching", "job"))
    meta["verification"] = ver
    if not ver["ok"]:
        raise RuntimeError(f"Embedding 缓存数值一致性校验失败: {ver}")
    jdump(meta, out_dir / "metadata.json")
    return meta


# ================================================================ 5. 特征
def step_build_features() -> dict:
    from .pair_features import (NUMERIC_FEATURE_COLUMNS, build_pair_features,
                                numeric_matrix)
    from .policy import audit_feature_set, check_feature_columns

    cfg = get_config()
    log = get_logger()

    resume = pd.read_csv(cfg.out("interim_matching") / "resume_normalized.csv",
                         encoding="utf-8", low_memory=False)
    job = pd.read_csv(cfg.out("interim_matching") / "job_normalized.csv",
                      encoding="utf-8", low_memory=False)
    matches = pd.read_csv(cfg.src("matching", "matches"), encoding="utf-8-sig",
                          low_memory=False)
    matches["pair_index"] = np.arange(len(matches), dtype=np.int64)

    feats, fstats = build_pair_features(matches, resume, job)

    # ---- 目标与输入物理隔离
    targets = matches[["pair_index", "candidate_id", "job_id", "label_strength",
                       "final_score", "candidate_rank", "candidate_rank_pct"]].copy()
    targets["candidate_id"] = targets["candidate_id"].astype(str)
    targets["label_ordinal"] = targets["label_strength"].map(
        {"weak_positive": 1, "medium_positive": 2, "strong_positive": 3}).astype("int64")
    targets["relevance_role"] = "proxy_relevance（原评分系统派生，非真实录用结果）"

    feat_cols = [c for c in feats.columns if c not in ("candidate_id", "job_id")]
    check_feature_columns("match_label_strength", feat_cols)

    fpath = cfg.out("processed_matching") / "features_pairs.csv"
    tpath = cfg.out("processed_matching") / "targets_pairs.csv"
    core.write_csv(feats, fpath, cfg.float_format)
    core.write_csv(targets, tpath, cfg.float_format)

    # ---- 数值特征矩阵 + 泄漏审计
    X, names = numeric_matrix(feats)
    np.savez(cfg.out("processed_matching") / "feature_matrix_match_label_strength.npz",
             X=X, feature_names=np.array(names, dtype=object))
    reference = {
        c: matches[c].to_numpy(dtype=np.float64)
        for c in cfg.derived_score_chain() if c in matches.columns
    }
    audit = audit_feature_set("match_label_strength", feats[feat_cols], reference,
                              raise_on_violation=False)

    # ---- 学历输入 / 标签物理隔离
    edu = pd.read_csv(cfg.out("interim_education") / "education_normalized.csv",
                      encoding="utf-8", low_memory=False)
    e_in = edu[["record_key", "user_hash", "job_title_norm", "slot_education_norm",
                "slot_present", "user_len"]].copy()
    e_lab = edu[["record_key", "label_tokens_json", "label_multi_hot", "label_status",
                 "unresolved_tokens_json", "label_provenance", "is_gold"]].copy()
    ipath = cfg.out("processed_education") / "education_inputs.csv"
    lpath = cfg.out("processed_education") / "education_labels.csv"
    core.write_csv(e_in, ipath, cfg.float_format)
    core.write_csv(e_lab, lpath, cfg.float_format)

    # 学历任务特征列同样过策略检查（键列 record_key / user_hash 仅作关联与文本摘要）
    e_key_cols = ["record_key", "user_hash"]
    e_feat_cols = [c for c in e_in.columns if c not in e_key_cols]
    e_check = check_feature_columns("edu_label_multilabel", e_feat_cols,
                                    raise_on_violation=True)

    schema_doc = {
        "generated_by": "step_build_features",
        "task": "match_label_strength",
        "numeric_feature_columns": NUMERIC_FEATURE_COLUMNS,
        "all_feature_columns": feat_cols,
        "target_file": rel(tpath),
        "target_columns": ["label_strength", "label_ordinal"],
        "relevance_columns": ["final_score", "candidate_rank", "candidate_rank_pct"],
        "features_file": rel(fpath),
        "matrix_file": rel(cfg.out("processed_matching") / "feature_matrix_match_label_strength.npz"),
        "matrix_shape": list(X.shape),
        "education_inputs_file": rel(ipath),
        "education_labels_file": rel(lpath),
        "education_target_columns": ["label_tokens_json", "label_multi_hot"],
        "education_feature_columns": e_feat_cols,
        "education_key_columns": e_key_cols,
        "forbidden_features": cfg.task("match_label_strength")["forbidden_features"],
        "uncertain_features": cfg.task("match_label_strength")["uncertain_features"],
        "indirect_leakage_rules": cfg.policy["indirect_leakage_rules"],
    }
    jdump(schema_doc, cfg.out("processed_matching") / "feature_schema.json")

    out = {
        "pair_features": fstats,
        "outputs": {
            "features_pairs": rel(fpath), "targets_pairs": rel(tpath),
            "feature_matrix": rel(cfg.out("processed_matching") /
                                  "feature_matrix_match_label_strength.npz"),
            "education_inputs": rel(ipath), "education_labels": rel(lpath),
        },
        "policy_audit": audit.to_dict(),
        "education_policy_check": e_check.to_dict(),
        "matrix_shape": list(X.shape),
    }
    jdump(out, cfg.path("reports") / "phase3-feature-build.json")
    log.info("[特征] pair 特征 %d 行 × %d 数值特征；泄漏审计 ok=%s，间接泄漏发现 %d 条",
             len(feats), len(names), audit.ok, len(audit.indirect_findings))
    return out


# ================================================================ 6. 切分
def step_build_splits() -> dict:
    from .education_data import build_education_splits, save_education_splits
    from .split_matching import build_all_protocols

    cfg = get_config()
    log = get_logger()
    matches = pd.read_csv(cfg.src("matching", "matches"), encoding="utf-8-sig",
                          low_memory=False)
    m = build_all_protocols(matches, cfg)

    edu = pd.read_csv(cfg.out("interim_education") / "education_normalized.csv",
                      encoding="utf-8", low_memory=False)
    manifest, excluded, dev, gold = build_education_splits(edu, cfg)
    saved = save_education_splits(manifest, excluded, dev, gold,
                                  cfg.out("splits_education"))
    out = {"matching": {k: v["manifest"] for k, v in m.items()},
           "education": saved["manifest"]}
    jdump(out, cfg.path("reports") / "phase3-split-summary.json")
    log.info("[切分] 匹配三协议 + 学历重划分完成")
    return out


# ================================================================ 7. Baseline
def step_run_baselines() -> dict:
    from .baseline_education import run_education_baselines
    from .baseline_ranking import run_matching_baselines

    cfg = get_config()
    log = get_logger()
    result: dict = {
        "generated_by": "step_run_baselines",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pipeline_version": PIPELINE_VERSION,
        "dataset_version": _dataset_version_now(),
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "torch": _torch_version(),
            "device_policy": "Baseline 全部使用 CPU 分块计算，不占用 GPU 显存",
        },
    }

    matches = pd.read_csv(cfg.src("matching", "matches"), encoding="utf-8-sig",
                          low_memory=False)
    matches["candidate_id"] = matches["candidate_id"].astype(str)
    matches["job_id"] = matches["job_id"].astype("int64")

    feats = pd.read_csv(cfg.out("processed_matching") / "features_pairs.csv",
                        encoding="utf-8", low_memory=False)

    emb_dir = cfg.out("processed_embeddings")
    cv_emb = np.load(emb_dir / "cv_embeddings.npy")
    job_emb = np.load(emb_dir / "job_embeddings.npy")
    cv_map = core.jload(emb_dir / "cv_id_map.json")["id_to_row"]
    job_map = core.jload(emb_dir / "job_id_map.json")["id_to_row"]
    from .baseline_ranking import cosine_scores
    cv_rows = np.array([cv_map[c] for c in matches["candidate_id"]], dtype=np.int64)
    job_rows = np.array([job_map[str(j)] for j in matches["job_id"]], dtype=np.int64)
    emb_scores = cosine_scores(cv_emb, job_emb, cv_rows, job_rows,
                               cfg.cosine_block_rows)

    matching = {}
    for proto in ("candidate_cold", "job_cold", "double_cold"):
        sdir = cfg.out("splits_matching") / proto
        parts = []
        for s in ("train", "validation", "test"):
            f = sdir / f"{s}.csv"
            d = pd.read_csv(f, encoding="utf-8")
            d["split"] = s
            parts.append(d)
        idx = pd.concat(parts, ignore_index=True)
        pairs = matches.merge(idx[["pair_index", "split"]], on="pair_index",
                              how="inner", validate="one_to_one")
        matching[proto] = run_matching_baselines(pairs, feats, emb_scores, proto)
    result["matching"] = matching

    # ---- 学历基线
    edu = pd.read_csv(cfg.out("interim_education") / "education_normalized.csv",
                      encoding="utf-8", low_memory=False)
    sdir = cfg.out("splits_education")
    tr_keys = set(pd.read_csv(sdir / "train.csv", encoding="utf-8")["record_key"].astype(str))
    va_keys = set(pd.read_csv(sdir / "validation.csv", encoding="utf-8")["record_key"].astype(str))
    go_keys = set(pd.read_csv(sdir / "gold_holdout.csv", encoding="utf-8")["record_key"].astype(str))
    dev_train = edu[edu["record_key"].astype(str).isin(tr_keys)]
    dev_val = edu[edu["record_key"].astype(str).isin(va_keys)]
    gold = edu[edu["record_key"].astype(str).isin(go_keys)]
    result["education"] = run_education_baselines(
        dev_train, dev_val, gold, result["dataset_version"])

    out_path = cfg.path("reports") / "baselines" / "baseline-results.json"
    jdump(result, out_path)
    log.info("[baseline] 结果已写出 %s", rel(out_path))
    return result


def _torch_version() -> str:
    try:
        import torch
        return torch.__version__
    except Exception:
        return "unavailable"


# ================================================================ 8. 门禁
def step_check_dependencies() -> dict:
    """依赖完整性（验收项 P3-13）：运行 pip check 并落盘证据。"""
    log = get_logger()
    proc = subprocess.run([sys.executable, "-m", "pip", "check"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT))
    out = {
        "generated_by": "step_check_dependencies",
        "command": f"{sys.executable} -m pip check",
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "ok": proc.returncode == 0,
    }
    jdump(out, ROOT / "reports" / "dependency-check.json")
    log.info("[依赖] pip check 退出码 %d：%s", proc.returncode,
             (proc.stdout or "").strip().replace("\n", " | ")[:300])
    return out


def step_run_gates() -> dict:
    log = get_logger()
    step_check_dependencies()
    test_dir = ROOT / "tests" / "data_pipeline"
    proc = subprocess.run([sys.executable, str(test_dir / "run_all.py")],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT))
    out_path = ROOT / "reports" / "data-quality-gates.json"
    result = core.jload(out_path) if out_path.exists() else {}
    result["console_output"] = (proc.stdout or "")[-12000:]
    result["returncode"] = proc.returncode
    jdump(result, out_path)
    log.info("[门禁] 测试退出码 %d", proc.returncode)
    if proc.returncode != 0:
        raise RuntimeError(f"数据质量门禁未通过（退出码 {proc.returncode}）")
    return result


# ================================================================ 9. 报告
def step_write_reports() -> dict:
    from .reporting import render_all
    return render_all()
