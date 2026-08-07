#!/usr/bin/env python3
"""Reject newly tracked large artifacts while preserving frozen history."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_BYTES = 5 * 1024 * 1024

# These files predate the artifact policy and are referenced by retained
# research records. Their bytes remain frozen; new large files are rejected.
FROZEN_LARGE_FILES = {
    "docs/signature_target_mixed_hook_exact_wave_55_rpf36.jsonl": (
        12_383_285,
        "86022f1abd7b4c10cda55fdc84f07c4c0252191dad55a3824786b1f0dd43f850",
    ),
    "docs/signature_target_mixed_hook_exact_wave_55_rpf36_result_signature_report.json": (
        6_650_500,
        "8ce91e333b3a7789abcf79172425b3f465694ee0dd093143faab54e29f0c94fb",
    ),
}


def tracked_paths(root: Path = ROOT) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return [root / item.decode("utf-8") for item in output.split(b"\0") if item]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for path in tracked_paths(root):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if size <= MAX_TRACKED_BYTES:
            continue
        frozen = FROZEN_LARGE_FILES.get(relative)
        if frozen is None:
            errors.append(
                f"{relative}: tracked file is {size} bytes; publish it as a "
                "versioned artifact and retain a compact manifest"
            )
            continue
        expected_size, expected_sha256 = frozen
        if size != expected_size or sha256(path) != expected_sha256:
            errors.append(f"{relative}: frozen historical artifact bytes changed")
    return errors


def main() -> int:
    errors = audit()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("repository artifact hygiene: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
