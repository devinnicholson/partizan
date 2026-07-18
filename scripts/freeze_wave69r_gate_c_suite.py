#!/usr/bin/env python3
"""Repository-local entry point for the Wave 69-R Gate C suite contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "python/partizan/wave69r_gate_c_suite.py"
)
SPEC = importlib.util.spec_from_file_location("partizan_wave69r_gate_c_suite", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("cannot load Wave 69-R Gate C suite module")
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


if __name__ == "__main__":
    raise SystemExit(suite.main())
