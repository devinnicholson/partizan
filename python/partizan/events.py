"""Deterministic, explicitly limited Partizan-to-Fugue input events."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ._native import analyze_subsystems, find_locked_pawns

EVENT_SCHEMA_VERSION = "partizan.event_stream.v0.1"
GENERATOR_VERSION = "0.1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_KEYS = {
    "schema_version",
    "generator",
    "position",
    "domain",
    "claim_boundaries",
    "events",
    "fugue_adapter",
}


def build_event_stream(fen: str) -> dict[str, Any]:
    """Build a deterministic structural observation stream for one FEN.

    The stream is an input artifact for a future Fugue adapter, not a complete
    `partizan_fugue.event_log.v1` record. In particular, it contains no claim of
    full-game independence, learned benefit, agency, chess temperature, or
    discovery.
    """

    locked_pawns = sorted(find_locked_pawns(fen))
    reported_partition, component_count = analyze_subsystems(fen)
    fen_sha256 = hashlib.sha256(fen.encode("utf-8")).hexdigest()
    events = [
        {
            "sequence": 0,
            "event_id": "evt-000",
            "event_kind": "locked_pawn_screen",
            "status": "observed",
            "payload": {"locked_pawn_squares": locked_pawns},
        },
        {
            "sequence": 1,
            "event_id": "evt-001",
            "event_kind": "conservative_structural_partition",
            "status": "observed" if reported_partition else "not_observed",
            "payload": {
                "reported_partition": bool(reported_partition),
                "component_count": int(component_count),
                "guarantee": (
                    "Current-position conservative structural observation only; "
                    "not a proof of independence throughout future play."
                ),
            },
        },
    ]
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "generator": {
            "name": "partizan-cgt",
            "version": GENERATOR_VERSION,
            "serialization": "utf8-json-sort-keys-compact-newline-v1",
        },
        "position": {"encoding": "fen", "text": fen, "sha256": fen_sha256},
        "domain": "formal_domain:first_constrained_chess:v0",
        "claim_boundaries": [
            {
                "claim_id": "P01",
                "status": "schema_checked_event_input",
                "statement": "The event stream follows a versioned local schema.",
            },
            {
                "claim_id": "P02",
                "status": "not_applicable",
                "statement": "This stream does not promote an exact composed label.",
            },
            {
                "claim_id": "P03",
                "status": "not_a_benchmark_metric",
                "statement": "Deterministic bytes do not establish a benchmark result.",
            },
            {
                "claim_id": "P04",
                "status": "negative_or_null_not_release_claim",
                "statement": "No learned decomposition benefit is claimed.",
            },
            {
                "claim_id": "P05",
                "status": "unvalidated_artistic_only",
                "statement": (
                    "Agency, chess temperature, and discovery are not technical claims."
                ),
            },
        ],
        "events": events,
        "fugue_adapter": {
            "target_schema": "partizan_fugue.event_log.v1",
            "status": "versioned_input_requires_fugue_adapter",
        },
    }


def validate_event_stream(value: Any) -> list[str]:
    """Return deterministic validation errors for an event stream."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return ["event stream must be an object"]
    if set(value) != _TOP_LEVEL_KEYS:
        errors.append("event stream top-level fields do not match the v0.1 contract")
    if value.get("schema_version") != EVENT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVENT_SCHEMA_VERSION}")
    generator = value.get("generator")
    if generator != {
        "name": "partizan-cgt",
        "version": GENERATOR_VERSION,
        "serialization": "utf8-json-sort-keys-compact-newline-v1",
    }:
        errors.append("generator must match the v0.1 generator contract")
    if value.get("domain") != "formal_domain:first_constrained_chess:v0":
        errors.append("domain must be formal_domain:first_constrained_chess:v0")
    position = value.get("position")
    if not isinstance(position, dict):
        errors.append("position must be an object")
    else:
        if set(position) != {"encoding", "text", "sha256"}:
            errors.append("position fields do not match the v0.1 contract")
        fen = position.get("text")
        digest = position.get("sha256")
        if position.get("encoding") != "fen" or not isinstance(fen, str) or not fen:
            errors.append("position must contain a non-empty FEN")
        elif digest != hashlib.sha256(fen.encode("utf-8")).hexdigest():
            errors.append("position.sha256 does not match position.text")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append("position.sha256 must be a lowercase SHA-256 digest")
    boundaries = value.get("claim_boundaries")
    if not isinstance(boundaries, list):
        errors.append("claim_boundaries must be an array")
    else:
        claim_ids = [item.get("claim_id") for item in boundaries if isinstance(item, dict)]
        if claim_ids != ["P01", "P02", "P03", "P04", "P05"]:
            errors.append("claim_boundaries must contain P01 through P05 in order")
        for index, boundary in enumerate(boundaries):
            if not isinstance(boundary, dict) or set(boundary) != {
                "claim_id",
                "status",
                "statement",
            }:
                errors.append(f"claim_boundaries[{index}] fields are invalid")
                continue
            if not isinstance(boundary["status"], str) or not boundary["status"]:
                errors.append(f"claim_boundaries[{index}].status must be non-empty")
            if not isinstance(boundary["statement"], str) or not boundary["statement"]:
                errors.append(f"claim_boundaries[{index}].statement must be non-empty")
    events = value.get("events")
    if not isinstance(events, list) or len(events) != 2:
        errors.append("events must contain the two v0.1 structural observations")
    else:
        for sequence, event in enumerate(events):
            if not isinstance(event, dict):
                errors.append(f"events[{sequence}] must be an object")
                continue
            if event.get("sequence") != sequence:
                errors.append(f"events[{sequence}].sequence must be {sequence}")
            if event.get("event_id") != f"evt-{sequence:03d}":
                errors.append(f"events[{sequence}].event_id is not canonical")
            expected_kind = (
                "locked_pawn_screen"
                if sequence == 0
                else "conservative_structural_partition"
            )
            if event.get("event_kind") != expected_kind:
                errors.append(f"events[{sequence}].event_kind is not canonical")
            if event.get("status") not in {"observed", "not_observed"}:
                errors.append(f"events[{sequence}].status is invalid")
            if not isinstance(event.get("payload"), dict):
                errors.append(f"events[{sequence}].payload must be an object")
    adapter = value.get("fugue_adapter")
    if adapter != {
        "target_schema": "partizan_fugue.event_log.v1",
        "status": "versioned_input_requires_fugue_adapter",
    }:
        errors.append("fugue_adapter must match the v0.1 adapter boundary")
    return errors


def canonical_event_bytes(value: dict[str, Any]) -> bytes:
    """Serialize a validated stream to canonical UTF-8 JSON plus one newline."""

    errors = validate_event_stream(value)
    if errors:
        raise ValueError("; ".join(errors))
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
