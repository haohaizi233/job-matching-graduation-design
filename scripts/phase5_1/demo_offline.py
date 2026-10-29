# -*- coding: utf-8 -*-
"""Phase5-1 离线业务闭环演示（模块 F）。

中文合成测试简历 -> 学生画像 -> 中文岗位 JD -> 岗位画像 ->
模型/Baseline 选择 -> 岗位排序 -> 匹配解释 -> JSON 结果输出。

纪律（输出中显式标注）：
  demo=true
  label_source=synthetic_or_unlabeled
  formal_evaluation=false

演示成功只证明服务链路可运行，不能证明中文匹配算法达到预期精度；
演示结果不得输入 Gold 评估程序充当人工标签。

用法：
  python scripts/phase5_1/demo_offline.py
  python scripts/phase5_1/demo_offline.py --mode experimental_model \\
      --experimental-model-dir models/matching/ridge/double_cold/ridge-double_cold-final-20261028-203750
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from job_matching.service import (JobEducationResolver, MatchingService,  # noqa: E402
                                  ModelRegistry, RankOptions,
                                  register_builtin_models)
from job_matching.service.job_parser import parse_job_text  # noqa: E402
from job_matching.service.resume_parser import parse_resume_text  # noqa: E402

FIXTURES = HERE / "fixtures"
DEMO_DISCLAIMER = (
    "Phase5-1 演示仅验证服务链路可运行；分数为排序参考分（heuristic_score / "
    "model_raw_score），不是录用概率；不代表中文人岗匹配模型真实效果验收通过。"
)


def load_demo_inputs() -> tuple[str, list[dict]]:
    resume_text = (FIXTURES / "synthetic_resume_zh.txt").read_text(encoding="utf-8")
    jobs = []
    with open(FIXTURES / "synthetic_jobs_zh.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                jobs.append(json.loads(line))
    return resume_text, jobs


def _resolve_dir(p: str | None) -> Path | None:
    if not p:
        return None
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def _rel_or_abs(path: Path) -> str:
    """输出目录可能在仓库外（如系统临时目录），此时退回绝对路径。"""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def run_demo(mode: str = "baseline", *,
             education_model_dir: str | None = None,
             experimental_model_dir: str | None = None,
             out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir or ROOT / "reports" / "phase5-1")
    out_dir.mkdir(parents=True, exist_ok=True)

    resume_text, job_rows = load_demo_inputs()
    student = parse_resume_text(resume_text, profile_id="synthetic_student_001",
                                is_synthetic=True,
                                source_document="scripts/phase5_1/fixtures/synthetic_resume_zh.txt")
    resolver = JobEducationResolver(_resolve_dir(education_model_dir))
    jobs = [parse_job_text(r["text"], job_id=r["job_id"],
                           source="scripts/phase5_1/fixtures/synthetic_jobs_zh.jsonl",
                           source_license="synthetic-generated-local",
                           resolver=resolver, is_synthetic=True)
            for r in job_rows]

    registry = ModelRegistry()
    register_builtin_models(registry,
                            matching_run_dir=_resolve_dir(experimental_model_dir),
                            education_run_dir=_resolve_dir(education_model_dir))
    service = MatchingService(registry)
    options = {"mode": mode, "top_k": 10, "allow_fallback": True,
               "timeout_ms": 30000}
    if mode == "experimental_model" and experimental_model_dir:
        options["model_id"] = "legacy_match_proxy_v1"
    ranking = service.rank(student, jobs, RankOptions.from_dict(options))

    demo_output = {
        "demo": True,
        "label_source": "synthetic_or_unlabeled",
        "formal_evaluation": False,
        "disclaimer": DEMO_DISCLAIMER,
        "input": {
            "resume_file": "scripts/phase5_1/fixtures/synthetic_resume_zh.txt",
            "resume_is_synthetic": True,
            "jobs_file": "scripts/phase5_1/fixtures/synthetic_jobs_zh.jsonl",
            "jobs_count": len(jobs),
            "jobs_are_synthetic_or_unlabeled": True,
        },
        "student_profile": student.to_dict(),
        "job_profiles": [j.to_dict() for j in jobs],
        "education_resolver": resolver.describe(),
        "ranking": ranking,
    }
    demo_path = out_dir / "demo-output.json"
    with open(demo_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(demo_output, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    integration = {
        "phase": "phase5-1",
        "generated_by": "scripts/phase5_1/demo_offline.py",
        "demo": True,
        "label_source": "synthetic_or_unlabeled",
        "formal_evaluation": False,
        "disclaimer": DEMO_DISCLAIMER,
        "h2_status": "BLOCKED（真实中文简历与人工 Gold 未到位，继承 Phase4-3A）",
        "pipeline": [
            {"step": "resume_parse", "status": student.parse_status,
             "fields_extracted": _field_summary(student)},
            {"step": "job_parse", "status": "ok",
             "jobs_parsed": len(jobs),
             "education_mode": resolver.mode},
            {"step": "rank", "status": "ok", "mode": ranking["mode"],
             "scoring_method": ranking["scoring_method"],
             "score_type": ranking["score_type"],
             "model_version": ranking["model_version"]},
            {"step": "explain", "status": "ok",
             "results_with_evidence": sum(1 for r in ranking["results"] if r["evidence"])},
        ],
        "model_registry": registry.describe_all(),
        "ranking_head": [
            {"job_id": r["job_id"], "rank": r["rank"], "score": r["score"],
             "score_type": r["score_type"],
             "matched": [m["canonical_name"] for m in r["matched_skills"]],
             "missing_required": [m["canonical_name"] for m in r["missing_required_skills"]],
             "education_constraint": r["education_constraint"]["status"],
             "experience_constraint": r["experience_constraint"]["status"]}
            for r in ranking["results"]
        ],
        "demo_output_file": _rel_or_abs(demo_path),
    }
    integration_path = out_dir / "integration-results.json"
    with open(integration_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(integration, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    demo_output["_integration_results_file"] = str(integration_path)
    return demo_output


def _field_summary(student) -> dict:
    out = {}
    for name in ("education_level", "major", "graduation_year", "employment_intention",
                 "preferred_cities", "employment_type"):
        fld = getattr(student, name)
        out[name] = {"status": fld.status, "fact_source": fld.fact_source}
    out["skills"] = len(student.skills)
    out["project_experiences"] = len(student.project_experiences)
    out["internship_experiences"] = len(student.internship_experiences)
    out["certificates"] = len(student.certificates)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phase5-1 离线业务闭环演示（合成数据）")
    ap.add_argument("--mode", default="baseline",
                    choices=["baseline", "experimental_model", "future_verified"])
    ap.add_argument("--education-model-dir", default=None)
    ap.add_argument("--experimental-model-dir", default=None)
    ap.add_argument("--out-dir", default=str(ROOT / "reports" / "phase5-1"))
    args = ap.parse_args(argv)
    try:
        out = run_demo(args.mode,
                       education_model_dir=args.education_model_dir,
                       experimental_model_dir=args.experimental_model_dir,
                       out_dir=Path(args.out_dir))
    except Exception as e:  # 演示失败必须显式报错退出，不得静默
        print(f"[demo] FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    summary = {
        "demo": out["demo"], "label_source": out["label_source"],
        "formal_evaluation": out["formal_evaluation"],
        "mode": out["ranking"]["mode"],
        "score_type": out["ranking"]["score_type"],
        "results": [{"job_id": r["job_id"], "rank": r["rank"], "score": r["score"]}
                    for r in out["ranking"]["results"]],
        "integration_results": out["_integration_results_file"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
