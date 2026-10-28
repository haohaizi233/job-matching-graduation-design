# -*- coding: utf-8 -*-
"""结构与质量审计：对 data/raw 下 8 个 CSV 做统一的结构/规模/质量画像。

产出：reports/data-audit/dataset-profile.json（本脚本只写 JSON，不写 Markdown）
用法：python scripts/data_audit/profile_datasets.py

只读 data/raw；大型文件按 usecols/分块读取，内存占用受控。
不输出简历全文、联系方式、公司地址等敏感原文。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

DATASETS = {
    "job-resume-matching/cv.csv": {
        "path": C.CV,
        "id_cols": ["candidate_id"],
        "text_cols": ["target_position", "resume_text", "clean_skills",
                      "education_text", "experience_text"],
        "key": "候选人画像表",
    },
    "job-resume-matching/job.csv": {
        "path": C.JOB,
        "id_cols": ["job_id"],
        "text_cols": ["job_title", "job_description", "job_text",
                      "clean_skills", "education_text"],
        "key": "岗位画像表",
    },
    "job-resume-matching/matches.csv": {
        "path": C.MATCHES,
        "id_cols": ["candidate_id", "job_id"],
        "text_cols": [],
        "key": "人岗兼容性记录表",
    },
    "other/all_df.csv/all_df.csv": {
        "path": C.RISK,
        "id_cols": [],
        "text_cols": ["job_name", "company_name", "company_address"],
        "key": "中文招聘岗位风险表",
    },
    "job-education/default/train/19w_0701.csv": {
        "path": C.EDU_TRAIN,
        "id_cols": ["job_id", "id"],
        "text_cols": ["user", "assistant", "system", "user_short", "user_short2"],
        "key": "学历抽取训练集",
    },
    "job-education/default/validation/4w_0708.csv": {
        "path": C.EDU_VAL,
        "id_cols": ["job_id", "id"],
        "text_cols": ["user", "assistant", "system", "user_short", "user_short2"],
        "key": "学历抽取验证集",
    },
    "job-education/default/test/2w_0716.csv": {
        "path": C.EDU_TEST,
        "id_cols": ["job_id", "id"],
        "text_cols": ["user", "assistant", "system", "user_short", "user_short2"],
        "key": "学历抽取测试集",
    },
    "job-education/annotated/2w_0716_eval.csv": {
        "path": C.EDU_ANNOT,
        "id_cols": ["job_id", "id"],
        "text_cols": ["user", "assistant", "user_short", "人工正确结果",
                      "模型结果-新的", "线上学历-旧的"],
        "key": "学历抽取人工标注评测集",
    },
}


def profile_one(name: str, cfg: dict) -> dict:
    p = cfg["path"]
    print("  处理 %s ..." % name, file=sys.stderr)
    df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    meta = C.file_meta(p)
    text_cols = [c for c in cfg["text_cols"] if c in df.columns]
    id_cols = [c for c in cfg["id_cols"] if c in df.columns]
    return {
        "dataset": name,
        "description": cfg["key"],
        "file": meta,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "column_count": int(df.shape[1]),
        "whole_row_duplicates": int(df.duplicated().sum()),
        "whole_row_duplicates_pct": round(float(df.duplicated().mean()) * 100, 4),
        "columns_profile": C.column_profile(df, text_cols=text_cols, id_cols=id_cols),
    }


def main() -> int:
    C.ensure_out()
    out = {
        "generated_by": "scripts/data_audit/profile_datasets.py",
        "root": str(C.ROOT),
        "note": "只读审计；未修改、未移动、未重写任何原始文件。",
        "datasets": {},
    }
    for name, cfg in DATASETS.items():
        if not cfg["path"].is_file():
            out["datasets"][name] = {"error": "文件不存在: %s" % cfg["path"]}
            continue
        out["datasets"][name] = profile_one(name, cfg)

    # 汇总表
    rows = []
    for name, d in out["datasets"].items():
        if "error" in d:
            rows.append({"dataset": name, "error": d["error"]})
            continue
        miss = {c: v["missing"] for c, v in d["columns_profile"].items() if v["missing"]}
        rows.append({
            "dataset": name,
            "rows": d["rows"],
            "columns": d["column_count"],
            "bytes": d["file"]["bytes"],
            "encoding": d["file"]["encoding"],
            "whole_row_duplicates": d["whole_row_duplicates"],
            "columns_with_missing": miss,
        })
    out["summary_table"] = rows

    C.jdump(out, C.OUT / "dataset-profile.json")
    print("\n=== 汇总 ===")
    print(pd.DataFrame(rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
