#!/usr/bin/env python3
"""Repository-local entry point for frozen Wave 69 baseline analysis."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "python"
    / "partizan"
    / "discovery_baselines.py"
)
SPEC = importlib.util.spec_from_file_location("partizan_discovery_baselines", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("could not load Wave 69 baseline module")
baselines = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baselines)

# Public contract used by the pre-verification suite freezer.  Keep this
# re-export at the wrapper boundary so dynamic script loaders do not need to
# know about the implementation module nested below it.
validate_policy_orders = baselines.validate_policy_orders


if __name__ == "__main__":
    raise SystemExit(baselines.main())
