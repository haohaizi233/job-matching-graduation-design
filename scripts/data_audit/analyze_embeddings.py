# -*- coding: utf-8 -*-
"""Embedding 字段专项分析：维度、解析率、范数、重复、来源判断。

产出：reports/data-audit/embedding-analysis.json
用法：python scripts/data_audit/analyze_embeddings.py

只读 data/raw。解析向量时只保留统计量与哈希，不把原始向量写入输出。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

OUT_JSON = "embedding-analysis.json"
SAMPLE_PAIRS = 3000          # 余弦相似度抽样规模
RNG = np.random.default_rng(20261028)


def parse_all(s: pd.Series):
    """逐条解析向量，返回 (矩阵, 成功掩码, 维度集合, 失败样例数)。"""
    vecs, dims, ok = [], set(), 0
    fail = 0
    for v in s.astype(str):
        a = C.parse_embedding(v)
        if a is None or a.size == 0:
            fail += 1
            vecs.append(None)
            continue
        ok += 1
        dims.add(int(a.size))
        vecs.append(a)
    return vecs, ok, dims, fail


def stats_from_matrix(M: np.ndarray) -> dict:
    norms = np.linalg.norm(M, axis=1)
    zero = int((norms == 0).sum())
    nan_rows = int(np.isnan(M).any(axis=1).sum())
    inf_rows = int(np.isinf(M).any(axis=1).sum())
    # 去重：按字节哈希
    import hashlib
    seen = {}
    dup = 0
    for row in M.astype(np.float32):
        h = hashlib.blake2b(row.tobytes(), digest_size=16).hexdigest()
        if h in seen:
            dup += 1
        else:
            seen[h] = 1
    return {
        "rows": int(M.shape[0]),
        "dim": int(M.shape[1]),
        "dtype_after_parse": str(M.dtype),
        "zero_vectors": zero,
        "zero_vectors_pct": round(100.0 * zero / max(1, M.shape[0]), 4),
        "rows_with_nan": nan_rows,
        "rows_with_inf": inf_rows,
        "norm": {
            "min": round(float(norms.min()), 6),
            "p25": round(float(np.percentile(norms, 25)), 6),
            "median": round(float(np.median(norms)), 6),
            "p75": round(float(np.percentile(norms, 75)), 6),
            "max": round(float(norms.max()), 6),
            "mean": round(float(norms.mean()), 6),
            "std": round(float(norms.std()), 6),
            "unit_norm_atol_1e-3_pct": round(
                100.0 * float(np.mean(np.abs(norms - 1.0) < 1e-3)), 4),
        },
        "value_range": {
            "global_min": round(float(np.nanmin(M)), 6),
            "global_max": round(float(np.nanmax(M)), 6),
            "global_mean": round(float(np.nanmean(M)), 6),
            "global_std": round(float(np.nanstd(M)), 6),
        },
        "duplicate_vectors": dup,
        "duplicate_vectors_pct": round(100.0 * dup / max(1, M.shape[0]), 4),
    }


def main() -> int:
    C.ensure_out()
    out = {
        "generated_by": "scripts/data_audit/analyze_embeddings.py",
        "note": "只读审计；未修改任何原始文件。输出只含统计量，不含原始向量。",
        "files": {},
    }

    # ---------------- cv.csv
    print("解析 cv.csv embedding ...", file=sys.stderr)
    cv = pd.read_csv(C.CV, encoding="utf-8-sig", low_memory=False,
                     usecols=["candidate_id", "embedding"])
    vecs, ok, dims, fail = parse_all(cv["embedding"])
    out["files"]["cv.csv"] = {
        "file": C.file_meta(C.CV),
        "column": "embedding",
        "raw_dtype": str(cv["embedding"].dtype),
        "total_rows": int(len(cv)),
        "parsed_ok": int(ok),
        "parse_failed": int(fail),
        "parse_success_pct": round(100.0 * ok / max(1, len(cv)), 4),
        "dims_seen": sorted(dims),
    }
    cv_mat = np.vstack([v for v in vecs if v is not None])
    out["files"]["cv.csv"]["stats"] = stats_from_matrix(cv_mat)
    cv_id_of_row = [i for i, v in enumerate(vecs) if v is not None]

    # ---------------- job.csv
    print("解析 job.csv embedding ...", file=sys.stderr)
    job = pd.read_csv(C.JOB, encoding="utf-8-sig", low_memory=False,
                      usecols=["job_id", "embedding"])
    jvecs, jok, jdims, jfail = parse_all(job["embedding"])
    out["files"]["job.csv"] = {
        "file": C.file_meta(C.JOB),
        "column": "embedding",
        "raw_dtype": str(job["embedding"].dtype),
        "total_rows": int(len(job)),
        "parsed_ok": int(jok),
        "parse_failed": int(jfail),
        "parse_success_pct": round(100.0 * jok / max(1, len(job)), 4),
        "dims_seen": sorted(jdims),
    }
    job_mat = np.vstack([v for v in jvecs if v is not None])
    out["files"]["job.csv"]["stats"] = stats_from_matrix(job_mat)
    job_id_of_row = [i for i, v in enumerate(jvecs) if v is not None]

    # ---------------- 空间一致性：cv 与 job 是否在同一向量空间
    print("检验 cv/job 向量空间一致性 ...", file=sys.stderr)
    space = {}
    space["cv_dim"] = int(cv_mat.shape[1])
    space["job_dim"] = int(job_mat.shape[1])
    space["same_dim"] = bool(cv_mat.shape[1] == job_mat.shape[1])
    space["cv_norm_mean"] = round(float(np.linalg.norm(cv_mat, axis=1).mean()), 6)
    space["job_norm_mean"] = round(float(np.linalg.norm(job_mat, axis=1).mean()), 6)

    cvn = cv_mat / np.clip(np.linalg.norm(cv_mat, axis=1, keepdims=True), 1e-12, None)
    jobn = job_mat / np.clip(np.linalg.norm(job_mat, axis=1, keepdims=True), 1e-12, None)

    # 随机配对余弦分布（基线）
    n_r = min(SAMPLE_PAIRS, len(cvn), len(jobn))
    ri = RNG.integers(0, len(cvn), n_r)
    rj = RNG.integers(0, len(jobn), n_r)
    rand_cos = np.einsum("ij,ij->i", cvn[ri], jobn[rj])
    space["random_pair_cosine"] = {
        "n": int(n_r),
        "mean": round(float(rand_cos.mean()), 6),
        "std": round(float(rand_cos.std()), 6),
        "min": round(float(rand_cos.min()), 6),
        "p50": round(float(np.median(rand_cos)), 6),
        "max": round(float(rand_cos.max()), 6),
    }

    # ---------------- 与 matches 语义分的一致性
    print("比对 semantic_score 与真实余弦相似度 ...", file=sys.stderr)
    m = pd.read_csv(C.MATCHES, encoding="utf-8-sig", low_memory=False,
                    usecols=["candidate_id", "job_id", "semantic_score",
                             "skill_score", "final_score", "label_strength"])
    cv_pos = {cid: i for i, cid in zip(cv_id_of_row,
                                       cv.loc[cv_id_of_row, "candidate_id"].tolist())}
    job_pos = {jid: i for i, jid in zip(job_id_of_row,
                                        job.loc[job_id_of_row, "job_id"].tolist())}
    mm = m[m["candidate_id"].isin(cv_pos) & m["job_id"].isin(job_pos)]
    if len(mm) > SAMPLE_PAIRS:
        mm = mm.sample(SAMPLE_PAIRS, random_state=0)
    ci = np.array([cv_pos[c] for c in mm["candidate_id"]])
    ji = np.array([job_pos[j] for j in mm["job_id"]])
    real_cos = np.einsum("ij,ij->i", cvn[ci], jobn[ji])
    sem = mm["semantic_score"].to_numpy(dtype=float)

    def _lin(x, y):
        A = np.vstack([x, np.ones(len(x))]).T
        (k, b), *_ = np.linalg.lstsq(A, y, rcond=None)
        pred = k * x + b
        resid = y - pred
        ss_res = float((resid ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        return {"slope": round(float(k), 8), "intercept": round(float(b), 8),
                "r2": round(1 - ss_res / max(ss_tot, 1e-12), 8),
                "max_abs_residual": round(float(np.abs(resid).max()), 8)}

    space["matched_pair_cosine_vs_semantic_score"] = {
        "n": int(len(mm)),
        "cosine_mean": round(float(real_cos.mean()), 6),
        "cosine_min": round(float(real_cos.min()), 6),
        "cosine_max": round(float(real_cos.max()), 6),
        "semantic_score_mean": round(float(sem.mean()), 6),
        "pearson": round(float(np.corrcoef(real_cos, sem)[0, 1]), 8),
        "spearman": round(float(pd.Series(real_cos).corr(pd.Series(sem), method="spearman")), 8),
        "linear_fit_semantic_vs_cosine": _lin(real_cos, sem),
        "linear_fit_cosine_vs_semantic": _lin(sem, real_cos),
    }
    # 分数归一化提示：semantic_score 是否为 cosine 的线性缩放
    k = space["matched_pair_cosine_vs_semantic_score"]["linear_fit_semantic_vs_cosine"]["slope"]
    b = space["matched_pair_cosine_vs_semantic_score"]["linear_fit_semantic_vs_cosine"]["intercept"]
    space["hypothesis_semantic_is_affine_of_cosine"] = {
        "affine": "semantic_score = %.6f * cosine + %.6f" % (k, b),
        "r2": space["matched_pair_cosine_vs_semantic_score"]["linear_fit_semantic_vs_cosine"]["r2"],
        "consistent_with_affine_transform": bool(
            space["matched_pair_cosine_vs_semantic_score"]["linear_fit_semantic_vs_cosine"]["r2"] > 0.99),
    }

    # 同一候选人内 cosine 与 semantic_score 的排序一致性
    tmp = pd.DataFrame({"cand": mm["candidate_id"].to_numpy(),
                        "cos": real_cos, "sem": sem})
    agree = []
    for _, g in tmp.groupby("cand"):
        if len(g) >= 3:
            agree.append(float(pd.Series(g["cos"]).rank().corr(pd.Series(g["sem"]).rank())))
    space["within_candidate_rank_corr_mean"] = (
        round(float(np.nanmean(agree)), 6) if agree else None)
    space["within_candidate_groups_checked"] = int(len(agree))

    # 向量空间是否与 skill_score 相关（判断 embedding 是否含技能信息）
    space["cosine_vs_skill_score_pearson"] = round(
        float(np.corrcoef(real_cos, mm["skill_score"].to_numpy(dtype=float))[0, 1]), 6)
    space["cosine_vs_final_score_pearson"] = round(
        float(np.corrcoef(real_cos, mm["final_score"].to_numpy(dtype=float))[0, 1]), 6)

    out["space_consistency"] = space

    # ---------------- 来源判断
    out["origin_assessment"] = {
        "facts_from_data": [
            "cv.csv 与 job.csv 的 embedding 列均可 100% 解析为 768 维 float32 向量。",
            "两个表的向量维度一致（768）。",
            "数据集 README 明确写明 embedding 为 'Precomputed 768-dimensional text embedding'，"
            "并在 Limitations 中写明 'The embedding model used to create the stored vectors is not specified in the dataset files.'",
        ],
        "evidence_based_inference": [
            "若 matched_pair_cosine_vs_semantic_score 的 pearson 接近 1 且 affine R² 接近 1，"
            "则可推断 semantic_score 直接由这两个向量的余弦相似度经线性缩放得到，"
            "即 cv/job 向量处于同一语义空间、且 semantic_score 是其派生量。",
        ],
        "unknown_from_data": [
            "无法从数据本身确定具体的编码模型（架构、训练语料、是否为 sentence-transformers 系列）。",
            "无法确定向量是对 resume_text / job_text 原文编码，还是对清洗后拼接文本编码。",
            "无法确定是否为单塔（共享编码器）或双塔（两个编码器）。",
        ],
        "do_not_infer": [
            "不能仅凭维度为 768 就断定编码模型为 BERT/RoBERTa/MPNet 等任一具体模型。",
            "不能把 embedding 当作独立于标签的'原始特征'——若 semantic_score 由它派生、"
            "而标签又由 semantic_score 参与生成，则 embedding 与标签之间存在派生链条。",
        ],
    }
    out["joint_representation_check"] = {
        "cv_embedding_used_for": "候选人侧（resume）表示",
        "job_embedding_used_for": "岗位侧（job）表示",
        "is_joint_pair_embedding": False,
        "basis": "两表各自持有独立的 embedding 列，matches.csv 不再单独持有 pair 级向量；"
                 "pair 级的 semantic_score 由两侧向量相似度派生（待 space_consistency 数值证实）。",
    }

    C.jdump(out, C.OUT / OUT_JSON)

    print("=== cv embedding ===")
    print(pd.Series({k: v for k, v in out["files"]["cv.csv"].items() if k != "stats"}).to_string())
    print(pd.Series(out["files"]["cv.csv"]["stats"]).to_string())
    print("\n=== job embedding ===")
    print(pd.Series(out["files"]["job.csv"]["stats"]).to_string())
    print("\n=== 空间一致性 ===")
    print(pd.Series({k: v for k, v in space.items() if not isinstance(v, dict)}).to_string())
    print(pd.Series(space["matched_pair_cosine_vs_semantic_score"]).to_string())
    print(pd.Series(space["random_pair_cosine"]).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
