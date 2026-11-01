# -*- coding: utf-8 -*-
"""Phase7-B / B4：模型产物许可与来源清点（只登记可核事实）。

逐个登记 Git 跟踪的 models/** 权重/预测产物：
  model_family / artifact_path / artifact_sha256 / source_dataset /
  source_dataset_version / source_url / source_license / redistribution_status /
  model_license / privacy_risk / license_evidence

纪律：
  * 无法证实的一律 UNKNOWN，**不自行编造 MIT / Apache-2.0 / SPDX**；
  * 本脚本只读扫描 + 计算哈希，不移动、不删除、不改写任何权重；
  * 文件已公开与许可未核实是两个并存事实，输出如实反映。

用法：
    py -3.13 scripts/phase7/audit_model_licenses.py \
        --out reports/phase7-b/model-license-inventory.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import common as p7common  # noqa: F401  （sys.path 注入）

ROOT = p7common.ROOT

#: 按模型族登记的**已核事实**（证据见 models/LICENSE-MODELS.md / docs/datasets/README.md）。
#: 任何值不得超出证据范围；未知即 UNKNOWN。
FAMILY_FACTS: dict[str, dict] = {
    "matching": {
        "source_dataset": "data/raw/job-resume-matching (cv.csv+job.csv+matches.csv)",
        "source_dataset_version": "huggingface snapshot（本地无 repo id 记录）",
        "source_url": "UNKNOWN",
        "source_license": "UNKNOWN",
        "source_license_note": (
            "数据集卡片 front-matter 写 license: mit，正文 License 节写 "
            "'Please update the dataset license before publishing.' —— 两者矛盾，按 UNKNOWN"),
        "model_license": "UNKNOWN",
        "redistribution_status": "BLOCKED_UNKNOWN_LICENSE",
        "privacy_risk": "MEDIUM_UNVERIFIED_SOURCE: 简历文本来源与授权链未核实；标签为英文代理标签",
        "license_evidence": [
            "models/LICENSE-MODELS.md#2.1",
            "docs/datasets/README.md#1",
            "reports/phase6-r/05-model-artifact-audit.md",
        ],
    },
    "education": {
        "source_dataset": "data/raw/job-education (train/validation/test/annotated)",
        "source_dataset_version": "huggingface snapshot（创建者 @wangzihaogithub）",
        "source_url": "UNKNOWN（本地未登记 repo id）",
        "source_license": "apache-2.0",
        "source_license_note": "数据集卡片 front-matter 声明 apache-2.0，本地可核",
        "model_license": "UNKNOWN",
        "redistribution_status": "NEEDS_MODEL_LICENSE",
        "privacy_risk": "LOW: 岗位文本（招聘要求），无个人简历；训练语料与岗位候选池存在文本重合（需披露）",
        "license_evidence": [
            "models/LICENSE-MODELS.md#2.2",
            "docs/datasets/README.md#2",
        ],
    },
}

#: 二进制权重/预测产物后缀（逐个清点）
ARTIFACT_SUFFIXES = {".pkl", ".pt", ".pth", ".npz", ".npy", ".joblib"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def family_of(rel: Path) -> str:
    parts = rel.parts
    return parts[1] if len(parts) > 2 and parts[0] == "models" else "unknown"


def scan() -> dict:
    models_dir = ROOT / "models"
    entries: list[dict] = []
    for p in sorted(models_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if rel.name in ("LICENSE-MODELS.md",):
            continue
        suffix = p.suffix.lower()
        is_artifact = suffix in ARTIFACT_SUFFIXES
        fam = family_of(rel)
        facts = FAMILY_FACTS.get(fam, {
            "source_dataset": "UNKNOWN", "source_dataset_version": "UNKNOWN",
            "source_url": "UNKNOWN", "source_license": "UNKNOWN",
            "source_license_note": "族未登记",
            "model_license": "UNKNOWN",
            "redistribution_status": "UNCLASSIFIED_PENDING_REVIEW",
            "privacy_risk": "UNKNOWN",
            "license_evidence": [],
        })
        entries.append({
            "model_family": fam,
            "artifact_path": rel.as_posix(),
            "artifact_type": (suffix.lstrip(".") or "none"),
            "is_binary_artifact": is_artifact,
            "bytes": p.stat().st_size,
            "artifact_sha256": sha256_file(p),
            **{k: facts[k] for k in (
                "source_dataset", "source_dataset_version", "source_url",
                "source_license", "source_license_note", "model_license",
                "redistribution_status", "privacy_risk", "license_evidence")},
        })

    by_family: dict[str, dict] = {}
    for e in entries:
        fam = by_family.setdefault(e["model_family"], {
            "model_family": e["model_family"], "n_files": 0,
            "n_binary_artifacts": 0, "bytes": 0,
            "source_license": e["source_license"],
            "model_license": e["model_license"],
            "redistribution_status": e["redistribution_status"],
        })
        fam["n_files"] += 1
        fam["bytes"] += e["bytes"]
        fam["n_binary_artifacts"] += 1 if e["is_binary_artifact"] else 0

    return {
        "inventory_id": f"model-license-inv-{time.strftime('%Y%m%d')}",
        "generated_by": "scripts/phase7/audit_model_licenses.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "discipline": ("只登记可核事实；UNKNOWN 不得擅自改为任何 SPDX 标识；"
                       "文件已公开与许可未核实并存"),
        "repo_root_license": "UNKNOWN（仓库根无 LICENSE 文件）",
        "totals": {
            "n_files": len(entries),
            "n_binary_artifacts": sum(1 for e in entries if e["is_binary_artifact"]),
            "bytes": sum(e["bytes"] for e in entries),
            "n_unknown_model_license": sum(1 for e in entries
                                           if e["model_license"] == "UNKNOWN"),
        },
        "by_family": sorted(by_family.values(), key=lambda d: d["model_family"]),
        "artifacts": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="模型产物许可与来源清点（只读）")
    ap.add_argument("--out", default="reports/phase7-b/model-license-inventory.json")
    args = ap.parse_args()
    payload = scan()
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    t = payload["totals"]
    print(f"files={t['n_files']} binary_artifacts={t['n_binary_artifacts']} "
          f"bytes={t['bytes']} unknown_model_license={t['n_unknown_model_license']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
