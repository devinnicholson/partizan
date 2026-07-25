#!/usr/bin/env python3
"""Build the checked fixed-value crossing used by the Partizan visualizer."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import partizan

SCHEMA_VERSION = "partizan.visual_crossing.v0.1"
DEFAULT_OUTPUT = Path("visualizer/public/evidence/crossing.json")
MAX_PLIES = 4
NODE_BUDGET = 20_000
REALIZATIONS = (
    {
        "label": "I",
        "name": "The distant queen",
        "fen": "7k/8/5K2/8/8/8/8/6Q1 w - - 0 1",
    },
    {
        "label": "II",
        "name": "The near queen",
        "fen": "7k/8/5KQ1/8/8/8/8/8 w - - 0 1",
    },
)


def _one() -> dict[str, Any]:
    zero = {"left": [], "right": []}
    return {"left": [zero], "right": []}


def build_evidence() -> dict[str, Any]:
    """Recompute the visual crossing from the native adapter and exact verifier."""

    records = [
        partizan.adapt_chess_position(
            item["fen"],
            max_plies=MAX_PLIES,
            node_budget=NODE_BUDGET,
        )
        for item in REALIZATIONS
    ]
    if any(record["status"] != "accepted" for record in records):
        raise ValueError("the visual crossing requires two accepted adapter records")

    target = partizan.fixed_value_target_from_chess_adapter(
        records[0],
        name="bounded-one",
    )
    candidates = [
        partizan.fixed_value_candidate_from_chess_adapter(record, ordinal=index)
        for index, record in enumerate(records)
    ]
    repertoire = partizan.build_repertoire(
        target,
        candidates,
        seed=0,
        budget=2,
        max_results=2,
    )
    if partizan.validate_repertoire(repertoire):
        raise ValueError("the visual crossing repertoire failed replay validation")

    one = _one()
    equal_to_one = [
        partizan.compare_short_games(candidate["literal_game"], one).equivalent
        for candidate in candidates
    ]
    equal_to_each_other = partizan.compare_short_games(
        candidates[0]["literal_game"],
        candidates[1]["literal_game"],
    ).equivalent
    transitions = sorted(
        {
            entry["admission_relation"]["transition_kind"]
            for entry in repertoire["entries"]
        }
    )
    if not all(equal_to_one) or not equal_to_each_other:
        raise ValueError("the visual crossing no longer certifies the value 1")
    if "literal_game_crossing" not in transitions:
        raise ValueError("the visual crossing lost its literal-game transition")

    realizations: list[dict[str, Any]] = []
    for item, record in zip(REALIZATIONS, records, strict=True):
        tactic = record["domain_gate"]["immediate_terminal_tactic"]
        moves = tactic["checkmating_moves"] if tactic else []
        if len(moves) != 1:
            raise ValueError("each visual realization requires one immediate mate")
        projection = record["projection"]
        realizations.append(
            {
                **item,
                "adapter_id": record["adapter_id"],
                "move_state_key": record["domain_gate"]["move_state_key"],
                "witness": {
                    "move": moves[0],
                    "result": "checkmate",
                    "plies": 1,
                },
                "statistics": projection["statistics"],
                "literal_game_sha256": projection["literal_game_sha256"],
                "thermograph_identity_sha256": projection[
                    "thermograph_identity"
                ]["digest_v1_sha256"],
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "claim": (
            "Mathematics pronounces the realizations identical while the encounter "
            "with each remains radically different."
        ),
        "projection": {
            "domain_id": partizan.CHESS_ADAPTER_PROJECTION_DOMAIN_ID,
            "rule": partizan.CHESS_ADAPTER_PROJECTION_RULE,
            "max_plies": MAX_PLIES,
            "node_budget": NODE_BUDGET,
        },
        "comparison": {
            "exact_value": "1",
            "canonical_game": "{0|}",
            "proof": "conway_recursive_order",
            "equal_to_value": equal_to_one,
            "equal_to_each_other": equal_to_each_other,
            "transition_kinds": transitions,
            "repertoire_id": repertoire["repertoire_id"],
            "admitted_count": repertoire["summary"]["admitted_count"],
        },
        "realizations": realizations,
    }
    return {
        **payload,
        "evidence_sha256": hashlib.sha256(
            partizan.canonical_json_bytes(payload)
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed evidence differs from a clean rebuild",
    )
    args = parser.parse_args()
    payload = partizan.canonical_json_bytes(build_evidence())
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != payload:
            raise SystemExit(f"{args.output}: generated evidence is stale")
        print(f"{args.output}: visual crossing evidence is current")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"{args.output}: wrote {len(payload)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
