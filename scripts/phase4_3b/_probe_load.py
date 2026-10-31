"""Quick probe: can historical checkpoints be loaded in the current env?"""
import glob
import os
import pickle
import sys
import time
import traceback

ROOT = r"D:\desktop\毕业设计\models"
PY = sys.version.split()[0]
import numpy, pandas, sklearn, joblib  # noqa
print(f"python={PY} numpy={numpy.__version__} pandas={pandas.__version__} "
      f"sklearn={sklearn.__version__} joblib={joblib.__version__}")
try:
    import torch
    print(f"torch={torch.__version__} cuda={torch.cuda.is_available()}")
except Exception as e:  # pragma: no cover
    print("torch:", e)

targets = []
targets += sorted(glob.glob(os.path.join(ROOT, "matching", "gradient_boosting", "*", "*", "model.pkl")))
targets += sorted(glob.glob(os.path.join(ROOT, "matching", "ridge", "*", "ridge-candidate_cold-final*", "model.pkl")))
targets += sorted(glob.glob(os.path.join(ROOT, "matching", "mlp", "*", "mlp-*final*", "model.pkl")))
targets += sorted(glob.glob(os.path.join(ROOT, "matching", "ranknet", "*", "ranknet-*final*", "model.pkl")))
targets += sorted(glob.glob(os.path.join(ROOT, "education", "tfidf", "tfidf-final-*", "model.pkl")))
targets += sorted(glob.glob(os.path.join(ROOT, "education", "charcnn", "charcnn-final-*", "model.pt")))

for p in targets:
    t0 = time.time()
    try:
        if p.endswith(".pt"):
            import torch
            obj = torch.load(p, map_location="cpu")
            kind = type(obj).__name__
        else:
            with open(p, "rb") as f:
                obj = pickle.load(f)
            kind = type(obj).__name__
        print(f"[OK ] {os.path.relpath(p, ROOT)}  type={kind}  {time.time()-t0:.3f}s")
    except Exception as e:
        print(f"[ERR] {os.path.relpath(p, ROOT)}  {type(e).__name__}: {e}")
