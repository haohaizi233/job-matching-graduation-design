# -*- coding: utf-8 -*-
"""真实中文简历安全导入 CLI（Phase4-3A-2 模块 A）。

用法：
  python scripts/phase4_3a_2/intake_resumes.py --source-class A_consented_individual \
      --source-name consented-2026q4 --resumes data/private/resumes \
      --consent data/private/consent/consent_records.csv

  python scripts/phase4_3a_2/intake_resumes.py --source-class C_synthetic \
      --source-name synthetic-fixture --resumes tests/fixtures/synthetic_resumes.jsonl

纪律：
  * 三类来源（A 经同意个人 / B 许可公开 / C 合成）严格隔离，来源与授权记录不一致直接报错；
  * 未授权真实简历拒绝进入 Gold（require_consent 默认开启）；
  * 导入即 PII 脱敏（掩码 ***），报告只登记命中类型与数量，不落原始号码；
  * 真实脱敏记录写入 data/private/accepted/（不入库），报告只含非敏感统计与哈希。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import (  # noqa: E402
    PRIVATE_ACCEPTED_DIR, find_resume_files, now, write_report,
)

from job_matching.annotation.consent import SOURCE_CLASSES  # noqa: E402
from job_matching.annotation.resume_intake import (  # noqa: E402
    ResumeIntakeError, intake_resumes, parse_structured,
)
from job_matching.core import ROOT, ensure_dir, sha256_file  # noqa: E402

SUPPORTED = (".txt", ".docx", ".pdf", ".csv", ".jsonl")


def load_consent_records(path: Path | None) -> list[dict]:
    if path is None:
        return []
    path = Path(path)
    if not path.exists():
        raise ResumeIntakeError(f"授权记录文件不存在: {path}")
    if path.suffix.lower() == ".jsonl":
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_items(resume_paths: list[Path]) -> list[dict]:
    """文档走文本抽取；CSV/JSONL 走结构化行（可带 path 溯源）。"""
    items: list[dict] = []
    for p in resume_paths:
        if p.suffix.lower() in (".csv", ".jsonl"):
            for row in parse_structured(p):
                items.append({"row": row, "path": str(p)})
        else:
            items.append({"path": str(p)})
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-class", required=True, choices=list(SOURCE_CLASSES))
    ap.add_argument("--source-name", required=True)
    ap.add_argument("--resumes", required=True, help="简历目录或单个文件")
    ap.add_argument("--consent", default=None, help="授权记录 CSV/JSONL（A/B 类必填）")
    ap.add_argument("--seed", type=int, default=20261212)
    ap.add_argument("--no-require-consent", action="store_true",
                    help="仅用于调试：关闭严格授权门禁（产出仍隔离未授权记录）")
    args = ap.parse_args()

    resume_path = Path(args.resumes)
    if not resume_path.is_absolute():
        resume_path = ROOT / resume_path
    if resume_path.is_dir():
        files = find_resume_files(resume_path)
    elif resume_path.exists():
        files = [resume_path]
    else:
        files = []
    consent_path = Path(args.consent) if args.consent else None
    if consent_path is not None and not consent_path.is_absolute():
        consent_path = ROOT / consent_path

    items = build_items(files)
    consent_records = load_consent_records(consent_path)

    try:
        result = intake_resumes(
            items, source_class=args.source_class,
            consent_records=consent_records, seed=args.seed,
            source_name=args.source_name,
            require_consent=not args.no_require_consent)
    except ResumeIntakeError as e:
        print(json.dumps({"status": "rejected", "error": str(e)}, ensure_ascii=False, indent=2))
        return 2

    accepted = result["accepted"]
    report = result["report"]

    # 真实脱敏记录只落本地非公开目录；合成记录也走同路径但永不进 Gold
    out_file = ensure_dir(PRIVATE_ACCEPTED_DIR) / f"resumes_accepted_{args.source_name}.jsonl"
    if accepted:
        with open(out_file, "w", encoding="utf-8", newline="\n") as f:
            for rec in accepted:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        out_file.write_text("", encoding="utf-8")

    audit = {
        "generated_by": "scripts/phase4_3a_2/intake_resumes.py",
        "created_at": now(),
        "source_class": args.source_class,
        "source_name": args.source_name,
        "consent_records_read": len(consent_records),
        "consent_file": (str(consent_path.relative_to(ROOT)).replace("\\", "/")
                         if consent_path else None),
        "resume_files": [{"file": str(p.relative_to(ROOT)).replace("\\", "/"),
                          "sha256": sha256_file(p), "bytes": p.stat().st_size}
                         for p in files],
        "items_read": report["items_read"],
        "accepted_real_gold": sum(1 for r in accepted if not r["is_synthetic"]),
        "accepted_synthetic_not_gold": sum(1 for r in accepted if r["is_synthetic"]),
        "quarantined": report["quarantined"],
        "quarantine_reasons": report["quarantine_reasons"],
        "formats": report["formats"],
        "pii_hits_masked": report["pii_hits_masked"],
        "accepted_file": str(out_file.relative_to(ROOT)).replace("\\", "/"),
        "accepted_file_sha256": sha256_file(out_file),
        "data_protection": {
            "raw_resume_location": "data/private/（不入库）",
            "accepted_records_location": "data/private/accepted/（不入库）",
            "pii_handling": "导入即脱敏掩码；报告只登记命中类型与数量",
            "id_policy": "resume_id 由内容哈希+种子派生，禁用真实姓名",
        },
        "status": ("real_data_collected" if any(not r["is_synthetic"] for r in accepted)
                   else ("synthetic_only" if accepted else "no_resumes_collected")),
        "note": ("真实简历收集未完成" if not any(not r["is_synthetic"] for r in accepted)
                 else "真实简历已导入（仍需人工双标注后方可冻结 Gold）"),
    }
    write_report("resume-intake-audit.json", audit)
    print(json.dumps({k: audit[k] for k in
                      ("source_class", "source_name", "items_read", "accepted_real_gold",
                       "accepted_synthetic_not_gold", "quarantined", "status")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
