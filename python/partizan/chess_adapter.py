"""Replayable bridge from constrained chess FENs to finite short games."""

from __future__ import annotations

import re
from typing import Any

from . import _native
from .fixed_value import (
    canonical_json_bytes,
    canonicalize_literal_game,
    literal_game_sha256,
    make_candidate,
    make_target,
    sha256_hex,
)

ADAPTER_SCHEMA_VERSION = "partizan.bounded_chess_adapter.v0.1"
NATIVE_ADAPTER_VERSION = "partizan.bounded_chess_adapter.native.v0.1"
DOMAIN_ID = "formal_domain:first_constrained_chess:v0"
PROJECTION_DOMAIN_ID = "formal_domain:bounded_chess_projection:v0"
PROJECTION_RULE = "bounded_alternating_legal_move_normal_play_v1"
MAX_PLIES = 8
MAX_NODE_BUDGET = 100_000
UPSTREAM_SOURCES = {
    "astralbase": {
        "version": "0.1.0",
        "source_commit": "81c7c583ee5b3cdd4c7e3a6d543e77803313bc54",
    },
    "bitmesh": {
        "version": "0.1.0",
        "source_commit": "961a918c16cda757322aca66e3a368cf95438cad",
    },
    "thermograph": {
        "version": "0.1.0",
        "source_commit": "bdf535c7a40ce76c4d1dbfb88d8c522eb034b8bd",
    },
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ADAPTER_ID_PATTERN = re.compile(r"^chess-adapter-sha256:[0-9a-f]{64}$")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _identity_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "adapter_id"}


def adapter_id_for(record: dict[str, Any]) -> str:
    """Compute the content identity of one adapter record."""

    return "chess-adapter-sha256:" + sha256_hex(
        canonical_json_bytes(_identity_payload(record))
    )


def adapt_chess_position(
    fen: str,
    *,
    max_plies: int = 2,
    node_budget: int = 10_000,
) -> dict[str, Any]:
    """Project one constrained FEN under the declared finite rule."""

    native_record = _native.adapt_chess_position(fen, max_plies, node_budget)
    record = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_id": "",
        **native_record,
    }
    if record["status"] == "accepted":
        projection = record["projection"]
        projection["literal_game"] = canonicalize_literal_game(
            projection["literal_game"]
        )
        projection["literal_game_sha256"] = literal_game_sha256(
            projection["literal_game"]
        )
    record["adapter_id"] = adapter_id_for(record)
    errors = validate_chess_adapter_record(record, replay=False)
    if errors:
        raise ValueError("; ".join(errors))
    return record


def _validate_settings(value: Any, refusal_code: str | None) -> list[str]:
    if not isinstance(value, dict):
        return ["adapter.settings must be an object"]
    errors: list[str] = []
    if set(value) != {"max_plies", "node_budget"}:
        errors.append("adapter.settings fields must be max_plies and node_budget")
    for name in ("max_plies", "node_budget"):
        if not _is_int(value.get(name)):
            errors.append(f"adapter.settings.{name} must be an integer")
    if errors or refusal_code == "invalid_adapter_settings":
        return errors
    if not 1 <= value["max_plies"] <= MAX_PLIES:
        errors.append(f"adapter.settings.max_plies must be from 1 through {MAX_PLIES}")
    if not 1 <= value["node_budget"] <= MAX_NODE_BUDGET:
        errors.append(
            f"adapter.settings.node_budget must be from 1 through {MAX_NODE_BUDGET}"
        )
    return errors


