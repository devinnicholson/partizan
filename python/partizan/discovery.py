"""Strict, deterministic contracts for bounded verifier-guided discovery.

The proposal contract is deliberately separate from verifier results.  A model
may consume only :func:`build_ranker_input`; verifier evidence is never copied
into that projection.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
from typing import Any, Iterable


TARGET_SCHEMA_VERSION = "partizan.discovery_target.v0.1"
BOARD_STREAM_SCHEMA_VERSION = "partizan.candidate_board_stream.v0.1"
PROPOSAL_SCHEMA_VERSION = "partizan.candidate_proposal.v0.1"
RESULT_SCHEMA_VERSION = "partizan.verifier_result.v0.1"
POOL_SCHEMA_VERSION = "partizan.candidate_pool_manifest.v0.1"
POOL_SCHEMA_VERSION_V2 = "partizan.candidate_pool_manifest.v0.2"
POOL_SCHEMA_VERSION_V3 = "partizan.candidate_pool_manifest.v0.3"
RUN_SCHEMA_VERSION = "partizan.discovery_run.v0.1"
RANKER_INPUT_SCHEMA_VERSION = "partizan.ranker_input.v0.1"
GENERATION_RECEIPT_SCHEMA_VERSION = "partizan.candidate_generation_receipt.v0.1"
GENERATION_RECEIPT_SCHEMA_VERSION_V2 = (
    "partizan.candidate_generation_receipt.v0.2"
)
CONSTRUCTION_CATALOG_SCHEMA_VERSION = (
    "partizan.dfile_two_component_constructive_catalog.v0.2"
)
CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION = (
    "partizan.structural_construction_certificate.v0.1"
)
CONSTRUCTION_CONTRACT_V2 = (
    "partizan.dfile_two_component_constructive_grammar.v0.2"
)
BOARD_TO_PROPOSAL_PROJECTION_CONTRACT_V1 = (
    "partizan.target_free_board_to_candidate_proposal.v0.1"
)

SERIALIZATION = "utf8-json-sort-keys-compact-newline-v1"
TARGET_KIND = "bounded_structural_game_form"
IDENTITY_CONTRACT = "thermograph_structural_tree_v1"
IDENTITY_SCOPE = "structural_tree_identity_only_not_arbitrary_cgt_equivalence"
LEGALITY_CONTRACT = "board_syntax_only"
VALUE_RULE = "component_depth2_local_move_game_v0"
PARTIZAN_POOL_GENERATOR_NAME = "partizan_candidate_pool_generator"

_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_TYPED_ID_RE = re.compile(
    r"^(target|candidate|proposal|result|pool|run)-sha256:[0-9a-f]{64}$"
)
_FORBIDDEN_FEATURE_KEY_TOKENS = (
    "certificate",
    "exact",
    "expanded_nodes",
    "label",
    "outcome",
    "rejected",
    "rejection",
    "result",
    "solver",
    "target_comparison",
    "target_match",
    "verifier",
)
_REQUIRED_GATE_IDS = ("domain", "board_syntax", "structure", "target_identity")

_TARGET_KEYS = {
    "schema_version",
    "target_id",
    "domain",
    "target",
    "position_constraints",
    "search_limits",
    "ranker_view",
    "provenance",
}
_PROPOSAL_KEYS = {
    "schema_version",
    "proposal_id",
    "target_id",
    "domain",
    "candidate_key",
    "ordinal",
    "position",
    "generator",
    "proposal_features",
}
_BOARD_STREAM_KEYS = {
    "schema_version",
    "board_id",
    "ordinal",
    "position",
    "generator",
    "construction",
    "proposal_features",
}
_CONSTRUCTION_CERTIFICATE_KEYS = {
    "schema_version",
    "certificate_id",
    "board_id",
    "ordinal",
    "catalog_id",
    "construction_contract",
    "stratum",
    "left",
    "right",
    "runtime_oracle_used",
}
BOARD_TO_PROPOSAL_MAPPING_V1 = {
    "/schema_version": "constant:partizan.candidate_proposal.v0.1",
    "/proposal_id": "canonical_identity:proposal_without_proposal_id",
    "/target_id": "target:/target_id",
    "/domain": "target:/domain",
    "/candidate_key": "canonical_identity:target_domain_plus_board_position",
    "/ordinal": "board:/ordinal",
    "/position": "board:/position",
    "/generator": "board:/generator",
    "/proposal_features": "board:/proposal_features",
}
_RESULT_KEYS = {
    "schema_version",
    "result_id",
    "target_id",
    "proposal_id",
    "candidate_key",
    "verifier",
    "verifier_io",
    "gates",
    "outcome",
    "target_comparison",
    "evidence",
}
_POOL_KEYS = {
    "schema_version",
    "pool_id",
    "target_ref",
    "candidate_artifact",
    "generator",
    "source_repositories",
    "determinism",
    "ranker_boundary",
}
_POOL_V3_KEYS = _POOL_KEYS | {"construction_lineage"}
_RUN_KEYS = {
    "schema_version",
    "run_id",
    "target_id",
    "pool_id",
    "policy",
    "budget",
    "calls",
    "summary",
}


def _validate_json_value(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, float):
        return [f"{path}: raw JSON floats are forbidden"]
    if value is None or isinstance(value, (bool, int)):
        return errors
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            errors.append(f"{path}: strings must be Unicode NFC")
        return errors
    if isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_validate_json_value(item, f"{path}[{index}]"))
        return errors
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                errors.append(f"{path}: object keys must be strings")
                continue
            errors.extend(_validate_json_value(key, f"{path}.<key>"))
            errors.extend(_validate_json_value(item, f"{path}.{key}"))
        return errors
    return [f"{path}: unsupported JSON value type {type(value).__name__}"]


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical compact JSON followed by exactly one newline."""

    errors = _validate_json_value(value)
    if errors:
        raise ValueError("; ".join(errors))
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def canonical_jsonl_bytes(values: Iterable[Any]) -> bytes:
    """Return concatenated canonical JSON rows with no blank records."""

    return b"".join(canonical_json_bytes(value) for value in values)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}-sha256:{sha256_hex(canonical_json_bytes(payload))}"


def target_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "target",
        {
            "domain": value.get("domain"),
            "target": value.get("target"),
            "position_constraints": value.get("position_constraints"),
            "verifier_contract": {
                "value_rule": value.get("target", {}).get("value_rule"),
                "identity_contract": value.get("target", {}).get(
                    "identity_contract"
                ),
                "node_budget": value.get("search_limits", {}).get(
                    "max_recursive_nodes_per_candidate"
                ),
            },
        },
    )


def candidate_key_for(domain: str, position: dict[str, Any]) -> str:
    return _identity(
        "candidate",
        {
            "domain": domain,
            "position": {
                "encoding": position.get("encoding"),
                "text": position.get("text"),
            },
        },
    )


def board_id_for(position: dict[str, Any]) -> str:
    """Return a target- and domain-free identity for a clock-free FEN state."""

    text = position.get("text")
    try:
        state_text = (
            fen_state_without_move_clocks(text) if isinstance(text, str) else text
        )
    except ValueError:
        state_text = text
    return _identity(
        "board",
        {
            "position_state": {
                "encoding": position.get("encoding"),
                "text_without_move_clocks": state_text,
            }
        },
    )


def fen_state_without_move_clocks(fen: str) -> str:
    fields = fen.split()
    if len(fields) != 6:
        raise ValueError("FEN state identity requires exactly six fields")
    return " ".join(fields[:4])


def reflect_fen_state_files(fen: str) -> str:
    fields = fen_state_without_move_clocks(fen).split()
    reflected_ranks: list[str] = []
    for encoded_rank in fields[0].split("/"):
        expanded: list[str] = []
        for token in encoded_rank:
            if token.isdigit():
                expanded.extend("." for _ in range(int(token)))
            else:
                expanded.append(token)
        if len(expanded) != 8:
            raise ValueError("FEN rank must expand to eight files")
        reflected: list[str] = []
        empty = 0
        for token in reversed(expanded):
            if token == ".":
                empty += 1
                continue
            if empty:
                reflected.append(str(empty))
                empty = 0
            reflected.append(token)
        if empty:
            reflected.append(str(empty))
        reflected_ranks.append("".join(reflected))
    if len(reflected_ranks) != 8:
        raise ValueError("FEN board must contain eight ranks")
    fields[0] = "/".join(reflected_ranks)
    return " ".join(fields)


def fen_file_reflection_orbit_sha256(fen: str) -> str:
    """Hash a clock-free FEN state modulo file reflection."""

    state = fen_state_without_move_clocks(fen)
    reflected = reflect_fen_state_files(fen)
    return sha256_hex(min(state, reflected).encode("utf-8"))


def partizan_pool_features_for_fen(fen: str) -> dict[str, Any]:
    """Return exactly the seven preregistered Wave 69 proposal features."""

    fields = fen_state_without_move_clocks(fen).split()
    ranks = fields[0].split("/")
    if len(ranks) != 8:
        raise ValueError("FEN board must contain eight ranks")
    pieces: list[tuple[str, str]] = []
    squares: dict[str, str] = {}
    for rank_number, encoded_rank in zip(range(8, 0, -1), ranks):
        file_index = 0
        for token in encoded_rank:
            if token.isdigit():
                file_index += int(token)
                continue
            if file_index >= 8:
                raise ValueError("FEN rank expands beyond eight files")
            square = f"{'abcdefgh'[file_index]}{rank_number}"
            pieces.append((square, token))
            squares[square] = token
            file_index += 1
        if file_index != 8:
            raise ValueError("FEN rank must expand to eight files")

    locked_backbone = {
        f"d{rank}": "P" if rank % 2 == 1 else "p"
        for rank in range(1, 9)
    }
    piece_tokens = [piece for _, piece in pieces]
    occupied_files = {square[0] for square, _ in pieces}
    return {
        "schema_version": "partizan.proposal_features.v0.1",
        "derivation_stage": "pre_verification",
        "categorical": {},
        "integer": {
            "black_piece_count": sum(piece.islower() for piece in piece_tokens),
            "non_pawn_piece_count": sum(
                piece.upper() != "P" for piece in piece_tokens
            ),
            "occupied_file_count": len(occupied_files),
            "pawn_count": sum(piece.upper() == "P" for piece in piece_tokens),
            "piece_count": len(piece_tokens),
            "white_piece_count": sum(piece.isupper() for piece in piece_tokens),
        },
        "boolean": {
            "has_locked_d_file_backbone": all(
                squares.get(square) == piece
                for square, piece in locked_backbone.items()
            )
        },
    }


def candidate_state_key_for(domain: str, position: dict[str, Any]) -> str:
    """Identify a FEN state while excluding the two move-clock fields.

    Wave 69 generation uses this identity so halfmove/fullmove bookkeeping
    cannot create nominally distinct candidates from the same board state.
    The earlier Astralbase fixture generator retains ``candidate_key_for`` for
    backward-compatible Wave 68 evidence replay.
    """

    text = position.get("text")
    try:
        state_text = (
            fen_state_without_move_clocks(text) if isinstance(text, str) else text
        )
    except ValueError:
        state_text = text
    return _identity(
        "candidate",
        {
            "domain": domain,
            "position_state": {
                "encoding": position.get("encoding"),
                "text_without_move_clocks": state_text,
            },
        },
    )


def astralbase_request_for(
    target_spec: dict[str, Any], proposal: dict[str, Any]
) -> dict[str, Any]:
    """Return the exact request object sent to the Astralbase verifier."""

    return {
        "request_id": proposal.get("proposal_id"),
        "domain_id": proposal.get("domain"),
        "position": {
            "encoding": proposal.get("position", {}).get("encoding"),
            "text": proposal.get("position", {}).get("text"),
        },
        "value_rule": target_spec.get("target", {}).get("value_rule"),
        "target": {
            "identity_kind": target_spec.get("target", {}).get("identity_contract"),
            "value_class": target_spec.get("target", {}).get("value_class"),
            "digest_v1_sha256": target_spec.get("target", {}).get("identity_sha256"),
        },
        "node_budget": target_spec.get("search_limits", {}).get(
            "max_recursive_nodes_per_candidate"
        ),
    }


def verifier_config_sha256_for(target_spec: dict[str, Any]) -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "value_rule": target_spec.get("target", {}).get("value_rule"),
                "node_budget": target_spec.get("search_limits", {}).get(
                    "max_recursive_nodes_per_candidate"
                ),
            }
        )
    )


def _gate_evidence_sha(value: Any) -> str:
    return sha256_hex(canonical_json_bytes(value))


def _failure_gate_for_reason(reason_code: str) -> str:
    if reason_code == "unsupported_domain":
        return "domain"
    if reason_code in {"invalid_fen", "unsupported_position_encoding"}:
        return "board_syntax"
    return "structure"


def verifier_gate_rows_for(
    response: dict[str, Any], proposal: dict[str, Any]
) -> list[dict[str, Any]]:
    """Derive all gate rows from the lossless Astralbase response envelope."""

    status = response.get("status")
    domain_evidence = {"domain": proposal.get("domain")}
    board_evidence = proposal.get("position", {}).get("sha256")
    if status in {"verified_match", "verified_nonmatch"}:
        actual = response.get("actual", {})
        observed = actual.get("digest_v1_sha256")
        observed_identity = {
            "value_class": actual.get("value_class"),
            "digest_v1_sha256": observed,
        }
        matches = status == "verified_match"
        return [
            {
                "gate_id": "domain",
                "status": "passed",
                "reason_codes": [],
                "evidence_sha256": _gate_evidence_sha(domain_evidence),
            },
            {
                "gate_id": "board_syntax",
                "status": "passed",
                "reason_codes": [],
                "evidence_sha256": _gate_evidence_sha(board_evidence),
            },
            {
                "gate_id": "structure",
                "status": "passed",
                "reason_codes": [],
                "evidence_sha256": _gate_evidence_sha(
                    actual.get("composition_digest")
                ),
            },
            {
                "gate_id": "target_identity",
                "status": "passed" if matches else "failed",
                "reason_codes": [] if matches else ["identity_mismatch"],
                "evidence_sha256": _gate_evidence_sha(observed_identity),
            },
        ]

    reason = response.get("reason_code") or (
        "astralbase_internal_error"
        if status == "internal_error"
        else "astralbase_rejected"
    )
    failure_gate = _failure_gate_for_reason(str(reason))
    failure_index = _REQUIRED_GATE_IDS.index(failure_gate)
    failure_status = "error" if status == "internal_error" else "failed"
    evidence_by_gate = {
        "domain": domain_evidence,
        "board_syntax": board_evidence,
        "structure": response,
    }
    rows: list[dict[str, Any]] = []
    for index, gate_id in enumerate(_REQUIRED_GATE_IDS):
        if index < failure_index:
            rows.append(
                {
                    "gate_id": gate_id,
                    "status": "passed",
                    "reason_codes": [],
                    "evidence_sha256": _gate_evidence_sha(evidence_by_gate[gate_id]),
                }
            )
        elif index == failure_index:
            rows.append(
                {
                    "gate_id": gate_id,
                    "status": failure_status,
                    "reason_codes": [str(reason)],
                    "evidence_sha256": _gate_evidence_sha(evidence_by_gate[gate_id]),
                }
            )
        else:
            rows.append(
                {
                    "gate_id": gate_id,
                    "status": "not_run",
                    "reason_codes": [],
                    "evidence_sha256": None,
                }
            )
    return rows


