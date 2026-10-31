# -*- coding: utf-8 -*-
"""tests/phase7 公共工具：路径与 sys.path 注入。"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase7"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase7"
