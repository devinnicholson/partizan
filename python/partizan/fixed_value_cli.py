"""Search and verify exact fixed-value repertoires."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .fixed_value import (
    build_repertoire,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    compare_repertoire_entries,
    generate_candidates,
    inspect_repertoire,
    load_json,
    load_jsonl,
    sha256_hex,
    validate_repertoire,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the fixed-value command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser(
        "search",
        help="certify and retain candidates equal to one short-game target",
    )
    search.add_argument("--target", type=Path, required=True)
    search.add_argument("--candidates", type=Path, required=True)
    search.add_argument("--seed", type=int, required=True)
    search.add_argument("--budget", type=int, required=True)
    search.add_argument("--max-results", type=int, required=True)
    search.add_argument("--output", type=Path, required=True)

    generate = commands.add_parser(
        "generate",
        help="generate deterministic equivalent short-game candidates",
    )
    generate.add_argument("--target", type=Path, required=True)
    generate.add_argument("--seed", type=int, required=True)
    generate.add_argument("--count", type=int, required=True)
    generate.add_argument("--max-expansion-depth", type=int, default=3)
    generate.add_argument("--output", type=Path, required=True)

    explore = commands.add_parser(
        "explore",
        help="generate, certify, and retain a fixed-value repertoire",
    )
    explore.add_argument("--target", type=Path, required=True)
    explore.add_argument("--seed", type=int, required=True)
    explore.add_argument("--count", type=int, required=True)
    explore.add_argument("--max-expansion-depth", type=int, default=3)
    explore.add_argument("--budget", type=int, required=True)
    explore.add_argument("--max-results", type=int, required=True)
    explore.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser(
        "verify", help="replay every repertoire admission decision"
    )
    verify.add_argument("repertoire", type=Path)

    inspect = commands.add_parser("inspect", help="print a compact repertoire summary")
    inspect.add_argument("repertoire", type=Path)

    compare = commands.add_parser("compare", help="compare two admitted realizations")
    compare.add_argument("repertoire", type=Path)
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    return parser


def _print_json(value: object) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(value))


def main(argv: list[str] | None = None) -> int:
    """Run the fixed-value explorer."""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "generate":
            candidates = generate_candidates(
                load_json(args.target),
                seed=args.seed,
                count=args.count,
                max_expansion_depth=args.max_expansion_depth,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            payload = canonical_jsonl_bytes(candidates)
            args.output.write_bytes(payload)
            print(
                "fixed-value generation: ok "
                f"({args.output}, candidates={len(candidates)}, "
                f"sha256={sha256_hex(payload)})"
            )
            return 0

        if args.command == "explore":
            target = load_json(args.target)
            candidates = generate_candidates(
                target,
                seed=args.seed,
                count=args.count,
                max_expansion_depth=args.max_expansion_depth,
            )
            repertoire = build_repertoire(
                target,
                candidates,
                seed=args.seed,
                budget=args.budget,
                max_results=args.max_results,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            payload = canonical_json_bytes(repertoire)
            args.output.write_bytes(payload)
            print(
                "fixed-value exploration: ok "
                f"({args.output}, admitted={len(repertoire['entries'])}, "
                f"evaluated={len(repertoire['evaluations'])}, "
                f"id={repertoire['repertoire_id']})"
            )
            return 0

        if args.command == "search":
            repertoire = build_repertoire(
                load_json(args.target),
                load_jsonl(args.candidates),
                seed=args.seed,
                budget=args.budget,
                max_results=args.max_results,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            payload = canonical_json_bytes(repertoire)
            args.output.write_bytes(payload)
            print(
                "fixed-value search: ok "
                f"({args.output}, admitted={len(repertoire['entries'])}, "
                f"evaluated={len(repertoire['evaluations'])}, "
                f"id={repertoire['repertoire_id']})"
            )
            return 0

        repertoire = load_json(args.repertoire)
        if args.command == "verify":
            errors = validate_repertoire(repertoire)
            if errors:
                for error in errors:
                    print(
                        f"{args.repertoire}: {error}",
                        file=sys.stderr,
                    )
                return 1
            print(
                "fixed-value repertoire: ok "
                f"({args.repertoire}, id={repertoire['repertoire_id']})"
            )
            return 0
        if args.command == "inspect":
            _print_json(inspect_repertoire(repertoire))
            return 0
        if args.command == "compare":
            _print_json(compare_repertoire_entries(repertoire, args.left, args.right))
            return 0
    except (OSError, TypeError, ValueError) as error:
        print(f"partizan: {error}", file=sys.stderr)
        return 1

    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
