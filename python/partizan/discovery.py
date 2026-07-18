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
PROPOSAL_SCHEMA_VERSION = "partizan.candidate_proposal.v0.1"
RESULT_SCHEMA_VERSION = "partizan.verifier_result.v0.1"
POOL_SCHEMA_VERSION = "partizan.candidate_pool_manifest.v0.1"
RUN_SCHEMA_VERSION = "partizan.discovery_run.v0.1"
RANKER_INPUT_SCHEMA_VERSION = "partizan.ranker_input.v0.1"

SERIALIZATION = "utf8-json-sort-keys-compact-newline-v1"
TARGET_KIND = "bounded_structural_game_form"
IDENTITY_CONTRACT = "thermograph_structural_tree_v1"
IDENTITY_SCOPE = "structural_tree_identity_only_not_arbitrary_cgt_equivalence"
LEGALITY_CONTRACT = "board_syntax_only"
VALUE_RULE = "component_depth2_local_move_game_v0"

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
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in value:
        errors.append(f"{path}: must be a repository-relative POSIX path without '..'")


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
        if row.get("candidate_key") != candidate_key_for(str(row.get("domain")), position):
            errors.append("proposal.candidate_key: does not match domain and position")

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

    if isinstance(row.get("proposal_id"), str) and row.get("proposal_id") != proposal_id_for(row):
        errors.append("proposal.proposal_id: does not match canonical proposal identity")
    return errors


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


def validate_candidate_pool_manifest(
    value: Any,
    target_spec: dict[str, Any],
    proposals: list[dict[str, Any]],
    proposals_path: Path | None = None,
) -> list[str]:
    errors = _validate_json_value(value)
    row = _exact_keys(value, _POOL_KEYS, "pool", errors)
    if row is None:
        return errors
    if row.get("schema_version") != POOL_SCHEMA_VERSION:
        errors.append(f"pool.schema_version: must be {POOL_SCHEMA_VERSION}")
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
    determinism = _exact_keys(
        row.get("determinism"),
        {"operation", "run_count", "byte_identical", "artifact_sha256"},
        "pool.determinism",
        errors,
    )
    if determinism is not None:
        if determinism.get("operation") != "canonicalization":
            errors.append(
                "pool.determinism.operation: freeze may attest only canonicalization"
            )
        if determinism.get("run_count") != 2 or determinism.get("byte_identical") is not True:
            errors.append(
                "pool.determinism: requires two byte-identical canonicalizations"
            )
        if artifact is not None and determinism.get("artifact_sha256") != artifact.get("sha256"):
            errors.append("pool.determinism.artifact_sha256: does not match proposal artifact")
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
    if isinstance(row.get("pool_id"), str) and row.get("pool_id") != candidate_pool_id_for(row):
        errors.append("pool.pool_id: does not match canonical pool identity")
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
        validate_candidate_pool_manifest(pool, target, proposals, proposals_path)
    )
    errors.extend(validate_discovery_run(run, target, pool, proposals, results))
    return errors
