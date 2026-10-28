# -*- coding: utf-8 -*-
"""第三阶段开工前的针对性实测（临时脚本，仅打印统计量，不输出原文）。"""
import ast, json, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"D:\desktop\毕业设计")
RAW = ROOT / "data" / "raw"
M = RAW / "job-resume-matching"
E = RAW / "job-education"

print("=" * 70)
print("1) matches.csv label_strength 真实取值")
mm = pd.read_csv(M / "matches.csv", usecols=["candidate_id", "job_id", "label_strength",
                                             "final_score", "candidate_rank", "candidate_rank_pct"])
print(mm["label_strength"].value_counts().to_dict())
print("dtypes:", mm.dtypes.to_dict())

print("=" * 70)
print("2) job.csv education_text 与 job_description 是否重复")
jb = pd.read_csv(M / "job.csv", usecols=["job_id", "job_title", "category", "job_description",
                                          "job_text", "clean_skills", "clean_skills_json",
                                          "education_text", "years_required"])
print("rows:", len(jb))
eq = (jb["education_text"].astype(str) == jb["job_description"].astype(str))
print("education_text == job_description :", int(eq.sum()), "/", len(jb))
print("years_required describe:", jb["years_required"].describe().to_dict())
print("years_required unique(sorted):", sorted(jb["years_required"].unique().tolist())[:70])
print("years_required 非整数个数:", int((jb["years_required"] % 1 != 0).sum()))

print("=" * 70)
print("3) cv.csv 关键字段")
cv = pd.read_csv(M / "cv.csv", usecols=["candidate_id", "target_position", "clean_skills",
                                        "education_text", "years_experience", "inferred_category"])
print("rows:", len(cv), "years_experience uniq:", sorted(cv["years_experience"].unique().tolist()))
print("inferred_category:", cv["inferred_category"].value_counts().to_dict())
print("clean_skills 空/极短:", int((cv["clean_skills"].astype(str).str.len() <= 3).sum()))

print("=" * 70)
print("4) 技能字段解析形态")
for name, df in (("cv", cv), ("job", jb)):
    s = df["clean_skills"].astype(str)
    ok, bad = 0, 0
    kinds = {}
    for v in s.head(2000):
        try:
            x = ast.literal_eval(v)
            kinds[type(x).__name__] = kinds.get(type(x).__name__, 0) + 1
            ok += 1
        except Exception:
            bad += 1
    print(name, "literal_eval ok:", ok, "bad:", bad, "types:", kinds)
    print(name, "样例(截断60字符):", repr(s.iloc[0][:60]))

print("=" * 70)
print("5) 学历数据：assistant 标签真实形态")
def vc(path, col, n=None):
    d = pd.read_csv(path, usecols=lambda c: c in (col, "job_id", "user"), encoding="utf-8-sig")
    return d

for rel_ in ["default/train/19w_0701.csv", "default/validation/4w_0708.csv",
             "default/test/2w_0716.csv", "annotated/2w_0716_eval.csv"]:
    p = E / rel_
    d = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    print("--", rel_, "rows:", len(d), "cols:", list(d.columns))
    if "assistant" in d.columns:
        a = d["assistant"]
        print("   assistant 缺失:", int(a.isna().sum()), " 唯一值:", int(a.nunique(dropna=True)))
        print("   assistant top15:", a.astype(str).value_counts().head(15).to_dict())
