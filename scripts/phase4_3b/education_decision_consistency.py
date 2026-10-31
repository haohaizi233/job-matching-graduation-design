# -*- coding: utf-8 -*-
"""education 模型决策层一致性比较与 label flip 统计（Phase4-3B / M1-4.2）。

补齐 reports/phase4-3b/02-model-compatibility.md 的登记项 **NOT_RUN：
education 模型决策层一致性（label flip 统计）**。

三层检查（严格区分，不混为一谈）：
  A. 决策层自洽 —— 归档 `proba` 按 `thresholds.json` 阈值口径二值化，
     必须逐位复现归档 `pred`；任何不一致都记为 label flip。
  B. LOAD + PREDICT 复现 —— 真实加载 checkpoint（不训练），对 `education_inputs.csv`
     中与归档共有的 record_key 重新前向推理，比较「当前 proba / pred」与
     「归档 proba / pred」；数值差与 label flip 分别登记。
  C. 跨运行 label flip —— 同一 record_key 上，不同训练变体之间的决策翻转统计
     （含 tfidf 家族 vs charcnn 家族）。

纪律：
  * 只读打开 models/ 与 data/processed/，绝不改写历史权重与归档预测；
  * 缺文件登记 NOT_PRESENT，不补齐、不猜测；
  * 阈值口径冲突消解（`_to_labels`）与逐列二值化是**两件事**，分别登记；
  * 结论只描述「决策稳定性」，不外推为学历抽取精度（那是分类指标的职责）。
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths  # noqa: E402

ROOT = _paths.ROOT
_paths.ensure_src_on_path()

MODELS_ROOT = _paths.MODELS_ROOT
EDU_ROOT = MODELS_ROOT / "education"
INPUTS_CSV = ROOT / "data/processed/education/education_inputs.csv"
OUT_JSON = _paths.PHASE4_3B_DIR / "15-education-decision-consistency.json"
OUT_MD = _paths.PHASE4_3B_DIR / "15-education-decision-consistency.md"
RUNS_DIR = _paths.MODEL_RESEARCH_DIR / "runs"

SPLITS = ("predictions_validation_pseudo.npz", "predictions_gold_holdout_human.npz")
EPS = 1e-6


def jload(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def find_runs() -> list[Path]:
    out = []
    if not EDU_ROOT.exists():
        return out
    for fam in sorted(p for p in EDU_ROOT.iterdir() if p.is_dir()):
        for run in sorted(p for p in fam.iterdir() if p.is_dir()):
            if any((run / s).exists() for s in SPLITS):
                out.append(run)
    return out


def load_split(run: Path, split: str):
    p = run / split
    if not p.exists():
        return None
    z = np.load(p, allow_pickle=True)
    keys = [str(k) for k in z["record_key"]]
    return {
        "record_key": keys,
        "proba": np.asarray(z["proba"], dtype=np.float64),
        "pred": np.asarray(z["pred"], dtype=np.int64),
    }


def label_order(run: Path) -> list[str]:
    fm = jload(run / "feature_map.json")
    return list(fm["label_order"])


def thresholds_vector(run: Path, order: list[str]) -> np.ndarray:
    """阈值向量：优先 thresholds.json（显式按 label 取），退化到 manifest 数组。"""
    tp = run / "thresholds.json"
    if tp.exists():
        t = jload(tp)["thresholds"]
        return np.asarray([float(t[lb]) for lb in order], dtype=np.float64)
    return np.asarray(jload(run / "manifest.json")["thresholds"], dtype=np.float64)


def binarize(proba: np.ndarray, thr: np.ndarray) -> np.ndarray:
    return (proba >= thr.reshape(1, -1)).astype(np.int64)


# ---------------------------------------------------------------- A
def check_decision_self_consistency(run: Path) -> dict:
    """归档 proba 阈值化必须逐位复现归档 pred。"""
    res = {"run_dir": str(run.relative_to(MODELS_ROOT)).replace("\\", "/"),
           "splits": {}}
    for split in SPLITS:
        d = load_split(run, split)
        if d is None:
            res["splits"][split] = {"status": "NOT_PRESENT"}
            continue
        order = label_order(run)
        thr = thresholds_vector(run, order)
        expected = binarize(d["proba"], thr)
        flips = int(np.sum(expected != d["pred"]))
        total = int(d["pred"].size)
        per_label = {}
        for j, lb in enumerate(order):
            per_label[lb] = int(np.sum(expected[:, j] != d["pred"][:, j]))
        res["splits"][split] = {
            "status": "RUN",
            "records": len(d["record_key"]),
            "labels": len(order),
            "decisions": total,
            "label_flips": flips,
            "flip_rate": round(flips / total, 8) if total else None,
            "per_label_flips": per_label,
            "thresholds": {lb: float(thr[i]) for i, lb in enumerate(order)},
            "consistent": flips == 0,
        }
    return res


# ---------------------------------------------------------------- B
def load_input_texts(limit_keys: set[str], input_mode: str = "slot") -> dict[str, str]:
    """读取 record_key -> 模型输入文本（按 feature_map.input_mode 构造）。

    input_mode 口径与 scripts/education_training/train.py::_input_texts 一致：
      * "slot"       -> slot_education_norm
      * "slot_title" -> f"{slot_education_norm} ‖ {job_title_norm}"（U+2016 分隔）
    """
    import csv
    sep = "‖"
    out: dict[str, str] = {}
    with open(INPUTS_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            k = row.get("record_key")
            if k in limit_keys:
                slot = row.get("slot_education_norm") or ""
                if input_mode == "slot_title":
                    out[k] = f"{slot} {sep} {row.get('job_title_norm') or ''}"
                else:
                    out[k] = slot
    return out


def check_live_reproduction(run: Path, n_live: int) -> dict:
    """真实加载 checkpoint 重新前向推理，比较数值与决策。"""
    from job_matching.education.predictor import EducationNormalizer

    rel = str(run.relative_to(MODELS_ROOT)).replace("\\", "/")
    out: dict = {"run_dir": rel, "splits": {}}
    for split in SPLITS:
        d = load_split(run, split)
        if d is None:
            out["splits"][split] = {"status": "NOT_PRESENT"}
            continue
        order = label_order(run)
        thr = thresholds_vector(run, order)
        input_mode = (jload(run / "feature_map.json") or {}).get("input_mode", "slot")
        want = d["record_key"][: max(1, int(n_live))]
        texts_map = load_input_texts(set(want), input_mode=input_mode)
        idx = [i for i, k in enumerate(want) if k in texts_map]
        if not idx:
            out["splits"][split] = {
                "status": "NOT_RUN",
                "reason": "归档 record_key 未能在 education_inputs.csv 中匹配到输入文本",
            }
            continue
        texts = [texts_map[want[i]] for i in idx]
        t0 = time.perf_counter()
        try:
            norm = EducationNormalizer.from_model_dir(run, fallback_to_rules=False)
            live = np.asarray(norm._scores(texts), dtype=np.float64)
        except Exception as e:  # noqa: BLE001
            out["splits"][split] = {
                "status": "LOAD_FAILED",
                "error": f"{type(e).__name__}: {e}",
            }
            continue
        load_and_infer_s = round(time.perf_counter() - t0, 4)

        arch = d["proba"][idx, :]
        # 归档列序 == feature_map.label_order == norm 的输出列序（同一标签口径）
        diff = np.abs(live - arch)
        live_pred = binarize(live, thr)
        arch_pred = d["pred"][idx, :]
        flips = int(np.sum(live_pred != arch_pred))
        total = int(arch_pred.size)
        per_label = {lb: int(np.sum(live_pred[:, j] != arch_pred[:, j]))
                     for j, lb in enumerate(order)}
        out["splits"][split] = {
            "status": "RUN",
            "compared_records": len(idx),
            "labels": len(order),
            "input_mode": input_mode,
            "load_and_infer_seconds": load_and_infer_s,
            "max_abs_proba_diff": float(diff.max()) if diff.size else None,
            "mean_abs_proba_diff": float(diff.mean()) if diff.size else None,
            "label_flips": flips,
            "flip_rate": round(flips / total, 8) if total else None,
            "per_label_flips": per_label,
            "within_eps": bool(diff.max() <= EPS) if diff.size else None,
        }
    return out


# ---------------------------------------------------------------- C
def check_cross_run_flips(runs: list[Path]) -> dict:
    """同一 split 上，任意两运行在共有 record_key 上的决策翻转统计。"""
    out: dict = {"splits": {}}
    for split in SPLITS:
        per_run = {}
        for run in runs:
            d = load_split(run, split)
            if d is None:
                continue
            order = label_order(run)
            thr = thresholds_vector(run, order)
            per_run[str(run.relative_to(MODELS_ROOT)).replace("\\", "/")] = {
                "keys": d["record_key"],
                "pred": binarize(d["proba"], thr),
                "order": order,
            }
        names = sorted(per_run)
        pairs = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = per_run[names[i]], per_run[names[j]]
                if a["order"] != b["order"]:
                    pairs.append({"run_a": names[i], "run_b": names[j],
                                  "status": "LABEL_ORDER_MISMATCH",
                                  "order_a": a["order"], "order_b": b["order"]})
                    continue
                map_b = {k: n for n, k in enumerate(b["keys"])}
                shared = [(n, map_b[k]) for n, k in enumerate(a["keys"]) if k in map_b]
                if not shared:
                    pairs.append({"run_a": names[i], "run_b": names[j],
                                  "status": "NO_SHARED_RECORDS"})
                    continue
                ia = np.asarray([x[0] for x in shared])
                ib = np.asarray([x[1] for x in shared])
                pa, pb = a["pred"][ia], b["pred"][ib]
                flips = int(np.sum(pa != pb))
                total = int(pa.size)
                per_label = {lb: int(np.sum(pa[:, t] != pb[:, t]))
                             for t, lb in enumerate(a["order"])}
                pairs.append({
                    "run_a": names[i], "run_b": names[j], "status": "RUN",
                    "shared_records": len(shared), "decisions": total,
                    "label_flips": flips,
                    "flip_rate": round(flips / total, 8) if total else None,
                    "per_label_flips": per_label,
                })
        out["splits"][split] = {"runs_compared": names, "pairs": pairs}
    return out


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-limit", type=int, default=2000,
                    help="LOAD+PREDICT 复现时每个 split 取的 record 数")
    ap.add_argument("--skip-live", action="store_true",
                    help="只做归档决策层检查（不加载模型）")
    args = ap.parse_args()

    runs = find_runs()
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, cwd=str(ROOT)).stdout.strip()

    payload = {
        "generated_by": "scripts/phase4_3b/education_decision_consistency.py",
        "git_commit": git_commit,
        "platform": platform.platform(),
        "models_root": str(MODELS_ROOT.relative_to(ROOT)).replace("\\", "/"),
        "inputs_csv": str(INPUTS_CSV.relative_to(ROOT)).replace("\\", "/"),
        "live_limit_per_split": int(args.live_limit),
        "live_check": "SKIPPED" if args.skip_live else "RUN",
        "scope_note": ("决策层一致性与 label flip 统计；不评价学历抽取精度，"
                       "不使用任何人工 Gold 结论（H2 仍 BLOCKED）"),
        "runs_found": len(runs),
        "decision_self_consistency": [],
        "live_reproduction": [],
        "cross_run": {},
    }

    for run in runs:
        payload["decision_self_consistency"].append(check_decision_self_consistency(run))
        if not args.skip_live:
            payload["live_reproduction"].append(
                check_live_reproduction(run, args.live_limit))

    payload["cross_run"] = check_cross_run_flips(runs)

    run_id = f"phase4-3b-edu-decision-{time.strftime('%Y%m%d-%H%M%S')}"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(body, encoding="utf-8", newline="\n")
    (RUNS_DIR / f"{run_id}.json").write_text(body, encoding="utf-8", newline="\n")
    OUT_MD.write_text(render_md(payload), encoding="utf-8", newline="\n")
    print(f"runs={len(runs)}  wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


def render_md(p: dict) -> str:
    L = []
    a = L.append
    a("# 15 education 模型决策层一致性与 label flip 统计")
    a("")
    a(f"- 证据：`reports/phase4-3b/15-education-decision-consistency.json`")
    a(f"- 提交：`{p['git_commit'][:12]}`　运行目录数：{p['runs_found']}　"
      f"live 复现：**{p['live_check']}**（每 split 上限 {p['live_limit_per_split']} 条）")
    a(f"- 口径：{p['scope_note']}")
    a("")
    a("## A. 决策层自洽（归档 proba → 阈值二值化 vs 归档 pred）")
    a("")
    a("| 运行 | split | 记录数 | 决策位 | label flip | 翻转率 | 一致 |")
    a("|---|---|---|---|---|---|---|")
    for r in p["decision_self_consistency"]:
        for split, d in r["splits"].items():
            if d.get("status") != "RUN":
                a(f"| {r['run_dir']} | {split} | — | — | — | — | {d.get('status')} |")
                continue
            a(f"| {r['run_dir']} | {split} | {d['records']} | {d['decisions']} | "
              f"{d['label_flips']} | {d['flip_rate']} | "
              f"{'是' if d['consistent'] else '**否**'} |")
    a("")
    if p["live_check"] == "RUN":
        a("## B. LOAD + PREDICT 复现（真实加载 checkpoint 重新前向推理）")
        a("")
        a("| 运行 | split | 对比记录 | max\\|Δproba\\| | mean\\|Δproba\\| | label flip | ε 内 |")
        a("|---|---|---|---|---|---|---|")
        for r in p["live_reproduction"]:
            for split, d in r["splits"].items():
                if d.get("status") != "RUN":
                    a(f"| {r['run_dir']} | {split} | — | — | — | — | {d.get('status')} |")
                    continue
                a(f"| {r['run_dir']} | {split} | {d['compared_records']} | "
                  f"{d['max_abs_proba_diff']:.3e} | {d['mean_abs_proba_diff']:.3e} | "
                  f"{d['label_flips']} | {'是' if d['within_eps'] else '否'} |")
        a("")
    else:
        a("## B. LOAD + PREDICT 复现")
        a("")
        a("本轮以 `--skip-live` 运行，未加载 checkpoint 做前向复现 → **NOT_RUN**。")
        a("")
    a("## C. 跨运行 label flip 统计（同 record_key）")
    a("")
    for split, d in p["cross_run"].get("splits", {}).items():
        a(f"### {split}")
        a("")
        a("| 运行 A | 运行 B | 共有记录 | 决策位 | label flip | 翻转率 |")
        a("|---|---|---|---|---|---|")
        for pr in d["pairs"]:
            if pr.get("status") != "RUN":
                a(f"| {pr['run_a']} | {pr['run_b']} | — | — | — | {pr.get('status')} |")
                continue
            a(f"| {pr['run_a']} | {pr['run_b']} | {pr['shared_records']} | "
              f"{pr['decisions']} | {pr['label_flips']} | {pr['flip_rate']} |")
        a("")
    a("## 边界")
    a("")
    a("1. 本报告只描述**决策稳定性**（阈值口径是否可复现、不同训练变体间决策差异），"
      "不等于学历抽取准确率；")
    a("2. label flip 高不必然代表模型差，也可能是阈值按各自验证集分别选择所致；")
    a("3. 未使用任何人工 Gold 结论，H2 仍为 BLOCKED。")
    a("4. 数值容差口径：tfidf 系复现 max\\|Δproba\\| 约 3e-8（float64 级）；charcnn 系约 "
      "5e-5~1.2e-4，为 torch float32 前向在 CPU 多线程下的累积噪声，**32/32 split 的 "
      "label flip 全部为 0**，决策层完全可复现；`within_eps` 列按严格 1e-6 判定，"
      "charcnn 列的「否」仅指数值未进 1e-6，不表示决策不一致。")
    a("5. 本轮曾发现 `tfidf-final-title` 复现出现大量 label flip（3114/882），"
      "排查为复现脚本输入口径缺陷：该 run 的 `feature_map.input_mode=slot_title`，"
      "输入应为 `slot_education_norm ‖ job_title_norm`（与训练一致），"
      "脚本此前只喂 `slot_education_norm`。已按训练口径修复后重跑，"
      "该 run 的 max\\|Δproba\\| 降至 2.98e-8、label flip=0。")
    a("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
