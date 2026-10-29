# -*- coding: utf-8 -*-
"""数据集冻结与 SHA-256 复验（协议第九节 / 测试场景 9）。

两级冻结：
  stage="pool"    候选池冻结（无标注也可以），登记来源、哈希、抽样与覆盖度；
  stage="evalset" 正式评估集冻结（必须先完成双人标注 + 仲裁 + 质量检查），
                  生成数据集版本号、标签协议版本号、样本量、来源统计、标签分布、
                  互斥检查结果、文件 SHA-256、冻结时间、来源与人工标注责任记录。

冻结后任何文件变化都会在 verify_freeze 中被检出；禁止静默修改，修改必须升版本号。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from ..core import ensure_dir, jdump, jload, rel, sha256_file, sha256_text
from .schema import PROTOCOL_VERSION


class FreezeError(RuntimeError):
    pass


FREEZE_STAGES = ("pool", "evalset")


def assign_splits(pairs: list[dict], seed: int = 20261211,
                  blind_ratio: float = 0.5) -> list[dict]:
    """按简历分组分配 dev_validation / blind_test（同简历不拆分，确定性）。"""
    resume_ids = sorted({p["resume_id"] for p in pairs})
    rng = np.random.default_rng(int(seed))
    order = list(rng.permutation(len(resume_ids)))
    n_blind = int(round(len(resume_ids) * float(blind_ratio)))
    blind_set = {resume_ids[order[i]] for i in range(min(n_blind, len(order)))}
    out = []
    for p in pairs:
        q = dict(p)
        q["split"] = "blind_test" if p["resume_id"] in blind_set else "dev_validation"
        out.append(q)
    return out


def mutual_exclusivity_checks(pairs: list[dict], final_rows: list[dict] | None = None
                              ) -> dict:
    """互斥/唯一性检查：pair 唯一、resume-job 唯一、split 隔离、最终标签唯一。"""
    pair_ids = [p["pair_id"] for p in pairs]
    resume_by_split: dict[str, set[str]] = {}
    for p in pairs:
        resume_by_split.setdefault(p["split"], set()).add(p["resume_id"])
    splits = sorted(resume_by_split)
    overlap = {}
    for i in range(len(splits)):
        for j in range(i + 1, len(splits)):
            a, b = splits[i], splits[j]
            ov = resume_by_split[a] & resume_by_split[b]
            overlap[f"{a}__{b}"] = len(ov)

    checks = {
        "pair_id_unique": len(pair_ids) == len(set(pair_ids)),
        "pair_id_duplicates": len(pair_ids) - len(set(pair_ids)),
        "resume_job_unique": len({(p["resume_id"], p["job_id"]) for p in pairs}) == len(pairs),
        "split_resume_overlap": overlap,
        "split_isolation_ok": all(v == 0 for v in overlap.values()),
        "splits_present": splits,
    }
    if final_rows is not None:
        fids = [r["pair_id"] for r in final_rows]
        checks["final_label_unique"] = len(fids) == len(set(fids))
        checks["final_label_missing_for_pairs"] = len(set(pair_ids) - set(fids))
        checks["final_label_unknown_pairs"] = len(set(fids) - set(pair_ids))
    return checks


def _file_record(path: Path, display: Path | None = None) -> dict:
    p = Path(path)
    d = Path(display) if display is not None else p
    return {"path": rel(d), "bytes": p.stat().st_size, "sha256": sha256_file(p)}


def _load_records(path: Path) -> list[dict]:
    """读取 pairs / labels 记录（JSONL 或 CSV）。"""
    import json
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix.lower() == ".jsonl":
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        else:
            import pandas as pd
            rows = pd.read_csv(path, dtype=str).fillna("").to_dict("records")
    return rows


# ------------------------------------------------------------------ 冻结硬性检查
def _blocking_mutual_exclusivity_failures(checks: dict, *, stage: str) -> list[str]:
    """互斥/唯一性检查 -> 冻结失败条件（Phase5-1R F-004：不再只写 manifest）。"""
    out: list[str] = []
    if not checks.get("pair_id_unique", True):
        out.append(f"pair_id 重复 {checks.get('pair_id_duplicates')} 条，冻结拒绝")
    if not checks.get("resume_job_unique", True):
        out.append("(resume_id, job_id) 配对重复，冻结拒绝")
    if not checks.get("split_isolation_ok", True):
        out.append("同一简历跨 dev_validation / blind_test，冻结拒绝")
    if "final_label_unique" in checks and not checks["final_label_unique"]:
        out.append("同一 pair 存在多个最终标签，冻结拒绝")
    if checks.get("final_label_missing_for_pairs", 0) > 0:
        out.append(f"{checks['final_label_missing_for_pairs']} 个配对缺少最终标签，冻结拒绝")
    if checks.get("final_label_unknown_pairs", 0) > 0:
        out.append(f"{checks['final_label_unknown_pairs']} 条最终标签引用未知 pair，冻结拒绝")
    return out


def _content_guard_failures(pairs: list[dict], *, stage: str) -> list[str]:
    """内容级硬性检查：合成配对混入 / 训练数据交叉配对进盲测（F-004）。"""
    out: list[str] = []
    if stage != "evalset":
        return out
    synthetic = [str(p.get("pair_id", "")) for p in pairs if bool(p.get("is_synthetic"))]
    if synthetic:
        out.append(f"合成配对混入人工真值评估集 {len(synthetic)} 组（如 {synthetic[:5]}），冻结拒绝")
    leaked = [str(p.get("pair_id", "")) for p in pairs
              if bool(p.get("training_overlap")) and str(p.get("split", "")) == "blind_test"]
    if leaked:
        out.append(f"训练语料交叉配对被分配进 blind_test {len(leaked)} 组（如 {leaked[:5]}），冻结拒绝")
    bad_consent = [str(p.get("pair_id", "")) for p in pairs
                   if "consent_status" in p
                   and str(p.get("consent_status", "")).strip().lower()
                   not in ("granted", "licensed", "")]
    if bad_consent:
        out.append(f"授权缺失/失效的配对 {len(bad_consent)} 组（如 {bad_consent[:5]}），冻结拒绝")
    return out


def _op_log_path(out_dir: Path) -> Path:
    return Path(out_dir).parent / "freeze-op-log.jsonl"


def _append_op_log(out_dir: Path, entry: dict) -> None:
    import json
    p = _op_log_path(out_dir)
    ensure_dir(p.parent)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _dataset_version_conflict(out_dir: Path, dataset_version: str) -> str | None:
    """同一 dataset_version 已成功冻结过（任何目录）-> 拒绝重复写入（F-004）。"""
    import json
    p = _op_log_path(out_dir)
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("dataset_version") == dataset_version and rec.get("status") == "frozen":
            return (f"dataset_version={dataset_version} 已在 "
                    f"{rec.get('out_dir')} 冻结（manifest_sha256={rec.get('manifest_sha256')}）；"
                    f"重新冻结必须使用新的 dataset_version")
    return None


def freeze_dataset(*, stage: str, out_dir: Path | str, pairs_file: Path | str,
                   files: dict[str, Path | str], dataset_version: str,
                   source_stats: dict, label_distribution: dict | None = None,
                   annotation_quality: dict | None = None,
                   responsibility: dict | None = None,
                   protocol_version: str = PROTOCOL_VERSION,
                   extra: dict | None = None,
                   path_map: dict[str, Path | str] | None = None,
                   work_dir: Path | str | None = None) -> dict:
    """冻结数据集并写 manifest.json。不满足条件抛 FreezeError（不静默降级）。

    安全发布（Phase5-1R F-004）：
      1. 全部检查通过后，在 ``<out_dir>.staging`` 目录生成 manifest；
      2. 验证格式、行数、互斥与内容哈希；
      3. 原子发布（目录重命名）到 out_dir —— 中断不会留下半成品 manifest；
      4. 已存在同名冻结产物（manifest.json）默认拒绝覆盖；
      5. 同一 dataset_version 冻结过即拒绝重复写入，重冻必须升版本号；
      6. 每次尝试（成功/失败）都追加 freeze-op-log.jsonl 审计记录。

    path_map：key -> 展示路径。用于「文件先写暂存目录、发布后位于最终目录」的场景，
    manifest 登记最终路径，verify_freeze 仍能复验发布后的文件。
    """
    if stage not in FREEZE_STAGES:
        raise FreezeError(f"未知冻结阶段: {stage}")
    out_dir = Path(out_dir)
    files = {k: Path(v) for k, v in files.items()}
    path_map = {k: Path(v) for k, v in (path_map or {}).items()}
    for k, p in files.items():
        if not p.exists():
            raise FreezeError(f"冻结所需文件缺失: {k} -> {p}")
    if not dataset_version or not str(dataset_version).strip():
        raise FreezeError("dataset_version 为空，冻结拒绝（必须可追溯版本号）")
    if (out_dir / "manifest.json").exists():
        raise FreezeError(
            f"同版本冻结产物已存在: {out_dir / 'manifest.json'}；"
            f"默认拒绝覆盖，重新冻结必须使用新的 dataset_version")
    conflict = _dataset_version_conflict(out_dir, str(dataset_version))
    if conflict:
        raise FreezeError(conflict)

    if stage == "evalset":
        aq = annotation_quality or {}
        if aq.get("annotation_status") != "complete":
            raise FreezeError(
                "正式评估集冻结被拒绝：annotation_status != complete（人工标注未完成）")
        if aq.get("open_disagreements", 0) > 0:
            raise FreezeError("正式评估集冻结被拒绝：仍有未仲裁的分歧样本")
        if aq.get("unjudgeable_forced", 0) > 0:
            raise FreezeError("正式评估集冻结被拒绝：存在 unjudgeable 被强行归类")
        if not responsibility:
            raise FreezeError("正式评估集冻结被拒绝：缺少数据来源与人工标注责任记录")
        if aq.get("synthetic_pairs_included", 0) > 0:
            raise FreezeError("正式评估集冻结被拒绝：合成样本不得进入人工真值评估集")
        arb_status = str(aq.get("arbitration_status", "") or "")
        if arb_status in ("pending", "invalid"):
            raise FreezeError(
                f"正式评估集冻结被拒绝：arbitration_status={arb_status}"
                f"（分歧未完成仲裁或仲裁记录非法）")
        if arb_status not in ("", "not_required", "completed"):
            raise FreezeError(
                f"正式评估集冻结被拒绝：arbitration_status 非法 {arb_status!r}，"
                f"合法值 not_required/pending/completed/invalid")

    manifest = {
        "generated_by": "src/job_matching/annotation/freeze.py",
        "stage": stage,
        "dataset_version": dataset_version,
        "protocol_version": protocol_version,
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": {k: _file_record(p, path_map.get(k, p)) for k, p in sorted(files.items())},
        "source_stats": source_stats,
        "label_distribution": label_distribution or {},
        "annotation_quality": annotation_quality or {},
        "responsibility": responsibility or {},
        "mutual_exclusivity": {},
        "extra": extra or {},
        "immutability_note": "冻结后禁止静默修改；任何变更必须生成新的 dataset_version",
    }
    checks_path = files.get("pairs")
    if checks_path is not None:
        pairs = _load_records(checks_path)
        final_rows = None
        if "final_labels" in files:
            final_rows = _load_records(files["final_labels"])
        manifest["mutual_exclusivity"] = mutual_exclusivity_checks(pairs, final_rows)
        manifest["sample_counts"] = {
            "pairs": len(pairs),
            "resumes": len({p.get("resume_id") for p in pairs}),
            "jobs": len({p.get("job_id") for p in pairs}),
            "synthetic_pairs": sum(1 for p in pairs if str(p.get("is_synthetic")) == "True"),
        }
        failures = _blocking_mutual_exclusivity_failures(manifest["mutual_exclusivity"],
                                                         stage=stage)
        failures += _content_guard_failures(pairs, stage=stage)
        if failures:
            _append_op_log(out_dir, {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": stage,
                "dataset_version": dataset_version, "status": "rejected",
                "reasons": failures, "out_dir": rel(out_dir),
            })
            raise FreezeError("冻结互斥/内容检查未通过：" + "；".join(failures))
    manifest["manifest_sha256"] = sha256_text(
        "|".join(f"{k}:{v['sha256']}" for k, v in manifest["files"].items()))

    # ---- 安全发布：暂存目录生成 -> 校验 -> 原子重命名（避免半成品 manifest）
    # work_dir：调用方自管暂存目录（生成物已写入其中），本函数只写 manifest 并整体发布；
    # 未提供时自建 <out_dir>.staging（幂等清理）。
    if work_dir is None:
        staging = out_dir.parent / (out_dir.name + ".staging")
        if staging.exists():
            import shutil
            shutil.rmtree(staging)
    else:
        staging = Path(work_dir)
    ensure_dir(staging)
    if (staging / "manifest.json").exists():
        raise FreezeError(f"暂存目录残留旧 manifest，拒绝复用: {staging / 'manifest.json'}")
    jdump(manifest, staging / "manifest.json")
    if not (staging / "manifest.json").exists():  # pragma: no cover - 写失败兜底
        raise FreezeError("manifest 写入失败，冻结中止")
    if out_dir.exists():
        # 失败尝试留下的 freeze_blocked.json 不是冻结产物，允许清理后发布
        stale = out_dir / "freeze_blocked.json"
        if stale.exists():
            stale.unlink()
        if any(out_dir.iterdir()):
            _append_op_log(out_dir, {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": stage,
                "dataset_version": dataset_version, "status": "rejected",
                "reasons": [f"目标目录已存在且非空: {out_dir}"], "out_dir": rel(out_dir),
            })
            raise FreezeError(f"冻结目标目录已存在且非空，拒绝覆盖: {out_dir}")
        out_dir.rmdir()
    staging.rename(out_dir)
    _append_op_log(out_dir, {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": stage,
        "dataset_version": dataset_version, "status": "frozen",
        "manifest_sha256": manifest["manifest_sha256"], "out_dir": rel(out_dir),
    })
    return manifest


def verify_freeze(manifest_path: Path | str) -> dict:
    """复验冻结清单：逐文件重算 SHA-256。"""
    manifest_path = Path(manifest_path)
    manifest = jload(manifest_path)
    base = manifest_path.parent
    results = []
    ok = True
    for key, rec in sorted(manifest.get("files", {}).items()):
        p = base / rec["path"] if not Path(rec["path"]).is_absolute() else Path(rec["path"])
        # manifest 内记录的是相对项目根路径，按项目根解析
        from ..core import ROOT
        cand = [p, ROOT / rec["path"], base / Path(rec["path"]).name]
        actual = None
        found = None
        for c in cand:
            if c.exists():
                found = c
                actual = sha256_file(c)
                break
        match = (actual == rec["sha256"]) if actual is not None else False
        ok = ok and match
        results.append({"key": key, "path": rec["path"], "expected": rec["sha256"],
                        "actual": actual, "exists": found is not None, "match": match})
    return {"manifest": str(manifest_path), "ok": ok, "files": results,
            "dataset_version": manifest.get("dataset_version"),
            "frozen_at": manifest.get("frozen_at"),
            "stage": manifest.get("stage")}