def _validate_refusal(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["adapter.refusal must be an object for a refused record"]
    errors: list[str] = []
    if set(value) != {"code", "message", "details"}:
        errors.append("adapter.refusal fields must be code, message, and details")
    if value.get("code") not in {
        "invalid_adapter_settings",
        "domain_rejected",
        "node_budget_exhausted",
        "position_transition_failed",
    }:
        errors.append("adapter.refusal.code is unsupported")
    if not isinstance(value.get("message"), str) or not value["message"]:
        errors.append("adapter.refusal.message must be non-empty")
    details = value.get("details")
    if details is not None and (
        not isinstance(details, list)
        or any(not isinstance(detail, str) or not detail for detail in details)
    ):
        errors.append("adapter.refusal.details must be null or non-empty strings")
    return errors


def _validate_decomposition(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["adapter.domain_gate.decomposition must be an object"]
    errors: list[str] = []
    expected = {
        "status",
        "active_component_count",
        "digest_sha256",
        "rejection_code",
        "conservative_one_ply_independence",
    }
    if set(value) != expected:
        errors.append("adapter decomposition fields do not match the v0.1 contract")
    status = value.get("status")
    if status not in {"strict", "rejected"}:
        errors.append("adapter decomposition status is unsupported")
    count = value.get("active_component_count")
    if not _is_int(count) or not 0 <= count <= 64:
        errors.append("adapter decomposition active_component_count is invalid")
    if not isinstance(value.get("digest_sha256"), str) or not _SHA256_PATTERN.fullmatch(
        value["digest_sha256"]
    ):
        errors.append("adapter decomposition digest_sha256 must be lowercase SHA-256")
    rejection_code = value.get("rejection_code")
    if status == "strict" and rejection_code is not None:
        errors.append("strict decomposition cannot carry a rejection code")
    if status == "rejected" and rejection_code not in {
        "no_locked_barrier",
        "less_than_two_active_components",
        "invalid_certificate",
    }:
        errors.append("rejected decomposition requires a supported rejection code")

    proof = value.get("conservative_one_ply_independence")
    if not isinstance(proof, dict):
        errors.append(
            "adapter decomposition conservative_one_ply_independence must be an object"
        )
        return errors
    if set(proof) != {
        "status",
        "proof_kind",
        "decomposition_digest_sha256",
    }:
        errors.append("adapter one-ply proof fields do not match the v0.1 contract")
    proof_status = proof.get("status")
    if proof_status == "certified":
        if proof.get("proof_kind") != "bitmesh:conservative_legal_independence:v0":
            errors.append("certified one-ply proof has an unsupported proof_kind")
        proof_digest = proof.get("decomposition_digest_sha256")
        if proof_digest != value.get("digest_sha256"):
            errors.append("one-ply proof digest must bind the decomposition")
    elif proof_status == "unavailable":
        if proof.get("proof_kind") is not None:
            errors.append("unavailable one-ply proof must have null proof_kind")
        if proof.get("decomposition_digest_sha256") is not None:
            errors.append("unavailable one-ply proof must have null digest")
    else:
        errors.append("adapter one-ply proof status is unsupported")
    return errors


def _validate_domain_gate(
    value: Any, status: str, refusal_code: str | None
) -> list[str]:
    if value is None:
        if refusal_code != "invalid_adapter_settings":
            return ["adapter.domain_gate may be null only for invalid settings"]
        return []
    if not isinstance(value, dict):
        return ["adapter.domain_gate must be an object or null"]
    errors: list[str] = []
    expected = {
        "status",
        "domain_id",
        "canonical_fen",
        "move_state_key",
        "terminal_status",
        "immediate_terminal_tactic",
        "decomposition",
        "reasons",
    }
    if set(value) != expected:
        errors.append("adapter.domain_gate fields do not match the v0.1 contract")
    gate_status = value.get("status")
    if gate_status not in {"accepted", "refused"}:
        errors.append("adapter.domain_gate.status is unsupported")
    if value.get("domain_id") != DOMAIN_ID:
        errors.append(f"adapter.domain_gate.domain_id must be {DOMAIN_ID}")
    reasons = value.get("reasons")
    if not isinstance(reasons, list):
        errors.append("adapter.domain_gate.reasons must be an array")
        reasons = []
    for index, reason in enumerate(reasons):
        if not isinstance(reason, dict) or set(reason) != {"code", "detail"}:
            errors.append(f"adapter.domain_gate.reasons[{index}] is malformed")
            continue
        if not isinstance(reason.get("code"), str) or not reason["code"]:
            errors.append(f"adapter.domain_gate.reasons[{index}].code is invalid")
        if reason.get("detail") is not None and not isinstance(
            reason.get("detail"), str
        ):
            errors.append(f"adapter.domain_gate.reasons[{index}].detail is invalid")

    if gate_status == "refused":
        if status != "refused" or refusal_code != "domain_rejected":
            errors.append("a refused domain gate requires a domain_rejected record")
        for field in (
            "canonical_fen",
            "move_state_key",
            "terminal_status",
            "immediate_terminal_tactic",
            "decomposition",
        ):
            if value.get(field) is not None:
                errors.append(f"refused domain gate requires null {field}")
        if not reasons:
            errors.append("refused domain gate requires at least one reason")
        return errors

    if not isinstance(value.get("canonical_fen"), str) or not value["canonical_fen"]:
        errors.append("accepted domain gate requires canonical_fen")
    if (
        not isinstance(value.get("move_state_key"), str)
        or len(value["move_state_key"].split()) != 4
    ):
        errors.append("accepted domain gate requires a four-field move_state_key")
    if value.get("terminal_status") not in {None, "checkmate", "stalemate"}:
        errors.append("adapter.domain_gate.terminal_status is unsupported")
    tactic = value.get("immediate_terminal_tactic")
    if tactic is not None:
        if not isinstance(tactic, dict) or set(tactic) != {
            "legal_move_count",
            "checkmating_moves",
            "stalemating_moves",
        }:
            errors.append("adapter immediate_terminal_tactic is malformed")
        else:
            if (
                not _is_int(tactic["legal_move_count"])
                or tactic["legal_move_count"] < 1
            ):
                errors.append("adapter tactic legal_move_count must be positive")
            for field in ("checkmating_moves", "stalemating_moves"):
                moves = tactic[field]
                if (
                    not isinstance(moves, list)
                    or any(not isinstance(move, str) or not move for move in moves)
                    or moves != sorted(moves)
                ):
                    errors.append(f"adapter tactic {field} must be sorted move strings")
    errors.extend(_validate_decomposition(value.get("decomposition")))
    if reasons:
        errors.append("accepted domain gate cannot carry rejection reasons")
    return errors


def _validate_statistics(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["adapter.projection.statistics must be an object"]
    errors: list[str] = []
    expected = {
        "visited_position_nodes",
        "legal_edges",
        "duplicate_literal_options_removed",
        "horizon_leaves",
        "checkmate_leaves",
        "stalemate_leaves",
        "max_depth_reached",
        "literal_game_nodes",
    }
    if set(value) != expected:
        errors.append("adapter projection statistics do not match the v0.1 contract")
    for field in expected:
        number = value.get(field)
        if not _is_int(number) or number < 0:
            errors.append(f"adapter.projection.statistics.{field} must be non-negative")
    if _is_int(value.get("literal_game_nodes")) and value["literal_game_nodes"] < 1:
        errors.append("adapter projection literal_game_nodes must be positive")
    return errors


def _validate_thermograph_identity(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["adapter.projection.thermograph_identity must be an object"]
    errors: list[str] = []
    expected = {
        "semantics",
        "value_class",
        "canonical_serialization",
        "legacy_digest",
        "digest_v1_sha256",
        "dyadic",
    }
    if set(value) != expected:
        errors.append("adapter Thermograph identity fields do not match v0.1")
    if value.get("semantics") != "structural_tree_identity_only":
        errors.append("adapter Thermograph semantics are unsupported")
    if value.get("value_class") not in {
        "number",
        "star",
        "up",
        "down",
        "switch",
        "game_tree",
    }:
        errors.append("adapter Thermograph value_class is unsupported")
    if (
        not isinstance(value.get("canonical_serialization"), str)
        or not value["canonical_serialization"]
    ):
        errors.append("adapter Thermograph canonical_serialization must be non-empty")
    if not isinstance(value.get("legacy_digest"), str) or not re.fullmatch(
        r"[0-9a-f]{16}", value["legacy_digest"]
    ):
        errors.append("adapter Thermograph legacy_digest must be 16 lowercase hex")
    if not isinstance(
        value.get("digest_v1_sha256"), str
    ) or not _SHA256_PATTERN.fullmatch(value["digest_v1_sha256"]):
        errors.append("adapter Thermograph digest_v1_sha256 must be lowercase SHA-256")
    dyadic = value.get("dyadic")
    if dyadic is not None:
        if not isinstance(dyadic, dict) or set(dyadic) != {
            "numerator",
            "denominator_power",
        }:
            errors.append("adapter Thermograph dyadic payload is malformed")
        elif not _is_int(dyadic["numerator"]) or not _is_int(
            dyadic["denominator_power"]
        ):
            errors.append("adapter Thermograph dyadic fields must be integers")
    return errors


def _validate_projection(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["adapter.projection must be an object for an accepted record"]
    errors: list[str] = []
    expected = {
        "domain_id",
        "rule",
        "root_turn",
        "literal_game",
        "literal_game_sha256",
        "statistics",
        "thermograph_identity",
    }
    if set(value) != expected:
        errors.append("adapter.projection fields do not match the v0.1 contract")
    if value.get("domain_id") != PROJECTION_DOMAIN_ID:
        errors.append(f"adapter.projection.domain_id must be {PROJECTION_DOMAIN_ID}")
    if value.get("rule") != PROJECTION_RULE:
        errors.append(f"adapter.projection.rule must be {PROJECTION_RULE}")
    if value.get("root_turn") not in {"white", "black"}:
        errors.append("adapter.projection.root_turn is unsupported")
    try:
        canonical_game = canonicalize_literal_game(value.get("literal_game"))
    except (TypeError, ValueError) as error:
        errors.append(f"adapter.projection.literal_game is invalid: {error}")
    else:
        if canonical_game != value.get("literal_game"):
            errors.append("adapter projection literal_game must be canonical")
        expected_digest = literal_game_sha256(canonical_game)
        if value.get("literal_game_sha256") != expected_digest:
            errors.append(
                "adapter projection literal_game_sha256 does not bind the tree"
            )
    errors.extend(_validate_statistics(value.get("statistics")))
    errors.extend(_validate_thermograph_identity(value.get("thermograph_identity")))
    return errors


def validate_chess_adapter_record(
    record: Any,
    *,
    replay: bool = True,
) -> list[str]:
    """Validate shape, hashes, semantic links, and optional native replay."""

    if not isinstance(record, dict):
        return ["adapter record must be an object"]
    errors: list[str] = []
    expected = {
        "schema_version",
        "adapter_id",
        "native_adapter_version",
        "upstream_sources",
        "status",
        "input",
        "settings",
        "domain_gate",
        "projection",
        "refusal",
    }
    if set(record) != expected:
        errors.append("adapter record fields do not match the v0.1 contract")
    if record.get("schema_version") != ADAPTER_SCHEMA_VERSION:
        errors.append(f"adapter schema_version must be {ADAPTER_SCHEMA_VERSION}")
    if record.get("native_adapter_version") != NATIVE_ADAPTER_VERSION:
        errors.append(
            f"adapter native_adapter_version must be {NATIVE_ADAPTER_VERSION}"
        )
    if record.get("upstream_sources") != UPSTREAM_SOURCES:
        errors.append(
            "adapter upstream_sources must match the frozen source candidates"
        )
    adapter_id = record.get("adapter_id")
    if not isinstance(adapter_id, str) or not _ADAPTER_ID_PATTERN.fullmatch(adapter_id):
        errors.append("adapter.adapter_id must be a chess-adapter SHA-256 identity")
    else:
        try:
            expected_id = adapter_id_for(record)
        except (TypeError, ValueError) as error:
            errors.append(f"adapter record is not canonical JSON: {error}")
        else:
            if adapter_id != expected_id:
                errors.append("adapter.adapter_id does not bind the record payload")

    status = record.get("status")
    if status not in {"accepted", "refused"}:
        errors.append("adapter.status is unsupported")
    input_record = record.get("input")
    if (
        not isinstance(input_record, dict)
        or set(input_record) != {"encoding", "fen"}
        or input_record.get("encoding") != "fen"
        or not isinstance(input_record.get("fen"), str)
        or not input_record["fen"]
    ):
        errors.append("adapter.input must contain a non-empty FEN")

    refusal = record.get("refusal")
    refusal_code = refusal.get("code") if isinstance(refusal, dict) else None
    errors.extend(_validate_settings(record.get("settings"), refusal_code))
    if status == "accepted":
        if refusal is not None:
            errors.append("accepted adapter record requires null refusal")
        errors.extend(_validate_projection(record.get("projection")))
    elif status == "refused":
        if record.get("projection") is not None:
            errors.append("refused adapter record requires null projection")
        errors.extend(_validate_refusal(refusal))
    errors.extend(
        _validate_domain_gate(record.get("domain_gate"), status, refusal_code)
    )

    if (
        replay
        and isinstance(input_record, dict)
        and isinstance(record.get("settings"), dict)
    ):
        try:
            expected_record = adapt_chess_position(
                input_record.get("fen"),
                max_plies=record["settings"].get("max_plies"),
                node_budget=record["settings"].get("node_budget"),
            )
        except (TypeError, ValueError) as error:
            errors.append(f"adapter native replay failed: {error}")
        else:
            if expected_record != record:
                errors.append(
                    "adapter record does not match deterministic native replay"
                )
    return errors


def target_from_adapter(record: dict[str, Any], *, name: str) -> dict[str, Any]:
    """Create a fixed-value target from one accepted adapter record."""

    errors = validate_chess_adapter_record(record)
    if errors:
        raise ValueError("; ".join(errors))
    if record["status"] != "accepted":
        raise ValueError("a fixed-value target requires an accepted adapter record")
    return make_target(name, record["projection"]["literal_game"])


def candidate_from_adapter(
    record: dict[str, Any],
    *,
    ordinal: int,
) -> dict[str, Any]:
    """Create a fixed-value candidate bound to one accepted chess projection."""

    errors = validate_chess_adapter_record(record)
    if errors:
        raise ValueError("; ".join(errors))
    if record["status"] != "accepted":
        raise ValueError("a fixed-value candidate requires an accepted adapter record")

    domain_gate = record["domain_gate"]
    projection = record["projection"]
    return make_candidate(
        ordinal=ordinal,
        representation={
            "encoding": "shakmaty-move-state-v1",
            "text": domain_gate["move_state_key"],
            "metadata": {},
        },
        literal_game=projection["literal_game"],
        generator={
            "name": "partizan-bounded-chess-adapter",
            "version": "0.1.0",
            "seed": 0,
            "operator": f"{PROJECTION_RULE}@{record['adapter_id']}",
        },
    )
