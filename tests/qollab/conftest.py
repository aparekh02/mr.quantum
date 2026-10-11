"""Make the Qollab project folder importable as Qollab runs it (flat modules)."""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2] / "qollab"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
