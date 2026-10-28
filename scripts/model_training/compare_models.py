# -*- coding: utf-8 -*-
"""第四阶段 4.1：模型对比、Bootstrap 置信区间、消融与错误分析，生成全部报告。

用法：
    python scripts/model_training/compare_models.py

产出（reports/model-training/）：
    experiment-summary.md / baseline-comparison.md / ranking-evaluation.md /
    ablation-study.md / error-analysis.md / resource-usage.md / results.json

纪律：
  * 零训练基线指标从 reports/baselines/baseline-results.json 机器读取，
    不手工转录；本地只复算「每查询指标」做配对 Bootstrap，并校验与报告一致；
  * 所有差值按查询组（candidate_id）重采样；
  * 代理标签限制必须随每个表格输出。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402
from common import setup_train_logging  # noqa: E402
from job_matching.core import ROOT, ensure_dir, jdump, sha256_file  # noqa: E402
from job_matching.evaluation.error_analysis import analyze_errors  # noqa: E402
from job_matching.evaluation.metrics import pairwise_accuracy  # noqa: E402
from job_matching.evaluation.statistical_tests import (  # noqa: E402
    bootstrap_diff, local_baseline_scores, per_query_ndcg, per_query_pairwise_accuracy,
)
from job_matching.training.config_train import get_train_config  # noqa: E402
from job_matching.training.dataset import load_pairs, load_protocol  # noqa: E402

OUT_DIR = ROOT / "reports" / "model-training"
RUNS_DIR = OUT_DIR / "runs"
BASELINE_REPORT = ROOT / "reports" / "baselines" / "baseline-results.json"
PROTOCOLS = ["candidate_cold", "job_cold", "double_cold"]
MODELS = ["ridge", "gradient_boosting", "mlp", "ranknet"]
BASELINES = ["random_ranking", "embedding_cosine", "skill_jaccard", "position_token_overlap"]

CAVEATS = [
    "label_strength / candidate_rank / final_score 全部由原评分系统公式派生，"
    "本节指标只能衡量预测结果与原系统代理偏好的一致程度，"
    "不代表真实录用概率、招聘成功率或用户满意度。",
    "Embedding Cosine 与代理标签生成机制直接耦合（semantic_score = 0.5*cosine+0.5），"
    "其高 NDCG 不构成独立语义匹配有效性证明。",
    "matches.csv 无真实负例，评估只在观测组合内部做组内排序。",
    "test 已在第三阶段用于零训练基线比较，本阶段只做方案锁定后的确认评估，不用于调参。",
    "RankNet 学习的是原评分系统的代理排序偏好，不是用户真实偏好。",
]


def jload(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def load_run_records() -> list[dict]:
    return [jload(p) for p in sorted(RUNS_DIR.glob("*.json"))]


def select_runs(records: list[dict]) -> tuple[dict, dict]:
    """返回 (final_runs[(model, protocol)] = record, ablation_runs[tag+(model,protocol)] = record)。"""
    final: dict = {}
    ablation: dict = {}
    for r in sorted(records, key=lambda d: d.get("created_at", "")):
        if r.get("smoke"):
            continue
        key = (r["model_name"], r["protocol"])
        if r.get("tag") == "final":
            final[key] = r
        elif str(r.get("tag", "")).startswith("ablation"):
            ablation[(r["tag"], r["model_name"], r["protocol"])] = r
    return final, ablation


def embedding_cosine_scores(pairs_frame) -> np.ndarray:
    """按 pair_index 全量对齐的 embedding 余弦分数（与第三阶段 baseline 同口径）。"""
    emb_dir = ROOT / "data/processed/embeddings"
    cv = np.load(emb_dir / "cv_embeddings.npy")
    job = np.load(emb_dir / "job_embeddings.npy")
    cv_map = jload(emb_dir / "cv_id_map.json")["id_to_row"]
    job_map = jload(emb_dir / "job_id_map.json")["id_to_row"]
    n = int(pairs_frame["pair_index"].max()) + 1
    out = np.zeros(n, dtype=np.float32)
    c_rows = np.array([cv_map[str(c)] for c in pairs_frame["candidate_id"]], dtype=np.int64)
    j_rows = np.array([job_map[str(int(j))] for j in pairs_frame["job_id"]], dtype=np.int64)
    vals = np.einsum("ij,ij->i", cv[c_rows], job[j_rows])
    out[pairs_frame["pair_index"].to_numpy(np.int64)] = vals
    return out


def fmt(v, digits: int = 6) -> str:
    if v is None:
        return "不可评估"
    return f"{float(v):.{digits}f}"


def main() -> int:
    log = setup_train_logging("compare_models")
    ensure_dir(OUT_DIR)
    cfg = get_train_config()
    t0 = time.time()

    records = load_run_records()
    final_runs, ablation_runs = select_runs(records)
    log.info("[runs] final=%d ablation=%d", len(final_runs), len(ablation_runs))

    baselines_report = jload(BASELINE_REPORT)["matching"]
    pairs_all = load_pairs()
    frame_all = pairs_all.frame
    emb_scores = embedding_cosine_scores(frame_all)
    splits = {p: load_protocol(p) for p in PROTOCOLS}

    # 预先加载每个 (protocol, subset) 的评估帧与模型预测
    frames: dict = {}
    preds: dict = {}
    for p in PROTOCOLS:
        for subset in ("validation", "test"):
            fr = pairs_all.subset(splits[p][subset])
            frames[(p, subset)] = fr
            preds[(p, subset)] = {}
            for (m, prot), rec in final_runs.items():
                if prot != p:
                    continue
                npz = Path(ROOT / rec["run_dir"]) / f"predictions_{subset}.npz"
                if npz.exists():
                    data = np.load(npz)
                    preds[(p, subset)][m] = data["pred_scores"].astype(np.float64)

    # ---------------- 基线本地复算一致性校验 + 每查询指标
    baseline_pq: dict = {}
    consistency = []
    for p in PROTOCOLS:
        for subset in ("validation", "test"):
            fr = frames[(p, subset)]
            groups = fr["candidate_id"].to_numpy()
            rel_score = fr["final_score"].to_numpy(np.float64)
            ord_map = {"weak_positive": 1.0, "medium_positive": 2.0, "strong_positive": 3.0}
            rel_ord = fr["label_strength"].map(ord_map).to_numpy(np.float64)
            for b in BASELINES:
                s = local_baseline_scores(
                    b, fr,
                    emb_scores=emb_scores if b == "embedding_cosine" else None,
                    seed=cfg.seed("random_baseline"))
                for mode, rel in (("score", rel_score), ("ordinal", rel_ord)):
                    pq5 = per_query_ndcg(groups, s, rel, k=5)
                    pq10 = per_query_ndcg(groups, s, rel, k=10)
                    baseline_pq[(p, subset, b, mode, 5)] = pq5
                    baseline_pq[(p, subset, b, mode, 10)] = pq10
                    entry = baselines_report[p]["subsets"][subset]["results"][mode][b]
                    src = entry["aggregate"]["size_ge_2"]
                    rep5 = src.get("ndcg@5")
                    local5 = float(np.mean(list(pq5.values()))) if pq5 else None
                    consistency.append({
                        "protocol": p, "subset": subset, "baseline": b, "gain_mode": mode,
                        "report_ndcg@5": rep5, "local_ndcg@5": round(local5, 6) if local5 else None,
                        "abs_diff": (round(abs(rep5 - local5), 9)
                                     if (rep5 is not None and local5 is not None) else None),
                    })
                baseline_pq[(p, subset, b, "pairwise", 0)] = per_query_pairwise_accuracy(
                    groups, s, rel_score, tie_eps=cfg.pairwise_tie_eps)
    max_diff = max((c["abs_diff"] or 0) for c in consistency)
    log.info("[consistency] 基线本地复算 vs 第三阶段报告 最大 |diff| = %.9f", max_diff)

    # ---------------- 模型每查询指标
    model_pq: dict = {}
    for (p, subset), mp in preds.items():
        fr = frames[(p, subset)]
        groups = fr["candidate_id"].to_numpy()
        rel_score = fr["final_score"].to_numpy(np.float64)
        ord_map = {"weak_positive": 1.0, "medium_positive": 2.0, "strong_positive": 3.0}
        rel_ord = fr["label_strength"].map(ord_map).to_numpy(np.float64)
        for m, s in mp.items():
            model_pq[(p, subset, m, "score", 5)] = per_query_ndcg(groups, s, rel_score, k=5)
            model_pq[(p, subset, m, "score", 10)] = per_query_ndcg(groups, s, rel_score, k=10)
            model_pq[(p, subset, m, "ordinal", 5)] = per_query_ndcg(groups, s, rel_ord, k=5)
            model_pq[(p, subset, m, "ordinal", 10)] = per_query_ndcg(groups, s, rel_ord, k=10)
            model_pq[(p, subset, m, "pairwise", 0)] = per_query_pairwise_accuracy(
                groups, s, rel_score, tie_eps=cfg.pairwise_tie_eps)

    # ---------------- Bootstrap：模型 - 基线（test，另附 validation）
    boot_rows = []
    for p in PROTOCOLS:
        for subset in ("test", "validation"):
            for m in MODELS:
                if (p, subset, m, "score", 5) not in model_pq:
                    continue
                for b in BASELINES:
                    for metric, key in (("ndcg@5_score", ("score", 5)),
                                        ("ndcg@5_ordinal", ("ordinal", 5)),
                                        ("pairwise_accuracy", ("pairwise", 0))):
                        a = model_pq[(p, subset, m) + key]
                        bb = baseline_pq[(p, subset, b) + key]
                        res = bootstrap_diff(a, bb, n_boot=cfg.bootstrap_repeats,
                                             seed=cfg.seed("bootstrap"))
                        res.update({"protocol": p, "subset": subset, "model": m,
                                    "baseline": b, "metric": metric})
                        boot_rows.append(res)

    # ---------------- 错误分析（每个模型 x candidate_cold/test）
    error_reports = {}
    for m, s in preds.get(("candidate_cold", "test"), {}).items():
        fr = frames[("candidate_cold", "test")]
        error_reports[m] = analyze_errors(fr, s, tie_eps=cfg.pairwise_tie_eps)

    # ---------------- 消融（validation + test）
    ablation_rows = []
    for (tag, m, p), rec in sorted(ablation_runs.items()):
        dropped = rec.get("ablation_dropped_groups", [])
        full = final_runs.get((m, p))
        row = {"tag": tag, "model": m, "protocol": p, "dropped_groups": dropped,
               "n_features": rec.get("n_features"),
               "validation": rec.get("validation", {}),
               "test": (rec.get("evaluations") or {}).get("test", {})}
        if full:
            row["full_validation"] = full.get("validation", {})
            row["full_test"] = (full.get("evaluations") or {}).get("test", {})
        ablation_rows.append(row)

    # ---------------- 资源占用
    resource_rows = []
    for (m, p), rec in sorted(final_runs.items()):
        run_dir = Path(ROOT / rec["run_dir"])
        size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
        resource_rows.append({
            "model": m, "protocol": p,
            "train_seconds": rec.get("train_seconds"),
            "model_parameters": rec.get("model_parameters"),
            "n_features": rec.get("n_features"),
            "artifact_bytes": int(size),
            "rows": rec.get("rows"),
            # sklearn 估计器固定在 CPU 训练；run 记录里的 device 字段为解析出的 torch 设备
            "device": ("cuda" if m in ("mlp", "ranknet") else "cpu"),
            "device_recorded_in_run": rec.get("device"),
            "inference_seconds_per_pair": ((rec.get("evaluations") or {})
                                           .get("test", {}) or {}).get("inference_seconds_per_pair"),
        })

    results = {
        "generated_by": "scripts/model_training/compare_models.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset_version": cfg.dataset_version,
        "protocols": PROTOCOLS,
        "models": MODELS,
        "baselines": BASELINES,
        "caveats": CAVEATS,
        "baseline_consistency": {"max_abs_diff": max_diff, "rows": consistency},
        "bootstrap": boot_rows,
        "ablation": ablation_rows,
        "error_analysis": error_reports,
        "resources": resource_rows,
        "runs": {f"{m}|{p}": {"run_id": r["run_id"], "run_dir": r["run_dir"],
                              "validation": r.get("validation"),
                              "test": (r.get("evaluations") or {}).get("test")}
                 for (m, p), r in final_runs.items()},
    }
    jdump(results, OUT_DIR / "results.json")

    _write_reports(results, final_runs, baselines_report, frames, preds, baseline_pq,
                   model_pq, cfg, resource_rows, ablation_rows, error_reports, boot_rows,
                   consistency, max_diff)
    log.info("[done] 报告已生成 -> %s（耗时 %.1fs）", OUT_DIR, time.time() - t0)
    return 0


# ------------------------------------------------------------------ 报告生成
def _write_reports(results, final_runs, baselines_report, frames, preds, baseline_pq,
                   model_pq, cfg, resource_rows, ablation_rows, error_reports, boot_rows,
                   consistency, max_diff) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    head = (f"# 第四阶段 4.1 · 人岗匹配模型训练报告\n\n"
            f"- 生成时间：{ts}\n"
            f"- 数据版本：`{cfg.dataset_version}`；协议：candidate_cold / job_cold / double_cold\n"
            f"- 排序查询单位：`candidate_id`（为一个候选人对其候选岗位排序）\n"
            f"- 模型选择指标：`{cfg.selection_metric}`（只看 validation）\n\n"
            f"## 评估语义前提（任何指标都必须与本节一起引用）\n\n" +
            "\n".join(f"{i+1}. {c}" for i, c in enumerate(CAVEATS)) + "\n")

    # ---- experiment-summary.md
    lines = [head, "\n## 一、实验总览\n\n",
             "| 模型 | 协议 | 参数量 | 特征数 | 训练耗时(s) | 最优验证指标 | test NDCG@5(score) | test NDCG@5(ordinal) | test Pairwise Acc |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for (m, p), rec in sorted(final_runs.items()):
        te = (rec.get("evaluations") or {}).get("test", {})
        lines.append(f"| {m} | {p} | {rec.get('model_parameters')} | {rec.get('n_features')} "
                     f"| {rec.get('train_seconds')} | {fmt(rec.get('selection_value'))} "
                     f"| {fmt(te.get('ndcg_at_5_score'))} | {fmt(te.get('ndcg_at_5_ordinal'))} "
                     f"| {fmt(te.get('pairwise_accuracy'))} |")
    lines.append("\n## 二、结论要点\n\n")
    lines.append(_conclusion_text(final_runs, baselines_report, boot_rows))
    (OUT_DIR / "experiment-summary.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- baseline-comparison.md
    det_rows = [c for c in consistency if c["baseline"] != "random_ranking"]
    rnd_rows = [c for c in consistency if c["baseline"] == "random_ranking"]
    max_det = max((c["abs_diff"] or 0) for c in det_rows) if det_rows else 0.0
    max_rnd = max((c["abs_diff"] or 0) for c in rnd_rows) if rnd_rows else 0.0
    bl = [head, "\n## 零训练 Baseline 与监督模型对比（指标直接读取第三阶段报告）\n\n",
          f"基线一致性校验：本地复算每查询 NDCG 与 `reports/baselines/baseline-results.json` "
          f"汇总值的最大绝对差——确定性基线（embedding_cosine / skill_jaccard / "
          f"position_token_overlap）**{max_det:.9f}**（< 1e-6 视为口径一致）；"
          f"random_ranking **{max_rnd:.9f}**，差异来源为第三阶段报告记录多次随机重复的均值、"
          f"本地复算使用固定单种子，属预期差异，不影响确定性方法之间的比较。\n"]
    for p in ("candidate_cold",):
        for subset in ("validation", "test"):
            bl.append(f"\n### 协议 {p} / {subset}\n")
            bl.append("| 方法 | NDCG@5(score) | NDCG@10(score) | NDCG@5(ordinal) | NDCG@10(ordinal) | Pairwise Acc | 来源 |")
            bl.append("|---|---:|---:|---:|---:|---:|---|")
            for b in BASELINES:
                e = baselines_report[p]["subsets"][subset]["results"]
                s5 = e["score"][b]["aggregate"]["size_ge_2"]["ndcg@5"]
                s10 = e["score"][b]["aggregate"]["size_ge_2"]["ndcg@10"]
                o5 = e["ordinal"][b]["aggregate"]["size_ge_2"]["ndcg@5"]
                o10 = e["ordinal"][b]["aggregate"]["size_ge_2"]["ndcg@10"]
                pw = float(np.mean(list(baseline_pq[(p, subset, b, "pairwise", 0)].values())))
                src = ("第三阶段报告 repeated_stats 均值" if b == "random_ranking"
                       else "第三阶段报告")
                bl.append(f"| {b} | {fmt(s5)} | {fmt(s10)} | {fmt(o5)} | {fmt(o10)} | {fmt(pw)} | {src} |")
            for m in MODELS:
                rec = final_runs.get((m, p))
                if not rec:
                    continue
                if subset == "validation":
                    d = rec.get("validation", {})
                else:
                    d = (rec.get("evaluations") or {}).get("test", {})
                bl.append(f"| **{m}** | {fmt(d.get('ndcg_at_5_score'))} | {fmt(d.get('ndcg_at_10_score'))} "
                          f"| {fmt(d.get('ndcg_at_5_ordinal'))} | {fmt(d.get('ndcg_at_10_ordinal'))} "
                          f"| {fmt(d.get('pairwise_accuracy'))} | 本阶段训练 |")
    bl.append("\n## 高分基线（Position Token Overlap）问题分析\n\n")
    bl.append(_high_score_analysis(final_runs, baselines_report, boot_rows))
    bl.append("\n## 相对零训练基线的查询级 Bootstrap 差值区间（test）\n\n")
    bl.append("| 协议 | 模型 | 对比基线 | 指标 | 均值差 | 95% CI | 显著 |")
    bl.append("|---|---|---|---|---:|---|---|")
    for r in boot_rows:
        if r["subset"] != "test" or r["baseline"] not in ("position_token_overlap",
                                                          "skill_jaccard", "random_ranking"):
            continue
        bl.append(f"| {r['protocol']} | {r['model']} | {r['baseline']} | {r['metric']} "
                  f"| {r['mean_diff']} | [{r['ci_low']}, {r['ci_high']}] "
                  f"| {'是' if r.get('significant_at_95') else '否'} |")
    (OUT_DIR / "baseline-comparison.md").write_text("\n".join(bl), encoding="utf-8")

    # ---- ranking-evaluation.md
    rk = [head, "\n## 排序指标明细（三协议 x validation/test，两种增益口径）\n"]
    for p in PROTOCOLS:
        for subset in ("validation", "test"):
            fr = frames[(p, subset)]
            rk.append(f"\n### 协议 {p} / {subset}（{len(fr)} 条记录，"
                      f"{fr['candidate_id'].nunique()} 个查询）\n")
            rk.append("| 方法 | NDCG@5 | NDCG@10 | MRR@5 | Recall@5 | Pairwise Acc | MAE | RMSE | Spearman | Kendall τb |")
            rk.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for m in MODELS:
                rec = final_runs.get((m, p))
                if not rec:
                    continue
                # 从各 run 的 metrics_<subset>.json 读取完整指标（与评估脚本同一来源）
                npz_dir = Path(ROOT / rec["run_dir"])
                mf = npz_dir / f"metrics_{subset}.json"
                if mf.exists():
                    rep = jload(mf)
                    g = rep["gain_modes"]["ordinal"]["size_ge_2"]
                    rk.append(f"| {m} (ordinal) | {fmt(g['ndcg@5'])} | {fmt(g['ndcg@10'])} "
                              f"| {fmt(g.get('mrr@5'))} | {fmt(g.get('recall@5'))} "
                              f"| {fmt(rep['pairwise']['pairwise_accuracy'])} "
                              f"| {fmt(rep['regression']['mae'])} | {fmt(rep['regression']['rmse'])} "
                              f"| {fmt(rep['regression']['spearman'])} "
                              f"| {fmt(rep['regression']['kendall_tau_b'])} |")
                    g2 = rep["gain_modes"]["score"]["size_ge_2"]
                    rk.append(f"| {m} (score) | {fmt(g2['ndcg@5'])} | {fmt(g2['ndcg@10'])} "
                              f"| {fmt(g2.get('mrr@5'))} | {fmt(g2.get('recall@5'))} "
                              f"| {fmt(rep['pairwise']['pairwise_accuracy'])} | - | - | - | - |")
    rk.append("\n## 指标口径\n\n"
              "- NDCG@K：`min(K, 组内候选数)` 截断，tie-breaking 稳定排序，与第三阶段一致；\n"
              "- Pairwise Accuracy：组内 final_score 差 > "
              f"{cfg.pairwise_tie_eps} 的对中预测顺序正确比例，先按查询求均值再宏平均；\n"
              "- Spearman / Kendall：整体样本相关；查询级 Spearman 见各 run 的 metrics 文件；\n"
              "- Recall@K / MRR@K 的二值相关项定义：`label_strength in {medium_positive, strong_positive}`（代理定义）。\n")
    (OUT_DIR / "ranking-evaluation.md").write_text("\n".join(rk), encoding="utf-8")

    # ---- ablation-study.md
    ab = [head, "\n## 特征组消融（整体移除一组高度关联的特征，避免只删一列留下等价信息）\n\n",
          "| 消融 | 模型 | 协议 | 移除组 | 特征数 | val NDCG@5(ordinal) | test NDCG@5(ordinal) | test Pairwise Acc |",
          "|---|---|---|---|---:|---:|---:|---:|"]
    for row in ablation_rows:
        full_tag = "全特征对照" if not row["dropped_groups"] else "+".join(row["dropped_groups"])
        ab.append(f"| {row['tag']} | {row['model']} | {row['protocol']} | {full_tag} "
                  f"| {row['n_features']} | {fmt(row['validation'].get('ndcg_at_5_ordinal'))} "
                  f"| {fmt(row['test'].get('ndcg_at_5_ordinal'))} "
                  f"| {fmt(row['test'].get('pairwise_accuracy'))} |")
    ab.append("\n说明：skill/position/category 组的成员见 `configs/training/common.yaml` "
              "（skill=技能重合 4 列；position=职位名称词元重合 + 目标职位 one-hot；"
              "category=类别一致性 + 双侧类别 one-hot）。experience 组只有 years_experience 一列，"
              "移除后无模型可用特征时不单独消融。\n")
    (OUT_DIR / "ablation-study.md").write_text("\n".join(ab), encoding="utf-8")

    # ---- error-analysis.md
    ea = [head, "\n## 预测错误分类（candidate_cold / test，每个查询取最大反序差的一对）\n"]
    for m, rep in error_reports.items():
        ea.append(f"\n### 模型 {m}\n")
        ea.append(f"- 偏好对总数 {rep['preference_pairs_total']}，"
                  f"反序对 {rep['preference_pairs_misordered']}（错误率 {rep['pair_error_rate']}）")
        ea.append(f"- 查询总数 {rep['queries_total']}，出现反序的查询 {rep['queries_with_error']}"
                  f"（{rep['query_error_rate']}）\n")
        ea.append("| 错误类别 | 查询数 |")
        ea.append("|---|---:|")
        for c, n in rep["category_counts_worst_pair_per_query"].items():
            ea.append(f"| {c} | {n} |")
    ea.append("\n样本展示只含 pair_index / job_id / 特征值 / 代理标签，"
              "不含简历正文与 JD 原文（完整样本见 `reports/model-training/results.json`）。\n")
    (OUT_DIR / "error-analysis.md").write_text("\n".join(ea), encoding="utf-8")

    # ---- resource-usage.md
    rs = [head, "\n## 训练与推理资源占用\n\n",
          "| 模型 | 协议 | 训练耗时(s) | 参数量 | 特征数 | 产物体积(KB) | 设备 | 推理单对耗时(s) |",
          "|---|---|---:|---:|---:|---:|---|---:|"]
    for r in resource_rows:
        rs.append(f"| {r['model']} | {r['protocol']} | {r['train_seconds']} "
                  f"| {r['model_parameters']} | {r['n_features']} "
                  f"| {round((r['artifact_bytes'] or 0) / 1024, 1)} | {r['device']} "
                  f"| {fmt(r.get('inference_seconds_per_pair'), 8)} |")
    rs.append("\n说明：RTX 2050（4GB）训练 MLP / RankNet；Ridge / GradientBoosting 使用 CPU（sklearn）。"
              "模型规模按 4GB 显存约束选择轻量结构，未为占满显存而扩大网络。"
              "表中设备列为实际计算设备；部分历史 run 记录（reports/model-training/runs/*.json）中的 "
              "`device` 字段记录的是解析出的 torch 设备，对 sklearn 模型不适用。\n")
    (OUT_DIR / "resource-usage.md").write_text("\n".join(rs), encoding="utf-8")


def _conclusion_text(final_runs, baselines_report, boot_rows) -> str:
    cc = "candidate_cold"
    te = {(m): (r.get("evaluations") or {}).get("test", {})
          for (m, p), r in final_runs.items() if p == cc}
    base = baselines_report[cc]["subsets"]["test"]["results"]["ordinal"]
    pto = base["position_token_overlap"]["aggregate"]["size_ge_2"]["ndcg@5"]
    best_m, best_v = None, None
    for m, d in te.items():
        v = d.get("ndcg_at_5_ordinal")
        if v is not None and (best_v is None or v > best_v):
            best_m, best_v = m, v
    diff = (best_v - pto) if (best_v is not None and pto is not None) else None
    sig = [r for r in boot_rows if r["subset"] == "test" and r["protocol"] == cc
           and r["baseline"] == "position_token_overlap" and r["metric"] == "ndcg@5_ordinal"
           and r["model"] == best_m]
    sig_txt = (f"，95% CI [{sig[0]['ci_low']}, {sig[0]['ci_high']}]，"
               f"{'统计上显著' if sig[0]['significant_at_95'] else '不显著'}") if sig else ""
    return (f"- 与第三阶段零训练 Baseline 相比，监督模型在 candidate_cold/test 上"
            f"最优为 **{best_m}**（ordinal NDCG@5 = {fmt(best_v)}），"
            f"Position Token Overlap 基线为 {fmt(pto)}，绝对差 {fmt(diff)}{sig_txt}。\n"
            f"- 回归模型（Ridge / GB）与成对排序模型（RankNet）的差异见 "
            f"`baseline-comparison.md` 与 `ranking-evaluation.md`。\n"
            f"- 全部结论只描述「与原系统代理偏好的一致程度」，不代表真实就业推荐效果。\n")


def _high_score_analysis(final_runs, baselines_report, boot_rows) -> str:
    cc = "candidate_cold"
    base = baselines_report[cc]["subsets"]["test"]["results"]["ordinal"]
    pto = base["position_token_overlap"]["aggregate"]["size_ge_2"]["ndcg@5"]
    rows = []
    for (m, p), rec in sorted(final_runs.items()):
        if p != cc:
            continue
        d = (rec.get("evaluations") or {}).get("test", {})
        v = d.get("ndcg_at_5_ordinal")
        lat = d.get("inference_seconds_per_pair")
        b = next((r for r in boot_rows if r["subset"] == "test" and r["protocol"] == cc
                  and r["baseline"] == "position_token_overlap"
                  and r["metric"] == "ndcg@5_ordinal" and r["model"] == m), None)
        rows.append(f"- **{m}**：ordinal NDCG@5 = {fmt(v)}，相对 Position Token Overlap 差 "
                    f"{fmt(v - pto if v is not None else None)}；"
                    + (f"95% CI [{b['ci_low']}, {b['ci_high']}]，"
                       f"{'显著' if b['significant_at_95'] else '不显著'}" if b else "无 Bootstrap")
                    + f"；单对推理 {fmt(lat, 8)}s。")
    return ("\n".join(rows) +
            "\n\n判定口径：① 绝对提升是否 > Bootstrap 置信区间下界；"
            "② 是否以明显更慢的推理与更复杂的模型为代价；"
            "③ 若无显著提升，应解释为「模型只学到代理评分系统中已被 "
            "position_token_overlap 等简单特征覆盖的部分」，而不是宣称模型无效或有效。\n")


if __name__ == "__main__":
    raise SystemExit(main())
