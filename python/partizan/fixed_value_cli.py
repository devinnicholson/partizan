"""Search and verify exact fixed-value repertoires."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chess_adapter import (
    adapt_chess_position,
    candidate_from_adapter,
    target_from_adapter,
    validate_chess_adapter_record,
)
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

    chess_adapt = commands.add_parser(
        "chess-adapt",
        help="project one constrained FEN into a finite short game",
    )
    chess_adapt.add_argument("--fen", required=True)
    chess_adapt.add_argument("--max-plies", type=int, default=2)
    chess_adapt.add_argument("--node-budget", type=int, default=10_000)
    chess_adapt.add_argument("--output", type=Path, required=True)

    chess_verify = commands.add_parser(
        "chess-verify",
        help="replay one bounded chess adapter record",
    )
    chess_verify.add_argument("record", type=Path)

    chess_target = commands.add_parser(
        "chess-target",
        help="convert an accepted chess adapter record into a fixed-value target",
    )
    chess_target.add_argument("record", type=Path)
    chess_target.add_argument("--name", required=True)
    chess_target.add_argument("--output", type=Path, required=True)

    chess_candidate = commands.add_parser(
        "chess-candidate",
        help="convert an accepted chess adapter record into a search candidate",
    )
    chess_candidate.add_argument("record", type=Path)
    chess_candidate.add_argument("--ordinal", type=int, required=True)
    chess_candidate.add_argument("--output", type=Path, required=True)

    chess_search = commands.add_parser(
        "chess-search",
        help="build a fixed-value repertoire from accepted adapter records",
    )
    chess_search.add_argument("--target-record", type=Path, required=True)
    chess_search.add_argument("--candidate-records", type=Path, required=True)
    chess_search.add_argument("--name", required=True)
    chess_search.add_argument("--seed", type=int, required=True)
    chess_search.add_argument("--budget", type=int, required=True)
    chess_search.add_argument("--max-results", type=int, required=True)
    chess_search.add_argument("--output", type=Path, required=True)
    return parser


def _print_json(value: object) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(value))


def main(argv: list[str] | None = None) -> int:
    """Run the fixed-value explorer."""

    args = build_parser().parse_args(argv)
    try:
        if args.command == "chess-adapt":
            record = adapt_chess_position(
                args.fen,
                max_plies=args.max_plies,
                node_budget=args.node_budget,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_json_bytes(record))
            if record["status"] == "accepted":
                print(
                    "bounded chess adapter: accepted "
                    f"({args.output}, id={record['adapter_id']}, "
                    f"literal={record['projection']['literal_game_sha256']})"
                )
                return 0
            print(
                "bounded chess adapter: refused "
                f"({args.output}, code={record['refusal']['code']}, "
                f"id={record['adapter_id']})"
            )
            return 2

        if args.command == "chess-verify":
            record = load_json(args.record)
            errors = validate_chess_adapter_record(record)
            if errors:
                for error in errors:
                    print(f"{args.record}: {error}", file=sys.stderr)
                return 1
            print(
                "bounded chess adapter record: ok "
                f"({args.record}, status={record['status']}, "
                f"id={record['adapter_id']})"
            )
            return 0

        if args.command == "chess-target":
            target = target_from_adapter(load_json(args.record), name=args.name)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_json_bytes(target))
            print(
                "fixed-value chess target: ok "
                f"({args.output}, id={target['target_id']})"
            )
            return 0

        if args.command == "chess-candidate":
            candidate = candidate_from_adapter(
                load_json(args.record),
                ordinal=args.ordinal,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_json_bytes(candidate))
            print(
                "fixed-value chess candidate: ok "
                f"({args.output}, id={candidate['candidate_id']})"
            )
            return 0

        if args.command == "chess-search":
            target = target_from_adapter(
                load_json(args.target_record),
                name=args.name,
            )
            candidates = [
                candidate_from_adapter(record, ordinal=ordinal)
                for ordinal, record in enumerate(load_jsonl(args.candidate_records))
            ]
            repertoire = build_repertoire(
                target,
                candidates,
                seed=args.seed,
                budget=args.budget,
                max_results=args.max_results,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_json_bytes(repertoire))
            print(
                "fixed-value chess search: ok "
                f"({args.output}, admitted={len(repertoire['entries'])}, "
                f"evaluated={len(repertoire['evaluations'])}, "
                f"id={repertoire['repertoire_id']})"
            )
            return 0

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
