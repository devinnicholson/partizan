#!/usr/bin/env python3
"""Validate fixed-value schemas, fixtures, and one replayed repertoire."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
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

    replay_errors = validate_repertoire(repertoire)
    if replay_errors:
        raise ValueError("; ".join(replay_errors))
    print(
        "fixed-value schemas: ok "
        f"(target=1, candidates={len(candidates)}, repertoire=1)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
