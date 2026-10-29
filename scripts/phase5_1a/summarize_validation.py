# -*- coding: utf-8 -*-
"""Artifact-dependent Validation 登记器：把"依赖真实数据/权重/GPU 的检查"逐项显式登记。

与 Core CI 的分界（Phase5-2 / Batch 0）：
  * Core CI                —— 全新 checkout、无真实数据、无权重、无 GPU 也能跑；
  * Artifact-dependent     —— 本脚本登记的检查项，必须有真实数据 / checkpoint / GPU。

状态口径（run_identity.STATUSES，禁止自造同义词）：
  PASS              已真实执行且通过
  FAIL              已真实执行且失败          -> 让本步骤退出非零
  BLOCKED           前置条件永久不满足（如 H2 真人 Gold 未到位）——如实登记，不计入 PASS
  NOT_RUN           前置条件本次不满足（如本机无权重）——如实登记，不计入 PASS
  ENV_INCOMPATIBLE  执行环境无法执行（如旧 checkpoint 依赖旧版依赖栈）——不计入 PASS

纪律：
  * 没有真实执行就没有 PASS；
  * 不允许用"报告文件存在"代替"本次真的执行了"（身份校验见 verify_run_freshness.py）；
  * 不在 CI 中偷偷下载来源不明的数据集（本脚本只探测本地已有产物，不联网）。

用法：
  python scripts/phase5_1a/summarize_validation.py [--run] [--strict] [--out PATH]
  --run    真的执行可执行项（不带则只做前置探测，全部记 NOT_RUN/BLOCKED）
  --strict 任意非 PASS 即退出非零（默认仅 FAIL 退出非零）
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import run_identity as _ri  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 1

# 数据 / 产物存在性探测（只读本地，不联网、不下载）
RAW_REQUIRED = [
    "data/raw/job-resume-matching/cv.csv",
    "data/raw/job-resume-matching/job.csv",
    "data/raw/job-resume-matching/matches.csv",
]


def _exists_all(paths: list[str]) -> tuple[bool, list[str]]:
    missing = [p for p in paths if not (ROOT / p).exists()]
    return (not missing), missing


def _model_manifests() -> list[Path]:
    return sorted(ROOT.glob("models/**/manifest.json"))


def _gpu_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


def _run_cmd(args: list[str], timeout: int = 1800) -> tuple[int, str]:
    try:
        r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return 2, f"{type(e).__name__}: {e}"
    tail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-2000:]
    return r.returncode, tail


class Registry:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, item_id: str, title: str, requires: list[str], status: str,
            reason: str, evidence: str = "", detail: dict | None = None,
            executed: bool = True) -> None:
        if status not in _ri.STATUSES:
            raise ValueError(f"非法状态 {status!r}")
        self.items.append({"id": item_id, "title": title, "requires": requires,
                           "status": status, "reason": reason,
                           "evidence": evidence, "detail": detail or {},
                           "executed": bool(executed)})

    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in _ri.STATUSES}
        for it in self.items:
            c[it["status"]] += 1
        return c


def collect(do_run: bool) -> Registry:
    reg = Registry()
    raw_ok, raw_missing = _exists_all(RAW_REQUIRED)
    models = _model_manifests()
    gpu = _gpu_available()

    # ---- 1. 原始数据不变（G1）：必须真实数据
    if not raw_ok:
        reg.add("raw_data_integrity", "原始数据不变（G1）", ["data"],
                "NOT_RUN", f"缺少真实原始数据: {raw_missing[:3]}；Core CI 不下载任何数据集",
                executed=False)
    elif not do_run:
        reg.add("raw_data_integrity", "原始数据不变（G1）", ["data"],
                "NOT_RUN", "已探测到原始数据，但本次未 --run 执行", executed=False)
    else:
        code, tail = _run_cmd([sys.executable, "tests/data_pipeline/run_all.py", "G1"])
        reg.add("raw_data_integrity", "原始数据不变（G1）", ["data"],
                "PASS" if code == 0 else "FAIL",
                f"tests/data_pipeline/run_all.py G1 退出码 {code}",
                "reports/data-quality-gates.json", {"tail": tail[-600:]})

    # ---- 2. 数据质量闸门 G2~G7：必须真实处理产物
    processed_ok, processed_missing = _exists_all([
        "data/processed/matching/features_pairs.csv",
        "data/processed/matching/targets_pairs.csv",
        "data/processed/embeddings/cv_embeddings.npy",
        "data/processed/embeddings/job_embeddings.npy",
        "data/processed/education/education_labels.csv",
    ])
    if not processed_ok:
        reg.add("data_quality_gates", "数据质量闸门 G2~G7", ["data"],
                "NOT_RUN", f"缺少处理产物: {processed_missing[:3]}", executed=False)
    elif not do_run:
        reg.add("data_quality_gates", "数据质量闸门 G2~G7", ["data"],
                "NOT_RUN", "已探测到处理产物，但本次未 --run 执行", executed=False)
    else:
        code, tail = _run_cmd([sys.executable, "tests/data_pipeline/run_all.py"])
        reg.add("data_quality_gates", "数据质量闸门 G2~G7", ["data"],
                "PASS" if code == 0 else "FAIL",
                f"tests/data_pipeline/run_all.py 退出码 {code}",
                "reports/data-quality-gates.json", {"tail": tail[-600:]})

    # ---- 3. 研究流程回归 Phase4-3A：必须真实数据
    p4_ok, p4_missing = _exists_all(["data/independent_eval/pool/job_pool_v2.jsonl"])
    if not p4_ok:
        reg.add("phase4_3a_regression", "研究流程回归（Phase4-3A）", ["data"],
                "NOT_RUN", f"缺少独立评估池: {p4_missing[:2]}", executed=False)
    elif not do_run:
        reg.add("phase4_3a_regression", "研究流程回归（Phase4-3A）", ["data"],
                "NOT_RUN", "本次未 --run 执行", executed=False)
    else:
        code, tail = _run_cmd([sys.executable, "tests/phase4_3a/run_all.py"])
        reg.add("phase4_3a_regression", "研究流程回归（Phase4-3A）", ["data"],
                "PASS" if code == 0 else "FAIL",
                f"tests/phase4_3a/run_all.py 退出码 {code}",
                "reports/phase4-3a/test-results.json", {"tail": tail[-600:]})

    # ---- 4. 模型权重存在性
    if not models:
        reg.add("model_artifacts_present", "历史 checkpoint 存在性", ["models"],
                "NOT_RUN", "models/**/manifest.json 为空；无权重可诊断（不计入 PASS）")
    else:
        reg.add("model_artifacts_present", "历史 checkpoint 存在性", ["models"],
                "PASS", f"发现 {len(models)} 份 checkpoint 清单", detail={"count": len(models)})

    # ---- 5. 模型兼容诊断（必须带运行身份，且必须本次执行）
    if not models:
        reg.add("model_compat_diagnosis", "历史模型兼容性诊断", ["models"],
                "NOT_RUN", "无 checkpoint，诊断未执行；显式 NOT_RUN，不得用旧报告冒充",
                executed=False)
    elif not do_run:
        reg.add("model_compat_diagnosis", "历史模型兼容性诊断", ["models"],
                "NOT_RUN", "已发现 checkpoint，但本次未 --run 执行（旧报告一律不采信）",
                executed=False)
    else:
        out = ROOT / "reports" / "phase5-2" / "ci" / "model-compatibility.json"
        rid = os.environ.get("JM_RUN_ID", f"adhoc-{int(time.time())}")
        code, tail = _run_cmd([sys.executable,
                               "scripts/phase5_1a/diagnose_model_compat.py",
                               "--out", str(out), "--run-id", rid])
        if code != 0:
            reg.add("model_compat_diagnosis", "历史模型兼容性诊断", ["models"],
                    "FAIL", f"诊断脚本退出码 {code}（未生成新报告，旧报告不采信）",
                    str(out), {"tail": tail[-600:]})
        else:
            try:
                data = json.loads(out.read_text(encoding="utf-8"))
                status = data["run_identity"]["status"]
            except Exception as e:  # noqa: BLE001
                status, data = "FAIL", {"error": str(e)}
            reg.add("model_compat_diagnosis", "历史模型兼容性诊断", ["models"],
                    status if status in _ri.STATUSES else "FAIL",
                    data.get("status_reason", "见报告"), str(out),
                    {"summary": data.get("summary", {})})

    # ---- 6. 历史 checkpoint 能否在当前环境加载（环境问题单列）
    if not models:
        reg.add("legacy_checkpoint_loadability", "历史 checkpoint 加载能力", ["models"],
                "NOT_RUN", "无 checkpoint 可加载", executed=False)
    else:
        statuses = set()
        for m in models:
            try:
                meta = json.loads(m.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                statuses.add("artifact_corrupt")
                continue
            run_dir = m.parent
            weights = [p for p in sorted(run_dir.glob("model.*")) if p.is_file()]
            if not weights:
                statuses.add("skipped")
                continue
            st, _note = __import__("importlib").import_module(
                "diagnose_model_compat").try_load_weights(weights[0])
            statuses.add(st)
        if "env_incompatible" in statuses:
            reg.add("legacy_checkpoint_loadability", "历史 checkpoint 加载能力", ["models"],
                    "ENV_INCOMPATIBLE",
                    f"存在环境不兼容的 checkpoint（{sorted(statuses)}）；"
                    "属历史依赖栈问题，不得记为权重缺失或业务失败",
                    detail={"statuses": sorted(statuses)})
        elif statuses & {"artifact_corrupt", "artifact_missing"}:
            reg.add("legacy_checkpoint_loadability", "历史 checkpoint 加载能力", ["models"],
                    "FAIL", f"存在损坏/缺失的权重（{sorted(statuses)}）",
                    detail={"statuses": sorted(statuses)})
        elif statuses <= {"skipped"}:
            reg.add("legacy_checkpoint_loadability", "历史 checkpoint 加载能力", ["models"],
                    "NOT_RUN", "全部 run_dir 无 model.* 权重文件", detail={"statuses": sorted(statuses)})
        else:
            reg.add("legacy_checkpoint_loadability", "历史 checkpoint 加载能力", ["models"],
                    "PASS", f"当前环境可加载（{sorted(statuses)}）", detail={"statuses": sorted(statuses)})

    # ---- 7. 训练流程回归（需真实数据 + 长时间）
    if not raw_ok:
        reg.add("model_training_regression", "模型训练回归（Phase4-1）", ["data", "time"],
                "NOT_RUN", "缺少真实训练数据", executed=False)
    else:
        reg.add("model_training_regression", "模型训练回归（Phase4-1）", ["data", "time"],
                "NOT_RUN", "训练回归属长耗时人工流程，未在本次登记执行；"
                           "历史基线见 reports/model-training/model-tests.json（只读）",
                executed=False)

    # ---- 8. GPU 训练复现
    if not gpu:
        reg.add("gpu_training_repro", "GPU 训练复现", ["gpu"],
                "BLOCKED", f"当前执行环境无 CUDA 设备（platform={platform.platform()}）；"
                           "GPU 复现属独立手动工作流", executed=False)
    else:
        reg.add("gpu_training_repro", "GPU 训练复现", ["gpu"],
                "NOT_RUN", "检测到 GPU，但本次未 --run 执行训练复现", executed=False)

    # ---- 9. H2：真实中文简历 + 真人 Gold
    reg.add("h2_real_chinese_gold", "H2 真实中文简历与真人 Gold 评估", ["real_data", "annotation"],
            "BLOCKED",
            "真实中文简历与真人 Gold 标签未到位；不得宣称旧英文代理标签模型适用于真实中文招聘。"
            "工程演示成功不代表模型真实业务效果通过", executed=False)
    reg.add("phase4_3b", "Phase4-3B", ["plan"],
            "BLOCKED", "Phase4-3B 尚未开始", executed=False)

    return reg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Artifact-dependent Validation 显式登记")
    ap.add_argument("--run", action="store_true", help="真的执行可执行项")
    ap.add_argument("--strict", action="store_true",
                    help="任意非 PASS 即退出非零（默认仅 FAIL 退出非零）")
    ap.add_argument("--out", default=str(ROOT / "reports" / "phase5-2" / "ci" /
                                        "artifact-validation.json"))
    args = ap.parse_args(argv)

    reg = collect(args.run)
    counts = reg.counts()
    if counts["FAIL"]:
        overall = "FAIL"
    elif counts["PASS"] == len(reg.items):
        overall = "PASS"
    else:
        overall = "INCOMPLETE"
    identity = _ri.build_run_identity(ROOT, artifact_count=len(reg.items),
                                      status="PASS" if overall == "PASS" else
                                      ("FAIL" if overall == "FAIL" else "NOT_RUN"),
                                      extra={"tool": "summarize_validation",
                                             "mode": "run" if args.run else "probe"})
    identity["run_id"] = os.environ.get("JM_RUN_ID", identity["run_id"])

    out = {
        "generated_by": "scripts/phase5_1a/summarize_validation.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "run" if args.run else "probe",
        "overall": overall,
        "counts": counts,
        "policy": ("NOT_RUN / BLOCKED / ENV_INCOMPATIBLE 一律不计入 PASS；"
                   "没有真实执行就没有 PASS；不下载任何来源不明数据集"),
        "run_identity": identity,
        "items": reg.items,
    }
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")

    print("=" * 78)
    print(f"Artifact-dependent Validation | mode={out['mode']} | overall={overall}")
    print("=" * 78)
    for it in reg.items:
        print(f"[{it['status']:>17}] {it['id']:<28} {it['reason'][:80]}")
    print("-" * 78)
    print("counts:", counts, "（NOT_RUN/BLOCKED/ENV_INCOMPATIBLE 不计入 PASS）")
    print(f"-> {p}")

    if overall == "FAIL":
        return EXIT_FAIL
    if args.strict and overall != "PASS":
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
