"""Make `quantlab` and the strategy modules importable when pytest starts at the repo root."""

import sys
from pathlib import Path


_QUANT_DIR = Path(__file__).resolve().parent
for _path in (_QUANT_DIR, _QUANT_DIR / "strategies", _QUANT_DIR / "strategies_r1"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
