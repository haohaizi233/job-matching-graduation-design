# -*- coding: utf-8 -*-
"""学历数据专项实测：标签词表、重复关系、金标准定位（临时脚本）。"""
import hashlib, re
from pathlib import Path
import pandas as pd

ROOT = Path(r"D:\desktop\毕业设计")
E = ROOT / "data" / "raw" / "job-education"

def load(p):
    return pd.read_csv(p, encoding="utf-8-sig", low_memory=False)

tr = load(E / "default/train/19w_0701.csv")
va = load(E / "default/validation/4w_0708.csv")
te = load(E / "default/test/2w_0716.csv")
an = load(E / "annotated/2w_0716_eval.csv")

print("rows:", len(tr), len(va), len(te), len(an))

def toks(s):
    out = set()
    for v in s.dropna().astype(str):
        for t in re.split(r"[、,，/|]", v):
            t = t.strip()
            if t:
                out.add(t)
    return out

allv = set()
for name, df in (("train", tr), ("val", va), ("test", te), ("annot", an)):
    for col in ("assistant", "人工正确结果", "线上学历-旧的", "模型结果-新的"):
        if col in df.columns:
            u = sorted(df[col].dropna().astype(str).unique().tolist())
            t = toks(df[col])
            allv |= t
            print(f"[{name}.{col}] unique={len(u)} 非空={int(df[col].notna().sum())}")
            if col in ("人工正确结果",) or name == "train":
                print("    值:", u)
            else:
                print("    值(前20):", u[:20])
print("\n全量 token 词表:", sorted(allv))

print("=" * 70)
print("金标准定位")
gold = an[an["人工正确结果"].notna()]
print("annotated 人工正确结果 非空:", len(gold))
print("gold.人工正确结果 值:", sorted(gold["人工正确结果"].astype(str).unique().tolist()))
print("gold 中 assistant 非空:", int(gold["assistant"].notna().sum()))
same = (gold["assistant"].astype(str) == gold["人工正确结果"].astype(str))
print("gold 中 assistant == 人工正确结果:", int(same.sum()), "/", len(gold))
same_old = (gold["线上学历-旧的"].astype(str) == gold["人工正确结果"].astype(str))
print("线上学历-旧的 == 人工正确结果:", int(same_old.sum()))
same_new = (gold["模型结果-新的"].astype(str) == gold["人工正确结果"].astype(str))
print("模型结果-新的 == 人工正确结果:", int(same_new.sum()))

print("=" * 70)
print("test 与 annotated 的行对应关系")
print("test.id 唯一:", te["id"].is_unique, "annot.id 唯一:", an["id"].is_unique)
print("id 集合相同:", set(te["id"].dropna().astype(str)) == set(an["id"].dropna().astype(str)))
m = te.merge(an, on="id", suffixes=("_te", "_an"))
print("按 id join 行数:", len(m))
print("user 完全一致:", int((m["user_te"].astype(str) == m["user_an"].astype(str)).sum()))
te_nn = te[te["assistant"].notna()]
print("test.assistant 非空:", len(te_nn))
mm = te_nn.merge(an[["id", "人工正确结果"]], on="id", how="left")
print("test 非空 assistant 与 gold 同行:", int(mm["人工正确结果"].notna().sum()),
      " 一致:", int((mm["assistant"].astype(str) == mm["人工正确结果"].astype(str)).sum()))

print("=" * 70)
print("重复关系（跨 default 三份）")
def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip()
def h(s):
    return hashlib.sha256(norm(s).encode("utf-8")).hexdigest()[:16]

for name, df in (("train", tr), ("val", va), ("test", te)):
    jid = df["job_id"]
    print(f"[{name}] rows={len(df)} job_id_dup={int(jid.duplicated().sum())} "
          f"user_dup={int(df['user'].duplicated().sum())} "
          f"(job_id,user)_dup={int(df.duplicated(['job_id','user']).sum())} "
          f"normuser_dup={int(df['user'].map(h).duplicated().sum())} "
          f"fullrow_dup={int(df.duplicated().sum())}")

sets = {}
for name, df in (("train", tr), ("val", va), ("test", te)):
    sets[name] = (set(df["job_id"].astype(str)), set(df["user"].map(h)))
    print(name, "job_id 唯一数:", df["job_id"].nunique(), "normuser 唯一数:", df["user"].map(h).nunique())

for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
    ja, ua = sets[a]; jb, ub = sets[b]
    print(f"{a}∩{b}: job_id={len(ja&jb)} normuser={len(ua&ub)}")

print("=" * 70)
print("金标准与 default 三份的交叉（按 norm user hash）")
gh = set(gold["user"].map(h))
gj = set(gold["job_id"].astype(str))
for name, df in (("train", tr), ("val", va), ("test", te)):
    uh = set(df["user"].map(h)); jj = set(df["job_id"].astype(str))
    print(f"gold ∩ {name}: normuser={len(gh & uh)} job_id={len(gj & jj)}")

print("=" * 70)
print("user 结构抽样（仅打印标签片段，不打印 JD 原文）")
u0 = an["user"].astype(str)
seg = u0.str.extract(r"<学历描述>(.*?)</学历描述>", expand=False)
print("含<学历描述>比例:", float(seg.notna().mean()))
print("学历描述 长度统计:", seg.dropna().str.len().describe().to_dict())
print("学历描述 top15:", seg.dropna().value_counts().head(15).to_dict())
print("是否英文岗位 值:", an["是否英文岗位"].value_counts(dropna=False).to_dict())
