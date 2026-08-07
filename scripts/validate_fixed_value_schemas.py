#!/usr/bin/env python3
"""Validate fixed-value schemas, fixtures, and one replayed repertoire."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from partizan.chess_adapter import (
    adapt_chess_position,
    validate_chess_adapter_record,
)
from partizan.fixed_value import (
    build_repertoire,
    load_json,
    load_jsonl,
    validate_repertoire,
)
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRECTORY = ROOT / "docs" / "schemas"
FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "fixed_value"
SCHEMA_NAMES = (
    "partizan-fixed-value-target-v0.1.schema.json",
    "partizan-fixed-value-candidate-v0.1.schema.json",
    "partizan-fixed-value-repertoire-v0.1.schema.json",
    "partizan-bounded-chess-adapter-v0.1.schema.json",
    "partizan-bounded-chess-adapter-v0.2.schema.json",
)


def main() -> int:
    """Validate schema definitions and their checked examples."""

    schemas = {
        name: json.loads((SCHEMA_DIRECTORY / name).read_text(encoding="utf-8"))
        for name in SCHEMA_NAMES
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)

    target = load_json(FIXTURE_DIRECTORY / "target-zero.valid.json")
    candidates = load_jsonl(FIXTURE_DIRECTORY / "candidates-zero.valid.jsonl")
    repertoire = build_repertoire(
        target,
        candidates,
        seed=0,
        budget=5,
        max_results=5,
    )
    Draft202012Validator(schemas[SCHEMA_NAMES[0]], registry=registry).validate(target)
    candidate_validator = Draft202012Validator(
        schemas[SCHEMA_NAMES[1]], registry=registry
    )
    for candidate in candidates:
        candidate_validator.validate(candidate)
    Draft202012Validator(schemas[SCHEMA_NAMES[2]], registry=registry).validate(
        repertoire
    )
    accepted_adapter = adapt_chess_position(
        "7k/5K2/6Q1/8/8/8/8/8 w - - 0 1",
        max_plies=1,
        node_budget=100,
    )
    refused_adapter = adapt_chess_position(
        "8/8/8/8/8/8/8/4K2k w - - 0 1",
        max_plies=2,
        node_budget=100,
    )
    adapter_validator = Draft202012Validator(
        schemas[SCHEMA_NAMES[4]], registry=registry
    )
    adapter_validator.validate(accepted_adapter)
    adapter_validator.validate(refused_adapter)
    legacy_adapter = load_json(
        FIXTURE_DIRECTORY / "chess-adapter-v0.1.valid.json"
    )
    Draft202012Validator(
        schemas[SCHEMA_NAMES[3]], registry=registry
    ).validate(legacy_adapter)
    legacy_errors = validate_chess_adapter_record(legacy_adapter)
    if legacy_errors:
        raise ValueError("; ".join(legacy_errors))

    replay_errors = validate_repertoire(repertoire)
    if replay_errors:
        raise ValueError("; ".join(replay_errors))
    print(
        "fixed-value schemas: ok "
        f"(target=1, candidates={len(candidates)}, repertoire=1, adapters=3)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