def proposal_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "proposal",
        {key: item for key, item in value.items() if key != "proposal_id"},
    )


def verifier_result_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "result",
        {key: item for key, item in value.items() if key != "result_id"},
    )


def candidate_pool_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "pool",
        {key: item for key, item in value.items() if key != "pool_id"},
    )


def generation_receipt_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "receipt",
        {key: item for key, item in value.items() if key != "receipt_id"},
    )


def construction_catalog_id_for(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload["catalog_id"] = "catalog-sha256:" + "0" * 64
    return _identity(
        "catalog",
        payload,
    )


def construction_certificate_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "certificate",
        {key: item for key, item in value.items() if key != "certificate_id"},
    )


def discovery_run_id_for(value: dict[str, Any]) -> str:
    return _identity(
        "run",
        {
            "target_id": value.get("target_id"),
            "pool_id": value.get("pool_id"),
            "policy": value.get("policy"),
            "budget": value.get("budget"),
        },
    )


def _mapping(value: Any, path: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return None
    return value


def _exact_keys(
    value: Any, expected: set[str], path: str, errors: list[str]
) -> dict[str, Any] | None:
    mapping = _mapping(value, path, errors)
    if mapping is not None and set(mapping) != expected:
        missing = sorted(expected - set(mapping))
        extra = sorted(set(mapping) - expected)
        errors.append(f"{path}: fields mismatch; missing={missing}, extra={extra}")
    return mapping


def _nonempty_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{path}: must be a non-empty string")


def _hex(value: Any, length: int, path: str, errors: list[str]) -> None:
    pattern = _HEX40_RE if length == 40 else _HEX64_RE
    if not isinstance(value, str) or not pattern.fullmatch(value):
        errors.append(f"{path}: must be {length} lowercase hexadecimal characters")


def _commit(value: Any, path: str, errors: list[str]) -> None:
    if value == "workspace":
        errors.append(f"{path}: 'workspace' is forbidden; record an immutable commit")
    else:
        _hex(value, 40, path, errors)


def _typed_id(value: Any, kind: str, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _TYPED_ID_RE.fullmatch(value):
        errors.append(f"{path}: must be a typed SHA-256 identifier")
    elif not value.startswith(f"{kind}-sha256:"):
        errors.append(f"{path}: must use the {kind}-sha256 prefix")


def _relative_path(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{path}: must be a non-empty repository-relative path")
        return
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in value
        or parsed.as_posix() != value
        or not parsed.parts
    ):
        errors.append(
            f"{path}: must be a normalized repository-relative POSIX path "
            "without '.' or '..'"
        )


def validate_target_spec(value: Any) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(value, _TARGET_KEYS, "target", errors)
    if row is None:
        return errors
    if row.get("schema_version") != TARGET_SCHEMA_VERSION:
        errors.append(f"target.schema_version: must be {TARGET_SCHEMA_VERSION}")
    _typed_id(row.get("target_id"), "target", "target.target_id", errors)
    _nonempty_string(row.get("domain"), "target.domain", errors)

    target = _exact_keys(
        row.get("target"),
        {
            "kind",
            "identity_contract",
            "identity_sha256",
            "value_rule",
            "value_class",
            "equality_scope",
        },
        "target.target",
        errors,
    )
    if target is not None:
        if target.get("kind") != TARGET_KIND:
            errors.append(f"target.target.kind: must be {TARGET_KIND}")
        if target.get("identity_contract") != IDENTITY_CONTRACT:
            errors.append(
                f"target.target.identity_contract: must be {IDENTITY_CONTRACT}"
            )
        if target.get("value_rule") != VALUE_RULE:
            errors.append(f"target.target.value_rule: must be {VALUE_RULE}")
        if target.get("equality_scope") != IDENTITY_SCOPE:
            errors.append(
                "target.target.equality_scope: must explicitly exclude arbitrary "
                "CGT equivalence"
            )
        _hex(target.get("identity_sha256"), 64, "target.target.identity_sha256", errors)
        _nonempty_string(target.get("value_class"), "target.target.value_class", errors)

    constraints = _exact_keys(
        row.get("position_constraints"),
        {"encoding", "legality_contract", "castling_rights", "en_passant"},
        "target.position_constraints",
        errors,
    )
    if constraints is not None:
        if constraints.get("encoding") != "fen":
            errors.append("target.position_constraints.encoding: must be 'fen'")
        if constraints.get("legality_contract") != LEGALITY_CONTRACT:
            errors.append(
                f"target.position_constraints.legality_contract: must be {LEGALITY_CONTRACT}"
            )
        if constraints.get("castling_rights") != "none":
            errors.append("target.position_constraints.castling_rights: must be 'none'")
        if constraints.get("en_passant") != "none":
            errors.append("target.position_constraints.en_passant: must be 'none'")

    limits = _exact_keys(
        row.get("search_limits"),
        {"max_pool_size", "max_verifier_calls", "max_recursive_nodes_per_candidate"},
        "target.search_limits",
        errors,
    )
    if limits is not None:
        for key in (
            "max_pool_size",
            "max_verifier_calls",
            "max_recursive_nodes_per_candidate",
        ):
            item = limits.get(key)
            if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
                errors.append(f"target.search_limits.{key}: must be a positive integer")

    ranker_view = _exact_keys(
        row.get("ranker_view"),
        {"kind", "identity_contract", "identity_sha256", "value_rule", "value_class"},
        "target.ranker_view",
        errors,
    )
    if target is not None and ranker_view is not None:
        expected_view = {
            "kind": target.get("kind"),
            "identity_contract": target.get("identity_contract"),
            "identity_sha256": target.get("identity_sha256"),
            "value_rule": target.get("value_rule"),
            "value_class": target.get("value_class"),
        }
        if ranker_view != expected_view:
            errors.append("target.ranker_view: must be the exact allowlisted target projection")

    provenance = _exact_keys(
        row.get("provenance"),
        {"source_artifact", "source_row_id", "source_commit"},
        "target.provenance",
        errors,
    )
    if provenance is not None:
        _relative_path(provenance.get("source_artifact"), "target.provenance.source_artifact", errors)
        _nonempty_string(provenance.get("source_row_id"), "target.provenance.source_row_id", errors)
        _commit(provenance.get("source_commit"), "target.provenance.source_commit", errors)

    if isinstance(row.get("target_id"), str) and row.get("target_id") != target_id_for(row):
        errors.append("target.target_id: does not match the canonical identity projection")
    return errors


def _feature_key_errors(value: Any, path: str = "proposal.proposal_features") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.lower()
            if any(token in normalized_key for token in _FORBIDDEN_FEATURE_KEY_TOKENS):
                errors.append(f"{path}.{key}: verifier-derived feature key is forbidden")
            errors.extend(_feature_key_errors(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_feature_key_errors(item, f"{path}[{index}]"))
    return errors


def validate_candidate_board_stream_row(value: Any) -> list[str]:
    """Validate one target-free board-stream row used by structural audits."""

    errors = _validate_json_value(value)
    row = _exact_keys(value, _BOARD_STREAM_KEYS, "board_stream", errors)
    if row is None:
        return errors
    if row.get("schema_version") != BOARD_STREAM_SCHEMA_VERSION:
        errors.append(
            f"board_stream.schema_version: must be {BOARD_STREAM_SCHEMA_VERSION}"
        )
    board_id = row.get("board_id")
    if not isinstance(board_id, str) or not re.fullmatch(
        r"board-sha256:[0-9a-f]{64}", board_id
    ):
        errors.append(
            "board_stream.board_id: must be a typed SHA-256 identifier"
        )
    ordinal = row.get("ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        errors.append("board_stream.ordinal: must be a non-negative integer")

    position = _exact_keys(
        row.get("position"),
        {"encoding", "text", "sha256", "symmetry_sha256"},
        "board_stream.position",
        errors,
    )
    fen: str | None = None
    if position is not None:
        if position.get("encoding") != "fen":
            errors.append("board_stream.position.encoding: must be 'fen'")
        fen_value = position.get("text")
        if not isinstance(fen_value, str) or len(fen_value.split()) != 6:
            errors.append(
                "board_stream.position.text: must be a six-field FEN string"
            )
        else:
            fen = fen_value
            if fen.split()[1:] != ["w", "-", "-", "0", "1"]:
                errors.append(
                    "board_stream.position.text: trailing FEN fields must be "
                    "exactly 'w - - 0 1'"
                )
            if position.get("sha256") != sha256_hex(fen.encode("utf-8")):
                errors.append(
                    "board_stream.position.sha256: does not match position text"
                )
            try:
                expected_orbit = fen_file_reflection_orbit_sha256(fen)
            except ValueError as error:
                errors.append(f"board_stream.position.text: {error}")
            else:
                if position.get("symmetry_sha256") != expected_orbit:
                    errors.append(
                        "board_stream.position.symmetry_sha256: does not match "
                        "the clock-free file-reflection orbit"
                    )
        _hex(
            position.get("symmetry_sha256"),
            64,
            "board_stream.position.symmetry_sha256",
            errors,
        )
        if row.get("board_id") != board_id_for(position):
            errors.append(
                "board_stream.board_id: does not match clock-free position"
            )

    generator = _exact_keys(
        row.get("generator"),
        {
            "name",
            "version",
            "code_commit",
            "family",
            "operator",
            "config_sha256",
            "random_seed",
        },
        "board_stream.generator",
        errors,
    )
    if generator is not None:
        for key in ("name", "version", "family", "operator"):
            _nonempty_string(
                generator.get(key), f"board_stream.generator.{key}", errors
            )
        if generator.get("name") != PARTIZAN_POOL_GENERATOR_NAME:
            errors.append("board_stream.generator.name: unsupported generator")
        _commit(
            generator.get("code_commit"),
            "board_stream.generator.code_commit",
            errors,
        )
        _hex(
            generator.get("config_sha256"),
            64,
            "board_stream.generator.config_sha256",
            errors,
        )
        seed = generator.get("random_seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            errors.append(
                "board_stream.generator.random_seed: must be a non-negative integer"
            )

    construction = _exact_keys(
        row.get("construction"),
        {
            "contract",
            "stratum",
            "left_active_piece_count",
            "right_active_piece_count",
            "left_template_id",
            "right_template_id",
            "runtime_oracle_used",
        },
        "board_stream.construction",
        errors,
    )
    if construction is not None:
        if construction.get("contract") != (
            "partizan.dfile_two_component_constructive_grammar.v0.2"
        ):
            errors.append("board_stream.construction.contract: invalid")
        if construction.get("stratum") not in {
            "outer_leaper",
            "pawn_phalanx",
            "ray_cage",
            "mixed_color_hook",
        }:
            errors.append("board_stream.construction.stratum: invalid")
        for key in ("left_active_piece_count", "right_active_piece_count"):
            count = construction.get(key)
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 5:
                errors.append(
                    f"board_stream.construction.{key}: must be an integer from 1 through 5"
                )
        for key in ("left_template_id", "right_template_id"):
            value = construction.get(key)
            if not isinstance(value, str) or not re.fullmatch(
                r"template-sha256:[0-9a-f]{64}", value
            ):
                errors.append(
                    f"board_stream.construction.{key}: must be a typed SHA-256 identifier"
                )
        if construction.get("runtime_oracle_used") is not False:
            errors.append(
                "board_stream.construction.runtime_oracle_used: must be false"
            )

    features = _exact_keys(
        row.get("proposal_features"),
        {"schema_version", "derivation_stage", "categorical", "integer", "boolean"},
        "board_stream.proposal_features",
        errors,
    )
    if features is not None and fen is not None:
        try:
            expected_features = partizan_pool_features_for_fen(fen)
        except ValueError as error:
            errors.append(f"board_stream.proposal_features: cannot derive: {error}")
        else:
            if features != expected_features:
                errors.append(
                    "board_stream.proposal_features: must equal the seven "
                    "pre-verification feature definitions"
                )
        errors.extend(
            _feature_key_errors(features, "board_stream.proposal_features")
        )
    return errors


def validate_construction_catalog(value: Any) -> list[str]:
    """Validate the immutable target-free construction catalog contract."""

    errors = _validate_json_value(value)
    row = _exact_keys(
        value,
        {
            "schema_version",
            "catalog_id",
            "construction_contract",
            "generator",
            "board_contract",
            "strata",
            "stratum_schedule",
            "deduplication",
            "source_boundary",
        },
        "construction_catalog",
        errors,
    )
    if row is None:
        return errors
    if row.get("schema_version") != CONSTRUCTION_CATALOG_SCHEMA_VERSION:
        errors.append(
            "construction_catalog.schema_version: must be "
            f"{CONSTRUCTION_CATALOG_SCHEMA_VERSION}"
        )
    catalog_id = row.get("catalog_id")
    if not isinstance(catalog_id, str) or not re.fullmatch(
        r"catalog-sha256:[0-9a-f]{64}", catalog_id
    ):
        errors.append(
            "construction_catalog.catalog_id: must be a typed SHA-256 identifier"
        )
    if row.get("construction_contract") != CONSTRUCTION_CONTRACT_V2:
        errors.append("construction_catalog.construction_contract: invalid")
    generator = _exact_keys(
        row.get("generator"),
        {"name", "version", "family", "operator"},
        "construction_catalog.generator",
        errors,
    )
    if generator is not None:
        if generator.get("name") != PARTIZAN_POOL_GENERATOR_NAME:
            errors.append("construction_catalog.generator.name: invalid")
        expected_generator = {
            "name": PARTIZAN_POOL_GENERATOR_NAME,
            "version": "0.2.0",
            "family": "dfile_two_component_constructive_grammar_v2",
            "operator": "seeded_constructive_component_composition_v2",
        }
        if generator != expected_generator:
            errors.append("construction_catalog.generator: invalid v0.2 identity")
    board = _exact_keys(
        row.get("board_contract"),
        {
            "barrier",
            "side_to_move",
            "castling_rights",
            "en_passant",
            "forbidden_active_files",
            "active_piece_count_per_component",
        },
        "construction_catalog.board_contract",
        errors,
    )
    if board is not None:
        expected_barrier = [
            [f"d{rank}", "P" if rank % 2 else "p"] for rank in range(1, 9)
        ]
        if board.get("barrier") != expected_barrier:
            errors.append("construction_catalog.board_contract.barrier: invalid")
        if board.get("side_to_move") != "w":
            errors.append("construction_catalog.board_contract.side_to_move: invalid")
        if board.get("castling_rights") != "none":
            errors.append("construction_catalog.board_contract.castling_rights: invalid")
        if board.get("en_passant") != "none":
            errors.append("construction_catalog.board_contract.en_passant: invalid")
        if board.get("forbidden_active_files") != ["e"]:
            errors.append(
                "construction_catalog.board_contract.forbidden_active_files: invalid"
            )
        counts = _exact_keys(
            board.get("active_piece_count_per_component"),
            {"minimum", "maximum"},
            "construction_catalog.board_contract.active_piece_count_per_component",
            errors,
        )
        if counts is not None and counts != {"minimum": 1, "maximum": 5}:
            errors.append(
                "construction_catalog.board_contract."
                "active_piece_count_per_component: invalid"
            )
    strata = _exact_keys(
        row.get("strata"),
        {"outer_leaper", "pawn_phalanx", "ray_cage", "mixed_color_hook"},
        "construction_catalog.strata",
        errors,
    )
    if strata is not None:
        for name in ("outer_leaper", "pawn_phalanx"):
            item = _exact_keys(
                strata.get(name),
                {"left", "right"},
                f"construction_catalog.strata.{name}",
                errors,
            )
            if item is not None:
                for side in ("left", "right"):
                    _nonempty_string(
                        item.get(side),
                        f"construction_catalog.strata.{name}.{side}",
                        errors,
                    )
        ray_cage = _exact_keys(
            strata.get("ray_cage"),
            {"left_bases", "right_bases", "extra_atoms"},
            "construction_catalog.strata.ray_cage",
            errors,
        )
        if ray_cage is not None:
            for side in ("left_bases", "right_bases"):
                bases = ray_cage.get(side)
                if not isinstance(bases, list) or not bases:
                    errors.append(
                        f"construction_catalog.strata.ray_cage.{side}: "
                        "must be a non-empty array"
                    )
                    continue
                for base_index, base in enumerate(bases):
                    if not isinstance(base, list) or not base:
                        errors.append(
                            "construction_catalog.strata.ray_cage."
                            f"{side}[{base_index}]: must be a non-empty piece array"
                        )
                        continue
                    for piece_index, piece in enumerate(base):
                        if (
                            not isinstance(piece, list)
                            or len(piece) != 2
                            or not isinstance(piece[0], str)
                            or not re.fullmatch(r"[a-h][1-8]", piece[0])
                            or not isinstance(piece[1], str)
                            or not re.fullmatch(r"[PNBRQKpnbrqk]", piece[1])
                        ):
                            errors.append(
                                "construction_catalog.strata.ray_cage."
                                f"{side}[{base_index}][{piece_index}]: invalid piece"
                            )
            _nonempty_string(
                ray_cage.get("extra_atoms"),
                "construction_catalog.strata.ray_cage.extra_atoms",
                errors,
            )
        mixed = _exact_keys(
            strata.get("mixed_color_hook"),
            {"left_base", "right_base", "extra_atoms"},
            "construction_catalog.strata.mixed_color_hook",
            errors,
        )
        if mixed is not None:
            for side in ("left_base", "right_base"):
                base = mixed.get(side)
                if not isinstance(base, list) or not base:
                    errors.append(
                        "construction_catalog.strata.mixed_color_hook."
                        f"{side}: must be a non-empty piece array"
                    )
                    continue
                for piece_index, piece in enumerate(base):
                    if (
                        not isinstance(piece, list)
                        or len(piece) != 2
                        or not isinstance(piece[0], str)
                        or not re.fullmatch(r"[a-h][1-8]", piece[0])
                        or not isinstance(piece[1], str)
                        or not re.fullmatch(r"[PNBRQKpnbrqk]", piece[1])
                    ):
                        errors.append(
                            "construction_catalog.strata.mixed_color_hook."
                            f"{side}[{piece_index}]: invalid piece"
                        )
            _nonempty_string(
                mixed.get("extra_atoms"),
                "construction_catalog.strata.mixed_color_hook.extra_atoms",
                errors,
            )
    if row.get("stratum_schedule") != "accepted_ordinal_modulo_four_v1":
        errors.append("construction_catalog.stratum_schedule: invalid")
    if row.get("deduplication") != [
        "target_free_board_id",
        "fen_horizontal_reflection_v0",
    ]:
        errors.append("construction_catalog.deduplication: invalid")
    source = _exact_keys(
        row.get("source_boundary"),
        {"astralbase_commit", "source_file", "published_source_families"},
        "construction_catalog.source_boundary",
        errors,
    )
    if source is not None:
        _commit(
            source.get("astralbase_commit"),
            "construction_catalog.source_boundary.astralbase_commit",
            errors,
        )
        _relative_path(
            source.get("source_file"),
            "construction_catalog.source_boundary.source_file",
            errors,
        )
        families = source.get("published_source_families")
        if not isinstance(families, list) or not families or not all(
            isinstance(item, str) and item for item in families
        ):
            errors.append(
                "construction_catalog.source_boundary.published_source_families: "
                "must be a non-empty string array"
            )
    if isinstance(catalog_id, str) and catalog_id != construction_catalog_id_for(row):
        errors.append(
            "construction_catalog.catalog_id: does not match canonical identity"
        )
    return errors


def _board_squares_from_fen(fen: str) -> dict[str, str]:
    fields = fen.split()
    if len(fields) != 6:
        raise ValueError("FEN must contain six fields")
    ranks = fields[0].split("/")
    if len(ranks) != 8:
        raise ValueError("FEN board must contain eight ranks")
    squares: dict[str, str] = {}
    for rank, encoded in zip(range(8, 0, -1), ranks):
        file_index = 0
        for token in encoded:
            if token.isdigit():
                file_index += int(token)
                continue
            if token not in "PNBRQKpnbrqk" or file_index >= 8:
                raise ValueError("FEN board contains an invalid piece placement")
            squares[f"{'abcdefgh'[file_index]}{rank}"] = token
            file_index += 1
        if file_index != 8:
            raise ValueError("FEN rank does not expand to eight files")
    return squares


def _constructive_template_id(
    *, stratum: str, side: str, pieces: dict[str, str]
) -> str:
    payload = {
        "construction_contract": CONSTRUCTION_CONTRACT_V2,
        "stratum": stratum,
        "side": side,
        "pieces": [[square, pieces[square]] for square in sorted(pieces)],
    }
    return "template-sha256:" + sha256_hex(canonical_json_bytes(payload))


def _constructive_v2_witness(
    board_row: dict[str, Any], catalog: dict[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    """Reconstruct and check the static grammar without trusting row claims."""

    catalog_errors = validate_construction_catalog(catalog)
    if catalog_errors:
        raise ValueError("invalid construction catalog: " + "; ".join(catalog_errors))
    fen = board_row.get("position", {}).get("text")
    if not isinstance(fen, str):
        raise ValueError("board row has no FEN text")
    squares = _board_squares_from_fen(fen)
    barrier = dict(catalog["board_contract"]["barrier"])
    if any(squares.get(square) != piece for square, piece in barrier.items()):
        raise ValueError("BarrierPawnNotFrozen")
    active = {square: piece for square, piece in squares.items() if square not in barrier}
    if any(square[0] in {"c", "e"} for square in active):
        raise ValueError("BarrierPieceCanBeCaptured")
    left = {square: piece for square, piece in active.items() if square[0] in "ab"}
    right = {square: piece for square, piece in active.items() if square[0] in "fgh"}
    if len(left) + len(right) != len(active):
        raise ValueError("PieceCanEnterOtherComponent")
    if not 1 <= len(left) <= 5 or not 1 <= len(right) <= 5:
        raise ValueError("RequiresStrictDecomposition")
    construction = board_row.get("construction")
    if not isinstance(construction, dict):
        raise ValueError("board row has no construction witness")
    stratum = construction.get("stratum")

    def outer_ok(region: dict[str, str], knight_file: str, pawn_file: str) -> bool:
        pawns = 0
        for square, piece in region.items():
            if square[0] == knight_file and piece in {"N", "n"}:
                continue
            rank = int(square[1])
            if square[0] != pawn_file or piece not in {"P", "p"}:
                return False
            if (piece == "P" and rank == 8) or (piece == "p" and rank == 1):
                return False
            pawns += 1
        return pawns <= 1

    def phalanx_ok(region: dict[str, str], files: set[str]) -> bool:
        return (
            len(region) == 2
            and {square[0] for square in region} == files
            and all(
                piece in {"P", "p"}
                and not (piece == "P" and square[1] == "8")
                and not (piece == "p" and square[1] == "1")
                for square, piece in region.items()
            )
        )

    def catalog_base_ok(
        region: dict[str, str],
        bases: list[list[list[str]]],
        extra_squares: set[str],
        maximum_extra_count: int,
    ) -> bool:
        for encoded_base in bases:
            base = dict(encoded_base)
            if not all(region.get(square) == piece for square, piece in base.items()):
                continue
            extras = {
                square: piece for square, piece in region.items() if square not in base
            }
            if len(extras) <= maximum_extra_count and all(
                square in extra_squares and piece in {"N", "n"}
                for square, piece in extras.items()
            ):
                return True
        return False

    if stratum == "outer_leaper":
        left_ok = outer_ok(left, "a", "b")
        right_ok = outer_ok(right, "h", "g")
    elif stratum == "pawn_phalanx":
        left_ok = phalanx_ok(left, {"a", "b"})
        right_ok = phalanx_ok(right, {"g", "h"})
    elif stratum == "ray_cage":
        ray = catalog["strata"]["ray_cage"]
        left_ok = catalog_base_ok(
            left,
            ray["left_bases"],
            {f"a{rank}" for rank in range(1, 9)},
            3,
        )
        right_ok = catalog_base_ok(
            right,
            ray["right_bases"],
            {f"h{rank}" for rank in range(1, 9)},
            3,
        )
    elif stratum == "mixed_color_hook":
        mixed = catalog["strata"]["mixed_color_hook"]
        left_ok = catalog_base_ok(
            left,
            [mixed["left_base"]],
            {f"a{rank}" for rank in range(4, 9)},
            2,
        )
        right_ok = catalog_base_ok(
            right,
            [mixed["right_base"]],
            {f"h{rank}" for rank in range(1, 6)},
            2,
        )
    else:
        left_ok = right_ok = False
    if not left_ok or not right_ok:
        raise ValueError("PieceCanEnterOtherComponent")
    if construction.get("contract") != catalog.get("construction_contract"):
        raise ValueError("construction contract does not match catalog")
    expected_claims = {
        "left_active_piece_count": len(left),
        "right_active_piece_count": len(right),
        "left_template_id": _constructive_template_id(
            stratum=str(stratum), side="left", pieces=left
        ),
        "right_template_id": _constructive_template_id(
            stratum=str(stratum), side="right", pieces=right
        ),
        "runtime_oracle_used": False,
    }
    for key, expected in expected_claims.items():
        if construction.get(key) != expected:
            raise ValueError(f"construction.{key} does not match board witness")
    return left, right


def construction_certificate_for_board_row(
    board_row: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    """Project a board's static construction witness into a sidecar row."""

    construction = board_row["construction"]
    left, right = _constructive_v2_witness(board_row, catalog)
    certificate: dict[str, Any] = {
        "schema_version": CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION,
        "certificate_id": "certificate-sha256:" + "0" * 64,
        "board_id": board_row["board_id"],
        "ordinal": board_row["ordinal"],
        "catalog_id": catalog["catalog_id"],
        "construction_contract": construction["contract"],
        "stratum": construction["stratum"],
        "left": {
            "active_piece_count": len(left),
            "template_id": _constructive_template_id(
                stratum=construction["stratum"], side="left", pieces=left
            ),
        },
        "right": {
            "active_piece_count": len(right),
            "template_id": _constructive_template_id(
                stratum=construction["stratum"], side="right", pieces=right
            ),
        },
        "runtime_oracle_used": construction["runtime_oracle_used"],
    }
    certificate["certificate_id"] = construction_certificate_id_for(certificate)
    return certificate


def validate_structural_construction_certificate(
    value: Any,
    board_row: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(
        value,
        _CONSTRUCTION_CERTIFICATE_KEYS,
        "construction_certificate",
        errors,
    )
    if row is None:
        return errors
    if row.get("schema_version") != CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION:
        errors.append(
            "construction_certificate.schema_version: must be "
            f"{CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION}"
        )
    certificate_id = row.get("certificate_id")
    if not isinstance(certificate_id, str) or not re.fullmatch(
        r"certificate-sha256:[0-9a-f]{64}", certificate_id
    ):
        errors.append(
            "construction_certificate.certificate_id: invalid typed identity"
        )
    if not isinstance(row.get("board_id"), str) or not re.fullmatch(
        r"board-sha256:[0-9a-f]{64}", row.get("board_id", "")
    ):
        errors.append("construction_certificate.board_id: invalid typed identity")
    ordinal = row.get("ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        errors.append(
            "construction_certificate.ordinal: must be a non-negative integer"
        )
    if not isinstance(row.get("catalog_id"), str) or not re.fullmatch(
        r"catalog-sha256:[0-9a-f]{64}", row.get("catalog_id", "")
    ):
        errors.append("construction_certificate.catalog_id: invalid typed identity")
    if row.get("construction_contract") != CONSTRUCTION_CONTRACT_V2:
        errors.append("construction_certificate.construction_contract: invalid")
    if row.get("stratum") not in {
        "outer_leaper",
        "pawn_phalanx",
        "ray_cage",
        "mixed_color_hook",
    }:
        errors.append("construction_certificate.stratum: invalid")
    for side in ("left", "right"):
        component = _exact_keys(
            row.get(side),
            {"active_piece_count", "template_id"},
            f"construction_certificate.{side}",
            errors,
        )
        if component is None:
            continue
        count = component.get("active_piece_count")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 5:
            errors.append(
                f"construction_certificate.{side}.active_piece_count: invalid"
            )
        template_id = component.get("template_id")
        if not isinstance(template_id, str) or not re.fullmatch(
            r"template-sha256:[0-9a-f]{64}", template_id
        ):
            errors.append(
                f"construction_certificate.{side}.template_id: invalid typed identity"
            )
    if row.get("runtime_oracle_used") is not False:
        errors.append("construction_certificate.runtime_oracle_used: must be false")
    if board_row is not None and catalog is not None:
        try:
            expected = construction_certificate_for_board_row(board_row, catalog)
        except (KeyError, TypeError, ValueError) as error:
            errors.append(
                "construction_certificate: cannot derive from bound board/catalog: "
                f"{error}"
            )
        else:
            if row != expected:
                errors.append(
                    "construction_certificate: does not equal the pure board/catalog projection"
                )
    if isinstance(certificate_id, str) and (
        certificate_id != construction_certificate_id_for(row)
    ):
        errors.append(
            "construction_certificate.certificate_id: does not match canonical identity"
        )
    return errors


def validate_candidate_proposal(value: Any, target_spec: dict[str, Any]) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(value, _PROPOSAL_KEYS, "proposal", errors)
    if row is None:
        return errors
    if row.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
        errors.append(f"proposal.schema_version: must be {PROPOSAL_SCHEMA_VERSION}")
    _typed_id(row.get("proposal_id"), "proposal", "proposal.proposal_id", errors)
    _typed_id(row.get("candidate_key"), "candidate", "proposal.candidate_key", errors)
    if row.get("target_id") != target_spec.get("target_id"):
        errors.append("proposal.target_id: does not match target")
    if row.get("domain") != target_spec.get("domain"):
        errors.append("proposal.domain: does not match target")
    ordinal = row.get("ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        errors.append("proposal.ordinal: must be a non-negative integer")

    position = _exact_keys(
        row.get("position"),
        {"encoding", "text", "sha256", "symmetry_sha256"},
        "proposal.position",
        errors,
    )
    if position is not None:
        if position.get("encoding") != "fen":
            errors.append("proposal.position.encoding: must be 'fen'")
        fen = position.get("text")
        if not isinstance(fen, str) or len(fen.split()) != 6:
            errors.append("proposal.position.text: must be a six-field FEN string")
        else:
            expected = sha256_hex(fen.encode("utf-8"))
            if position.get("sha256") != expected:
                errors.append("proposal.position.sha256: does not match position text")
        _hex(position.get("symmetry_sha256"), 64, "proposal.position.symmetry_sha256", errors)
        generator_value = row.get("generator")
        generator_name = (
            generator_value.get("name")
            if isinstance(generator_value, dict)
            else None
        )
        candidate_key_builder = (
            candidate_state_key_for
            if generator_name == PARTIZAN_POOL_GENERATOR_NAME
            else candidate_key_for
        )
        if row.get("candidate_key") != candidate_key_builder(
            str(row.get("domain")), position
        ):
            errors.append("proposal.candidate_key: does not match domain and position")
        if generator_name == PARTIZAN_POOL_GENERATOR_NAME and isinstance(fen, str):
            try:
                expected_orbit = fen_file_reflection_orbit_sha256(fen)
            except ValueError as error:
                errors.append(f"proposal.position.text: {error}")
            else:
                if position.get("symmetry_sha256") != expected_orbit:
                    errors.append(
                        "proposal.position.symmetry_sha256: does not match the "
                        "clock-free file-reflection orbit"
                    )

    generator = _exact_keys(
        row.get("generator"),
        {"name", "version", "code_commit", "family", "operator", "config_sha256", "random_seed"},
        "proposal.generator",
        errors,
    )
    if generator is not None:
        for key in ("name", "version", "family", "operator"):
            _nonempty_string(generator.get(key), f"proposal.generator.{key}", errors)
        _commit(generator.get("code_commit"), "proposal.generator.code_commit", errors)
        _hex(generator.get("config_sha256"), 64, "proposal.generator.config_sha256", errors)
        seed = generator.get("random_seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            errors.append("proposal.generator.random_seed: must be a non-negative integer")

    features = _exact_keys(
        row.get("proposal_features"),
        {"schema_version", "derivation_stage", "categorical", "integer", "boolean"},
        "proposal.proposal_features",
        errors,
    )
    if features is not None:
        if features.get("schema_version") != "partizan.proposal_features.v0.1":
            errors.append("proposal.proposal_features.schema_version: invalid")
        if features.get("derivation_stage") != "pre_verification":
            errors.append("proposal.proposal_features.derivation_stage: must be pre_verification")
        for key, expected_type in (
            ("categorical", str),
            ("integer", int),
            ("boolean", bool),
        ):
            mapping = _mapping(features.get(key), f"proposal.proposal_features.{key}", errors)
            if mapping is None:
                continue
            for feature_name, feature_value in mapping.items():
                if not feature_name:
                    errors.append(f"proposal.proposal_features.{key}: feature names must be non-empty")
                if expected_type is int:
                    valid_type = isinstance(feature_value, int) and not isinstance(feature_value, bool)
                else:
                    valid_type = isinstance(feature_value, expected_type)
                if not valid_type:
                    errors.append(
                        f"proposal.proposal_features.{key}.{feature_name}: invalid value type"
                    )
        errors.extend(_feature_key_errors(features))
        generator_value = row.get("generator")
        generator_name = (
            generator_value.get("name")
            if isinstance(generator_value, dict)
            else None
        )
        fen = position.get("text") if isinstance(position, dict) else None
        if generator_name == PARTIZAN_POOL_GENERATOR_NAME and isinstance(fen, str):
            try:
                expected_features = partizan_pool_features_for_fen(fen)
            except ValueError as error:
                errors.append(f"proposal.proposal_features: cannot derive: {error}")
            else:
                if features != expected_features:
                    errors.append(
                        "proposal.proposal_features: must equal the seven "
                        "preregistered Partizan feature definitions"
                    )

    if isinstance(row.get("proposal_id"), str) and row.get("proposal_id") != proposal_id_for(row):
        errors.append("proposal.proposal_id: does not match canonical proposal identity")
    return errors


def project_board_stream_to_proposals(
    target_spec: dict[str, Any], board_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply the complete, target-limited v0.1 board-to-proposal projection."""

    target_errors = validate_target_spec(target_spec)
    if target_errors:
        raise ValueError("; ".join(target_errors))
    maximum = target_spec["search_limits"]["max_pool_size"]
    if len(board_rows) > maximum:
        raise ValueError("board stream exceeds target max_pool_size")
    proposals: list[dict[str, Any]] = []
    for ordinal, board_row in enumerate(board_rows):
        row_errors = validate_candidate_board_stream_row(board_row)
        if row_errors:
            raise ValueError(f"board_stream[{ordinal}]: " + "; ".join(row_errors))
        if board_row["ordinal"] != ordinal:
            raise ValueError("board stream ordinals must be contiguous and ordered")
        proposal: dict[str, Any] = {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "proposal_id": "proposal-sha256:" + "0" * 64,
            "target_id": target_spec["target_id"],
            "domain": target_spec["domain"],
            "candidate_key": candidate_state_key_for(
                target_spec["domain"], board_row["position"]
            ),
            "ordinal": ordinal,
            "position": dict(board_row["position"]),
            "generator": dict(board_row["generator"]),
            "proposal_features": board_row["proposal_features"],
        }
        proposal["proposal_id"] = proposal_id_for(proposal)
        proposal_errors = validate_candidate_proposal(proposal, target_spec)
        if proposal_errors:
            raise ValueError(f"proposal[{ordinal}]: " + "; ".join(proposal_errors))
        proposals.append(proposal)
    return proposals


def validate_verifier_result(
    value: Any, target_spec: dict[str, Any], proposal: dict[str, Any]
) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(value, _RESULT_KEYS, "result", errors)
    if row is None:
        return errors
    if row.get("schema_version") != RESULT_SCHEMA_VERSION:
        errors.append(f"result.schema_version: must be {RESULT_SCHEMA_VERSION}")
    _typed_id(row.get("result_id"), "result", "result.result_id", errors)
    for key in ("target_id", "proposal_id", "candidate_key"):
        expected = target_spec.get("target_id") if key == "target_id" else proposal.get(key)
        if row.get(key) != expected:
            errors.append(f"result.{key}: does not match referenced contract")

    verifier = _exact_keys(
        row.get("verifier"),
        {"name", "version", "config_sha256", "code_commits"},
        "result.verifier",
        errors,
    )
    if verifier is not None:
        _nonempty_string(verifier.get("name"), "result.verifier.name", errors)
        _nonempty_string(verifier.get("version"), "result.verifier.version", errors)
        _hex(verifier.get("config_sha256"), 64, "result.verifier.config_sha256", errors)
        commits = _exact_keys(
            verifier.get("code_commits"),
            {"astralbase", "bitmesh", "thermograph", "partizan"},
            "result.verifier.code_commits",
            errors,
        )
        if commits is not None:
            for name, commit in commits.items():
                _commit(commit, f"result.verifier.code_commits.{name}", errors)
        expected_config = verifier_config_sha256_for(target_spec)
        if verifier.get("config_sha256") != expected_config:
            errors.append(
                "result.verifier.config_sha256: does not bind value_rule and node_budget"
            )

    verifier_io = _exact_keys(
        row.get("verifier_io"),
        {"request", "request_sha256", "response", "response_sha256"},
        "result.verifier_io",
        errors,
    )
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    if verifier_io is not None:
        request = _mapping(
            verifier_io.get("request"), "result.verifier_io.request", errors
        )
        response = _mapping(
            verifier_io.get("response"), "result.verifier_io.response", errors
        )
        _hex(
            verifier_io.get("request_sha256"),
            64,
            "result.verifier_io.request_sha256",
            errors,
        )
        _hex(
            verifier_io.get("response_sha256"),
            64,
            "result.verifier_io.response_sha256",
            errors,
        )
        if request is not None:
            expected_request = astralbase_request_for(target_spec, proposal)
            if request != expected_request:
                errors.append(
                    "result.verifier_io.request: does not match target, proposal, and node budget"
                )
            if verifier_io.get("request_sha256") != sha256_hex(
                canonical_json_bytes(request)
            ):
                errors.append(
                    "result.verifier_io.request_sha256: does not match canonical request"
                )
        if response is not None:
            if response.get("request_id") != proposal.get("proposal_id"):
                errors.append(
                    "result.verifier_io.response.request_id: does not match proposal"
                )
            if verifier_io.get("response_sha256") != sha256_hex(
                canonical_json_bytes(response)
            ):
                errors.append(
                    "result.verifier_io.response_sha256: does not match canonical response"
                )

    gates = row.get("gates")
    gate_statuses: dict[str, str] = {}
    if not isinstance(gates, list) or len(gates) != len(_REQUIRED_GATE_IDS):
        errors.append("result.gates: must contain the four ordered verifier gates")
    else:
        for index, (expected_id, gate) in enumerate(zip(_REQUIRED_GATE_IDS, gates)):
            gate_row = _exact_keys(
                gate,
                {"gate_id", "status", "reason_codes", "evidence_sha256"},
                f"result.gates[{index}]",
                errors,
            )
            if gate_row is None:
                continue
            if gate_row.get("gate_id") != expected_id:
                errors.append(f"result.gates[{index}].gate_id: must be {expected_id}")
            status = gate_row.get("status")
            if status not in {"passed", "failed", "not_run", "error"}:
                errors.append(f"result.gates[{index}].status: invalid")
            else:
                gate_statuses[expected_id] = status
            reasons = gate_row.get("reason_codes")
            if not isinstance(reasons, list) or not all(
                isinstance(reason, str) and reason for reason in reasons
            ):
                errors.append(f"result.gates[{index}].reason_codes: invalid")
            evidence_digest = gate_row.get("evidence_sha256")
            if evidence_digest is not None:
                _hex(evidence_digest, 64, f"result.gates[{index}].evidence_sha256", errors)

    comparison = _exact_keys(
        row.get("target_comparison"),
        {"identity_contract", "target_identity_sha256", "observed_identity_sha256", "matches"},
        "result.target_comparison",
        errors,
    )
    if comparison is not None:
        if comparison.get("identity_contract") != IDENTITY_CONTRACT:
            errors.append("result.target_comparison.identity_contract: invalid")
        if comparison.get("target_identity_sha256") != target_spec.get("target", {}).get("identity_sha256"):
            errors.append("result.target_comparison.target_identity_sha256: does not match target")
        observed = comparison.get("observed_identity_sha256")
        if observed is not None:
            _hex(observed, 64, "result.target_comparison.observed_identity_sha256", errors)
        if comparison.get("matches") not in {True, False, None}:
            errors.append("result.target_comparison.matches: must be boolean or null")

    evidence = _exact_keys(
        row.get("evidence"),
        {
            "label_kind",
            "certificate_digest",
            "rejection_codes",
            "decomposition_digest",
            "composition_digest",
            "observed_structural_sha256",
            "recursive_nodes",
        },
        "result.evidence",
        errors,
    )
    if evidence is not None:
        if evidence.get("label_kind") not in {"exact", "rejected"}:
            errors.append("result.evidence.label_kind: invalid")
        certificate = evidence.get("certificate_digest")
        if certificate is not None:
            _nonempty_string(certificate, "result.evidence.certificate_digest", errors)
        rejection_codes = evidence.get("rejection_codes")
        if not isinstance(rejection_codes, list) or not all(
            isinstance(code, str) and code for code in rejection_codes
        ):
            errors.append("result.evidence.rejection_codes: invalid")
        for digest_key in (
            "decomposition_digest",
            "composition_digest",
            "observed_structural_sha256",
        ):
            digest_value = evidence.get(digest_key)
            if digest_value is not None:
                _hex(digest_value, 64, f"result.evidence.{digest_key}", errors)
        recursive_nodes = evidence.get("recursive_nodes")
        if recursive_nodes is not None and (
            not isinstance(recursive_nodes, int)
            or isinstance(recursive_nodes, bool)
            or recursive_nodes < 0
        ):
            errors.append("result.evidence.recursive_nodes: must be non-negative or null")

    outcome = row.get("outcome")
    if outcome not in {"certified_target", "certified_other", "rejected", "error"}:
        errors.append("result.outcome: invalid")
    elif comparison is not None and evidence is not None:
        matches = comparison.get("matches")
        observed = comparison.get("observed_identity_sha256")
        label_kind = evidence.get("label_kind")
        rejection_codes = evidence.get("rejection_codes")
        structural_evidence = (
            evidence.get("decomposition_digest"),
            evidence.get("composition_digest"),
            evidence.get("observed_structural_sha256"),
            evidence.get("recursive_nodes"),
        )
        if outcome == "certified_target":
            if any(gate_statuses.get(gate) != "passed" for gate in _REQUIRED_GATE_IDS):
                errors.append("result.outcome: certified_target requires every gate to pass")
            if matches is not True or observed != comparison.get("target_identity_sha256"):
                errors.append("result.outcome: certified_target requires matching identities")
            if label_kind != "exact" or rejection_codes:
                errors.append("result.evidence: certified_target requires an exact non-rejected label")
            if evidence.get("certificate_digest") is None:
                errors.append("result.evidence: certified_target requires a certificate digest")
            if any(item is None for item in structural_evidence):
                errors.append("result.evidence: certified_target requires complete structural evidence")
            if evidence.get("observed_structural_sha256") != observed:
                errors.append("result.evidence: observed structural SHA must match comparison")
        elif outcome == "certified_other":
            if any(gate_statuses.get(gate) != "passed" for gate in _REQUIRED_GATE_IDS[:-1]):
                errors.append("result.outcome: certified_other requires proof gates to pass")
            if gate_statuses.get("target_identity") != "failed" or matches is not False or observed is None:
                errors.append("result.outcome: certified_other requires a nonmatching exact identity")
            if label_kind != "exact" or rejection_codes:
                errors.append("result.evidence: certified_other requires an exact non-rejected label")
            if evidence.get("certificate_digest") is None:
                errors.append("result.evidence: certified_other requires a certificate digest")
            if any(item is None for item in structural_evidence):
                errors.append("result.evidence: certified_other requires complete structural evidence")
            if evidence.get("observed_structural_sha256") != observed:
                errors.append("result.evidence: observed structural SHA must match comparison")
        elif outcome == "rejected":
            if matches is not None or observed is not None:
                errors.append("result.target_comparison: rejected results cannot claim an observed identity")
            if label_kind != "rejected" or not rejection_codes:
                errors.append("result.evidence: rejected outcomes require rejection codes")
            if evidence.get("certificate_digest") is not None:
                errors.append("result.evidence: rejected outcomes cannot claim a certificate")
            if not any(status == "failed" for status in gate_statuses.values()):
                errors.append("result.outcome: rejected requires a failed gate")
            if any(item is not None for item in structural_evidence):
                errors.append("result.evidence: rejected outcomes cannot claim structural evidence")
        elif outcome == "error":
            if matches is not None or observed is not None:
                errors.append("result.target_comparison: error results cannot claim an observed identity")
            if label_kind != "rejected" or not rejection_codes:
                errors.append("result.evidence: error outcomes require an error code")
            if evidence.get("certificate_digest") is not None:
                errors.append("result.evidence: error outcomes cannot claim a certificate")
            if not any(status == "error" for status in gate_statuses.values()):
                errors.append("result.outcome: error requires an error gate")
            if any(item is not None for item in structural_evidence):
                errors.append("result.evidence: error outcomes cannot claim structural evidence")

    if response is not None and comparison is not None and evidence is not None:
        status_to_outcome = {
            "verified_match": "certified_target",
            "verified_nonmatch": "certified_other",
            "rejected": "rejected",
            "internal_error": "error",
        }
        response_status = response.get("status")
        expected_outcome = status_to_outcome.get(response_status)
        if expected_outcome is None:
            errors.append("result.verifier_io.response.status: unsupported")
        elif outcome != expected_outcome:
            errors.append(
                "result.outcome: does not match the exhaustive Astralbase status mapping"
            )
        try:
            expected_gates = verifier_gate_rows_for(response, proposal)
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"result.verifier_io.response: cannot derive gates: {error}")
        else:
            if gates != expected_gates:
                errors.append(
                    "result.gates: do not match recomputed response evidence and failure order"
                )

        actual = response.get("actual")
        if response_status in {"verified_match", "verified_nonmatch"}:
            required_actual = {
                "identity_kind",
                "semantics",
                "value_class",
                "digest_v1_sha256",
                "legacy_digest",
                "recursive_nodes",
                "decomposition_digest",
                "composition_digest",
                "component_legacy_digests",
            }
            if not isinstance(actual, dict) or not required_actual.issubset(actual):
                errors.append(
                    "result.verifier_io.response.actual: certified response is incomplete"
                )
            else:
                if actual.get("identity_kind") != IDENTITY_CONTRACT:
                    errors.append(
                        "result.verifier_io.response.actual.identity_kind: invalid"
                    )
                if actual.get("semantics") != "structural_tree_identity_only":
                    errors.append(
                        "result.verifier_io.response.actual.semantics: invalid"
                    )
                actual_value_class = actual.get("value_class")
                target_value_class = target_spec.get("target", {}).get("value_class")
                if not isinstance(actual_value_class, str) or not actual_value_class:
                    errors.append(
                        "result.verifier_io.response.actual.value_class: invalid"
                    )
                if not isinstance(actual.get("legacy_digest"), str) or not actual.get(
                    "legacy_digest"
                ):
                    errors.append(
                        "result.verifier_io.response.actual.legacy_digest: invalid"
                    )
                component_digests = actual.get("component_legacy_digests")
                if (
                    not isinstance(component_digests, dict)
                    or not component_digests
                    or not all(
                    isinstance(key, str)
                    and key
                    and isinstance(item, str)
                    and item
                    for key, item in component_digests.items()
                    )
                ):
                    errors.append(
                        "result.verifier_io.response.actual.component_legacy_digests: invalid"
                    )
                if actual.get("digest_v1_sha256") != comparison.get(
                    "observed_identity_sha256"
                ):
                    errors.append(
                        "result.verifier_io.response.actual.digest_v1_sha256: does not match comparison"
                    )
                class_equal = actual_value_class == target_value_class
                digest_equal = actual.get("digest_v1_sha256") == comparison.get(
                    "target_identity_sha256"
                )
                actual_matches = class_equal and digest_equal
                if (response_status == "verified_match") != actual_matches:
                    errors.append(
                        "result.verifier_io.response.status: contradicts exact value-class and structural-digest identity"
                    )
                if actual.get("decomposition_digest") != evidence.get(
                    "decomposition_digest"
                ):
                    errors.append(
                        "result.evidence.decomposition_digest: does not match verifier response"
                    )
                if actual.get("composition_digest") != evidence.get(
                    "composition_digest"
                ):
                    errors.append(
                        "result.evidence.composition_digest: does not match verifier response"
                    )
                if actual.get("digest_v1_sha256") != evidence.get(
                    "observed_structural_sha256"
                ):
                    errors.append(
                        "result.evidence.observed_structural_sha256: does not match verifier response"
                    )
                nodes = actual.get("recursive_nodes")
                node_budget = target_spec.get("search_limits", {}).get(
                    "max_recursive_nodes_per_candidate"
                )
                if (
                    not isinstance(nodes, int)
                    or isinstance(nodes, bool)
                    or nodes < 0
                    or not isinstance(node_budget, int)
                    or nodes > node_budget
                ):
                    errors.append(
                        "result.verifier_io.response.actual.recursive_nodes: exceeds request budget"
                    )
                if nodes != evidence.get("recursive_nodes"):
                    errors.append(
                        "result.evidence.recursive_nodes: does not match verifier response"
                    )
                expected_certificate = "astralbase-actual-sha256:" + sha256_hex(
                    canonical_json_bytes(actual)
                )
                if evidence.get("certificate_digest") != expected_certificate:
                    errors.append(
                        "result.evidence.certificate_digest: does not bind exact verifier actual"
                    )
        elif response_status in {"rejected", "internal_error"}:
            if actual is not None:
                errors.append(
                    "result.verifier_io.response.actual: non-certified response cannot claim actual"
                )
            fallback = (
                "astralbase_internal_error"
                if response_status == "internal_error"
                else "astralbase_rejected"
            )
            expected_reason = response.get("reason_code") or fallback
            if evidence.get("rejection_codes") != [expected_reason]:
                errors.append(
                    "result.evidence.rejection_codes: does not bind verifier reason_code"
                )

    if isinstance(row.get("result_id"), str) and row.get("result_id") != verifier_result_id_for(row):
        errors.append("result.result_id: does not match canonical result identity")
    return errors


def validate_generation_receipt(
    value: Any,
    target_spec: dict[str, Any],
    proposals: list[dict[str, Any]],
) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(
        value,
        {
            "schema_version",
            "receipt_id",
            "target_id",
            "domain",
            "generator",
            "candidate_artifact",
            "executions",
        },
        "generation_receipt",
        errors,
    )
    if row is None:
        return errors
    if row.get("schema_version") != GENERATION_RECEIPT_SCHEMA_VERSION:
        errors.append(
            "generation_receipt.schema_version: must be "
            f"{GENERATION_RECEIPT_SCHEMA_VERSION}"
        )
    receipt_id = row.get("receipt_id")
    if not isinstance(receipt_id, str) or not re.fullmatch(
        r"receipt-sha256:[0-9a-f]{64}", receipt_id
    ):
        errors.append(
            "generation_receipt.receipt_id: must be a typed SHA-256 identifier"
        )
    if row.get("target_id") != target_spec.get("target_id"):
        errors.append("generation_receipt.target_id: does not match target")
    if row.get("domain") != target_spec.get("domain"):
        errors.append("generation_receipt.domain: does not match target")

    generator = _exact_keys(
        row.get("generator"),
        {"name", "version", "code_commit", "config_sha256", "random_seed"},
        "generation_receipt.generator",
        errors,
    )
    if generator is not None:
        if generator.get("name") != PARTIZAN_POOL_GENERATOR_NAME:
            errors.append(
                "generation_receipt.generator.name: unsupported generator identity"
            )
        _nonempty_string(
            generator.get("version"), "generation_receipt.generator.version", errors
        )
        _commit(
            generator.get("code_commit"),
            "generation_receipt.generator.code_commit",
            errors,
        )
        _hex(
            generator.get("config_sha256"),
            64,
            "generation_receipt.generator.config_sha256",
            errors,
        )
        seed = generator.get("random_seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            errors.append(
                "generation_receipt.generator.random_seed: must be a "
                "non-negative integer"
            )
        if proposals:
            first_generator = proposals[0].get("generator")
            if isinstance(first_generator, dict):
                expected_generator = {
                    key: first_generator.get(key)
                    for key in (
                        "name",
                        "version",
                        "code_commit",
                        "config_sha256",
                        "random_seed",
                    )
                }
                if generator != expected_generator:
                    errors.append(
                        "generation_receipt.generator: does not match proposals"
                    )

    artifact = _exact_keys(
        row.get("candidate_artifact"),
        {"schema_version", "row_count", "sha256"},
        "generation_receipt.candidate_artifact",
        errors,
    )
    expected_artifact_sha = sha256_hex(canonical_jsonl_bytes(proposals))
    if artifact is not None:
        if artifact.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            errors.append(
                "generation_receipt.candidate_artifact.schema_version: invalid"
            )
        if artifact.get("row_count") != len(proposals):
            errors.append(
                "generation_receipt.candidate_artifact.row_count: does not "
                "match proposals"
            )
        if artifact.get("sha256") != expected_artifact_sha:
            errors.append(
                "generation_receipt.candidate_artifact.sha256: does not match proposals"
            )

    executions = _exact_keys(
        row.get("executions"),
        {"mode", "run_count", "raw_artifact_sha256", "byte_identical"},
        "generation_receipt.executions",
        errors,
    )
    if executions is not None:
        if executions.get("mode") != "separate_python_processes_v1":
            errors.append(
                "generation_receipt.executions.mode: must attest separate processes"
            )
        if executions.get("run_count") != 2:
            errors.append("generation_receipt.executions.run_count: must be 2")
        hashes = executions.get("raw_artifact_sha256")
        if not isinstance(hashes, list) or len(hashes) != 2:
            errors.append(
                "generation_receipt.executions.raw_artifact_sha256: must contain "
                "two hashes"
            )
        else:
            for index, digest in enumerate(hashes):
                _hex(
                    digest,
                    64,
                    "generation_receipt.executions.raw_artifact_sha256"
                    f"[{index}]",
                    errors,
                )
            if hashes != [expected_artifact_sha, expected_artifact_sha]:
                errors.append(
                    "generation_receipt.executions.raw_artifact_sha256: both "
                    "runs must equal the candidate artifact"
                )
        if executions.get("byte_identical") is not True:
            errors.append(
                "generation_receipt.executions.byte_identical: must be true"
            )

    if isinstance(receipt_id, str) and receipt_id != generation_receipt_id_for(row):
        errors.append(
            "generation_receipt.receipt_id: does not match canonical receipt identity"
        )
    return errors


def _load_repository_artifact_bytes(
    relative_path: Any,
    repository_root: Path | None,
    path: str,
    errors: list[str],
) -> bytes | None:
    _relative_path(relative_path, path, errors)
    if repository_root is None:
        errors.append(f"{path}: repository_root is required")
        return None
    if not isinstance(relative_path, str):
        return None
    try:
        root = repository_root.resolve(strict=True)
        artifact = (root / Path(*PurePosixPath(relative_path).parts)).resolve(
            strict=True
        )
        artifact.relative_to(root)
        return artifact.read_bytes()
    except (OSError, ValueError) as error:
        errors.append(f"{path}: cannot load inside repository_root: {error}")
        return None


def _load_bound_json_artifact(
    reference: dict[str, Any] | None,
    repository_root: Path | None,
    path: str,
    errors: list[str],
    *,
    require_canonical: bool = True,
) -> dict[str, Any] | None:
    if reference is None:
        return None
    payload = _load_repository_artifact_bytes(
        reference.get("path"), repository_root, f"{path}.path", errors
    )
    if payload is None:
        return None
    if reference.get("sha256") != sha256_hex(payload):
        errors.append(f"{path}.sha256: does not match artifact bytes")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"{path}.path: invalid UTF-8 JSON: {error}")
        return None
    if not isinstance(decoded, dict):
        errors.append(f"{path}.path: artifact must contain one JSON object")
        return None
    try:
        canonical = canonical_json_bytes(decoded)
    except ValueError as error:
        errors.append(f"{path}.path: cannot canonicalize: {error}")
        return None
    if require_canonical and payload != canonical:
        errors.append(f"{path}.path: artifact bytes are not canonical")
    return decoded


def _load_bound_jsonl_artifact(
    reference: dict[str, Any] | None,
    repository_root: Path | None,
    path: str,
    errors: list[str],
) -> list[dict[str, Any]] | None:
    if reference is None:
        return None
    payload = _load_repository_artifact_bytes(
        reference.get("path"), repository_root, f"{path}.path", errors
    )
    if payload is None:
        return None
    if reference.get("sha256") != sha256_hex(payload):
        errors.append(f"{path}.sha256: does not match artifact bytes")
    try:
        text = payload.decode("utf-8")
        lines = text.splitlines()
        if not lines or any(not line for line in lines):
            raise ValueError("artifact must be non-empty JSONL without blank rows")
        values = [json.loads(line) for line in lines]
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"{path}.path: invalid UTF-8 JSONL: {error}")
        return None
    if not all(isinstance(item, dict) for item in values):
        errors.append(f"{path}.path: every JSONL row must be an object")
        return None
    try:
        canonical = canonical_jsonl_bytes(values)
    except ValueError as error:
        errors.append(f"{path}.path: cannot canonicalize: {error}")
        return None
    if payload != canonical:
        errors.append(f"{path}.path: artifact bytes are not canonical")
    if reference.get("row_count") != len(values):
        errors.append(f"{path}.row_count: does not match artifact rows")
    return values


def validate_generation_receipt_v2(
    value: Any,
    target_spec: dict[str, Any],
    proposals: list[dict[str, Any]],
    repository_root: Path | None,
) -> list[str]:
    """Validate Wave 69-R lineage without invoking a target verifier."""

    errors = _validate_json_value(value)
    errors.extend(
        f"generation_receipt_v2.target: {error}"
        for error in validate_target_spec(target_spec)
    )
    row = _exact_keys(
        value,
        {
            "schema_version",
            "receipt_id",
            "target_ref",
            "board_stream",
            "construction_catalog",
            "construction_certificates",
            "projection",
            "generator",
            "candidate_artifact",
            "executions",
            "source_repositories",
        },
        "generation_receipt_v2",
        errors,
    )
    if row is None:
        return errors
    if row.get("schema_version") != GENERATION_RECEIPT_SCHEMA_VERSION_V2:
        errors.append(
            "generation_receipt_v2.schema_version: must be "
            f"{GENERATION_RECEIPT_SCHEMA_VERSION_V2}"
        )
    receipt_id = row.get("receipt_id")
    if not isinstance(receipt_id, str) or not re.fullmatch(
        r"receipt-sha256:[0-9a-f]{64}", receipt_id
    ):
        errors.append("generation_receipt_v2.receipt_id: invalid typed identity")

    target_ref = _exact_keys(
        row.get("target_ref"),
        {"path", "schema_version", "target_id", "sha256"},
        "generation_receipt_v2.target_ref",
        errors,
    )
    loaded_target = _load_bound_json_artifact(
        target_ref,
        repository_root,
        "generation_receipt_v2.target_ref",
        errors,
    )
    if target_ref is not None:
        if target_ref.get("schema_version") != TARGET_SCHEMA_VERSION:
            errors.append("generation_receipt_v2.target_ref.schema_version: invalid")
        if target_ref.get("target_id") != target_spec.get("target_id"):
            errors.append("generation_receipt_v2.target_ref.target_id: target mismatch")
        if target_ref.get("sha256") != sha256_hex(canonical_json_bytes(target_spec)):
            errors.append("generation_receipt_v2.target_ref.sha256: target mismatch")
    if loaded_target is not None and loaded_target != target_spec:
        errors.append("generation_receipt_v2.target_ref.path: target payload mismatch")

    board_ref = _exact_keys(
        row.get("board_stream"),
        {"path", "schema_version", "row_count", "sha256"},
        "generation_receipt_v2.board_stream",
        errors,
    )
    board_rows = _load_bound_jsonl_artifact(
        board_ref,
        repository_root,
        "generation_receipt_v2.board_stream",
        errors,
    )
    if board_ref is not None and board_ref.get("schema_version") != BOARD_STREAM_SCHEMA_VERSION:
        errors.append("generation_receipt_v2.board_stream.schema_version: invalid")
    if board_rows is not None:
        for index, board_row in enumerate(board_rows):
            errors.extend(
                f"generation_receipt_v2.board_stream[{index}]: {error}"
                for error in validate_candidate_board_stream_row(board_row)
            )
            if board_row.get("ordinal") != index:
                errors.append(
                    f"generation_receipt_v2.board_stream[{index}].ordinal: "
                    "must be contiguous"
                )

    catalog_ref = _exact_keys(
        row.get("construction_catalog"),
        {
            "path",
            "schema_version",
            "catalog_id",
            "sha256",
            "construction_contract",
        },
        "generation_receipt_v2.construction_catalog",
        errors,
    )
    catalog = _load_bound_json_artifact(
        catalog_ref,
        repository_root,
        "generation_receipt_v2.construction_catalog",
        errors,
        require_canonical=False,
    )
    if catalog_ref is not None:
        if catalog_ref.get("schema_version") != CONSTRUCTION_CATALOG_SCHEMA_VERSION:
            errors.append(
                "generation_receipt_v2.construction_catalog.schema_version: invalid"
            )
        if catalog_ref.get("construction_contract") != CONSTRUCTION_CONTRACT_V2:
            errors.append(
                "generation_receipt_v2.construction_catalog."
                "construction_contract: invalid"
            )
        catalog_id = catalog_ref.get("catalog_id")
        if not isinstance(catalog_id, str) or not re.fullmatch(
            r"catalog-sha256:[0-9a-f]{64}", catalog_id
        ):
            errors.append(
                "generation_receipt_v2.construction_catalog.catalog_id: invalid"
            )
    if catalog is not None:
        errors.extend(validate_construction_catalog(catalog))
        if catalog_ref is not None:
            for key in ("schema_version", "catalog_id", "construction_contract"):
                if catalog_ref.get(key) != catalog.get(key):
                    errors.append(
                        "generation_receipt_v2.construction_catalog."
                        f"{key}: does not match catalog"
                    )

    certificate_ref = _exact_keys(
        row.get("construction_certificates"),
        {"path", "schema_version", "row_count", "sha256", "template_ids_sha256"},
        "generation_receipt_v2.construction_certificates",
        errors,
    )
    certificates = _load_bound_jsonl_artifact(
        certificate_ref,
        repository_root,
        "generation_receipt_v2.construction_certificates",
        errors,
    )
    if certificate_ref is not None:
        if certificate_ref.get("schema_version") != CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION:
            errors.append(
                "generation_receipt_v2.construction_certificates.schema_version: invalid"
            )
        _hex(
            certificate_ref.get("template_ids_sha256"),
            64,
            "generation_receipt_v2.construction_certificates.template_ids_sha256",
            errors,
        )
    if certificates is not None:
        template_ids = [
            [item.get("left", {}).get("template_id"), item.get("right", {}).get("template_id")]
            for item in certificates
        ]
        if certificate_ref is not None and certificate_ref.get(
            "template_ids_sha256"
        ) != sha256_hex(canonical_json_bytes(template_ids)):
            errors.append(
                "generation_receipt_v2.construction_certificates."
                "template_ids_sha256: does not match sidecar"
            )
        if board_rows is not None and len(certificates) != len(board_rows):
            errors.append(
                "generation_receipt_v2.construction_certificates: row count "
                "does not match board stream"
            )
        for index, certificate in enumerate(certificates):
            board_row = (
                board_rows[index]
                if board_rows is not None and index < len(board_rows)
                else None
            )
            errors.extend(
                f"generation_receipt_v2.construction_certificates[{index}]: {error}"
                for error in validate_structural_construction_certificate(
                    certificate, board_row, catalog
                )
            )

    projection = _exact_keys(
        row.get("projection"),
        {
            "contract_id",
            "implementation_commit",
            "target_fields_consumed",
            "mapping",
        },
        "generation_receipt_v2.projection",
        errors,
    )
    if projection is not None:
        if projection.get("contract_id") != BOARD_TO_PROPOSAL_PROJECTION_CONTRACT_V1:
            errors.append("generation_receipt_v2.projection.contract_id: invalid")
        _commit(
            projection.get("implementation_commit"),
            "generation_receipt_v2.projection.implementation_commit",
            errors,
        )
        if projection.get("target_fields_consumed") != [
            "/domain",
            "/search_limits/max_pool_size",
            "/target_id",
        ]:
            errors.append(
                "generation_receipt_v2.projection.target_fields_consumed: invalid"
            )
        if projection.get("mapping") != BOARD_TO_PROPOSAL_MAPPING_V1:
            errors.append("generation_receipt_v2.projection.mapping: invalid")

    generator = _exact_keys(
        row.get("generator"),
        {
            "name",
            "version",
            "code_commit",
            "family",
            "operator",
            "config_sha256",
            "random_seed",
        },
        "generation_receipt_v2.generator",
        errors,
    )
    if generator is not None:
        if generator.get("name") != PARTIZAN_POOL_GENERATOR_NAME:
            errors.append("generation_receipt_v2.generator.name: invalid")
        for key in ("version", "family", "operator"):
            _nonempty_string(
                generator.get(key), f"generation_receipt_v2.generator.{key}", errors
            )
        _commit(
            generator.get("code_commit"),
            "generation_receipt_v2.generator.code_commit",
            errors,
        )
        _hex(
            generator.get("config_sha256"),
            64,
            "generation_receipt_v2.generator.config_sha256",
            errors,
        )
        seed = generator.get("random_seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            errors.append(
                "generation_receipt_v2.generator.random_seed: must be non-negative"
            )
        for collection_name, collection in (
            ("board_stream", board_rows),
            ("candidate_artifact", proposals),
        ):
            if collection:
                for index, item in enumerate(collection):
                    if item.get("generator") != generator:
                        errors.append(
                            f"generation_receipt_v2.{collection_name}[{index}]."
                            "generator: does not match receipt"
                        )
        if catalog is not None:
            catalog_generator = catalog.get("generator")
            if isinstance(catalog_generator, dict):
                expected_catalog_generator = {
                    key: generator.get(key)
                    for key in ("name", "version", "family", "operator")
                }
                if catalog_generator != expected_catalog_generator:
                    errors.append(
                        "generation_receipt_v2.generator: does not match "
                        "construction catalog identity"
                    )

    candidate_ref = _exact_keys(
        row.get("candidate_artifact"),
        {"path", "schema_version", "row_count", "sha256"},
        "generation_receipt_v2.candidate_artifact",
        errors,
    )
    loaded_proposals = _load_bound_jsonl_artifact(
        candidate_ref,
        repository_root,
        "generation_receipt_v2.candidate_artifact",
        errors,
    )
    expected_proposal_bytes = canonical_jsonl_bytes(proposals)
    if candidate_ref is not None:
        if candidate_ref.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            errors.append("generation_receipt_v2.candidate_artifact.schema_version: invalid")
        if candidate_ref.get("row_count") != len(proposals):
            errors.append(
                "generation_receipt_v2.candidate_artifact.row_count: proposal mismatch"
            )
        if candidate_ref.get("sha256") != sha256_hex(expected_proposal_bytes):
            errors.append(
                "generation_receipt_v2.candidate_artifact.sha256: proposal mismatch"
            )
    if loaded_proposals is not None and loaded_proposals != proposals:
        errors.append(
            "generation_receipt_v2.candidate_artifact.path: proposal payload mismatch"
        )
    if board_rows is not None:
        try:
            expected_proposals = project_board_stream_to_proposals(
                target_spec, board_rows
            )
        except ValueError as error:
            errors.append(
                "generation_receipt_v2.projection: cannot recompute pure projection: "
                f"{error}"
            )
        else:
            if proposals != expected_proposals:
                errors.append(
                    "generation_receipt_v2.projection: candidate artifact does not "
                    "equal the pure board-to-proposal projection"
                )

    executions = _exact_keys(
        row.get("executions"),
        {
            "mode",
            "run_count",
            "board_stream_raw_sha256",
            "construction_certificate_sha256",
            "projection_artifact_sha256",
            "byte_identical",
        },
        "generation_receipt_v2.executions",
        errors,
    )
    if executions is not None:
        if executions.get("mode") != "separate_python_processes_v1":
            errors.append("generation_receipt_v2.executions.mode: invalid")
        if executions.get("run_count") != 2:
            errors.append("generation_receipt_v2.executions.run_count: must be 2")
        expected_hashes = {
            "board_stream_raw_sha256": board_ref.get("sha256") if board_ref else None,
            "construction_certificate_sha256": (
                certificate_ref.get("sha256") if certificate_ref else None
            ),
            "projection_artifact_sha256": (
                candidate_ref.get("sha256") if candidate_ref else None
            ),
        }
        for key, expected in expected_hashes.items():
            hashes = executions.get(key)
            if hashes != [expected, expected]:
                errors.append(
                    f"generation_receipt_v2.executions.{key}: must contain two "
                    "identical bound hashes"
                )
        if executions.get("byte_identical") is not True:
            errors.append("generation_receipt_v2.executions.byte_identical: must be true")

    repos = _exact_keys(
        row.get("source_repositories"),
        {"astralbase", "bitmesh", "thermograph", "partizan"},
        "generation_receipt_v2.source_repositories",
        errors,
    )
    if repos is not None:
        for name, commit in repos.items():
            _commit(commit, f"generation_receipt_v2.source_repositories.{name}", errors)
        if generator is not None and repos.get("partizan") != generator.get("code_commit"):
            errors.append(
                "generation_receipt_v2.source_repositories.partizan: generator mismatch"
            )
        if projection is not None and repos.get("partizan") != projection.get(
            "implementation_commit"
        ):
            errors.append(
                "generation_receipt_v2.source_repositories.partizan: projection mismatch"
            )
        if catalog is not None and repos.get("astralbase") != catalog.get(
            "source_boundary", {}
        ).get("astralbase_commit"):
            errors.append(
                "generation_receipt_v2.source_repositories.astralbase: catalog mismatch"
            )
    if isinstance(receipt_id, str) and receipt_id != generation_receipt_id_for(row):
        errors.append(
            "generation_receipt_v2.receipt_id: does not match canonical identity"
        )
    return errors


def build_generation_receipt_v2(
    *,
    target_path: str,
    target_spec: dict[str, Any],
    board_stream_path: str,
    board_rows: list[dict[str, Any]],
    construction_catalog_path: str,
    construction_catalog: dict[str, Any],
    construction_catalog_sha256: str,
    construction_certificates_path: str,
    construction_certificates: list[dict[str, Any]],
    candidate_artifact_path: str,
    proposals: list[dict[str, Any]],
    board_stream_process_sha256: list[str],
    construction_certificate_process_sha256: list[str],
    projection_process_sha256: list[str],
    source_repositories: dict[str, str],
) -> dict[str, Any]:
    """Build a v0.2 lineage receipt from already-materialized artifacts."""

    if not board_rows or not proposals or not construction_certificates:
        raise ValueError("Wave 69-R receipt artifacts must be non-empty")
    if not (
        len(board_rows) == len(proposals) == len(construction_certificates)
    ):
        raise ValueError("Wave 69-R receipt artifact row counts must match")
    generator = dict(board_rows[0]["generator"])
    board_bytes = canonical_jsonl_bytes(board_rows)
    certificate_bytes = canonical_jsonl_bytes(construction_certificates)
    proposal_bytes = canonical_jsonl_bytes(proposals)
    expected_process_hashes = (
        (board_stream_process_sha256, sha256_hex(board_bytes), "board stream"),
        (
            construction_certificate_process_sha256,
            sha256_hex(certificate_bytes),
            "construction certificates",
        ),
        (projection_process_sha256, sha256_hex(proposal_bytes), "projection"),
    )
    for hashes, expected, name in expected_process_hashes:
        if hashes != [expected, expected]:
            raise ValueError(f"{name} requires two identical process hashes")
    template_ids = [
        [item["left"]["template_id"], item["right"]["template_id"]]
        for item in construction_certificates
    ]
    receipt: dict[str, Any] = {
        "schema_version": GENERATION_RECEIPT_SCHEMA_VERSION_V2,
        "receipt_id": "receipt-sha256:" + "0" * 64,
        "target_ref": {
            "path": target_path,
            "schema_version": TARGET_SCHEMA_VERSION,
            "target_id": target_spec["target_id"],
            "sha256": sha256_hex(canonical_json_bytes(target_spec)),
        },
        "board_stream": {
            "path": board_stream_path,
            "schema_version": BOARD_STREAM_SCHEMA_VERSION,
            "row_count": len(board_rows),
            "sha256": sha256_hex(board_bytes),
        },
        "construction_catalog": {
            "path": construction_catalog_path,
            "schema_version": construction_catalog["schema_version"],
            "catalog_id": construction_catalog["catalog_id"],
            "sha256": construction_catalog_sha256,
            "construction_contract": construction_catalog[
                "construction_contract"
            ],
        },
        "construction_certificates": {
            "path": construction_certificates_path,
            "schema_version": CONSTRUCTION_CERTIFICATE_SCHEMA_VERSION,
            "row_count": len(construction_certificates),
            "sha256": sha256_hex(certificate_bytes),
            "template_ids_sha256": sha256_hex(canonical_json_bytes(template_ids)),
        },
        "projection": {
            "contract_id": BOARD_TO_PROPOSAL_PROJECTION_CONTRACT_V1,
            "implementation_commit": source_repositories["partizan"],
            "target_fields_consumed": [
                "/domain",
                "/search_limits/max_pool_size",
                "/target_id",
            ],
            "mapping": dict(BOARD_TO_PROPOSAL_MAPPING_V1),
        },
        "generator": generator,
        "candidate_artifact": {
            "path": candidate_artifact_path,
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "row_count": len(proposals),
            "sha256": sha256_hex(proposal_bytes),
        },
        "executions": {
            "mode": "separate_python_processes_v1",
            "run_count": 2,
            "board_stream_raw_sha256": list(board_stream_process_sha256),
            "construction_certificate_sha256": list(
                construction_certificate_process_sha256
            ),
            "projection_artifact_sha256": list(projection_process_sha256),
            "byte_identical": True,
        },
        "source_repositories": dict(source_repositories),
    }
    receipt["receipt_id"] = generation_receipt_id_for(receipt)
    return receipt


def build_candidate_pool_manifest_v3(
    *, generation_receipt: dict[str, Any], generation_receipt_path: str
) -> dict[str, Any]:
    """Build the v0.3 pool projection from a validated v0.2 receipt."""

    receipt_bytes = canonical_json_bytes(generation_receipt)
    target_ref = generation_receipt["target_ref"]
    manifest: dict[str, Any] = {
        "schema_version": POOL_SCHEMA_VERSION_V3,
        "pool_id": "pool-sha256:" + "0" * 64,
        "target_ref": {
            key: target_ref[key] for key in ("path", "target_id", "sha256")
        },
        "candidate_artifact": dict(generation_receipt["candidate_artifact"]),
        "generator": dict(generation_receipt["generator"]),
        "source_repositories": dict(generation_receipt["source_repositories"]),
        "determinism": {
            "operation": "target_free_generation_then_pure_projection",
            "run_count": 2,
            "byte_identical": True,
            "artifact_sha256": generation_receipt["candidate_artifact"]["sha256"],
            "board_stream_raw_sha256": list(
                generation_receipt["executions"]["board_stream_raw_sha256"]
            ),
            "projection_artifact_sha256": list(
                generation_receipt["executions"]["projection_artifact_sha256"]
            ),
            "generation_receipt_ref": {
                "path": generation_receipt_path,
                "schema_version": generation_receipt["schema_version"],
                "receipt_id": generation_receipt["receipt_id"],
                "sha256": sha256_hex(receipt_bytes),
            },
        },
        "construction_lineage": {
            "board_stream_ref": dict(generation_receipt["board_stream"]),
            "construction_catalog_ref": dict(
                generation_receipt["construction_catalog"]
            ),
            "construction_certificates_ref": dict(
                generation_receipt["construction_certificates"]
            ),
            "projection_contract_id": generation_receipt["projection"][
                "contract_id"
            ],
        },
        "ranker_boundary": {
            "contract_id": "proposal_only_ranker_input_v0.1",
            "generation_phase": "offline_before_any_verifier_call",
            "allowed_target_paths": ["/ranker_view"],
            "allowed_proposal_paths": ["/position", "/proposal_features"],
            "audit_passed": True,
        },
    }
    manifest["pool_id"] = candidate_pool_id_for(manifest)
    return manifest


def _validate_generation_receipt_reference(
    value: Any,
    target_spec: dict[str, Any],
    proposals: list[dict[str, Any]],
    repository_root: Path | None,
    errors: list[str],
) -> dict[str, Any] | None:
    reference = _exact_keys(
        value,
        {"path", "schema_version", "receipt_id", "sha256"},
        "pool.determinism.generation_receipt_ref",
        errors,
    )
    if reference is None:
        return None
    path_value = reference.get("path")
    _relative_path(
        path_value,
        "pool.determinism.generation_receipt_ref.path",
        errors,
    )
    if reference.get("schema_version") != GENERATION_RECEIPT_SCHEMA_VERSION:
        errors.append(
            "pool.determinism.generation_receipt_ref.schema_version: invalid"
        )
    receipt_id = reference.get("receipt_id")
    if not isinstance(receipt_id, str) or not re.fullmatch(
        r"receipt-sha256:[0-9a-f]{64}", receipt_id
    ):
        errors.append(
            "pool.determinism.generation_receipt_ref.receipt_id: invalid "
            "typed identity"
        )
    _hex(
        reference.get("sha256"),
        64,
        "pool.determinism.generation_receipt_ref.sha256",
        errors,
    )
    if repository_root is None:
        errors.append(
            "pool.determinism.generation_receipt_ref: repository_root is "
            "required to validate the receipt"
        )
        return None
    if not isinstance(path_value, str):
        return None

    try:
        root = repository_root.resolve(strict=True)
        receipt_path = (root / Path(*PurePosixPath(path_value).parts)).resolve(
            strict=True
        )
        receipt_path.relative_to(root)
    except (OSError, ValueError) as error:
        errors.append(
            "pool.determinism.generation_receipt_ref.path: cannot resolve "
            f"inside repository_root: {error}"
        )
        return None
    try:
        receipt_bytes = receipt_path.read_bytes()
        decoded = receipt_bytes.decode("utf-8")
        receipt = json.loads(decoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(
            "pool.determinism.generation_receipt_ref.path: cannot load "
            f"receipt: {error}"
        )
        return None
    if not isinstance(receipt, dict):
        errors.append(
            "pool.determinism.generation_receipt_ref.path: receipt must be an object"
        )
        return None
    try:
        canonical_receipt = canonical_json_bytes(receipt)
    except ValueError as error:
        errors.append(
            "pool.determinism.generation_receipt_ref.path: receipt is not "
            f"canonicalizable: {error}"
        )
        return None
    if receipt_bytes != canonical_receipt:
        errors.append(
            "pool.determinism.generation_receipt_ref.path: receipt bytes are "
            "not canonical"
        )
    if reference.get("sha256") != sha256_hex(receipt_bytes):
        errors.append(
            "pool.determinism.generation_receipt_ref.sha256: does not match "
            "receipt bytes"
        )
    if reference.get("receipt_id") != receipt.get("receipt_id"):
        errors.append(
            "pool.determinism.generation_receipt_ref.receipt_id: does not "
            "match receipt"
        )
    if reference.get("schema_version") != receipt.get("schema_version"):
        errors.append(
            "pool.determinism.generation_receipt_ref.schema_version: does not "
            "match receipt"
        )
    errors.extend(validate_generation_receipt(receipt, target_spec, proposals))
    return receipt


def validate_candidate_pool_manifest(
    value: Any,
    target_spec: dict[str, Any],
    proposals: list[dict[str, Any]],
    proposals_path: Path | None = None,
    repository_root: Path | None = None,
) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(value, _POOL_KEYS, "pool", errors)
    if row is None:
        return errors
    schema_version = row.get("schema_version")
    if schema_version not in {POOL_SCHEMA_VERSION, POOL_SCHEMA_VERSION_V2}:
        errors.append(
            "pool.schema_version: must be "
            f"{POOL_SCHEMA_VERSION} or {POOL_SCHEMA_VERSION_V2}"
        )
    _typed_id(row.get("pool_id"), "pool", "pool.pool_id", errors)
    target_ref = _exact_keys(
        row.get("target_ref"), {"target_id", "sha256"}, "pool.target_ref", errors
    )
    if target_ref is not None:
        if target_ref.get("target_id") != target_spec.get("target_id"):
            errors.append("pool.target_ref.target_id: does not match target")
        if target_ref.get("sha256") != sha256_hex(canonical_json_bytes(target_spec)):
            errors.append("pool.target_ref.sha256: does not match target bytes")

    artifact = _exact_keys(
        row.get("candidate_artifact"),
        {"path", "schema_version", "sha256", "row_count"},
        "pool.candidate_artifact",
        errors,
    )
    if artifact is not None:
        _relative_path(artifact.get("path"), "pool.candidate_artifact.path", errors)
        if artifact.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            errors.append("pool.candidate_artifact.schema_version: invalid")
        if artifact.get("row_count") != len(proposals):
            errors.append("pool.candidate_artifact.row_count: does not match proposals")
        expected_bytes = canonical_jsonl_bytes(proposals)
        if artifact.get("sha256") != sha256_hex(expected_bytes):
            errors.append("pool.candidate_artifact.sha256: does not match proposals")
        if proposals_path is not None and proposals_path.read_bytes() != expected_bytes:
            errors.append("pool.candidate_artifact: proposal file is not canonically serialized")

    generator = _exact_keys(
        row.get("generator"),
        {"name", "version", "config_sha256", "random_seed"},
        "pool.generator",
        errors,
    )
    if generator is not None:
        _nonempty_string(generator.get("name"), "pool.generator.name", errors)
        _nonempty_string(generator.get("version"), "pool.generator.version", errors)
        _hex(generator.get("config_sha256"), 64, "pool.generator.config_sha256", errors)
        if not isinstance(generator.get("random_seed"), int) or isinstance(generator.get("random_seed"), bool):
            errors.append("pool.generator.random_seed: must be an integer")
    repos = _exact_keys(
        row.get("source_repositories"),
        {"astralbase", "bitmesh", "thermograph", "partizan"},
        "pool.source_repositories",
        errors,
    )
    if repos is not None:
        for name, commit in repos.items():
            _commit(commit, f"pool.source_repositories.{name}", errors)
    partizan_generation = (
        generator is not None
        and generator.get("name") == PARTIZAN_POOL_GENERATOR_NAME
    )
    if schema_version == POOL_SCHEMA_VERSION and partizan_generation:
        errors.append(
            "pool.schema_version: Partizan-generated pools require "
            f"{POOL_SCHEMA_VERSION_V2}"
        )
    if schema_version == POOL_SCHEMA_VERSION_V2 and not partizan_generation:
        errors.append(
            "pool.generator.name: v0.2 is reserved for the exact Partizan "
            "candidate-pool generator"
        )
    determinism_keys = {
        "operation",
        "run_count",
        "byte_identical",
        "artifact_sha256",
    }
    if schema_version == POOL_SCHEMA_VERSION_V2:
        determinism_keys.update(
            {
                "raw_artifact_sha256",
                "generation_receipt_ref",
            }
        )
    determinism = _exact_keys(
        row.get("determinism"),
        determinism_keys,
        "pool.determinism",
        errors,
    )
    if determinism is not None:
        expected_operation = (
            "separate_process_generation"
            if schema_version == POOL_SCHEMA_VERSION_V2
            else "canonicalization"
        )
        if determinism.get("operation") != expected_operation:
            errors.append(
                f"pool.determinism.operation: must be {expected_operation}"
            )
        if (
            determinism.get("run_count") != 2
            or determinism.get("byte_identical") is not True
        ):
            errors.append(
                "pool.determinism: requires two byte-identical executions"
            )
        if (
            artifact is not None
            and determinism.get("artifact_sha256") != artifact.get("sha256")
        ):
            errors.append(
                "pool.determinism.artifact_sha256: does not match proposal artifact"
            )
        if schema_version == POOL_SCHEMA_VERSION_V2:
            raw_hashes = determinism.get("raw_artifact_sha256")
            expected_sha = artifact.get("sha256") if artifact is not None else None
            if raw_hashes != [expected_sha, expected_sha]:
                errors.append(
                    "pool.determinism.raw_artifact_sha256: must bind both raw "
                    "generator executions"
                )
            receipt = _validate_generation_receipt_reference(
                determinism.get("generation_receipt_ref"),
                target_spec,
                proposals,
                repository_root,
                errors,
            )
            if receipt is not None and repos is not None:
                receipt_commit = receipt.get("generator", {}).get("code_commit")
                if receipt_commit != repos.get("partizan"):
                    errors.append(
                        "pool.determinism.generation_receipt_ref: generator "
                        "commit does not match source_repositories.partizan"
                    )
    boundary = _exact_keys(
        row.get("ranker_boundary"),
        {"contract_id", "generation_phase", "allowed_target_paths", "allowed_proposal_paths", "audit_passed"},
        "pool.ranker_boundary",
        errors,
    )
    if boundary is not None:
        expected_boundary = {
            "contract_id": "proposal_only_ranker_input_v0.1",
            "generation_phase": "offline_before_any_verifier_call",
            "allowed_target_paths": ["/ranker_view"],
            "allowed_proposal_paths": ["/position", "/proposal_features"],
            "audit_passed": True,
        }
        if boundary != expected_boundary:
            errors.append("pool.ranker_boundary: does not match the proposal-only contract")

    ordinals = [proposal.get("ordinal") for proposal in proposals]
    if ordinals != list(range(len(proposals))):
        errors.append("pool: proposal ordinals must be contiguous and file ordered")
    for field in ("proposal_id", "candidate_key"):
        counts = Counter(str(proposal.get(field)) for proposal in proposals)
        if any(count != 1 for count in counts.values()):
            errors.append(f"pool: duplicate {field} values are forbidden")
    if schema_version == POOL_SCHEMA_VERSION_V2 and generator is not None:
        expected_generator = {
            key: generator.get(key)
            for key in ("name", "version", "config_sha256", "random_seed")
        }
        for index, proposal in enumerate(proposals):
            proposal_generator = proposal.get("generator")
            if not isinstance(proposal_generator, dict):
                continue
            observed_generator = {
                key: proposal_generator.get(key)
                for key in ("name", "version", "config_sha256", "random_seed")
            }
            if observed_generator != expected_generator:
                errors.append(
                    f"pool.proposals[{index}].generator: does not match pool generator"
                )
            if repos is not None and proposal_generator.get("code_commit") != repos.get(
                "partizan"
            ):
                errors.append(
                    f"pool.proposals[{index}].generator.code_commit: does not "
                    "match source_repositories.partizan"
                )
    partizan_orbits: list[str] = []
    for index, proposal in enumerate(proposals):
        generator = proposal.get("generator")
        if not isinstance(generator, dict) or generator.get("name") != PARTIZAN_POOL_GENERATOR_NAME:
            continue
        position = proposal.get("position")
        if not isinstance(position, dict) or not isinstance(position.get("text"), str):
            continue
        try:
            expected_orbit = fen_file_reflection_orbit_sha256(position["text"])
        except ValueError as error:
            errors.append(f"pool.proposals[{index}].position.text: {error}")
            continue
        if position.get("symmetry_sha256") != expected_orbit:
            errors.append(
                f"pool.proposals[{index}].position.symmetry_sha256: does not "
                "match the clock-free file-reflection orbit"
            )
        partizan_orbits.append(expected_orbit)
    orbit_counts = Counter(partizan_orbits)
    if any(count != 1 for count in orbit_counts.values()):
        errors.append(
            "pool: duplicate clock-free file-reflection orbit values are forbidden"
        )
    if isinstance(row.get("pool_id"), str) and row.get("pool_id") != candidate_pool_id_for(row):
        errors.append("pool.pool_id: does not match canonical pool identity")
    return errors


def validate_candidate_pool_manifest_v3(
    value: Any,
    target_spec: dict[str, Any],
    proposals: list[dict[str, Any]],
    repository_root: Path | None,
) -> list[str]:
    """Validate a Wave 69-R pool and all referenced target-free lineage."""

    errors = _validate_json_value(value)
    row = _exact_keys(value, _POOL_V3_KEYS, "pool_v3", errors)
    if row is None:
        return errors
    if row.get("schema_version") != POOL_SCHEMA_VERSION_V3:
        errors.append(f"pool_v3.schema_version: must be {POOL_SCHEMA_VERSION_V3}")
    _typed_id(row.get("pool_id"), "pool", "pool_v3.pool_id", errors)

    target_ref = _exact_keys(
        row.get("target_ref"),
        {"path", "target_id", "sha256"},
        "pool_v3.target_ref",
        errors,
    )
    loaded_target = _load_bound_json_artifact(
        target_ref, repository_root, "pool_v3.target_ref", errors
    )
    if target_ref is not None:
        if target_ref.get("target_id") != target_spec.get("target_id"):
            errors.append("pool_v3.target_ref.target_id: target mismatch")
        if target_ref.get("sha256") != sha256_hex(canonical_json_bytes(target_spec)):
            errors.append("pool_v3.target_ref.sha256: target mismatch")
    if loaded_target is not None and loaded_target != target_spec:
        errors.append("pool_v3.target_ref.path: target payload mismatch")

    candidate_ref = _exact_keys(
        row.get("candidate_artifact"),
        {"path", "schema_version", "sha256", "row_count"},
        "pool_v3.candidate_artifact",
        errors,
    )
    loaded_proposals = _load_bound_jsonl_artifact(
        candidate_ref, repository_root, "pool_v3.candidate_artifact", errors
    )
    candidate_sha = sha256_hex(canonical_jsonl_bytes(proposals))
    if candidate_ref is not None:
        if candidate_ref.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            errors.append("pool_v3.candidate_artifact.schema_version: invalid")
        if candidate_ref.get("row_count") != len(proposals):
            errors.append("pool_v3.candidate_artifact.row_count: proposal mismatch")
        if candidate_ref.get("sha256") != candidate_sha:
            errors.append("pool_v3.candidate_artifact.sha256: proposal mismatch")
    if loaded_proposals is not None and loaded_proposals != proposals:
        errors.append("pool_v3.candidate_artifact.path: proposal payload mismatch")

    generator = _exact_keys(
        row.get("generator"),
        {
            "name",
            "version",
            "code_commit",
            "family",
            "operator",
            "config_sha256",
            "random_seed",
        },
        "pool_v3.generator",
        errors,
    )
    if generator is not None:
        if generator.get("name") != PARTIZAN_POOL_GENERATOR_NAME:
            errors.append("pool_v3.generator.name: invalid")
        _commit(generator.get("code_commit"), "pool_v3.generator.code_commit", errors)
        _hex(generator.get("config_sha256"), 64, "pool_v3.generator.config_sha256", errors)
        seed = generator.get("random_seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            errors.append("pool_v3.generator.random_seed: must be non-negative")
        for key in ("version", "family", "operator"):
            _nonempty_string(generator.get(key), f"pool_v3.generator.{key}", errors)
        for index, proposal in enumerate(proposals):
            if proposal.get("generator") != generator:
                errors.append(
                    f"pool_v3.proposals[{index}].generator: does not match manifest"
                )

    repos = _exact_keys(
        row.get("source_repositories"),
        {"astralbase", "bitmesh", "thermograph", "partizan"},
        "pool_v3.source_repositories",
        errors,
    )
    if repos is not None:
        for name, commit in repos.items():
            _commit(commit, f"pool_v3.source_repositories.{name}", errors)
        if generator is not None and repos.get("partizan") != generator.get(
            "code_commit"
        ):
            errors.append("pool_v3.source_repositories.partizan: generator mismatch")

    determinism = _exact_keys(
        row.get("determinism"),
        {
            "operation",
            "run_count",
            "byte_identical",
            "artifact_sha256",
            "board_stream_raw_sha256",
            "projection_artifact_sha256",
            "generation_receipt_ref",
        },
        "pool_v3.determinism",
        errors,
    )
    receipt: dict[str, Any] | None = None
    if determinism is not None:
        if determinism.get("operation") != "target_free_generation_then_pure_projection":
            errors.append("pool_v3.determinism.operation: invalid")
        if determinism.get("run_count") != 2:
            errors.append("pool_v3.determinism.run_count: must be 2")
        if determinism.get("byte_identical") is not True:
            errors.append("pool_v3.determinism.byte_identical: must be true")
        if determinism.get("artifact_sha256") != candidate_sha:
            errors.append("pool_v3.determinism.artifact_sha256: candidate mismatch")
        receipt_ref = _exact_keys(
            determinism.get("generation_receipt_ref"),
            {"path", "schema_version", "receipt_id", "sha256"},
            "pool_v3.determinism.generation_receipt_ref",
            errors,
        )
        receipt = _load_bound_json_artifact(
            receipt_ref,
            repository_root,
            "pool_v3.determinism.generation_receipt_ref",
            errors,
        )
        if receipt_ref is not None:
            if receipt_ref.get("schema_version") != GENERATION_RECEIPT_SCHEMA_VERSION_V2:
                errors.append(
                    "pool_v3.determinism.generation_receipt_ref.schema_version: invalid"
                )
            receipt_id = receipt_ref.get("receipt_id")
            if not isinstance(receipt_id, str) or not re.fullmatch(
                r"receipt-sha256:[0-9a-f]{64}", receipt_id
            ):
                errors.append(
                    "pool_v3.determinism.generation_receipt_ref.receipt_id: invalid"
                )
        if receipt is not None:
            if receipt_ref is not None:
                if receipt_ref.get("receipt_id") != receipt.get("receipt_id"):
                    errors.append(
                        "pool_v3.determinism.generation_receipt_ref.receipt_id: "
                        "receipt mismatch"
                    )
                if receipt_ref.get("schema_version") != receipt.get("schema_version"):
                    errors.append(
                        "pool_v3.determinism.generation_receipt_ref.schema_version: "
                        "receipt mismatch"
                    )
            errors.extend(
                validate_generation_receipt_v2(
                    receipt, target_spec, proposals, repository_root
                )
            )
            if determinism.get("board_stream_raw_sha256") != receipt.get(
                "executions", {}
            ).get("board_stream_raw_sha256"):
                errors.append(
                    "pool_v3.determinism.board_stream_raw_sha256: receipt mismatch"
                )
            if determinism.get("projection_artifact_sha256") != receipt.get(
                "executions", {}
            ).get("projection_artifact_sha256"):
                errors.append(
                    "pool_v3.determinism.projection_artifact_sha256: receipt mismatch"
                )

    lineage = _exact_keys(
        row.get("construction_lineage"),
        {
            "board_stream_ref",
            "construction_catalog_ref",
            "construction_certificates_ref",
            "projection_contract_id",
        },
        "pool_v3.construction_lineage",
        errors,
    )
    if lineage is not None:
        if lineage.get("projection_contract_id") != BOARD_TO_PROPOSAL_PROJECTION_CONTRACT_V1:
            errors.append("pool_v3.construction_lineage.projection_contract_id: invalid")
        if receipt is not None:
            expected_lineage = {
                "board_stream_ref": receipt.get("board_stream"),
                "construction_catalog_ref": receipt.get("construction_catalog"),
                "construction_certificates_ref": receipt.get(
                    "construction_certificates"
                ),
                "projection_contract_id": receipt.get("projection", {}).get(
                    "contract_id"
                ),
            }
            if lineage != expected_lineage:
                errors.append(
                    "pool_v3.construction_lineage: does not match generation receipt"
                )

    boundary = _exact_keys(
        row.get("ranker_boundary"),
        {
            "contract_id",
            "generation_phase",
            "allowed_target_paths",
            "allowed_proposal_paths",
            "audit_passed",
        },
        "pool_v3.ranker_boundary",
        errors,
    )
    expected_boundary = {
        "contract_id": "proposal_only_ranker_input_v0.1",
        "generation_phase": "offline_before_any_verifier_call",
        "allowed_target_paths": ["/ranker_view"],
        "allowed_proposal_paths": ["/position", "/proposal_features"],
        "audit_passed": True,
    }
    if boundary is not None and boundary != expected_boundary:
        errors.append("pool_v3.ranker_boundary: invalid")

    ordinals = [proposal.get("ordinal") for proposal in proposals]
    if ordinals != list(range(len(proposals))):
        errors.append("pool_v3: proposal ordinals must be contiguous and ordered")
    for field in ("proposal_id", "candidate_key"):
        counts = Counter(str(proposal.get(field)) for proposal in proposals)
        if any(count != 1 for count in counts.values()):
            errors.append(f"pool_v3: duplicate {field} values are forbidden")
    if receipt is not None:
        if target_ref is not None and target_ref != {
            key: receipt.get("target_ref", {}).get(key)
            for key in ("path", "target_id", "sha256")
        }:
            errors.append("pool_v3.target_ref: does not match generation receipt")
        if candidate_ref is not None and candidate_ref != receipt.get(
            "candidate_artifact"
        ):
            errors.append(
                "pool_v3.candidate_artifact: does not match generation receipt"
            )
        if generator is not None and generator != receipt.get("generator"):
            errors.append("pool_v3.generator: does not match generation receipt")
        if repos is not None and repos != receipt.get("source_repositories"):
            errors.append(
                "pool_v3.source_repositories: does not match generation receipt"
            )
    if isinstance(row.get("pool_id"), str) and row.get("pool_id") != candidate_pool_id_for(row):
        errors.append("pool_v3.pool_id: does not match canonical identity")
    return errors


def validate_discovery_run(
    value: Any,
    target_spec: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(value, _RUN_KEYS, "run", errors)
    if row is None:
        return errors
    if row.get("schema_version") != RUN_SCHEMA_VERSION:
        errors.append(f"run.schema_version: must be {RUN_SCHEMA_VERSION}")
    _typed_id(row.get("run_id"), "run", "run.run_id", errors)
    if row.get("target_id") != target_spec.get("target_id"):
        errors.append("run.target_id: does not match target")
    if row.get("pool_id") != pool.get("pool_id"):
        errors.append("run.pool_id: does not match pool")

    policy = _exact_keys(
        row.get("policy"),
        {"policy_id", "version", "random_seed", "checkpoint_sha256", "candidate_order_sha256"},
        "run.policy",
        errors,
    )
    if policy is not None:
        if policy.get("policy_id") != "input_order_v0":
            errors.append("run.policy.policy_id: Wave 68 supports only input_order_v0")
        _nonempty_string(policy.get("version"), "run.policy.version", errors)
        if policy.get("checkpoint_sha256") is not None:
            errors.append("run.policy.checkpoint_sha256: input_order_v0 cannot use a model")
        if not isinstance(policy.get("random_seed"), int) or isinstance(policy.get("random_seed"), bool):
            errors.append("run.policy.random_seed: must be an integer")
        order = [proposal.get("proposal_id") for proposal in proposals]
        expected_order_digest = sha256_hex(canonical_json_bytes(order))
        if policy.get("candidate_order_sha256") != expected_order_digest:
            errors.append("run.policy.candidate_order_sha256: does not match frozen proposal order")

    budget = _exact_keys(
        row.get("budget"), {"max_verifier_calls", "calls_made"}, "run.budget", errors
    )
    calls = row.get("calls")
    if not isinstance(calls, list):
        errors.append("run.calls: must be an array")
        calls = []
    if budget is not None:
        maximum = budget.get("max_verifier_calls")
        made = budget.get("calls_made")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            errors.append("run.budget.max_verifier_calls: must be positive")
        if made != len(calls):
            errors.append("run.budget.calls_made: does not match calls")
        if isinstance(maximum, int) and len(calls) > maximum:
            errors.append("run.calls: exceeds verifier budget")
        target_max = target_spec.get("search_limits", {}).get("max_verifier_calls")
        if isinstance(maximum, int) and isinstance(target_max, int) and maximum > target_max:
            errors.append("run.budget.max_verifier_calls: exceeds target search limit")

    results_by_id = {result.get("result_id"): result for result in results}
    called_proposals: list[str] = []
    outcomes: list[str] = []
    for index, call in enumerate(calls):
        call_row = _exact_keys(
            call,
            {"call_index", "proposal_id", "candidate_key", "score_float_hex", "result_id"},
            f"run.calls[{index}]",
            errors,
        )
        if call_row is None:
            continue
        if call_row.get("call_index") != index:
            errors.append(f"run.calls[{index}].call_index: must be contiguous")
        if index < len(proposals):
            proposal = proposals[index]
            if call_row.get("proposal_id") != proposal.get("proposal_id"):
                errors.append(f"run.calls[{index}].proposal_id: violates frozen input order")
            if call_row.get("candidate_key") != proposal.get("candidate_key"):
                errors.append(f"run.calls[{index}].candidate_key: does not match proposal")
        if call_row.get("score_float_hex") is not None:
            errors.append(f"run.calls[{index}].score_float_hex: input_order_v0 has no score")
        result = results_by_id.get(call_row.get("result_id"))
        if result is None:
            errors.append(f"run.calls[{index}].result_id: unknown result")
        else:
            if result.get("proposal_id") != call_row.get("proposal_id"):
                errors.append(f"run.calls[{index}].result_id: belongs to another proposal")
            outcomes.append(str(result.get("outcome")))
        called_proposals.append(str(call_row.get("proposal_id")))
    if len(called_proposals) != len(set(called_proposals)):
        errors.append("run.calls: a proposal may be verified only once")

    summary = _exact_keys(
        row.get("summary"),
        {"calls_made", "unique_candidates_verified", "outcome_counts", "unique_certified_targets", "first_target_call_index", "budget_exhausted"},
        "run.summary",
        errors,
    )
    if summary is not None:
        expected_counts = dict(sorted(Counter(outcomes).items()))
        expected_first = next(
            (index for index, outcome in enumerate(outcomes) if outcome == "certified_target"),
            None,
        )
        expected_summary = {
            "calls_made": len(calls),
            "unique_candidates_verified": len({call.get("candidate_key") for call in calls if isinstance(call, dict)}),
            "outcome_counts": expected_counts,
            "unique_certified_targets": len(
                {
                    call.get("candidate_key")
                    for call, outcome in zip(calls, outcomes)
                    if isinstance(call, dict) and outcome == "certified_target"
                }
            ),
            "first_target_call_index": expected_first,
            "budget_exhausted": bool(
                budget is not None
                and isinstance(budget.get("max_verifier_calls"), int)
                and len(calls) == budget.get("max_verifier_calls")
            ),
        }
        if summary != expected_summary:
            errors.append("run.summary: does not match recomputed outcomes")
    if isinstance(row.get("run_id"), str) and row.get("run_id") != discovery_run_id_for(row):
        errors.append("run.run_id: does not match canonical run identity")
    return errors


def build_ranker_input(
    target_spec: dict[str, Any], proposal: dict[str, Any]
) -> dict[str, Any]:
    """Construct the complete and only supported Wave 68 ranker projection."""

    target_errors = validate_target_spec(target_spec)
    proposal_errors = validate_candidate_proposal(proposal, target_spec)
    if target_errors or proposal_errors:
        raise ValueError("; ".join(target_errors + proposal_errors))
    return {
        "schema_version": RANKER_INPUT_SCHEMA_VERSION,
        "target": dict(target_spec["ranker_view"]),
        "candidate": {
            "position": dict(proposal["position"]),
            "proposal_features": json.loads(
                json.dumps(proposal["proposal_features"], sort_keys=True)
            ),
        },
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL rows are forbidden")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def validate_discovery_bundle(
    target_path: Path,
    proposals_path: Path,
    results_path: Path,
    pool_path: Path,
    run_path: Path,
    repository_root: Path | None = None,
) -> list[str]:
    """Validate all five contracts and their cross-artifact references."""

    target = load_json(target_path)
    proposals = load_jsonl(proposals_path)
    results = load_jsonl(results_path)
    pool = load_json(pool_path)
    run = load_json(run_path)
    errors = validate_target_spec(target)
    for index, proposal in enumerate(proposals):
        errors.extend(
            f"proposals[{index}]: {error}"
            for error in validate_candidate_proposal(proposal, target)
        )
    proposals_by_id = {proposal.get("proposal_id"): proposal for proposal in proposals}
    for index, result in enumerate(results):
        proposal = proposals_by_id.get(result.get("proposal_id"))
        if proposal is None:
            errors.append(f"results[{index}]: unknown proposal_id")
            continue
        errors.extend(
            f"results[{index}]: {error}"
            for error in validate_verifier_result(result, target, proposal)
        )
    if len(results) != len(proposals):
        errors.append("bundle: proposal and result counts must match")
    errors.extend(
        validate_candidate_pool_manifest(
            pool,
            target,
            proposals,
            proposals_path,
            repository_root=repository_root,
        )
    )
    errors.extend(validate_discovery_run(run, target, pool, proposals, results))
    return errors
