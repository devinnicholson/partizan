#!/usr/bin/env python3
"""Execute or check the Wave 69-R Gate C evidence lane."""

from pathlib import Path
import importlib.util
import sys


MODULE = Path(__file__).resolve().parents[1] / "python/partizan/wave69r_gate_c_evidence.py"
SPEC = importlib.util.spec_from_file_location("partizan_wave69r_gate_c_evidence", MODULE)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load {MODULE}")
IMPLEMENTATION = importlib.util.module_from_spec(SPEC)
PREVIOUS_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    SPEC.loader.exec_module(IMPLEMENTATION)
finally:
    sys.dont_write_bytecode = PREVIOUS_BYTECODE


if __name__ == "__main__":
    raise SystemExit(IMPLEMENTATION.main())
