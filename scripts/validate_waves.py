#!/usr/bin/env python3
"""Validate the research network and every checked-in Wave plan."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str) -> None:
    """Run one network validation command or fail immediately."""

    result = subprocess.run(
        (sys.executable, "agents/network.py", *arguments), cwd=ROOT, check=False
    )
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> int:
    """Validate the network and all Wave JSON files in stable order."""

    run("validate")
    wave_paths = sorted((ROOT / "agents" / "waves").glob("wave_*.json"))
    for path in wave_paths:
        run("validate-wave", str(path.relative_to(ROOT)))
    print(f"wave validation: ok ({len(wave_paths)} plans)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
