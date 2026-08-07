#!/usr/bin/env python3
"""Check the public Partizan source-distribution inventory."""

from __future__ import annotations

import argparse
from pathlib import PurePosixPath
import tarfile


REQUIRED = {
    "README.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "DCO.md",
    "LICENSE",
    "SECURITY.md",
    "SUPPORT.md",
    "pyproject.toml",
    "docs/bounded_chess_adapter.md",
    "docs/bounded_short_game.md",
    "docs/package_boundary.md",
    "docs/schemas/partizan-bounded-chess-adapter-v0.1.schema.json",
    "docs/schemas/partizan-bounded-chess-adapter-v0.2.schema.json",
    "engine/Cargo.lock",
    "engine/Cargo.toml",
    "engine/src/chess_adapter.rs",
    "python/partizan/chess_adapter.py",
    "scripts/check_sdist_contents.py",
    "tests/fixtures/semantic/day2-semantic-ids-v1.txt",
    "tests/fixtures/fixed_value/chess-adapter-v0.1.valid.json",
    "tests/fixtures/fixed_value/README.md",
    "tests/test_bounded_short_game.py",
    "tests/test_chess_adapter.py",
    "tests/test_semantic_canonical_form.py",
}
FORBIDDEN_PREFIXES = (".git/", "output/", "visualizer/", "paper/")
MAX_MEMBER_BYTES = 5 * 1024 * 1024


def _relative_names(archive: tarfile.TarFile) -> dict[str, tarfile.TarInfo]:
    files: dict[str, tarfile.TarInfo] = {}
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if member.isdir() or len(path.parts) < 2:
            continue
        relative = PurePosixPath(*path.parts[1:]).as_posix()
        files[relative] = member
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    args = parser.parse_args()

    with tarfile.open(args.archive, mode="r:gz") as archive:
        files = _relative_names(archive)

    missing = sorted(REQUIRED - files.keys())
    forbidden = sorted(
        name for name in files if name.startswith(FORBIDDEN_PREFIXES)
    )
    oversized = sorted(
        name for name, member in files.items() if member.size > MAX_MEMBER_BYTES
    )
    if missing or forbidden or oversized:
        raise SystemExit(
            "sdist inventory failed: "
            f"missing={missing}, forbidden={forbidden}, oversized={oversized}"
        )
    print(f"sdist inventory: ok ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
