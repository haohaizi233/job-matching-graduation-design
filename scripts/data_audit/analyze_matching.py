# -*- coding: utf-8 -*-
"""人岗匹配数据专项分析：关联关系、标签机制、负样本、数据泄漏。

产出：reports/data-audit/matching-analysis.json
用法：python scripts/data_audit/analyze_matching.py

只读 data/raw，不写入、不移动、不改写任何原始记录。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

OUT_JSON = "matching-analysis.json"


# ---------------------------------------------------------------- 读取
def load_tables():
    print("读取 cv.csv / job.csv / matches.csv ...", file=sys.stderr)
    cv = pd.read_csv(C.CV, encoding="utf-8-sig", low_memory=False,
                     usecols=["candidate_id", "target_position", "years_experience",
                              "inferred_category", "clean_skills"])
    job = pd.read_csv(C.JOB, encoding="utf-8-sig", low_memory=False,
                      usecols=["job_id", "job_title", "category", "years_required",
                               "clean_skills"])
    m = pd.read_csv(C.MATCHES, encoding="utf-8-sig", low_memory=False)
    return cv, job, m


# ---------------------------------------------------------------- 关联关系
def analyze_relations(cv: pd.DataFrame, job: pd.DataFrame, m: pd.DataFrame) -> dict:
    r = {}
    r["cv_rows"] = int(len(cv))
    r["job_rows"] = int(len(job))
    r["matches_rows"] = int(len(m))

    r["candidate_id_unique_in_cv"] = bool(cv["candidate_id"].is_unique)
    r["candidate_id_dup_rows_in_cv"] = int(cv["candidate_id"].duplicated().sum())
    r["job_id_unique_in_job"] = bool(job["job_id"].is_unique)
    r["job_id_dup_rows_in_job"] = int(job["job_id"].duplicated().sum())

    cv_ids, job_ids = set(cv["candidate_id"]), set(job["job_id"])
    m_cand, m_job = set(m["candidate_id"]), set(m["job_id"])
    r["matches_unique_candidate_id"] = int(len(m_cand))
    r["matches_unique_job_id"] = int(len(m_job))
    r["matches_candidate_id_orphan"] = int(len(m_cand - cv_ids))
    r["matches_job_id_orphan"] = int(len(m_job - job_ids))
    r["cv_candidate_never_in_matches"] = int(len(cv_ids - m_cand))
    r["job_job_never_in_matches"] = int(len(job_ids - m_job))
    r["referential_integrity_complete"] = bool(
        len(m_cand - cv_ids) == 0 and len(m_job - job_ids) == 0)

    # 度分布
    per_cand = m.groupby("candidate_id")["job_id"].nunique()
    per_job = m.groupby("job_id")["candidate_id"].nunique()
    r["jobs_per_candidate"] = {
        "min": int(per_cand.min()), "p25": float(per_cand.quantile(0.25)),
        "median": float(per_cand.median()), "p75": float(per_cand.quantile(0.75)),
        "max": int(per_cand.max()), "mean": round(float(per_cand.mean()), 3),
        "value_counts": {str(k): int(v) for k, v in per_cand.value_counts().sort_index().items()},
    }
    r["candidates_per_job"] = {
        "min": int(per_job.min()), "p25": float(per_job.quantile(0.25)),
        "median": float(per_job.median()), "p75": float(per_job.quantile(0.75)),
        "max": int(per_job.max()), "mean": round(float(per_job.mean()), 3),
    }

    # 组合唯一性 / 标签冲突
    pair = m.groupby(["candidate_id", "job_id"])
    pair_n = pair.size()
    r["pair_total"] = int(len(pair_n))
    r["pair_duplicated"] = int((pair_n > 1).sum())
    r["pair_duplicated_rows"] = int(pair_n[pair_n > 1].sum())
    r["pair_max_repeat"] = int(pair_n.max())
    lab_nunique = pair["label_strength"].nunique()
    r["pair_label_conflict"] = int((lab_nunique > 1).sum())
    score_nunique = pair["final_score"].nunique()
    r["pair_final_score_conflict"] = int((score_nunique > 1).sum())

    # 是否全组合
    r["full_cross_product_size"] = int(len(cv_ids) * len(job_ids))
    r["observed_pair_ratio_pct"] = round(
        100.0 * len(pair_n) / max(1, len(cv_ids) * len(job_ids)), 4)
    return r


# ---------------------------------------------------------------- 标签机制
def _lstsq_fit(X: np.ndarray, y: np.ndarray) -> dict:
    """最小二乘拟合 y ~ X·w + b，返回权重、R²、最大绝对残差。"""
    A = np.hstack([X, np.ones((len(X), 1))])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    resid = y - pred
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "weights": [round(float(v), 6) for v in coef[:-1]],
        "bias": round(float(coef[-1]), 6),
        "r2": round(1.0 - ss_res / max(ss_tot, 1e-12), 8),
        "max_abs_residual": round(float(np.abs(resid).max()), 8),
        "residual_std": round(float(resid.std()), 8),
    }


def analyze_labels(m: pd.DataFrame) -> dict:
    r = {}
    r["label_strength_value_counts"] = {str(k): int(v) for k, v in
                                        m["label_strength"].value_counts(dropna=False).items()}
    total = len(m)
    r["label_strength_pct"] = {str(k): round(100.0 * v / total, 4) for k, v in
                               m["label_strength"].value_counts(dropna=False).items()}
    r["label_missing"] = int(m["label_strength"].isna().sum())

    feats = C.FEATS
    X = m[feats].to_numpy(dtype=float)
    y_final = m["final_score"].to_numpy(dtype=float)
    y_raw = m["raw_score"].to_numpy(dtype=float)

    # 1) final_score / raw_score 是否为六维的确定性线性组合
    r["final_score_vs_6feats"] = _lstsq_fit(X, y_final)
    r["raw_score_vs_6feats"] = _lstsq_fit(X, y_raw)

    # 2) final_score 与 raw_score 的关系
    r["final_vs_raw"] = _lstsq_fit(y_raw.reshape(-1, 1), y_final)
    r["final_vs_raw_pearson"] = round(float(np.corrcoef(y_final, y_raw)[0, 1]), 8)
    r["final_vs_raw_spearman"] = round(float(
        pd.Series(y_final).corr(pd.Series(y_raw), method="spearman")), 8)

    # 3) 各特征与分数的相关性
    corr = {}
    for f in feats:
        s = m[f]
        corr[f] = {
            "pearson_with_final_score": round(float(s.corr(m["final_score"])), 6),
            "pearson_with_raw_score": round(float(s.corr(m["raw_score"])), 6),
            "spearman_with_final_score": round(float(s.corr(m["final_score"], method="spearman")), 6),
        }
    # 与序数标签的相关性（weak=0, medium=1, strong=2）
    order = {"weak_positive": 0, "medium_positive": 1, "strong_positive": 2}
    y_lab = m["label_strength"].map(order)
    r["label_ordinal_encoding"] = order
    for f in feats:
        corr[f]["pearson_with_label_ordinal"] = round(float(m[f].corr(y_lab)), 6)
        corr[f]["spearman_with_label_ordinal"] = round(float(m[f].corr(y_lab, method="spearman")), 6)
    corr["final_score"] = {
        "pearson_with_label_ordinal": round(float(m["final_score"].corr(y_lab)), 6),
        "spearman_with_label_ordinal": round(float(m["final_score"].corr(y_lab, method="spearman")), 6),
    }
    corr["raw_score"] = {
        "pearson_with_label_ordinal": round(float(m["raw_score"].corr(y_lab)), 6),
        "spearman_with_label_ordinal": round(float(m["raw_score"].corr(y_lab, method="spearman")), 6),
    }
    corr["candidate_rank_pct"] = {
        "pearson_with_label_ordinal": round(float(m["candidate_rank_pct"].corr(y_lab)), 6),
        "spearman_with_label_ordinal": round(float(m["candidate_rank_pct"].corr(y_lab, method="spearman")), 6),
    }
    r["feature_correlations"] = corr

    # 4) 标签与分数的区间（是否可用单阈值切分）
    interval = {}
    for lab, g in m.groupby("label_strength"):
        interval[str(lab)] = {
            "n": int(len(g)),
            "final_score_min": round(float(g["final_score"].min()), 6),
            "final_score_max": round(float(g["final_score"].max()), 6),
            "final_score_mean": round(float(g["final_score"].mean()), 6),
            "raw_score_min": round(float(g["raw_score"].min()), 6),
            "raw_score_max": round(float(g["raw_score"].max()), 6),
            "raw_score_mean": round(float(g["raw_score"].mean()), 6),
        }
    r["label_score_intervals"] = interval
    # 区间是否不相交
    order_labs = [l for l in ["weak_positive", "medium_positive", "strong_positive"]
                  if l in interval]
    disjoint = True
    for a, b in zip(order_labs, order_labs[1:]):
        if interval[a]["final_score_max"] >= interval[b]["final_score_min"]:
            disjoint = False
    r["label_final_score_intervals_disjoint"] = bool(disjoint)

    # 5) 决策树规则拟合：能否用分数/特征完美复现标签
    from sklearn.tree import DecisionTreeClassifier
    tree_res = {}
    for name, cols in [
        ("final_score_only", ["final_score"]),
        ("raw_score_only", ["raw_score"]),
        ("six_features", feats),
        ("six_features_plus_scores", feats + ["final_score", "raw_score"]),
        ("all_numeric_no_rank", feats + ["final_score", "raw_score"]),
    ]:
        Xc = m[cols].to_numpy(dtype=float)
        clf = DecisionTreeClassifier(max_depth=4, random_state=0)
        clf.fit(Xc, y_lab)
        acc = float((clf.predict(Xc) == y_lab.to_numpy()).mean())
        tree_res[name] = {
            "columns": cols,
            "train_accuracy_depth4": round(acc, 6),
            "tree_depth_actual": int(clf.get_depth()),
            "leaves": int(clf.get_n_leaves()),
        }
        clf2 = DecisionTreeClassifier(max_depth=2, random_state=0)
        clf2.fit(Xc, y_lab)
        acc2 = float((clf2.predict(Xc) == y_lab.to_numpy()).mean())
        tree_res[name]["train_accuracy_depth2"] = round(acc2, 6)
        tree_res[name]["tree_depth2_actual"] = int(clf2.get_depth())
    r["tree_rule_fit"] = tree_res

    # 6) 阈值规则检验：单变量 final_score 阈值能否完全分离标签
    thr = {}
    for a, b in zip(order_labs, order_labs[1:]):
        hi = m.loc[m["label_strength"] == a, "final_score"].max()
        lo = m.loc[m["label_strength"] == b, "final_score"].min()
        thr["%s->%s" % (a, b)] = {
            "prev_max": round(float(hi), 6),
            "next_min": round(float(lo), 6),
            "gap": round(float(lo - hi), 6),
            "separable": bool(lo > hi),
        }
    r["threshold_gaps_final_score"] = thr

    # 7) 一致性：完全相同的六维打分是否总是对应同一标签
    key = m[feats].round(8).astype(str).agg("|".join, axis=1)
    g = m.groupby(key)["label_strength"].nunique()
    r["identical_feature_vectors"] = int(len(g))
    r["identical_feature_vectors_with_label_conflict"] = int((g > 1).sum())

    # 8) 与 final_score 完全相同的行是否标签一致
    g2 = m.groupby(m["final_score"].round(8))["label_strength"].nunique()
    r["identical_final_score_values"] = int(len(g2))
    r["identical_final_score_with_label_conflict"] = int((g2 > 1).sum())

    # 9) 强正样本稀缺性
    r["strong_positive_count"] = int((m["label_strength"] == "strong_positive").sum())
    r["strong_positive_ratio_pct"] = round(
        100.0 * (m["label_strength"] == "strong_positive").mean(), 4)
    r["imbalance_ratio_medium_to_strong"] = round(
        float((m["label_strength"] == "medium_positive").sum()) /
        max(1, (m["label_strength"] == "strong_positive").sum()), 3)
    r["imbalance_ratio_weak_to_strong"] = round(
        float((m["label_strength"] == "weak_positive").sum()) /
        max(1, (m["label_strength"] == "strong_positive").sum()), 3)

    # 10) strong_positive 覆盖到多少候选人 / 岗位
    sp = m[m["label_strength"] == "strong_positive"]
    r["strong_positive_unique_candidates"] = int(sp["candidate_id"].nunique())
    r["strong_positive_unique_jobs"] = int(sp["job_id"].nunique())
    return r


# ---------------------------------------------------------------- 排序字段
def analyze_rank_fields(m: pd.DataFrame) -> dict:
    r = {}
    # candidate_rank 是否等于组内 final_score 降序名次
    ok_rank, ok_pct, n_groups = 0, 0, 0
    for _, g in m.groupby("candidate_id"):
        n_groups += 1
        expected = g["final_score"].rank(ascending=False, method="min").astype(int)
        if (expected.to_numpy() == g["candidate_rank"].to_numpy()).all():
            ok_rank += 1
        n = len(g)
        exp_pct = (n - g["final_score"].rank(ascending=False, method="min") + 1) / n
        if np.allclose(exp_pct.to_numpy(), g["candidate_rank_pct"].to_numpy(), atol=1e-6):
            ok_pct += 1
    r["candidate_groups_checked"] = n_groups
    r["candidate_rank_matches_score_desc_rank"] = ok_rank
    r["candidate_rank_matches_pct"] = ok_pct
    r["candidate_rank_is_deterministic_from_score"] = bool(ok_rank == n_groups)

    # 全局范围
    r["candidate_rank_value_counts_top"] = {str(k): int(v) for k, v in
                                            m["candidate_rank"].value_counts().head(15).items()}
    r["candidate_rank_pct_summary"] = C.num_summary(m["candidate_rank_pct"])
    r["candidate_rank_summary"] = C.num_summary(m["candidate_rank"])
    return r


# ---------------------------------------------------------------- 负样本
def analyze_negative_sampling(m: pd.DataFrame, cv: pd.DataFrame, job: pd.DataFrame) -> dict:
    r = {}
    r["labels_present"] = sorted(m["label_strength"].dropna().unique().tolist())
    r["has_explicit_negative_label"] = bool(
        any(str(x).lower() in ("negative", "neg", "0", "no", "不匹配", "负样本")
            for x in m["label_strength"].dropna().unique()))
    r["observed_pairs"] = int(m.groupby(["candidate_id", "job_id"]).ngroups)
    r["all_possible_pairs"] = int(cv["candidate_id"].nunique() * job["job_id"].nunique())
    r["unobserved_pairs"] = int(r["all_possible_pairs"] - r["observed_pairs"])
    r["observed_ratio_pct"] = round(100.0 * r["observed_pairs"] / max(1, r["all_possible_pairs"]), 4)

    # weak_positive 的分数区间，用于说明它不是"负例"
    for lab in ["weak_positive", "medium_positive", "strong_positive"]:
        g = m[m["label_strength"] == lab]
        r["%s_semantic_score_mean" % lab] = round(float(g["semantic_score"].mean()), 6)
        r["%s_final_score_mean" % lab] = round(float(g["final_score"].mean()), 6)
    return r


# ---------------------------------------------------------------- 泄漏
def analyze_leakage(m: pd.DataFrame, cv: pd.DataFrame) -> dict:
    r = {}
    # 1) 同一候选人多行 → 行级随机划分会把同一人放进不同集合
    per_cand = m.groupby("candidate_id").size()
    r["candidates_with_multiple_rows"] = int((per_cand > 1).sum())
    r["max_rows_per_candidate"] = int(per_cand.max())
    r["rows_in_multirow_candidates_pct"] = round(
        100.0 * per_cand[per_cand > 1].sum() / len(m), 4)
    per_job = m.groupby("job_id").size()
    r["jobs_with_multiple_rows"] = int((per_job > 1).sum())
    r["max_rows_per_job"] = int(per_job.max())

    # 2) 行级随机划分下，验证集里的候选人/岗位在训练集出现的概率（模拟 8:1:1）
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(m))
    n = len(m)
    tr, va = set(idx[: int(n * 0.8)]), set(idx[int(n * 0.8): int(n * 0.9)])
    m_tr, m_va = m.iloc[sorted(tr)], m.iloc[sorted(va)]
    cand_overlap = len(set(m_va["candidate_id"]) & set(m_tr["candidate_id"]))
    job_overlap = len(set(m_va["job_id"]) & set(m_tr["job_id"]))
    r["random_split_8_1_1_sim"] = {
        "val_rows": int(len(m_va)),
        "val_candidates_seen_in_train_pct": round(
            100.0 * cand_overlap / max(1, m_va["candidate_id"].nunique()), 3),
        "val_jobs_seen_in_train_pct": round(
            100.0 * job_overlap / max(1, m_va["job_id"].nunique()), 3),
    }

    # 3) 派生字段泄漏
    r["derived_fields"] = {
        "final_score": "六维打分的函数（见 matching-analysis.json 中 final_score_vs_6feats）",
        "raw_score": "六维打分的函数",
        "candidate_rank": "组内按 final_score 降序的名次（确定性派生）",
        "candidate_rank_pct": "组内名次的百分位（确定性派生）",
    }
    r["high_leakage_features_for_label_prediction"] = [
        "final_score", "raw_score", "candidate_rank", "candidate_rank_pct"]

    # 4) 六维特征是否本身含有标签（若标签由它们生成）
    r["note_on_derived_label"] = (
        "若 label_strength 由 final_score/六维打分阈值生成，则用六维或分数预测标签属"
        "于目标泄漏（等价于复现生成公式），不能作为模型效果证据。")
    return r


# ---------------------------------------------------------------- 主流程
def main() -> int:
    C.ensure_out()
    cv, job, m = load_tables()
    out = {
        "generated_by": "scripts/data_audit/analyze_matching.py",
        "note": "只读审计；未修改、未移动、未重写任何原始文件。",
        "files": {k: C.file_meta(p) for k, p in
                  [("cv.csv", C.CV), ("job.csv", C.JOB), ("matches.csv", C.MATCHES)]},
        "relations": analyze_relations(cv, job, m),
        "labels": analyze_labels(m),
        "rank_fields": analyze_rank_fields(m),
        "negative_sampling": analyze_negative_sampling(m, cv, job),
        "leakage": analyze_leakage(m, cv),
    }
    C.jdump(out, C.OUT / OUT_JSON)

    print("=== 关联关系 ===")
    print(pd.Series(out["relations"]).to_string())
    print("\n=== 标签分布 ===")
    print(pd.Series(out["labels"]["label_strength_value_counts"]).to_string())
    print("\n=== final_score ~ 六维线性拟合 ===")
    print(out["labels"]["final_score_vs_6feats"])
    print("\n=== raw_score ~ 六维线性拟合 ===")
    print(out["labels"]["raw_score_vs_6feats"])
    print("\n=== final_score ~ raw_score ===")
    print(out["labels"]["final_vs_raw"])
    print("\n=== 标签分数区间 ===")
    print(pd.DataFrame(out["labels"]["label_score_intervals"]).T.to_string())
    print("\n=== 决策树规则拟合 ===")
    print(pd.DataFrame(out["labels"]["tree_rule_fit"]).T.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
