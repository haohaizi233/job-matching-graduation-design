# -*- coding: utf-8 -*-
"""学历数据集的整合、去重、金标准隔离与重新划分（第三阶段 3.2.2，验收项 P3-09）。

实测事实（2026-10-28）：
  * default/test 完全被 default/validation 包含（job_id 100% 重合），不能直接用作测试集；
  * annotated/2w_0716_eval.csv 中 人工正确结果 非空的 736 行是人工金标准；
  * test.assistant 非空的 736 行与 人工正确结果 逐行相同（736/736），故 test 的可用标签
    就是这 736 条金标准，不再重复登记；
  * 金标准输入与 default/validation 的输入 100% 存在交叉（job_id 736/736、规范化文本 702/736）。

处置：
  * 金标准 736 条整体隔离为 gold_holdout，只做一次性最终评估；
  * 开发池 = default/train + default/validation 的伪标注样本，先剔除与金标准输入重复的行，
    再按输入文本哈希分组切分 train / validation，保证输入文本在集合间完全互斥；
  * 无法构建独立可信的 test：伪标签可信度低（人工复核一致率 45.92%），且原 test ⊂ validation。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from .core import (PIPELINE_VERSION, get_logger, jdump, norm_text, rel,
                   sha256_file, sha256_text, write_csv)
from .preprocess_education import normalize_label, parse_user_segments

SPLIT_ORDER = ["train", "validation"]


def _record_key(job_id, user_hash: str) -> str:
    return sha256_text(f"{str(job_id)}\x1f{user_hash}")[:16]


def _read_labels(path: Path, label_col: str, provenance: str, is_gold: bool,
                 chunksize: int = 20000, only_gold: bool = False,
                 extra_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    """分块读取一份学历 CSV，产出规范化记录（不含原文，只保留哈希与槽位）。"""
    usecols = ["job_id", "user", label_col] + [c for c in extra_cols]
    usecols = [c for c in usecols if c]
    pieces: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=usecols, encoding="utf-8-sig",
                             low_memory=False, chunksize=chunksize):
        if only_gold:
            chunk = chunk[chunk[label_col].notna()]
            if len(chunk) == 0:
                continue
        segs = chunk["user"].map(parse_user_segments)
        user_norm = segs.map(lambda d: d["user_norm"])
        user_hash = user_norm.map(sha256_text)
        labels = chunk[label_col].map(normalize_label)
        rec = pd.DataFrame({
            "job_id": chunk["job_id"].astype(str).to_numpy(),
            "user_hash": user_hash.to_numpy(),
            "user_len": segs.map(lambda d: d["user_len"]).to_numpy(),
            "slot_education_norm": segs.map(lambda d: d["slot_education_norm"]).to_numpy(),
            "slot_present": segs.map(lambda d: d["slot_present"]).astype(int).to_numpy(),
            "job_title_norm": segs.map(lambda d: d["job_title_norm"]).to_numpy(),
            "label_raw": chunk[label_col].astype(str).to_numpy(),
            "label_tokens_json": labels.map(
                lambda d: __import__("json").dumps(d["tokens"], ensure_ascii=False)).to_numpy(),
            "label_multi_hot": labels.map(lambda d: "".join(str(x) for x in d["multi_hot"])).to_numpy(),
            "label_status": labels.map(lambda d: d["status"]).to_numpy(),
            "unresolved_tokens_json": labels.map(
                lambda d: __import__("json").dumps(d["unresolved"], ensure_ascii=False)).to_numpy(),
            "label_provenance": provenance,
            "is_gold": int(is_gold),
            "source_file": rel(path),
        })
        for c in extra_cols:
            if c in chunk.columns:
                rec[c] = chunk[c].astype(str).to_numpy()
        pieces.append(rec)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def build_education_table(cfg) -> tuple[pd.DataFrame, dict]:
    """整合 default/train、default/validation 与 annotated 金标准，产出统一记录表。"""
    log = get_logger()
    t0 = time.time()

    tr = _read_labels(cfg.src("education", "train"), "assistant", "pseudo_online", False)
    va = _read_labels(cfg.src("education", "validation"), "assistant", "pseudo_online", False)
    gold = _read_labels(cfg.src("education", "annotated"), "人工正确结果", "human_gold", True,
                        extra_cols=("线上学历-旧的", "模型结果-新的"))
    te = _read_labels(cfg.src("education", "test"), "assistant", "pseudo_online", False,
                      only_gold=True)

    tr["source_split"] = "default_train"
    va["source_split"] = "default_validation"
    gold["source_split"] = "annotated_gold"
    te["source_split"] = "default_test_gold"

    # 校验 test 的金标准行与 annotated 金标准完全一致（实测 736/736）
    gold_keys = set(gold["user_hash"])
    te_keys = set(te["user_hash"])
    gold_identity = {
        "test_gold_rows": int(len(te)),
        "annotated_gold_rows": int(len(gold)),
        "same_user_hash_sets": gold_keys == te_keys,
    }

    table = pd.concat([tr, va, gold], ignore_index=True, sort=False)
    table["record_key"] = [_record_key(j, h) for j, h in
                           zip(table["job_id"], table["user_hash"])]

    stats = {
        "source_rows": {
            "default_train": int(len(tr)),
            "default_validation": int(len(va)),
            "default_test_total": 22730,
            "default_test_with_gold_label": int(len(te)),
            "annotated_gold": int(len(gold)),
            "annotated_total": 22730,
        },
        "gold_identity_check": gold_identity,
        "merged_rows": int(len(table)),
    }
    log.info("[学历] 合并 %d 行（train %d + val %d + gold %d），耗时 %.1fs",
             len(table), len(tr), len(va), len(gold), time.time() - t0)
    return table, stats


# ------------------------------------------------------------------ 重复与冲突
def analyze_duplicates(table: pd.DataFrame) -> dict:
    """重复检查：ID / 输入文本 / (ID,输入) / 完整记录 / 标签冲突。"""
    out: dict = {}
    out["rows"] = int(len(table))
    out["job_id_duplicated_rows"] = int(table["job_id"].duplicated().sum())
    out["user_hash_duplicated_rows"] = int(table["user_hash"].duplicated().sum())
    out["record_key_duplicated_rows"] = int(table["record_key"].duplicated().sum())
    out["unique_job_id"] = int(table["job_id"].nunique())
    out["unique_user_hash"] = int(table["user_hash"].nunique())

    # 相同输入 -> 不同标签（标签冲突）
    g = table.groupby("user_hash")["label_tokens_json"].nunique()
    conflict_hashes = set(g[g > 1].index)
    out["input_groups_with_label_conflict"] = int(len(conflict_hashes))
    out["rows_in_label_conflict_groups"] = int(table["user_hash"].isin(conflict_hashes).sum())

    # 跨来源交叉
    by_src = {s: set(sub["user_hash"]) for s, sub in table.groupby("source_split")}
    keys = list(by_src)
    cross = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            cross[f"{a}&{b}"] = int(len(by_src[a] & by_src[b]))
    out["cross_source_input_overlap"] = cross
    out["_conflict_hashes"] = conflict_hashes
    return out


def build_education_splits(table: pd.DataFrame, cfg) -> tuple[dict, pd.DataFrame]:
    """金标准隔离 + 开发池按输入文本哈希分组切分。"""
    log = get_logger()
    seed = cfg.seed("split_education")
    dup = analyze_duplicates(table)
    conflict_hashes = dup.pop("_conflict_hashes")

    gold = table[table["is_gold"] == 1].copy()
    gold_hashes = set(gold["user_hash"])

    dev = table[table["is_gold"] == 0].copy()
    n_dev_raw = len(dev)

    # 1) 与金标准输入重复的开发行 -> 剔除（保留真实金标准做最终独立评估）
    overlap_gold = dev["user_hash"].isin(gold_hashes)
    dev_gold_overlap = dev[overlap_gold].copy()
    dev = dev[~overlap_gold]

    # 2) 标签冲突的输入组 -> 剔除并单独登记
    conflict_mask = dev["user_hash"].isin(conflict_hashes)
    dev_conflict = dev[conflict_mask].copy()
    dev = dev[~conflict_mask]

    # 3) 输入文本重复 -> 每个 user_hash 只保留一条（确定性：按 record_key 升序）
    dev = dev.sort_values("record_key", kind="mergesort").reset_index(drop=True)
    dup_mask = dev["user_hash"].duplicated(keep="first")
    dev_dup = dev[dup_mask].copy()
    dev = dev[~dup_mask].reset_index(drop=True)

    # 4) 按 user_hash 分组做 80/20 切分（组 = 输入文本，保证输入不跨集合）
    ratios = {"train": 0.8, "validation": 0.2}
    sizes = dev.groupby("user_hash").size()
    total = float(sizes.sum())
    ids = list(sizes.index)
    rng = np.random.default_rng(seed)
    order = [ids[i] for i in rng.permutation(len(ids))]
    targets = {k: ratios[k] * total for k in SPLIT_ORDER}
    current = {k: 0.0 for k in SPLIT_ORDER}
    assign: dict[str, str] = {}
    size_map = sizes.to_dict()
    for g in order:
        best_key, best_val = SPLIT_ORDER[0], -np.inf
        for k in SPLIT_ORDER:
            t = targets[k]
            v = ((t - current[k]) / t) if t > 0 else 0.0
            if v > best_val:
                best_key, best_val = k, v
        assign[g] = best_key
        current[best_key] += float(size_map[g])
    dev["split"] = dev["user_hash"].map(assign)

    gold = gold.copy()
    gold["split"] = "gold_holdout"
    gold = gold.sort_values("record_key", kind="mergesort").reset_index(drop=True)

    dev_gold_overlap["split"] = "excluded_gold_input_overlap"
    dev_conflict["split"] = "excluded_label_conflict"
    dev_dup["split"] = "excluded_input_duplicate"
    excluded = pd.concat([dev_gold_overlap, dev_conflict, dev_dup], ignore_index=True,
                         sort=False)

    splits = {}
    for s in SPLIT_ORDER:
        sub = dev[dev["split"] == s]
        splits[s] = {
            "rows": int(len(sub)),
            "unique_job_id": int(sub["job_id"].nunique()),
            "unique_user_hash": int(sub["user_hash"].nunique()),
            "label_status_counts": sub["label_status"].value_counts().to_dict(),
            "label_distribution": sub["label_tokens_json"].value_counts().head(15).to_dict(),
            "label_provenance": sub["label_provenance"].value_counts().to_dict(),
            "slot_present_ratio": round(float(sub["slot_present"].mean()), 6) if len(sub) else 0.0,
        }
    splits["gold_holdout"] = {
        "rows": int(len(gold)),
        "unique_job_id": int(gold["job_id"].nunique()),
        "unique_user_hash": int(gold["user_hash"].nunique()),
        "label_status_counts": gold["label_status"].value_counts().to_dict(),
        "label_distribution": gold["label_tokens_json"].value_counts().head(15).to_dict(),
        "label_provenance": {"human_gold": int(len(gold))},
        "slot_present_ratio": round(float(gold["slot_present"].mean()), 6) if len(gold) else 0.0,
    }

    # ---- 互斥性检查
    def pairwise(col):
        sets = {s: set(dev.loc[dev["split"] == s, col]) for s in SPLIT_ORDER}
        sets["gold_holdout"] = set(gold[col])
        keys = list(sets)
        return {f"{a}&{b}": int(len(sets[a] & sets[b]))
                for i, a in enumerate(keys) for b in keys[i + 1:]}

    overlap_check = {
        "user_hash_overlap": pairwise("user_hash"),
        "job_id_overlap": pairwise("job_id"),
        "record_key_overlap": pairwise("record_key"),
    }

    gold_iso = {
        "gold_rows": int(len(gold)),
        "dev_rows_removed_due_to_gold_input_overlap": int(len(dev_gold_overlap)),
        "gold_input_hashes": int(len(gold_hashes)),
        "dev_input_hashes_touching_gold_after_removal": int(
            len(set(dev["user_hash"]) & gold_hashes)),
        "gold_label_provenance": "human_gold（人工正确结果，736 条）",
        "gold_used_for_rule_fitting": False,
        "gold_eval_policy": "只做一次性最终评估；规则定义与阈值在开发集上确定后锁定，不对金标准反复调参",
    }

    manifest = {
        "generated_by": "src/job_matching/education_data.py",
        "pipeline_version": PIPELINE_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seed": seed,
        "ratios": ratios,
        "group_key": "user_hash（规范化输入文本）",
        "group_key_reason": "job_id 在 train 中并非严格唯一（43 行重复），而输入文本重复率 6.5%；"
                            "按 user_hash 分组可同时保证输入文本与记录键在集合间互斥",
        "duplicate_analysis": {k: v for k, v in dup.items() if not k.startswith("_")},
        "splits": splits,
        "excluded": {
            "rows": int(len(excluded)),
            "by_reason": excluded["split"].value_counts().to_dict(),
        },
        "overlap_check": overlap_check,
        "gold_isolation": gold_iso,
        "test_set_decision": {
            "built": False,
            "reason": "原 default/test 100% 被 default/validation 包含（job_id 22,730/22,730 重合），"
                      "且其可用标签就是 736 条人工金标准；无法据此构建独立可信测试集。"
                      "最终独立评估改用 gold_holdout。",
        },
        "label_provenance_policy": {
            "pseudo_online": "default/* 的 assistant，来源为线上旧系统输出，人工复核一致率 45.92%（338/736），可信度标记 low",
            "human_gold": "annotated 的 人工正确结果，736 条，可信度标记 high",
            "model_new": "annotated 的 模型结果-新的，实测含长文本噪声（22 个 '唯一值' 中含 JD 片段），不可用作标签",
        },
    }
    return manifest, excluded, dev, gold


def save_education_splits(manifest: dict, excluded: pd.DataFrame, dev: pd.DataFrame,
                          gold: pd.DataFrame, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["record_key", "job_id", "source_split", "user_hash", "label_provenance",
            "is_gold", "split"]
    files = []
    for s in SPLIT_ORDER:
        sub = dev[dev["split"] == s][cols].sort_values("record_key", kind="mergesort")
        p = out_dir / f"{s}.csv"
        write_csv(sub.reset_index(drop=True), p)
        files.append({"split": s, "path": rel(p), "rows": int(len(sub)),
                      "sha256": sha256_file(p)})
    sub = gold[cols].sort_values("record_key", kind="mergesort")
    p = out_dir / "gold_holdout.csv"
    write_csv(sub.reset_index(drop=True), p)
    files.append({"split": "gold_holdout", "path": rel(p), "rows": int(len(sub)),
                  "sha256": sha256_file(p)})

    p = out_dir / "excluded.csv"
    write_csv(excluded[cols].sort_values("record_key", kind="mergesort").reset_index(drop=True), p)
    files.append({"split": "excluded", "path": rel(p), "rows": int(len(excluded)),
                  "sha256": sha256_file(p)})

    manifest = dict(manifest)
    manifest["files"] = files
    jdump(manifest, out_dir / "manifest.json")
    return {"dir": rel(out_dir), "manifest": manifest, "files": files}
