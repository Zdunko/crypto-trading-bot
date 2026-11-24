"""Make the `quantlab` package importable when pytest is started from the repository root."""

import sys
from pathlib import Path


_QUANT_DIR = str(Path(__file__).resolve().parent)
if _QUANT_DIR not in sys.path:
    sys.path.insert(0, _QUANT_DIR)
