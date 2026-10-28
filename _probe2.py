import json
from pathlib import Path
root = Path(r"D:\desktop\毕业设计")
out=[]
def add(s): out.append(str(s))
import numpy, pandas, sklearn, scipy
add(f"numpy={numpy.__version__} pandas={pandas.__version__} sklearn={sklearn.__version__} scipy={scipy.__version__}")
import torch
add(f"torch={torch.__version__} cuda_available={torch.cuda.is_available()} torch.version.cuda={torch.version.cuda}")
if torch.cuda.is_available():
    add(f"gpu={torch.cuda.get_device_name(0)} cap={torch.cuda.get_device_capability(0)} mem={torch.cuda.get_device_properties(0).total_memory/1024**2:.0f}MB")
b = json.loads((root/"reports/baselines/baseline-results.json").read_text(encoding="utf-8"))
m = b["matching"]
add("matching keys: " + str(list(m.keys())))
cc = m["candidate_cold"]
add("candidate_cold keys: " + str(list(cc.keys())))
add("subsets keys: " + str(list(cc["subsets"].keys())))
te = cc["subsets"]["test"]
add("test keys: " + str(list(te.keys())))
add("results gain modes: " + str(list(te["results"].keys())))
gm = te["results"]["score"]
for name, val in gm.items():
    add(f"baseline {name} keys: {list(val.keys())}")
    if "aggregate" in val:
        add(f"   aggregate: {json.dumps(val['aggregate'].get('size_ge_2', {}), ensure_ascii=False)}")
    if "repeated_stats" in val:
        add(f"   repeated: {json.dumps(val['repeated_stats'], ensure_ascii=False)}")
# features/targets quick check
import pandas as pd
f = pd.read_csv(root/"data/processed/matching/features_pairs.csv", nrows=3)
add("features dtypes: " + str({c: str(t) for c, t in f.dtypes.items()}))
t = pd.read_csv(root/"data/processed/matching/targets_pairs.csv", nrows=3)
add("targets ok")
add("idmap sample: " + (root/"data/processed/embeddings/cv_id_map.json").read_text(encoding="utf-8")[:300])
(root/"_scan4.txt").write_text("\n".join(out), encoding="utf-8")