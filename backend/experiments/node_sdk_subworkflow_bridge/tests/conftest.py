"""Make the experiments package and Syntara src importable for this POC."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
SRC = BACKEND / "src"
EXPERIMENTS = BACKEND / "experiments"

for path in (SRC, EXPERIMENTS):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
