#!/usr/bin/env python3
"""Build the legal-replay artifact for the visualizer's Elkies prelude."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import partizan


SCHEMA_VERSION = "partizan.historical_chess_witness.v0.1"
DEFAULT_OUTPUT = Path("visualizer/public/evidence/elkies-study.json")
INITIAL_FEN = "5Q2/5P1b/8/7K/8/1q4k1/1p4B1/8 w - - 0 1"
MOVES_UCI = (
    "f8g7",
    "g3h2",
    "f7f8q",
    "b3b5",
    "h5h6",
    "b5b6",
    "g2c6",
    "b6c6",
    "h6h7",
    "b2b1q",
    "h7h8",
    "h2h1",
    "f8g8",
)
FINAL_FEN = "6QK/6Q1/2q5/8/8/8/8/1q5k b - - 3 7"
SOURCE_URL = "https://library.slmath.org/books/Book29/files/stiller.pdf"


def build_evidence() -> dict[str, Any]:
    """Replay the published line and bind its source and claim boundary."""

    witness = partizan.replay_chess_witness(INITIAL_FEN, list(MOVES_UCI))
    frames = witness["frames"]
    if len(frames) != len(MOVES_UCI) + 1:
        raise ValueError("the historical witness lost a replay frame")
    if frames[-1]["fen"] != FINAL_FEN:
        raise ValueError("the historical witness no longer reaches the recorded kernel")
    if [frame["move_uci"] for frame in frames[1:]] != list(MOVES_UCI):
        raise ValueError("the historical witness changed move order")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "role": "historical_prelude",
        "title": "From composition to kernel",
        "claim": (
            "A thirteen-ply published line carries an eight-piece composition "
            "into a rotated KQQKQQ mutual-zugzwang kernel."
        ),
        "source": {
            "author": "Lewis Stiller",
            "title": "Multilinear Algebra and Chess Endgames",
            "venue": "Games of No Chance, MSRI Publications 29",
            "year": 1996,
            "pages": "176-177",
            "figure": "Figure 7",
            "url": SOURCE_URL,
            "historical_attribution": (
                "Stiller reports the computer-found kernel and Noam Elkies's "
                "composition derived from it."
            ),
        },
        "scope": {
            "legal_replay": "machine_verified",
            "line_origin": "published_analysis",
            "line_optimality": "not_machine_verified",
            "forcedness": "not_machine_verified",
            "cgt_value": "not_asserted",
        },
        "position": {
            "name": "Noam Elkies composition",
            "initial_fen": INITIAL_FEN,
            "initial_piece_count": 8,
            "final_fen": FINAL_FEN,
            "final_piece_count": 6,
        },
        "witness": witness,
        "motifs": [
            {
                "at_ply": 3,
                "name": "white promotion",
                "move_san": frames[3]["move_san"],
            },
            {
                "at_ply": 7,
                "name": "bishop interposition",
                "move_san": frames[7]["move_san"],
            },
            {
                "at_ply": 10,
                "name": "black promotion with check",
                "move_san": frames[10]["move_san"],
            },
            {
                "at_ply": 12,
                "name": "quiet defensive king move",
                "move_san": frames[12]["move_san"],
            },
            {
                "at_ply": 13,
                "name": "quiet move into mutual zugzwang",
                "move_san": frames[13]["move_san"],
            },
        ],
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
        print(f"{args.output}: historical witness evidence is current")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"{args.output}: wrote {len(payload)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
