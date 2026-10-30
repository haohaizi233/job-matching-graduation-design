# -*- coding: utf-8 -*-
"""消融实验 / 统计分析 / 资源基准（Phase4-3B / M5-8.3, 8.4, 8.5）。

结论边界：
  * 数据仍是合成中文研究集（8 个查询组），样本量极小；
    Bootstrap 置信区间只是**方向性**参考，统计功效极低，不得当作显著性证明。
  * 重采样单位 = 查询组（简历），与评价单位一致，不把相关的人岗 pair 当独立样本。
  * 消融只移除单个组件、其余条件保持一致；组件不存在或数据不支持时登记 NOT_RUN。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("JM_ROOT", r"D:\desktop\job-matching-model-research"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "phase4_3b"))

from run_research_experiments import (  # noqa: E402
    ResearchSet, load_pairs, evaluate_task_a, evaluate_task_b,
    skill_set, _edu_tokens, _years_min, _to_float, jdump, sha256_file, PAIRS_FILE,
    LABEL_SOURCE)

OUT_ROOT = ROOT / "reports/model-research"
SEED = 20261031
N_BOOT = 2000


# ---------------------------------------------------------------- 融合打分器
def build_full_scorer(rs: ResearchSet, *, use_semantic: bool = True,
                      use_skill: bool = True, use_education: bool = True,
                      use_experience: bool = True, use_intent: bool = True,
                      use_reranker: bool = True, recall_backend: str = "bge"):
    """完整两阶段打分器，可按开关移除单个组件做消融。"""
    from job_matching.models.text_encoder import BgeEncoder, HashNgramEncoder
    from job_matching.models.retrieval import EmbeddingRecall, BM25Recall
    from job_matching.models.reranker import build_reranker
    from job_matching.models.fusion import FeatureFusion, FusionConfig, DEFAULT_WEIGHTS

    job_docs = [rs.job_doc(j) for j in rs.job_ids]
    resume_docs = [rs.resume_doc(r) for r in rs.resume_ids]

    if recall_backend == "bge":
        enc = BgeEncoder(device="cpu", max_length=256, batch_size=16, local_files_only=True)
    else:
        enc = HashNgramEncoder(dim=512)
    recall = EmbeddingRecall(enc)
    recall.build(job_docs)
    recall_fallback = BM25Recall()
    recall_fallback.build(job_docs)

    if use_reranker:
        try:
            reranker = build_reranker("bge_reranker_base", device="cpu",
                                      local_files_only=True, max_length=256)
        except Exception:  # noqa: BLE001
            reranker = build_reranker("lexical")
    else:
        reranker = build_reranker("lexical")

    w = dict(DEFAULT_WEIGHTS)
    dropped = []
    if not use_semantic:
        w["semantic"] = 0.0
        dropped.append("semantic")
    if not use_skill:
        w["skill"] = 0.0
        dropped.append("skill")
    if not use_education:
        w["education"] = 0.0
        dropped.append("education")
    if not use_experience:
        w["experience"] = 0.0
        dropped.append("experience")
    if not use_intent:
        w["intent"] = 0.0
        dropped.append("intent")
    if dropped:
        s = sum(w.values())
        if s <= 0:
            raise ValueError("消融后权重全为 0，无法评估")
        w = {k: v / s for k, v in w.items()}

    cfg = FusionConfig(weights=w, hard_education=use_education)
    fusion = FeatureFusion(cfg)

    cache: dict[str, dict[str, float]] = {}
    trunc = {"reranker_truncated_pairs": 0}

    def score(rid: str, jid: str) -> float:
        if rid not in cache:
            qi = rs.resume_ids.index(rid)
            qdoc = resume_docs[qi]
            if use_semantic:
                cands = recall.search([qdoc], top_k=20)[0]
            else:
                cands = recall_fallback.search([qdoc], top_k=20)[0]
            docs = [rs.job_doc(rs.job_ids[d]) for d, _ in cands]
            rr = reranker.score([qdoc] * len(docs), docs) if docs else None
            if rr is not None:
                trunc["reranker_truncated_pairs"] += int(rr.truncated)
                raw = rr.scores
            else:
                raw = np.zeros(len(docs))
            table: dict[str, float] = {}
            for (d, sem), r in zip(cands, raw):
                jj = rs.job_ids[d]
                row_r, row_j = rs.resumes[rid], rs.jobs[jj]
                b = fusion.score(
                    {"education_level": row_r.get("resume_education_level"),
                     "skills": skill_set(row_r.get("resume_skills")),
                     "years_experience": _to_float(row_r.get("resume_years_experience")),
                     "inferred_category": row_r.get("job_category"),
                     "city": row_r.get("city"),
                     "target_position": row_r.get("resume_target_position")},
                    {"skills": skill_set(row_j.get("required_skills")),
                     "education_tokens": _edu_tokens(row_j.get("education_requirement")),
                     "years_min": _years_min(row_j.get("experience_requirement")),
                     "category": row_j.get("job_category"),
                     "city": row_j.get("city"),
                     "job_title": row_j.get("job_title")},
                    semantic_score=(float(sem) if use_semantic else None))
                if use_reranker:
                    val = 0.0 if b.filtered else (0.5 * b.total + 0.5 * float(r))
                else:
                    val = 0.0 if b.filtered else b.total
                table[jj] = float(val)
            cache[rid] = table
        return cache[rid].get(jid, -1e9)

    score.reranker_id = getattr(reranker, "reranker_id", "?")
    score.truncation = trunc
    return score


# ---------------------------------------------------------------- Bootstrap
def per_query_ndcg(rs: ResearchSet, scorer, k: int = 10) -> tuple[list[str], np.ndarray]:
    from job_matching.evaluation.retrieval import ndcg_at_k
    from run_research_experiments import TIER_RELEVANCE
    ids, vals = [], []
    for rid, rows in rs.observed_pairs().items():
        y = np.asarray([TIER_RELEVANCE.get(r.get("difficulty_tier", ""), 0) for r in rows],
                       dtype=np.float64)
        s = np.asarray([scorer(rid, str(r["job_id"])) for r in rows], dtype=np.float64)
        if len(y) < 2 or float(y.sum()) <= 0:
            continue
        ids.append(rid)
        vals.append(ndcg_at_k(y, s, k, "ordinal"))
    return ids, np.asarray(vals, dtype=np.float64)


def paired_bootstrap(ids_a, a: np.ndarray, ids_b, b: np.ndarray,
                     n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    common = [i for i, x in enumerate(ids_a) if x in set(ids_b)]
    if len(common) < 2:
        return {"status": "NOT_RUN", "reason": "可配对查询组不足 2 个"}
    pos_b = {g: i for i, g in enumerate(ids_b)}
    A = np.asarray([a[i] for i in common], dtype=np.float64)
    B = np.asarray([b[pos_b[ids_a[i]]] for i in common], dtype=np.float64)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot, dtype=np.float64)
    n = len(A)
    for r in range(n_boot):
        idx = rng.integers(0, n, size=n)
        diffs[r] = float(np.mean(A[idx] - B[idx]))
    point = float(np.mean(A - B))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    wins = int(np.sum(A > B))
    losses = int(np.sum(A < B))
    return {
        "status": "RUN",
        "unit": "query_group(resume_id)",
        "n_groups": n,
        "point_estimate_mean_diff": point,
        "ci95": [float(lo), float(hi)],
        "bootstrap_repeats": n_boot,
        "seed": seed,
        "groups_a_better": wins,
        "groups_b_better": losses,
        "groups_tied": int(n - wins - losses),
        "power_warning": ("n_groups=%d，统计功效极低；CI 仅方向性参考，"
                          "不得作为显著性结论" % n),
    }


# ---------------------------------------------------------------- 资源基准
def resource_benchmark() -> dict:
    import torch
    from job_matching.models.text_encoder import HashNgramEncoder
    out: dict = {"device_probe": {
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gpu_total_memory_mb": round(
            torch.cuda.get_device_properties(0).total_memory / (1024 ** 2))
        if torch.cuda.is_available() else None,
    }}

    texts = ["负责数据分析与报表开发，熟练使用 Excel、SQL、Python。"] * 64

    tracemalloc.start()
    t0 = time.perf_counter()
    henc = HashNgramEncoder(dim=512)
    out["hash_encoder"] = {
        "load_seconds": round(time.perf_counter() - t0, 4),
        "single_encode_seconds": None,
        "batch64_seconds": None,
    }
    t1 = time.perf_counter()
    henc.encode(texts[:1])
    out["hash_encoder"]["single_encode_seconds"] = round(time.perf_counter() - t1, 5)
    t1 = time.perf_counter()
    henc.encode(texts)
    out["hash_encoder"]["batch64_seconds"] = round(time.perf_counter() - t1, 5)
    out["hash_encoder"]["dim"] = 512

    out["bge_encoder"] = {"status": "NOT_RUN"}
    try:
        from job_matching.models.text_encoder import BgeEncoder
        cur, peak = tracemalloc.get_traced_memory()
        t0 = time.perf_counter()
        bge = BgeEncoder(device="cpu", max_length=256, batch_size=16, local_files_only=True)
        load_s = round(time.perf_counter() - t0, 4)
        bge.encode(texts[:1])
        t1 = time.perf_counter()
        bge.encode(texts[:1])
        single = round(time.perf_counter() - t1, 5)
        t1 = time.perf_counter()
        bge.encode(texts)
        batch = round(time.perf_counter() - t1, 5)
        cur, peak = tracemalloc.get_traced_memory()
        out["bge_encoder"] = {
            "status": "RUN", "load_seconds": load_s,
            "single_encode_seconds": single, "batch64_seconds": batch,
            "throughput_texts_per_sec": round(len(texts) / batch, 2) if batch else None,
            "dim": bge.dim, "device": "cpu",
            "python_peak_memory_mb": round(peak / (1024 ** 2), 2),
            "describe": bge.describe().to_dict(),
        }
    except Exception as e:  # noqa: BLE001
        out["bge_encoder"] = {"status": "NOT_RUN", "error": f"{type(e).__name__}: {e}"}

    out["reranker"] = {"status": "NOT_RUN"}
    try:
        from job_matching.models.reranker import build_reranker
        t0 = time.perf_counter()
        rr = build_reranker("bge_reranker_base", device="cpu",
                            local_files_only=True, max_length=256)
        load_s = round(time.perf_counter() - t0, 4)
        q = ["数据分析岗位"] * 16
        d = ["招聘数据分析师，要求 Excel、SQL"] * 16
        rr.score(q[:1], d[:1])
        t1 = time.perf_counter()
        rr.score(q[:1], d[:1])
        single = round(time.perf_counter() - t1, 5)
        t1 = time.perf_counter()
        rr.score(q, d)
        batch = round(time.perf_counter() - t1, 5)
        out["reranker"] = {
            "status": "RUN", "load_seconds": load_s,
            "single_pair_seconds": single, "batch16_seconds": batch,
            "describe": rr.describe(),
        }
    except Exception as e:  # noqa: BLE001
        out["reranker"] = {"status": "NOT_RUN", "error": f"{type(e).__name__}: {e}"}

    # 端到端（含召回 + 精排 + 融合），不同 Top-K 规模
    try:
        rows = load_pairs()
        rs = ResearchSet(rows)
        from job_matching.models.text_encoder import HashNgramEncoder as H
        from job_matching.models.retrieval import EmbeddingRecall
        job_docs = [rs.job_doc(j) for j in rs.job_ids]
        enc = H(dim=512)
        rec = EmbeddingRecall(enc)
        rec.build(job_docs)
        e2e = {}
        for k in (5, 10, 20, 55):
            t1 = time.perf_counter()
            for rid in rs.resume_ids:
                rec.search([rs.resume_doc(rid)], top_k=k)
            e2e[f"top_{k}"] = round(time.perf_counter() - t1, 4)
        out["end_to_end_recall"] = {
            "status": "RUN", "pool_size": len(job_docs),
            "queries": len(rs.resume_ids), "seconds_by_topk": e2e,
            "note": "仅召回阶段（离线哈希向量），不含预处理/数据库；CPU",
        }
    except Exception as e:  # noqa: BLE001
        out["end_to_end_recall"] = {"status": "NOT_RUN", "error": f"{type(e).__name__}: {e}"}

    tracemalloc.stop()
    return out


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    args = ap.parse_args()

    t0 = time.time()
    rows = load_pairs()
    rs = ResearchSet(rows)
    run_id = f"phase4-3b-ablation-stats-{time.strftime('%Y%m%d-%H%M%S')}"

    variants = {
        "Full": dict(),
        "-SemanticEmbedding": dict(use_semantic=False),
        "-SkillFeatures": dict(use_skill=False),
        "-EducationConstraints": dict(use_education=False),
        "-ExperienceConstraints": dict(use_experience=False),
        "-IntentFeatures": dict(use_intent=False),
        "-CrossEncoderReranking": dict(use_reranker=False),
    }

    per_query: dict[str, tuple[list[str], np.ndarray]] = {}
    results = {}
    for name, kw in variants.items():
        t1 = time.time()
        try:
            sc = build_full_scorer(rs, **kw)
            a = evaluate_task_a(rs, sc)
            b = evaluate_task_b(rs, sc)
            ids, v = per_query_ndcg(rs, sc, k=10)
            per_query[name] = (ids, v)
            results[name] = {
                "status": "RUN", "config": kw, "reranker": sc.reranker_id,
                "truncation": sc.truncation,
                "task_A": a, "task_B": b,
                "per_query_ndcg@10": dict(zip(ids, [float(x) for x in v])),
                "seconds": round(time.time() - t1, 3),
            }
        except Exception as e:  # noqa: BLE001
            results[name] = {"status": "FAILED", "config": kw,
                             "error": f"{type(e).__name__}: {e}"}
        print(f"{name}: {results[name]['status']}")

    stats = {}
    if "Full" in per_query:
        fid, fv = per_query["Full"]
        for name in variants:
            if name == "Full" or name not in per_query:
                continue
            nid, nv = per_query[name]
            stats[f"Full_vs_{name}"] = paired_bootstrap(
                fid, fv, nid, nv, n_boot=args.n_boot)

    multi_seed = {"status": "NOT_RUN",
                  "reason": ("当前评估集为确定性合成夹具（8 个查询组），"
                             "无可训练参数的检索基线本身无随机性；"
                             "多随机种子实验需在真实 Gold 与监督训练数据到位后执行")}

    payload = {
        "meta": {
            "experiment_id": "phase4-3b-ablation-stats-v1",
            "run_id": run_id,
            "git_commit": os.popen(f'git -C "{ROOT}" rev-parse HEAD').read().strip(),
            "dataset_file": str(PAIRS_FILE),
            "dataset_sha256": sha256_file(PAIRS_FILE),
            "label_source": LABEL_SOURCE,
            "gold_status": "BLOCKED — 非正式性能结论",
            "seed": SEED,
            "dependency_versions": {"python": platform.python_version(),
                                    "numpy": np.__version__},
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)),
            "ablation_protocol": "只移除单个组件，其余条件（数据/切分/召回 Top-K/权重归一）保持一致",
        },
        "ablation": results,
        "statistical": {
            "paired_bootstrap_ndcg10": stats,
            "multi_seed": multi_seed,
            "unit": "query_group(resume_id)",
            "caveat": ("重采样单位与评价单位一致（查询组）；"
                       "n_groups=8 时 CI 覆盖极宽，不构成显著性证据"),
        },
        "resources": resource_benchmark(),
    }
    payload["meta"]["end_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["meta"]["total_seconds"] = round(time.time() - t0, 3)

    jdump(payload, ROOT / "reports/phase4-3b/08-ablation-study.json")
    jdump(payload["statistical"], ROOT / "reports/phase4-3b/09-statistical-analysis.json")
    jdump(payload["resources"], ROOT / "reports/phase4-3b/10-resource-benchmark.json")
    jdump(payload, OUT_ROOT / "runs" / f"{run_id}.json")
    print(f"wrote reports/phase4-3b/08-ablation-study.json ({payload['meta']['total_seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
