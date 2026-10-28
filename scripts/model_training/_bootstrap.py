# -*- coding: utf-8 -*-
"""把 <项目根>/src 加入 sys.path，供 scripts/model_training 与 tests/model_training 复用。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
