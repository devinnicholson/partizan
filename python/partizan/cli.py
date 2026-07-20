"""Command-line interface for versioned Partizan event streams."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .events import build_event_stream, canonical_event_bytes, validate_event_stream


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    from_fen = commands.add_parser("from-fen", help="emit a validated event stream")
    from_fen.add_argument("--fen", required=True)
    from_fen.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate an event stream")
    validate.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the event-stream CLI."""

    args = build_parser().parse_args(argv)
    if args.command == "from-fen":
        try:
            payload = canonical_event_bytes(build_event_stream(args.fen))
        except (ValueError, RuntimeError) as error:
            print(f"partizan-events: {error}", file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        print(f"event stream: ok ({args.output}, bytes={len(payload)})")
        return 0
    value = json.loads(args.path.read_text(encoding="utf-8"))
    errors = validate_event_stream(value)
    if errors:
        for error in errors:
            print(f"{args.path}: {error}", file=sys.stderr)
        return 1
    print(f"event stream: ok ({args.path})")
    return 0
