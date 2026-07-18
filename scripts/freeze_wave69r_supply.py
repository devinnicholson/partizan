#!/usr/bin/env python3
"""Freeze or check the target-free Wave 69-R Gate S pre-result inputs."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "python/partizan/wave69r_supply.py"
SPEC = importlib.util.spec_from_file_location("partizan_wave69r_supply", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load supply freezer from {MODULE_PATH}")
supply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(supply)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subcommands = value.add_subparsers(dest="command", required=True)
    freeze = subcommands.add_parser("freeze")
    check = subcommands.add_parser("check")
    for command in (freeze, check):
        command.add_argument("--input-root", type=Path, default=supply.DEFAULT_INPUT_ROOT)
        command.add_argument("--partizan-dir", type=Path, default=ROOT)
        command.add_argument(
            "--astralbase-dir", type=Path, default=supply.DEFAULT_ASTRALBASE_DIR
        )
        command.add_argument("--bitmesh-dir", type=Path, default=supply.DEFAULT_BITMESH_DIR)
        command.add_argument(
            "--thermograph-dir", type=Path, default=supply.DEFAULT_THERMOGRAPH_DIR
        )
    check.add_argument(
        "--expected-implementation-commit",
        help="explicitly pin I instead of inspecting all four current clean heads",
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "freeze":
            suite = supply.freeze_supply_suite(
                output_root=args.input_root,
                partizan_dir=args.partizan_dir,
                astralbase_dir=args.astralbase_dir,
                bitmesh_dir=args.bitmesh_dir,
                thermograph_dir=args.thermograph_dir,
            )
            print(
                "freeze-wave69r-supply: ok "
                f"(suite_id={suite['suite_id']}, rows={suite['totals']['row_count']})"
            )
        else:
            expected_commits = supply.collect_clean_repository_commits(
                partizan_dir=args.partizan_dir,
                astralbase_dir=args.astralbase_dir,
                bitmesh_dir=args.bitmesh_dir,
                thermograph_dir=args.thermograph_dir,
            )
            suite = supply.validate_supply_suite(
                input_root=args.input_root,
                expected_commits=expected_commits,
                expected_implementation_commit=args.expected_implementation_commit,
                repository_root=args.partizan_dir,
            )
            print(
                "check-wave69r-supply: ok "
                f"(suite_id={suite['suite_id']}, rows={suite['totals']['row_count']})"
            )
        return 0
    except supply.SupplyFreezeError as error:
        print(f"{args.command}-wave69r-supply: error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
