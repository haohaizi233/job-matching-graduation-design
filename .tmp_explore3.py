# -*- coding: utf-8 -*-
"""临时探查：二部图结构与 double-cold 切分策略对比（不写入任何产物）。"""
import io
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, "src")

m = pd.read_csv("data/raw/job-resume-matching/matches.csv", encoding="utf-8-sig",
                low_memory=False)
m["candidate_id"] = m["candidate_id"].astype(str)
m["job_id"] = m["job_id"].astype("int64")
print("edges", len(m), "cands", m.candidate_id.nunique(), "jobs", m.job_id.nunique())

cdeg = m.groupby("candidate_id").size()
jdeg = m.groupby("job_id").size()
print("candidate degree: min %d p50 %.1f mean %.1f max %d" %
      (cdeg.min(), cdeg.median(), cdeg.mean(), cdeg.max()))
print("job degree: min %d p50 %.1f mean %.1f max %d" %
      (jdeg.min(), jdeg.median(), jdeg.mean(), jdeg.max()))

# 类别同配性
res = pd.read_csv("data/interim/matching/resume_normalized.csv", usecols=["candidate_id", "inferred_category"], low_memory=False)
job = pd.read_csv("data/interim/matching/job_normalized.csv", usecols=["job_id", "category"], low_memory=False)
m2 = m.merge(res, on="candidate_id").merge(job, on="job_id")
print("category_match rate:", float((m2.inferred_category == m2.category).mean()))

# 候选人侧 80/10/10 后，验证/测试候选人的作业分布
sys.path.insert(0, "scripts/data_pipeline")
from job_matching.split_matching import assign_groups  # noqa: E402

ratios = {"train": 0.8, "validation": 0.1, "test": 0.1}
cand_assign = assign_groups(cdeg, ratios, 20261030)
m["cs"] = m["candidate_id"].map(cand_assign)
print("\n== 策略 A：job argmax（当前实现）==")
jc = m.groupby("job_id")["cs"].value_counts().unstack(fill_value=0)
for s in ("train", "validation", "test"):
    jc[s] = jc.get(s, 0)
job_assign = jc[["train", "validation", "test"]].idxmax(axis=1)
m["js"] = m["job_id"].map(job_assign)
kept = m[m.cs == m.js]
print("kept", len(kept), "ratio %.4f" % (len(kept) / len(m)))
print(kept.cs.value_counts())
for s in ("validation", "test"):
    sub = kept[kept.cs == s]
    g = sub.groupby("candidate_id").size()
    print(s, "edges", len(sub), "cands", len(g), "rankable>=2", int((g >= 2).sum()))

print("\n== 策略 B：job 按 n_s(j) 比例随机（种子 20261030）==")
rng = np.random.default_rng(20261030)
vals = jc[["train", "validation", "test"]].to_numpy(dtype=float)
prob = vals / vals.sum(axis=1, keepdims=True)
u = rng.random(len(jc))
cum = np.cumsum(prob, axis=1)
jsb = np.array([["train", "validation", "test"][int(np.searchsorted(cum[i], u[i]))]
                for i in range(len(jc))])
m["js"] = m["job_id"].map(dict(zip(jc.index, jsb)))
kept = m[m.cs == m.js]
print("kept", len(kept), "ratio %.4f" % (len(kept) / len(m)))
print(kept.cs.value_counts())
for s in ("validation", "test"):
    sub = kept[kept.cs == s]
    g = sub.groupby("candidate_id").size()
    print(s, "edges", len(sub), "cands", len(g), "rankable>=2", int((g >= 2).sum()))

print("\n== 策略 D3：成本效益贪心 + 每个次要集合独立预算 ==")
cand_split = dict(zip(m["candidate_id"], m["cs"]))
edges_by_job = {j: g["candidate_id"].tolist() for j, g in m.groupby("job_id")}
for budget_ratio in (0.15, 0.20, 0.30):
    rng3 = np.random.default_rng(20261031)
    job_order = [int(x) for x in rng3.permutation(jc.index.to_numpy())]
    n_side2 = {int(j): {"train": int(jc.loc[j, "train"]),
                        "validation": int(jc.loc[j, "validation"]),
                        "test": int(jc.loc[j, "test"])} for j in jc.index}
    eval_edges = {s: {j: [c for c in edges_by_job[j] if cand_split.get(c) == s]
                      for j in job_order} for s in ("validation", "test")}
    kept_count2 = {s: {c: 0 for c, sp in cand_split.items() if sp == s}
                   for s in ("validation", "test")}
    assign4 = {}
    for s in ("validation", "test"):
        budget = budget_ratio * len(m)
        spent = 0
        unassigned = {j for j in job_order if j not in assign4}
        while True:
            best, best_score, best_cost = None, -1.0, 0
            for j in unassigned:
                gain = 0
                for c in eval_edges[s][j]:
                    k = kept_count2[s][c]
                    if k == 1:
                        gain += 4
                    elif k == 0:
                        gain += 1
                if gain <= 0:
                    continue
                cost = n_side2[j]["train"]
                if spent + cost > budget:
                    continue
                score = gain / max(cost, 1)
                if score > best_score:
                    best, best_score, best_cost = j, score, cost
            if best is None:
                break
            assign4[best] = s
            spent += best_cost
            unassigned.discard(best)
            for c in eval_edges[s][best]:
                kept_count2[s][c] += 1
    for j in job_order:
        if j not in assign4:
            assign4[j] = max(("train", "validation", "test"),
                             key=lambda s: (n_side2[j][s], 0))
    m["js4"] = m["job_id"].map(assign4)
    kept = m[m.cs == m.js4]
    print("per-split budget %.2f kept %d ratio %.4f | train %d" %
          (budget_ratio, len(kept), len(kept) / len(m), int((kept.cs == "train").sum())))
    for s in ("validation", "test"):
        sub = kept[kept.cs == s]
        g = sub.groupby("candidate_id").size()
        print("   %s edges %d cands %d rankable>=2 %d ge5 %d ge10 %d" %
              (s, len(sub), len(g), int((g >= 2).sum()), int((g >= 5).sum()),
               int((g >= 10).sum())))
