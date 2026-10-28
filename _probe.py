import json, sys
from pathlib import Path
root = Path(r"D:\desktop\毕业设计")
out = []
def add(s): out.append(str(s))
b = json.loads((root/"reports/baselines/baseline-results.json").read_text(encoding="utf-8"))
add("== baseline-results.json top keys ==")
add(list(b.keys()))
for k,v in b.items():
    if isinstance(v, dict):
        add(f"  {k}: dict keys={list(v.keys())[:12]}")
    else:
        add(f"  {k}: {type(v).__name__} = {str(v)[:200]}")
sub = b.get("protocols") or b.get("results") or {}
add("--- nested sample ---")
add(json.dumps({k: (list(v.keys()) if isinstance(v,dict) else v) for k,v in list(sub.items())[:3]}, ensure_ascii=False)[:2000])
import yaml
cfg = yaml.safe_load((root/"configs/data_pipeline.yaml").read_text(encoding="utf-8"))
add("== data_pipeline.yaml ==")
add(json.dumps(cfg, ensure_ascii=False, indent=1)[:4000])
ms = yaml.safe_load((root/"configs/matching_splits.yaml").read_text(encoding="utf-8"))
add("== matching_splits.yaml ==")
add(json.dumps(ms, ensure_ascii=False, indent=1)[:3000])
add("== targets_pairs head ==")
import pandas as pd
t = pd.read_csv(root/"data/processed/matching/targets_pairs.csv", nrows=5)
add(t.to_string())
add(t.dtypes.to_dict())
add("== relevance_role values ==")
t2 = pd.read_csv(root/"data/processed/matching/targets_pairs.csv", usecols=["relevance_role","label_ordinal"])
add(t2["relevance_role"].value_counts().to_dict())
add(t2["label_ordinal"].value_counts().to_dict())
add("== embeddings metadata ==")
add((root/"data/processed/embeddings/metadata.json").read_text(encoding="utf-8")[:2500])
(root/"_scan3.txt").write_text("\n".join(out), encoding="utf-8")