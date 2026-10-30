# -*- coding: utf-8 -*-
"""中文人岗匹配检索 / 两阶段架构实验矩阵 E00–E07（Phase4-3B / M3-M5）。

数据与结论边界（必须随结果一起引用）：
  * 本脚本只使用 data/independent_eval/pairs/pairs_synthetic_v1.jsonl
    （75 组合成中文配对、8 份合成简历、55 条真实中文 JD，全部 is_synthetic=True、
    eligible_for_gold=False）；
  * 相关性标签来自合成夹具的 difficulty_tier 分层（见 TIER_RELEVANCE），
    属**分析者定义的代理相关性**，不是人工标注，也不是真实投递/录用结果；
  * 该代理相关性部分由技能/类别重合度构造，与技能类基线存在**循环性风险**，
    因此结果只用于「同一口径下的相对可执行性对照」，**不得**写成真实推荐效果；
  * 正式 Gold（H2）当前 BLOCKED，require_gold() 不满足，本脚本不产出正式性能结论。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("JM_ROOT", r"D:\desktop\job-matching-model-research"))
sys.path.insert(0, str(ROOT / "src"))

PAIRS_FILE = ROOT / "data/independent_eval/pairs/pairs_synthetic_v1.jsonl"
OUT_ROOT = ROOT / "reports/model-research"
OUT_REPORT = ROOT / "reports/phase4-3b/06-retrieval-benchmark.json"

# 分析者定义的合成夹具代理相关性（NOT gold）
TIER_RELEVANCE = {
    "high_skill_overlap": 3,
    "medium_skill_overlap": 2,
    "same_direction_diff_duties": 1,
    "hard_requirement_gap": 1,
    "cross_category_negative": 0,
}
LABEL_SOURCE = "synthetic_fixture_tier_proxy"

SEED = 20261031


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    return str(o)


def jdump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_json_default)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pairs() -> list[dict]:
    with open(PAIRS_FILE, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def skill_set(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip().lower() for v in value if str(v).strip()}
    s = str(value).strip()
    if not s:
        return set()
    if s.startswith("["):
        try:
            return {str(v).strip().lower() for v in json.loads(s) if str(v).strip()}
        except Exception:  # noqa: BLE001
            return set()
    return {p.strip().lower() for p in s.replace("；", ";").replace("、", ";").split(";") if p.strip()}


# ---------------------------------------------------------------- 数据视图
class ResearchSet:
    """合成中文研究集：查询组 = 简历；候选 = 岗位池 / 观测配对。"""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.resumes = {r["resume_id"]: r for r in rows}
        self.jobs: dict[str, dict] = {}
        for r in rows:
            self.jobs[str(r["job_id"])] = r
        self.resume_ids = sorted(self.resumes)
        self.job_ids = sorted(self.jobs, key=lambda x: int(x) if x.isdigit() else x)

    def job_doc(self, job_id: str) -> str:
        r = self.jobs[job_id]
        return f"{r.get('job_title') or ''} {r.get('job_text') or ''}"

    def resume_doc(self, resume_id: str) -> str:
        r = self.resumes[resume_id]
        return f"{r.get('resume_target_position') or ''} {r.get('resume_text') or ''}"

    def observed_pairs(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self.rows:
            out.setdefault(r["resume_id"], []).append(r)
        return {k: out[k] for k in sorted(out)}

    def summary(self) -> dict:
        tiers = {}
        for r in self.rows:
            tiers[r.get("difficulty_tier", "?")] = tiers.get(r.get("difficulty_tier", "?"), 0) + 1
        return {
            "pairs": len(self.rows),
            "resumes": len(self.resume_ids),
            "jobs": len(self.job_ids),
            "difficulty_tiers": tiers,
            "is_synthetic_all": all(str(r.get("is_synthetic")) == "True" for r in self.rows),
            "eligible_for_gold_any": any(str(r.get("eligible_for_gold")) == "True" for r in self.rows),
        }


# ---------------------------------------------------------------- 打分器
def score_matrix(scorer, resume_ids: list[str], job_ids: list[str],
                 rs: ResearchSet) -> np.ndarray:
    """scorer(resume_id, job_id) -> float；返回 (n_resume, n_job) 矩阵。"""
    M = np.zeros((len(resume_ids), len(job_ids)), dtype=np.float64)
    for i, rid in enumerate(resume_ids):
        for j, jid in enumerate(job_ids):
            M[i, j] = float(scorer(rid, jid))
    return M


def make_scorers(rs: ResearchSet) -> dict[str, callable]:
    from job_matching.models.text_encoder import HashNgramEncoder
    from job_matching.models.retrieval import BM25Recall, TfidfRecall
    from job_matching.models.fusion import FeatureFusion

    job_docs = [rs.job_doc(j) for j in rs.job_ids]
    resume_docs = [rs.resume_doc(r) for r in rs.resume_ids]

    bm25 = BM25Recall(); bm25.build(job_docs)
    tfidf = TfidfRecall(); tfidf.build(job_docs)

    scorers: dict[str, callable] = {}

    def _by_index(index):
        cache: dict[str, dict[int, float]] = {}

        def f(rid: str, jid: str) -> float:
            if rid not in cache:
                qi = rs.resume_ids.index(rid)
                res = index.search([resume_docs[qi]], top_k=len(rs.job_ids))[0]
                cache[rid] = {d: float(s) for d, s in res}
            return cache[rid].get(rs.job_ids.index(jid), 0.0)
        return f

    scorers["E02_bm25"] = _by_index(bm25)
    scorers["E01_tfidf_char"] = _by_index(tfidf)

    # E03 语义召回：离线哈希向量（可执行基线）
    hash_enc = HashNgramEncoder(dim=512, ngram_range=(2, 4))
    from job_matching.models.retrieval import EmbeddingRecall
    hash_index = EmbeddingRecall(hash_enc)
    hash_index.build(job_docs)
    scorers["E03_embedding_hash"] = _by_index(hash_index)

    # E03b 语义召回：BAAI/bge-small-zh-v1.5（MIT，固定 revision，离线本地权重）
    encoder_status = {}
    bge_index = None
    try:
        from job_matching.models.text_encoder import BgeEncoder
        bge_enc = BgeEncoder(device="cpu", max_length=256, batch_size=16,
                             local_files_only=True)
        bge_index = EmbeddingRecall(bge_enc)
        bge_index.build(job_docs)
        scorers["E03_embedding_bge"] = _by_index(bge_index)
        encoder_status["E03_embedding_bge"] = bge_enc.describe().to_dict()

        def _e04b(rid: str, jid: str) -> float:
            sem = scorers["E03_embedding_bge"](rid, jid)
            return 0.5 * float(sem) + 0.5 * _rule(rid, jid)

        scorers["E04_embedding_bge_plus_rule"] = _e04b
    except Exception as e:  # noqa: BLE001
        encoder_status["E03_embedding_bge"] = {
            "status": "NOT_RUN", "error": f"{type(e).__name__}: {e}"}
    scorers["_encoder_status"] = encoder_status  # 供 main 读取后移除

    # E00 规则融合（人工权重）
    fusion = FeatureFusion()

    def _rule(rid: str, jid: str) -> float:
        row_r = rs.resumes[rid]
        row_j = rs.jobs[jid]
        resume = {
            "education_level": row_r.get("resume_education_level"),
            "skills": skill_set(row_r.get("resume_skills")),
            "years_experience": _to_float(row_r.get("resume_years_experience")),
            "inferred_category": row_r.get("job_category"),
            "city": row_r.get("city"),
            "target_position": row_r.get("resume_target_position"),
        }
        job = {
            "skills": skill_set(row_j.get("required_skills")),
            "education_tokens": _edu_tokens(row_j.get("education_requirement")),
            "years_min": _years_min(row_j.get("experience_requirement")),
            "category": row_j.get("job_category"),
            "city": row_j.get("city"),
            "job_title": row_j.get("job_title"),
        }
        return fusion.score(resume, job).total

    scorers["E00_rule_fusion"] = _rule

    # E04 = 语义 + 规则（人工权重 0.5/0.5）
    def _e04(rid: str, jid: str) -> float:
        sem = scorers["E03_embedding_hash"](rid, jid)
        return 0.5 * float(sem) + 0.5 * _rule(rid, jid)

    scorers["E04_embedding_plus_rule"] = _e04

    # 已训练英文模型（conditional，见 independent_eval.baselines 适用性登记）
    from job_matching.independent_eval.baselines import (
        features_from_pair, resolve_run_dir, TRAINED_MODELS)
    from job_matching.inference.predictor import MatchPredictor
    for name in TRAINED_MODELS:
        rd = resolve_run_dir(name)
        if rd is None:
            continue
        try:
            mp = MatchPredictor(rd, device="cpu")
        except Exception:  # noqa: BLE001
            continue

        def _mk(mp=mp):
            def f(rid: str, jid: str) -> float:
                row_r, row_j = rs.resumes[rid], rs.jobs[jid]
                resume, _ = features_from_pair(dict(row_r))
                _, job = features_from_pair(dict(row_j))
                return float(mp.predict_score(resume, job))
            return f
        scorers[f"E00x_trained_{name}"] = _mk()

    return scorers


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _edu_tokens(raw) -> list[str]:
    if raw is None:
        return []
    s = str(raw).strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
            return list(d.get("tokens") or [])
        except Exception:  # noqa: BLE001
            return []
    return [p for p in s.replace("、", ";").split(";") if p]


def _years_min(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
            v = d.get("years_min")
            return None if v is None else float(v)
        except Exception:  # noqa: BLE001
            return None
    return None


# ---------------------------------------------------------------- 评估
def evaluate_task_a(rs: ResearchSet, scorer) -> dict:
    """任务 A：观测配对内部的组内排序（代理相关性 = difficulty_tier）。"""
    from job_matching.evaluation.retrieval import evaluate_groups, RelevanceSpec
    groups, scores, rels = [], [], []
    for rid, rows in rs.observed_pairs().items():
        for r in rows:
            groups.append(rid)
            scores.append(scorer(rid, str(r["job_id"])))
            rels.append(float(TIER_RELEVANCE.get(r.get("difficulty_tier", ""), 0)))
    spec = RelevanceSpec(kind="graded", relevant_values=("3", "2", "1"),
                         gain_mode="ordinal", label_source=LABEL_SOURCE)
    out = evaluate_groups(np.asarray(groups), np.asarray(scores), np.asarray(rels),
                          ks=(5, 10), spec=spec, min_group_size=2)
    return _strip_groups(out)


def evaluate_task_b(rs: ResearchSet, scorer, ks=(5, 10)) -> dict:
    """任务 B：全岗位池检索（相关 = 夹具中与该简历配对的岗位）。"""
    from job_matching.evaluation.retrieval import evaluate_groups, RelevanceSpec
    observed = {rid: {str(r["job_id"]) for r in rows}
                for rid, rows in rs.observed_pairs().items()}
    groups, scores, rels = [], [], []
    for rid in rs.resume_ids:
        rel_jobs = observed.get(rid, set())
        for jid in rs.job_ids:
            groups.append(rid)
            scores.append(scorer(rid, jid))
            rels.append(1.0 if jid in rel_jobs else 0.0)
    spec = RelevanceSpec(kind="binary", relevant_values=("1",), gain_mode="binary",
                         label_source=LABEL_SOURCE + "+full_pool_retrieval")
    out = evaluate_groups(np.asarray(groups), np.asarray(scores), np.asarray(rels),
                          ks=ks, spec=spec, min_group_size=2)
    return _strip_groups(out)


def _strip_groups(out: dict) -> dict:
    return {"summary": out["summary"],
            "per_group_skipped": {k: v for k, v in out["summary"]["queries_skipped"].items()}}


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoder", default="hash", choices=["hash", "bge"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    t_start = time.time()
    rows = load_pairs()
    rs = ResearchSet(rows)

    experiment_id = "phase4-3b-retrieval-matrix-v1"
    run_id = f"{experiment_id}-{time.strftime('%Y%m%d-%H%M%S')}"

    meta = {
        "experiment_id": experiment_id,
        "run_id": run_id,
        "git_commit": os.popen(f'git -C "{ROOT}" rev-parse HEAD').read().strip(),
        "dataset_version": rows[0].get("dataset_version") if rows else None,
        "dataset_file": str(PAIRS_FILE),
        "dataset_sha256": sha256_file(PAIRS_FILE) if PAIRS_FILE.exists() else None,
        "split_version": "synthetic_fixture_split_pool_only",
        "label_source": LABEL_SOURCE,
        "label_provenance": ("分析者把 difficulty_tier 映射为 0/1/2/3 的分级代理相关性，"
                             "非人工标注、非真实录用结果"),
        "circularity_warning": ("difficulty_tier 由技能/类别重合度分层生成，"
                                "与技能类基线共享构造信号，存在循环性风险"),
        "gold_status": "BLOCKED — H2 真实人工 Gold 未冻结，本结果不得作为正式性能结论",
        "seed": SEED,
        "device": "cpu",
        "dependency_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t_start)),
        "research_set": rs.summary(),
        "task_definitions": {
            "task_A_within_observed_pairs": "组内排序：候选 = 该简历的观测配对，相关性 = tier 分级",
            "task_B_full_pool_retrieval": "全池检索：候选 = 55 条 JD，相关 = 夹具配对过的岗位",
        },
    }

    scorers = make_scorers(rs)
    encoder_status = scorers.pop("_encoder_status", {})
    meta["encoder_status"] = encoder_status
    results = {}
    for name, fn in sorted(scorers.items()):
        t0 = time.time()
        try:
            a = evaluate_task_a(rs, fn)
            b = evaluate_task_b(rs, fn)
            status = "RUN"
            err = None
        except Exception as e:  # noqa: BLE001
            a = b = None
            status = "FAILED"
            err = f"{type(e).__name__}: {e}"
        results[name] = {
            "status": status, "error": err,
            "task_A": a, "task_B": b,
            "seconds": round(time.time() - t0, 3),
        }
        print(f"{name}: {status}")

    # E05/E06 两阶段：召回 Top-K -> 精排
    try:
        from job_matching.models.retrieval import EmbeddingRecall
        from job_matching.models.text_encoder import HashNgramEncoder
        from job_matching.models.reranker import build_reranker
        from job_matching.models.fusion import FeatureFusion
        job_docs = [rs.job_doc(j) for j in rs.job_ids]
        enc = HashNgramEncoder(dim=512)
        recall = EmbeddingRecall(enc); recall.build(job_docs)
        fused = FeatureFusion()
        e05, e06 = {}, {}
        t0 = time.time()
        try:
            reranker = build_reranker("bge_reranker_base", device="cpu",
                                      local_files_only=True, max_length=256)
            rerank_name = reranker.reranker_id
        except Exception as e:  # noqa: BLE001
            reranker = build_reranker("lexical")
            rerank_name = f"lexical(fallback:{type(e).__name__})"
        for rid in rs.resume_ids:
            qdoc = rs.resume_doc(rid)
            cands = recall.search([qdoc], top_k=20)[0]
            docs = [rs.job_doc(rs.job_ids[d]) for d, _ in cands]
            rr = reranker.score([qdoc] * len(docs), docs).scores
            for (d, sem), raw in zip(cands, rr):
                jid = rs.job_ids[d]
                row_r, row_j = rs.resumes[rid], rs.jobs[jid]
                b = fused.score(
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
                    semantic_score=float(sem))
                e05.setdefault(rid, {})[jid] = float(raw)
                e06.setdefault(rid, {})[jid] = 0.0 if b.filtered else b.total

        def _twostage_lookup(table):
            def f(rid, jid):
                return table.get(rid, {}).get(jid, -1e9)
            return f

        results["E05_embedding_plus_reranker"] = {
            "status": "RUN", "reranker": rerank_name,
            "task_A": evaluate_task_a(rs, _twostage_lookup(e05)),
            "task_B": evaluate_task_b(rs, _twostage_lookup(e05)),
            "seconds": round(time.time() - t0, 3),
            "note": "两阶段：Embedding 召回 Top20 -> Cross-Encoder 精排；未覆盖候选记 -1e9（视为未召回）",
        }
        results["E06_full_two_stage_with_constraints"] = {
            "status": "RUN", "reranker": rerank_name,
            "task_A": evaluate_task_a(rs, _twostage_lookup(e06)),
            "task_B": evaluate_task_b(rs, _twostage_lookup(e06)),
            "seconds": round(time.time() - t0, 3),
            "note": "E05 + 硬/软约束（学历硬约束、技能/经验/类别/意向软约束，人工权重）",
        }
    except Exception as e:  # noqa: BLE001
        results["E05_embedding_plus_reranker"] = {"status": "FAILED",
                                                  "error": f"{type(e).__name__}: {e}"}
        results["E06_full_two_stage_with_constraints"] = {"status": "FAILED",
                                                          "error": f"{type(e).__name__}: {e}"}

    results["E07_finetuned_model"] = {
        "status": "NOT_RUN",
        "reason": ("缺少合法、足量、正确切分的监督训练数据（H2 Gold 未冻结），"
                   "且不得用合成夹具或盲测 Gold 微调；前置条件未满足"),
    }

    meta["end_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta["total_seconds"] = round(time.time() - t_start, 3)
    meta["encoder_used"] = args.encoder
    payload = {"meta": meta, "results": results}

    out_path = Path(args.out) if args.out else OUT_REPORT
    jdump(payload, out_path)
    run_out = OUT_ROOT / "runs" / f"{run_id}.json"
    jdump(payload, run_out)
    jdump(meta, OUT_ROOT / "manifests" / f"{run_id}.manifest.json")
    print(f"wrote {out_path}")
    print(f"wrote {run_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
