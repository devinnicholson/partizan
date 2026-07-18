#!/usr/bin/env python3
"""Repository-local entry point for the target-free Wave 69-R Gate S lane."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "python/partizan/gate_s.py"
SPEC = importlib.util.spec_from_file_location("partizan_gate_s", MODULE)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load Gate S implementation from {MODULE}")
gate_s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate_s)


if __name__ == "__main__":
    raise SystemExit(gate_s.main())
