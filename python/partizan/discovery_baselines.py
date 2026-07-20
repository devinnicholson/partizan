"""Frozen, result-blind Wave 69 baseline orders and ledger-only analysis.

This module intentionally has no verifier entry point.  Policy orders are a
pure function of a frozen proposal artifact, and reports are a pure join of
those orders to one complete verifier-result ledger.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable


_DISCOVERY_SPEC = importlib.util.spec_from_file_location(
    "partizan_discovery_contract_for_baselines",
    Path(__file__).with_name("discovery.py"),
)
if _DISCOVERY_SPEC is None or _DISCOVERY_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("could not load the Partizan discovery contract")
discovery = importlib.util.module_from_spec(_DISCOVERY_SPEC)
_DISCOVERY_SPEC.loader.exec_module(discovery)


POLICY_ORDERS_SCHEMA_VERSION = "partizan.policy_orders.v0.1"
BASELINE_REPORT_SCHEMA_VERSION = "partizan.baseline_report.v0.1"
BASELINE_SUITE_REPORT_SCHEMA_VERSION = "partizan.baseline_suite_report.v0.1"
BASELINE_SUITE_INPUT_SCHEMA_VERSION = "partizan.baseline_suite_input.v0.1"
PRE_VERIFICATION_SUITE_SCHEMA_VERSION = "partizan.wave69_stage_suite.v0.1"
RANDOM_POLICY_VERSION = "partizan.random_permutation.v1"
HEURISTIC_POLICY_VERSION = "partizan.fixed_structural_heuristic.v1"
GENERATOR_ORDINAL_AUDIT_VERSION = "partizan.generator_ordinal_audit.v1"
RANDOM_REPLICATE_COUNT = 1_000
METRIC_BUDGETS = (64, 256, 1_024)
NAUDC_BUDGET = 1_024
RATE_KEYS = ("verified_match", "verified_nonmatch", "rejection", "internal_error")
OUTCOME_TO_RATE_KEY = {
    "certified_target": "verified_match",
    "certified_other": "verified_nonmatch",
    "rejected": "rejection",
    "error": "internal_error",
}

SEED_DERIVATION = (
    'first_u64_be_sha256("partizan/w69/random/v1\\0" || pool_id || "\\0" || '
    "ascii_decimal_replicate)"
)
PERMUTATION_ALGORITHM = "splitmix64_rejection_fisher_yates_v1"
HEURISTIC_FORMULA = (
    "1000*has_locked_d_file_backbone + 25*occupied_file_count + "
    "10*non_pawn_piece_count - 5*abs(white_piece_count-black_piece_count) "
    "- piece_count"
)
HEURISTIC_FEATURES = (
    "has_locked_d_file_backbone",
    "occupied_file_count",
    "non_pawn_piece_count",
    "white_piece_count",
    "black_piece_count",
    "piece_count",
)
TIE_BREAK = "candidate_key_ascending"
NAUDC_METHOD = "right_endpoint_rectangles_calls_1_through_1024_v1"
PERCENTILE_METHOD = "nearest_rank_ceiling_v1"
TARGET_BOOTSTRAP_REPLICATES = 10_000

_MASK64 = (1 << 64) - 1
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_TYPED_SHA_RE = re.compile(
    r"^(target|pool|proposal|candidate|result|policy-order|policy-orders|baseline-report|baseline-suite-report|baseline-suite-input)-sha256:[0-9a-f]{64}$"
)


class BaselineContractError(ValueError):
    """Raised when a frozen baseline input or output violates its contract."""


def _fail(errors: list[str]) -> None:
    if errors:
        raise BaselineContractError("; ".join(errors))


def _exact_keys(value: Any, expected: set[str], path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object")
        return
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{path}: fields mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _typed_sha(value: Any, prefix: str, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _TYPED_SHA_RE.fullmatch(value):
        errors.append(f"{path}: must be a typed SHA-256 identifier")
    elif not value.startswith(prefix + "-sha256:"):
        errors.append(f"{path}: must use the {prefix}-sha256 prefix")


def _hex64(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        errors.append(f"{path}: must be 64 lowercase hexadecimal characters")


def _identity(prefix: str, payload: Any) -> str:
    return f"{prefix}-sha256:{discovery.sha256_hex(discovery.canonical_json_bytes(payload))}"


def _without(value: dict[str, Any], key: str) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != key}


def policy_order_id_for(value: dict[str, Any]) -> str:
    return _identity("policy-order", _without(value, "order_id"))


def policy_orders_id_for(value: dict[str, Any]) -> str:
    return _identity("policy-orders", _without(value, "policy_orders_id"))


def baseline_report_id_for(value: dict[str, Any]) -> str:
    return _identity("baseline-report", _without(value, "report_id"))


def baseline_suite_report_id_for(value: dict[str, Any]) -> str:
    return _identity("baseline-suite-report", _without(value, "suite_report_id"))


def baseline_suite_input_id_for(value: dict[str, Any]) -> str:
    return _identity("baseline-suite-input", _without(value, "suite_input_id"))


def _first_u64_be_sha256(payload: bytes) -> int:
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def random_seed_for(pool_id: str, replicate: int) -> int:
    if not isinstance(replicate, int) or isinstance(replicate, bool) or replicate < 0:
        raise BaselineContractError("replicate must be a non-negative integer")
    payload = (
        b"partizan/w69/random/v1\0"
        + pool_id.encode("ascii")
        + b"\0"
        + str(replicate).encode("ascii")
    )
    return _first_u64_be_sha256(payload)


class _SplitMix64:
    """Fully specified 64-bit generator; independent of Python RNG versions."""

    def __init__(self, seed: int) -> None:
        self.state = seed & _MASK64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
        return (value ^ (value >> 31)) & _MASK64

    def randbelow(self, bound: int) -> int:
        if bound <= 0 or bound > 1 << 64:
            raise BaselineContractError("random bound must be in [1, 2**64]")
        limit = (1 << 64) - ((1 << 64) % bound)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % bound


def stable_random_permutation(values: Iterable[str], seed: int) -> list[str]:
    ordered = list(values)
    rng = _SplitMix64(seed)
    for index in range(len(ordered) - 1, 0, -1):
        swap_index = rng.randbelow(index + 1)
        ordered[index], ordered[swap_index] = ordered[swap_index], ordered[index]
    return ordered


def _integer_feature(proposal: dict[str, Any], name: str) -> int:
    value = proposal.get("proposal_features", {}).get("integer", {}).get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BaselineContractError(f"proposal {proposal.get('proposal_id')} lacks integer feature {name}")
    return value


def _boolean_feature(proposal: dict[str, Any], name: str) -> bool:
    value = proposal.get("proposal_features", {}).get("boolean", {}).get(name)
    if not isinstance(value, bool):
        raise BaselineContractError(f"proposal {proposal.get('proposal_id')} lacks boolean feature {name}")
    return value


def heuristic_score(proposal: dict[str, Any]) -> int:
    locked = int(_boolean_feature(proposal, "has_locked_d_file_backbone"))
    occupied = _integer_feature(proposal, "occupied_file_count")
    non_pawns = _integer_feature(proposal, "non_pawn_piece_count")
    white = _integer_feature(proposal, "white_piece_count")
    black = _integer_feature(proposal, "black_piece_count")
    pieces = _integer_feature(proposal, "piece_count")
    return 1_000 * locked + 25 * occupied + 10 * non_pawns - 5 * abs(white - black) - pieces


def heuristic_order(proposals: list[dict[str, Any]]) -> list[str]:
    scored = [
        (heuristic_score(proposal), proposal["candidate_key"], proposal["proposal_id"])
        for proposal in proposals
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [proposal_id for _, _, proposal_id in scored]


def _order_commitment(
    *, target_id: str, pool_id: str, policy: str, replicate: int | None,
    seed: int | None, ordered_ids: list[str]
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "order_id": "policy-order-sha256:" + "0" * 64,
        "policy": policy,
        "replicate": replicate,
        "seed": seed,
        "ordered_proposal_ids_sha256": discovery.sha256_hex(
            discovery.canonical_json_bytes(ordered_ids)
        ),
        "proposal_count": len(ordered_ids),
        "target_id": target_id,
        "pool_id": pool_id,
    }
    row["order_id"] = policy_order_id_for(row)
    return row


def _proposal_ids(proposals: list[dict[str, Any]]) -> list[str]:
    ids = [proposal.get("proposal_id") for proposal in proposals]
    if not all(isinstance(item, str) for item in ids):
        raise BaselineContractError("every proposal must have a proposal_id")
    if len(ids) != len(set(ids)):
        raise BaselineContractError("proposal IDs must be unique")
    candidate_keys = [proposal.get("candidate_key") for proposal in proposals]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise BaselineContractError("candidate keys must be unique")
    return ids  # type: ignore[return-value]


def build_policy_orders(
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    proposals_path: Path,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Build all order commitments without accepting or reading result data."""

    _fail(
        _pool_validation_errors(
            target,
            pool,
            proposals,
            proposals_path=proposals_path,
            repository_root=repository_root,
        )
    )
    proposal_ids = _proposal_ids(proposals)
    target_id = target.get("target_id")
    pool_id = pool.get("pool_id")
    if pool.get("target_ref", {}).get("target_id") != target_id:
        raise BaselineContractError("pool target does not match the target spec")
    proposal_bytes = discovery.canonical_jsonl_bytes(proposals)
    proposal_sha = discovery.sha256_hex(proposal_bytes)
    if pool.get("candidate_artifact", {}).get("sha256") != proposal_sha:
        raise BaselineContractError("pool does not bind the canonical proposal bytes")
    if pool.get("candidate_artifact", {}).get("row_count") != len(proposals):
        raise BaselineContractError("pool proposal row count is inconsistent")

    random_orders = []
    for replicate in range(RANDOM_REPLICATE_COUNT):
        seed = random_seed_for(str(pool_id), replicate)
        ordered = stable_random_permutation(proposal_ids, seed)
        random_orders.append(
            _order_commitment(
                target_id=str(target_id), pool_id=str(pool_id),
                policy="random", replicate=replicate, seed=seed,
                ordered_ids=ordered,
            )
        )
    heuristic_ids = heuristic_order(proposals)
    heuristic_commitment = _order_commitment(
        target_id=str(target_id), pool_id=str(pool_id), policy="fixed_heuristic",
        replicate=None, seed=None, ordered_ids=heuristic_ids,
    )
    artifact: dict[str, Any] = {
        "schema_version": POLICY_ORDERS_SCHEMA_VERSION,
        "policy_orders_id": "policy-orders-sha256:" + "0" * 64,
        "target_id": target_id,
        "pool_id": pool_id,
        "proposal_artifact": {
            "schema_version": discovery.PROPOSAL_SCHEMA_VERSION,
            "sha256": proposal_sha,
            "row_count": len(proposals),
        },
        "freeze_boundary": "before_any_verifier_result",
        "order_serialization": discovery.SERIALIZATION,
        "random_policy": {
            "version": RANDOM_POLICY_VERSION,
            "replicate_count": RANDOM_REPLICATE_COUNT,
            "seed_derivation": SEED_DERIVATION,
            "permutation_algorithm": PERMUTATION_ALGORITHM,
            "orders": random_orders,
        },
        "heuristic_policy": {
            "version": HEURISTIC_POLICY_VERSION,
            "formula": HEURISTIC_FORMULA,
            "features": list(HEURISTIC_FEATURES),
            "sort_direction": "score_descending",
            "tie_break": TIE_BREAK,
            "order": heuristic_commitment,
        },
        "generator_ordinal_audit": {
            "version": GENERATOR_ORDINAL_AUDIT_VERSION,
            "competitive_baseline": False,
            "order": _order_commitment(
                target_id=str(target_id),
                pool_id=str(pool_id),
                policy="generator_ordinal_audit",
                replicate=None,
                seed=None,
                ordered_ids=proposal_ids,
            ),
        },
    }
    artifact["policy_orders_id"] = policy_orders_id_for(artifact)
    _fail(
        validate_policy_orders(
            artifact,
            target,
            pool,
            proposals,
            proposals_path=proposals_path,
            repository_root=repository_root,
        )
    )
    return artifact


def _validate_commitment_shape(value: Any, path: str, errors: list[str]) -> None:
    expected = {
        "order_id", "policy", "replicate", "seed",
        "ordered_proposal_ids_sha256", "proposal_count", "target_id", "pool_id",
    }
    _exact_keys(value, expected, path, errors)
    if not isinstance(value, dict):
        return
    _typed_sha(value.get("order_id"), "policy-order", f"{path}.order_id", errors)
    _hex64(value.get("ordered_proposal_ids_sha256"), f"{path}.ordered_proposal_ids_sha256", errors)
    if value.get("order_id") != policy_order_id_for(value):
        errors.append(f"{path}.order_id: canonical identity mismatch")


def validate_policy_orders(
    artifact: Any,
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    proposals_path: Path,
    repository_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    pool_errors = _pool_validation_errors(
        target,
        pool,
        proposals,
        proposals_path=proposals_path,
        repository_root=repository_root,
    )
    if pool_errors:
        return pool_errors
    errors.extend(discovery._validate_json_value(artifact))
    _exact_keys(
        artifact,
        {"schema_version", "policy_orders_id", "target_id", "pool_id", "proposal_artifact", "freeze_boundary", "order_serialization", "random_policy", "heuristic_policy", "generator_ordinal_audit"},
        "policy_orders",
        errors,
    )
    if not isinstance(artifact, dict):
        return errors
    if artifact.get("schema_version") != POLICY_ORDERS_SCHEMA_VERSION:
        errors.append("policy_orders.schema_version: invalid")
    _typed_sha(artifact.get("policy_orders_id"), "policy-orders", "policy_orders.policy_orders_id", errors)
    if artifact.get("target_id") != target.get("target_id"):
        errors.append("policy_orders.target_id: does not match target")
    if artifact.get("pool_id") != pool.get("pool_id"):
        errors.append("policy_orders.pool_id: does not match pool")
    if artifact.get("freeze_boundary") != "before_any_verifier_result":
        errors.append("policy_orders.freeze_boundary: must precede results")
    if artifact.get("order_serialization") != discovery.SERIALIZATION:
        errors.append("policy_orders.order_serialization: invalid")

    try:
        proposal_ids = _proposal_ids(proposals)
        proposal_sha = discovery.sha256_hex(discovery.canonical_jsonl_bytes(proposals))
    except (BaselineContractError, ValueError) as error:
        errors.append(f"proposals: {error}")
        return errors
    proposal_artifact = artifact.get("proposal_artifact")
    _exact_keys(proposal_artifact, {"schema_version", "sha256", "row_count"}, "policy_orders.proposal_artifact", errors)
    if isinstance(proposal_artifact, dict):
        if proposal_artifact.get("schema_version") != discovery.PROPOSAL_SCHEMA_VERSION:
            errors.append("policy_orders.proposal_artifact.schema_version: invalid")
        if proposal_artifact.get("sha256") != proposal_sha:
            errors.append("policy_orders.proposal_artifact.sha256: does not match proposals")
        if proposal_artifact.get("row_count") != len(proposals):
            errors.append("policy_orders.proposal_artifact.row_count: does not match proposals")

    random_policy = artifact.get("random_policy")
    _exact_keys(random_policy, {"version", "replicate_count", "seed_derivation", "permutation_algorithm", "orders"}, "policy_orders.random_policy", errors)
    all_order_ids: list[str] = []
    if isinstance(random_policy, dict):
        expected_metadata = {
            "version": RANDOM_POLICY_VERSION,
            "replicate_count": RANDOM_REPLICATE_COUNT,
            "seed_derivation": SEED_DERIVATION,
            "permutation_algorithm": PERMUTATION_ALGORITHM,
        }
        for key, expected in expected_metadata.items():
            if random_policy.get(key) != expected:
                errors.append(f"policy_orders.random_policy.{key}: invalid")
        orders = random_policy.get("orders")
        if not isinstance(orders, list) or len(orders) != RANDOM_REPLICATE_COUNT:
            errors.append("policy_orders.random_policy.orders: must contain exactly 1000 orders")
        else:
            for replicate, order in enumerate(orders):
                path = f"policy_orders.random_policy.orders[{replicate}]"
                _validate_commitment_shape(order, path, errors)
                if not isinstance(order, dict):
                    continue
                all_order_ids.append(str(order.get("order_id")))
                seed = random_seed_for(str(pool.get("pool_id")), replicate)
                expected_order = stable_random_permutation(proposal_ids, seed)
                expected_sha = discovery.sha256_hex(discovery.canonical_json_bytes(expected_order))
                expected = {
                    "policy": "random", "replicate": replicate, "seed": seed,
                    "proposal_count": len(proposals), "target_id": target.get("target_id"),
                    "pool_id": pool.get("pool_id"), "ordered_proposal_ids_sha256": expected_sha,
                }
                for key, item in expected.items():
                    if order.get(key) != item:
                        errors.append(f"{path}.{key}: does not match frozen random order")

    heuristic_policy = artifact.get("heuristic_policy")
    _exact_keys(heuristic_policy, {"version", "formula", "features", "sort_direction", "tie_break", "order"}, "policy_orders.heuristic_policy", errors)
    if isinstance(heuristic_policy, dict):
        expected_metadata = {
            "version": HEURISTIC_POLICY_VERSION,
            "formula": HEURISTIC_FORMULA,
            "features": list(HEURISTIC_FEATURES),
            "sort_direction": "score_descending",
            "tie_break": TIE_BREAK,
        }
        for key, expected in expected_metadata.items():
            if heuristic_policy.get(key) != expected:
                errors.append(f"policy_orders.heuristic_policy.{key}: invalid")
        order = heuristic_policy.get("order")
        _validate_commitment_shape(order, "policy_orders.heuristic_policy.order", errors)
        if isinstance(order, dict):
            all_order_ids.append(str(order.get("order_id")))
            try:
                expected_ids = heuristic_order(proposals)
            except BaselineContractError as error:
                errors.append(f"policy_orders.heuristic_policy: {error}")
            else:
                expected_sha = discovery.sha256_hex(discovery.canonical_json_bytes(expected_ids))
                expected = {
                    "policy": "fixed_heuristic", "replicate": None, "seed": None,
                    "proposal_count": len(proposals), "target_id": target.get("target_id"),
                    "pool_id": pool.get("pool_id"), "ordered_proposal_ids_sha256": expected_sha,
                }
                for key, item in expected.items():
                    if order.get(key) != item:
                        errors.append(f"policy_orders.heuristic_policy.order.{key}: does not match frozen heuristic order")
    audit_policy = artifact.get("generator_ordinal_audit")
    _exact_keys(
        audit_policy,
        {"version", "competitive_baseline", "order"},
        "policy_orders.generator_ordinal_audit",
        errors,
    )
    if isinstance(audit_policy, dict):
        if audit_policy.get("version") != GENERATOR_ORDINAL_AUDIT_VERSION:
            errors.append("policy_orders.generator_ordinal_audit.version: invalid")
        if audit_policy.get("competitive_baseline") is not False:
            errors.append(
                "policy_orders.generator_ordinal_audit.competitive_baseline: must be false"
            )
        order = audit_policy.get("order")
        _validate_commitment_shape(
            order, "policy_orders.generator_ordinal_audit.order", errors
        )
        if isinstance(order, dict):
            all_order_ids.append(str(order.get("order_id")))
            expected_sha = discovery.sha256_hex(
                discovery.canonical_json_bytes(proposal_ids)
            )
            expected = {
                "policy": "generator_ordinal_audit",
                "replicate": None,
                "seed": None,
                "proposal_count": len(proposals),
                "target_id": target.get("target_id"),
                "pool_id": pool.get("pool_id"),
                "ordered_proposal_ids_sha256": expected_sha,
            }
            for key, item in expected.items():
                if order.get(key) != item:
                    errors.append(
                        "policy_orders.generator_ordinal_audit.order."
                        f"{key}: does not match generator ordinal order"
                    )
    if len(all_order_ids) != len(set(all_order_ids)):
        errors.append("policy_orders: duplicate order IDs are forbidden")
    if artifact.get("policy_orders_id") != policy_orders_id_for(artifact):
        errors.append("policy_orders.policy_orders_id: canonical identity mismatch")
    return errors


def _pool_validation_errors(
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    proposals_path: Path,
    repository_root: Path | None,
) -> list[str]:
    """Persistently validate proposal bytes and any v0.2 receipt sidecar."""

    root = Path.cwd() if repository_root is None else repository_root
    try:
        resolved_root = root.resolve(strict=True)
        resolved_proposals = proposals_path.resolve(strict=True)
        resolved_proposals.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        return [
            "pool: proposals_path must resolve inside repository_root: "
            f"{error}"
        ]
    try:
        return discovery.validate_candidate_pool_manifest(
            pool,
            target,
            proposals,
            resolved_proposals,
            repository_root=resolved_root,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return [f"pool: persistent artifact validation failed: {error}"]


def _ratio(numerator: int, denominator: int) -> dict[str, int]:
    return {"numerator": numerator, "denominator": denominator}


def _is_success(result: dict[str, Any], target: dict[str, Any]) -> bool:
    response = result.get("verifier_io", {}).get("response", {})
    actual = response.get("actual") if isinstance(response, dict) else None
    return bool(
        result.get("outcome") == "certified_target"
        and result.get("target_comparison", {}).get("matches") is True
        and result.get("target_comparison", {}).get("observed_identity_sha256")
        == target.get("target", {}).get("identity_sha256")
        and response.get("status") == "verified_match"
        and isinstance(actual, dict)
        and actual.get("value_class") == target.get("target", {}).get("value_class")
        and actual.get("digest_v1_sha256") == target.get("target", {}).get("identity_sha256")
    )


def _metrics_for_order(
    ordered_ids: list[str],
    proposals_by_id: dict[str, dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
    target: dict[str, Any],
) -> dict[str, Any]:
    if len(ordered_ids) < NAUDC_BUDGET:
        raise BaselineContractError("baseline analysis requires at least 1024 proposals")
    seen_symmetry: set[str] = set()
    raw_successes = 0
    calls_to_first: int | None = None
    outcome_counts: Counter[str] = Counter()
    budget_metrics: list[dict[str, Any]] = []
    area = 0
    budget_set = set(METRIC_BUDGETS)
    for call_index, proposal_id in enumerate(ordered_ids, start=1):
        proposal = proposals_by_id[proposal_id]
        result = results_by_id[proposal_id]
        outcome = result["outcome"]
        outcome_counts[OUTCOME_TO_RATE_KEY[outcome]] += 1
        if _is_success(result, target):
            raw_successes += 1
            if calls_to_first is None:
                calls_to_first = call_index
            seen_symmetry.add(proposal["position"]["symmetry_sha256"])
        if call_index <= NAUDC_BUDGET:
            area += len(seen_symmetry)
        if call_index in budget_set:
            counts = {name: outcome_counts[name] for name in RATE_KEYS}
            budget_metrics.append(
                {
                    "calls": call_index,
                    "raw_successes": raw_successes,
                    "symmetry_unique_successes": len(seen_symmetry),
                    "discovery_efficiency": _ratio(len(seen_symmetry), call_index),
                    "outcome_counts": counts,
                    "outcome_rates": {
                        name: _ratio(counts[name], call_index) for name in RATE_KEYS
                    },
                }
            )
    full_counts = {name: outcome_counts[name] for name in RATE_KEYS}
    return {
        "budget_metrics": budget_metrics,
        "naudc_through_1024": _ratio(area, NAUDC_BUDGET * NAUDC_BUDGET),
        "naudc_method": NAUDC_METHOD,
        "calls_to_first_success": calls_to_first,
        "full_pool": {
            "calls": len(ordered_ids),
            "raw_successes": raw_successes,
            "symmetry_unique_successes": len(seen_symmetry),
            "outcome_counts": full_counts,
            "outcome_rates": {
                name: _ratio(full_counts[name], len(ordered_ids)) for name in RATE_KEYS
            },
        },
    }


def _exact_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        raise BaselineContractError("cannot summarize an empty metric")
    ordered = sorted(values)
    count = len(ordered)
    if count % 2:
        median = _ratio(ordered[count // 2], 1)
    else:
        median = _ratio(ordered[count // 2 - 1] + ordered[count // 2], 2)
    def nearest_rank(numerator: int, denominator: int) -> int:
        rank = (numerator * count + denominator - 1) // denominator
        return ordered[max(1, rank) - 1]
    return {
        "mean": _ratio(sum(ordered), count),
        "median": median,
        "percentile_025": nearest_rank(25, 1_000),
        "percentile_975": nearest_rank(975, 1_000),
        "percentile_method": PERCENTILE_METHOD,
    }


def _random_summary(replicates: list[dict[str, Any]], proposal_count: int) -> dict[str, Any]:
    by_budget = []
    for budget_index, budget in enumerate(METRIC_BUDGETS):
        rows = [item["metrics"]["budget_metrics"][budget_index] for item in replicates]
        by_budget.append(
            {
                "calls": budget,
                "raw_successes": _exact_summary([row["raw_successes"] for row in rows]),
                "symmetry_unique_successes": _exact_summary([row["symmetry_unique_successes"] for row in rows]),
                "discovery_efficiency_numerator": _exact_summary(
                    [row["discovery_efficiency"]["numerator"] for row in rows]
                ),
                "discovery_efficiency_denominator": budget,
                "outcome_count_summaries": {
                    outcome: _exact_summary([row["outcome_counts"][outcome] for row in rows])
                    for outcome in RATE_KEYS
                },
                "outcome_rate_denominator": budget,
            }
        )
    calls = [
        item["metrics"]["calls_to_first_success"]
        if item["metrics"]["calls_to_first_success"] is not None
        else proposal_count + 1
        for item in replicates
    ]
    return {
        "replicate_count": len(replicates),
        "by_budget": by_budget,
        "naudc_numerator": _exact_summary(
            [item["metrics"]["naudc_through_1024"]["numerator"] for item in replicates]
        ),
        "naudc_denominator": NAUDC_BUDGET * NAUDC_BUDGET,
        "calls_to_first_success": {
            "summary_with_no_success_right_censored": _exact_summary(calls),
            "right_censoring_value": proposal_count + 1,
            "no_success_replicates": sum(
                item["metrics"]["calls_to_first_success"] is None for item in replicates
            ),
        },
    }


def _validated_inputs(
    target: dict[str, Any], pool: dict[str, Any], proposals: list[dict[str, Any]],
    results: list[dict[str, Any]], policy_orders: dict[str, Any],
    *, proposals_path: Path, repository_root: Path | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    errors.extend(f"target: {item}" for item in discovery.validate_target_spec(target))
    for index, proposal in enumerate(proposals):
        errors.extend(
            f"proposal[{index}]: {item}"
            for item in discovery.validate_candidate_proposal(proposal, target)
        )
    errors.extend(
        validate_policy_orders(
            policy_orders,
            target,
            pool,
            proposals,
            proposals_path=proposals_path,
            repository_root=repository_root,
        )
    )
    proposal_ids = _proposal_ids(proposals)
    if len(proposal_ids) < NAUDC_BUDGET:
        errors.append("proposals: at least 1024 rows are required")
    result_proposal_ids = [result.get("proposal_id") for result in results]
    if len(result_proposal_ids) != len(set(result_proposal_ids)):
        errors.append("results: duplicate proposal IDs are forbidden")
    if result_proposal_ids != proposal_ids:
        missing = sorted(set(proposal_ids) - set(result_proposal_ids))
        extra = sorted(set(result_proposal_ids) - set(proposal_ids))
        errors.append(
            "results: ledger must contain exactly one result per proposal in input order; "
            f"missing={missing}, extra={extra}"
        )
    proposals_by_id = {proposal["proposal_id"]: proposal for proposal in proposals}
    results_by_id: dict[str, dict[str, Any]] = {}
    result_ids: list[str] = []
    for index, result in enumerate(results):
        proposal = proposals_by_id.get(result.get("proposal_id"))
        if proposal is None:
            continue
        errors.extend(
            f"result[{index}]: {item}"
            for item in discovery.validate_verifier_result(result, target, proposal)
        )
        if result.get("verifier", {}).get("code_commits") != pool.get(
            "source_repositories"
        ):
            errors.append(
                f"result[{index}].verifier.code_commits: does not match the "
                "frozen pool source repositories"
            )
        result_ids.append(str(result.get("result_id")))
        results_by_id[proposal["proposal_id"]] = result
    if len(result_ids) != len(set(result_ids)):
        errors.append("results: duplicate result IDs are forbidden")
    _fail(errors)
    return proposals_by_id, results_by_id


def analyze_baselines(
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    results: list[dict[str, Any]],
    policy_orders: dict[str, Any],
    *,
    proposals_path: Path,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Analyze one complete ledger.  This function cannot invoke a verifier."""

    proposals_by_id, results_by_id = _validated_inputs(
        target,
        pool,
        proposals,
        results,
        policy_orders,
        proposals_path=proposals_path,
        repository_root=repository_root,
    )
    proposal_ids = [proposal["proposal_id"] for proposal in proposals]
    heuristic_ids = heuristic_order(proposals)
    heuristic_metrics = _metrics_for_order(
        heuristic_ids, proposals_by_id, results_by_id, target
    )
    random_replicates = []
    for order in policy_orders["random_policy"]["orders"]:
        ordered_ids = stable_random_permutation(proposal_ids, order["seed"])
        random_replicates.append(
            {
                "order_id": order["order_id"],
                "replicate": order["replicate"],
                "metrics": _metrics_for_order(
                    ordered_ids, proposals_by_id, results_by_id, target
                ),
            }
        )
    result_bytes = discovery.canonical_jsonl_bytes(results)
    report: dict[str, Any] = {
        "schema_version": BASELINE_REPORT_SCHEMA_VERSION,
        "report_id": "baseline-report-sha256:" + "0" * 64,
        "target_id": target["target_id"],
        "pool_id": pool["pool_id"],
        "input_bindings": {
            "target_sha256": discovery.sha256_hex(discovery.canonical_json_bytes(target)),
            "pool_sha256": discovery.sha256_hex(discovery.canonical_json_bytes(pool)),
            "proposals_sha256": discovery.sha256_hex(discovery.canonical_jsonl_bytes(proposals)),
            "results_sha256": discovery.sha256_hex(result_bytes),
            "result_row_count": len(results),
            "policy_orders_id": policy_orders["policy_orders_id"],
            "policy_orders_sha256": discovery.sha256_hex(discovery.canonical_json_bytes(policy_orders)),
        },
        "join_contract": {
            "mode": "one_complete_frozen_ledger_no_verifier_rerun",
            "every_proposal_consumes_one_call": True,
            "proposal_count": len(proposals),
            "result_count": len(results),
            "result_order_matches_proposal_order": True,
        },
        "metric_contract": {
            "budgets": list(METRIC_BUDGETS),
            "success": "verified_match_with_exact_target_value_class_and_structural_sha256",
            "distinctness": "proposal.position.symmetry_sha256",
            "outcome_rate_keys": list(RATE_KEYS),
            "naudc_method": NAUDC_METHOD,
            "percentile_method": PERCENTILE_METHOD,
        },
        "heuristic": {
            "order_id": policy_orders["heuristic_policy"]["order"]["order_id"],
            "metrics": heuristic_metrics,
        },
        "generator_ordinal_audit": {
            "competitive_baseline": False,
            "order_id": policy_orders["generator_ordinal_audit"]["order"][
                "order_id"
            ],
            "metrics": _metrics_for_order(
                proposal_ids, proposals_by_id, results_by_id, target
            ),
        },
        "random": {
            "replicates": random_replicates,
            "summary": _random_summary(random_replicates, len(proposals)),
        },
    }
    report["report_id"] = baseline_report_id_for(report)
    return report


def validate_baseline_report(
    report: Any,
    target: dict[str, Any],
    pool: dict[str, Any],
    proposals: list[dict[str, Any]],
    results: list[dict[str, Any]],
    policy_orders: dict[str, Any],
    *,
    proposals_path: Path,
    repository_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(discovery._validate_json_value(report))
    if not isinstance(report, dict):
        return errors + ["report: must be an object"]
    _exact_keys(
        report,
        {"schema_version", "report_id", "target_id", "pool_id", "input_bindings", "join_contract", "metric_contract", "heuristic", "generator_ordinal_audit", "random"},
        "report",
        errors,
    )
    if report.get("schema_version") != BASELINE_REPORT_SCHEMA_VERSION:
        errors.append("report.schema_version: invalid")
    _typed_sha(report.get("report_id"), "baseline-report", "report.report_id", errors)
    if report.get("report_id") != baseline_report_id_for(report):
        errors.append("report.report_id: canonical identity mismatch")
    try:
        expected = analyze_baselines(
            target,
            pool,
            proposals,
            results,
            policy_orders,
            proposals_path=proposals_path,
            repository_root=repository_root,
        )
    except (BaselineContractError, ValueError, KeyError, TypeError) as error:
        errors.append(f"report inputs: {error}")
    else:
        if report != expected:
            errors.append("report: does not exactly match ledger-only recomputation")
    return errors


_SUITE_BUNDLE_KEYS = {
    "target_id",
    "pool_id",
    "target_ref",
    "pool_manifest_ref",
    "proposals_ref",
    "policy_orders_ref",
    "verifier_results_ref",
    "baseline_report_ref",
}


def _relative_artifact_path(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{path}: must be a non-empty repo-relative path")
        return
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or parsed.as_posix() != value
        or ".." in parsed.parts
        or "\\" in value
    ):
        errors.append(
            f"{path}: must be normalized repo-relative POSIX without aliases"
        )


def _load_bound_artifact(
    repository_root: Path,
    reference: dict[str, Any],
    *,
    path_label: str,
    jsonl: bool,
) -> tuple[Any, Path]:
    relative = reference["path"]
    try:
        root = repository_root.resolve(strict=True)
        path = (root / Path(*PurePosixPath(relative).parts)).resolve(strict=True)
        path.relative_to(root)
        raw = path.read_bytes()
    except (OSError, ValueError) as error:
        raise BaselineContractError(
            f"{path_label}.path cannot resolve inside repository_root: {error}"
        ) from error
    if discovery.sha256_hex(raw) != reference["sha256"]:
        raise BaselineContractError(f"{path_label}.sha256 does not match file bytes")
    try:
        if jsonl:
            rows = load_jsonl(path)
            canonical = discovery.canonical_jsonl_bytes(rows)
            if reference["row_count"] != len(rows):
                raise BaselineContractError(
                    f"{path_label}.row_count does not match file rows"
                )
            value: Any = rows
        else:
            value = load_json(path)
            canonical = discovery.canonical_json_bytes(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise BaselineContractError(f"{path_label} cannot be loaded: {error}") from error
    if raw != canonical:
        raise BaselineContractError(f"{path_label} bytes are not canonical")
    return value, path


def _suite_reference_shape(
    reference: Any,
    *,
    path: str,
    schema_version: str,
    id_key: str | None,
    id_prefix: str | None,
    row_count: bool,
    errors: list[str],
) -> None:
    expected = {"path", "schema_version", "sha256"}
    if id_key is not None:
        expected.add(id_key)
    if row_count:
        expected.add("row_count")
    _exact_keys(reference, expected, path, errors)
    if not isinstance(reference, dict):
        return
    _relative_artifact_path(reference.get("path"), f"{path}.path", errors)
    if reference.get("schema_version") != schema_version:
        errors.append(f"{path}.schema_version: must be {schema_version}")
    _hex64(reference.get("sha256"), f"{path}.sha256", errors)
    if id_key is not None and id_prefix is not None:
        _typed_sha(reference.get(id_key), id_prefix, f"{path}.{id_key}", errors)
    if row_count:
        count = reference.get("row_count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            errors.append(f"{path}.row_count: must be a positive integer")


def _validate_pre_verification_suite(
    value: Any,
    *,
    expected_stage: str,
    expected_rows: int,
    expected_ref: dict[str, Any],
) -> None:
    errors: list[str] = []
    expected_keys = {
        "schema_version", "suite_id", "stage", "phase", "registry_ref",
        "preregistration_ref", "implementation", "source_repositories",
        "seed_contract", "target_count", "proposal_count_per_target",
        "targets", "freeze_boundary",
    }
    _exact_keys(value, expected_keys, "pre_verification_suite", errors)
    if not isinstance(value, dict):
        _fail(errors)
        return
    if value.get("schema_version") != PRE_VERIFICATION_SUITE_SCHEMA_VERSION:
        errors.append("pre_verification_suite.schema_version: invalid")
    if value.get("stage") != expected_stage:
        errors.append("pre_verification_suite.stage: does not match analysis stage")
    if value.get("phase") != "pre_verification_freeze":
        errors.append("pre_verification_suite.phase: invalid")
    if value.get("target_count") != 6:
        errors.append("pre_verification_suite.target_count: must be 6")
    if value.get("proposal_count_per_target") != expected_rows:
        errors.append(
            "pre_verification_suite.proposal_count_per_target: stage size mismatch"
        )
    freeze = value.get("freeze_boundary")
    expected_freeze = {
        "verifier_calls": 0,
        "results_artifacts_present": False,
        "policy_orders_frozen_before_verification": True,
        "wave70_material_present": False,
    }
    if freeze != expected_freeze:
        errors.append("pre_verification_suite.freeze_boundary: invalid")
    for key, id_key, pattern in (
        ("registry_ref", "registry_id", r"registry-sha256:[0-9a-f]{64}"),
        (
            "preregistration_ref",
            "preregistration_id",
            r"prereg-sha256:[0-9a-f]{64}",
        ),
    ):
        reference = value.get(key)
        _exact_keys(reference, {"path", id_key, "sha256"}, f"pre_verification_suite.{key}", errors)
        if isinstance(reference, dict):
            _relative_artifact_path(
                reference.get("path"), f"pre_verification_suite.{key}.path", errors
            )
            if not isinstance(reference.get(id_key), str) or not re.fullmatch(
                pattern, str(reference.get(id_key))
            ):
                errors.append(f"pre_verification_suite.{key}.{id_key}: invalid")
            _hex64(reference.get("sha256"), f"pre_verification_suite.{key}.sha256", errors)
    implementation = value.get("implementation")
    _exact_keys(
        implementation,
        {"implementation_id", "partizan_commit", "components"},
        "pre_verification_suite.implementation",
        errors,
    )
    if isinstance(implementation, dict):
        if not isinstance(implementation.get("implementation_id"), str) or not re.fullmatch(
            r"implementation-sha256:[0-9a-f]{64}",
            str(implementation.get("implementation_id")),
        ):
            errors.append("pre_verification_suite.implementation.implementation_id: invalid")
        commit = implementation.get("partizan_commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            errors.append("pre_verification_suite.implementation.partizan_commit: invalid")
        components = implementation.get("components")
        if not isinstance(components, list) or len(components) != 3:
            errors.append("pre_verification_suite.implementation.components: requires three entries")
        else:
            for index, component in enumerate(components):
                path = f"pre_verification_suite.implementation.components[{index}]"
                _exact_keys(component, {"path", "sha256"}, path, errors)
                if isinstance(component, dict):
                    _relative_artifact_path(component.get("path"), f"{path}.path", errors)
                    _hex64(component.get("sha256"), f"{path}.sha256", errors)
    repositories = value.get("source_repositories")
    _exact_keys(
        repositories,
        {"astralbase", "bitmesh", "partizan", "thermograph"},
        "pre_verification_suite.source_repositories",
        errors,
    )
    if isinstance(repositories, dict):
        for name, commit in repositories.items():
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                errors.append(
                    f"pre_verification_suite.source_repositories.{name}: invalid commit"
                )
    seed_contract = value.get("seed_contract")
    expected_seed_contract = {
        "algorithm": "sha256_first_u64_big_endian_v1",
        "domain_hex": "70617274697a616e2f7736392f706f6f6c2f763100",
        "stage": expected_stage,
        "target_id_encoding": "utf8",
    }
    if seed_contract != expected_seed_contract:
        errors.append("pre_verification_suite.seed_contract: invalid")
    suite_id = value.get("suite_id")
    expected_id = "suite-sha256:" + discovery.sha256_hex(
        discovery.canonical_json_bytes(_without(value, "suite_id"))
    )
    if suite_id != expected_id or suite_id != expected_ref.get("suite_id"):
        errors.append("pre_verification_suite.suite_id: identity mismatch")
    targets = value.get("targets")
    if not isinstance(targets, list) or len(targets) != 6:
        errors.append("pre_verification_suite.targets: requires six entries")
        targets = []
    target_keys = {
        "target_id", "family", "bin_index", "seed", "target_ref",
        "proposals_ref", "generation_receipt_ref", "pool_manifest_ref",
        "policy_orders_ref",
    }
    for index, target in enumerate(targets):
        path = f"pre_verification_suite.targets[{index}]"
        _exact_keys(target, target_keys, path, errors)
        if not isinstance(target, dict):
            continue
        _typed_sha(target.get("target_id"), "target", f"{path}.target_id", errors)
        if not isinstance(target.get("family"), str) or not target.get("family"):
            errors.append(f"{path}.family: must be non-empty")
        if target.get("bin_index") not in {0, 3}:
            errors.append(f"{path}.bin_index: invalid")
        seed = target.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 1 << 64:
            errors.append(f"{path}.seed: invalid")
        _suite_reference_shape(
            target.get("target_ref"), path=f"{path}.target_ref",
            schema_version=discovery.TARGET_SCHEMA_VERSION,
            id_key="target_id", id_prefix="target", row_count=False,
            errors=errors,
        )
        if isinstance(target.get("target_ref"), dict) and (
            target["target_ref"].get("target_id") != target.get("target_id")
        ):
            errors.append(f"{path}.target_ref.target_id: mismatch")
        if isinstance(target.get("proposals_ref"), dict) and (
            target["proposals_ref"].get("row_count") != expected_rows
        ):
            errors.append(f"{path}.proposals_ref.row_count: stage size mismatch")
        _suite_reference_shape(
            target.get("proposals_ref"), path=f"{path}.proposals_ref",
            schema_version=discovery.PROPOSAL_SCHEMA_VERSION,
            id_key=None, id_prefix=None, row_count=True, errors=errors,
        )
        _suite_reference_shape(
            target.get("pool_manifest_ref"), path=f"{path}.pool_manifest_ref",
            schema_version=discovery.POOL_SCHEMA_VERSION_V2,
            id_key="pool_id", id_prefix="pool", row_count=False,
            errors=errors,
        )
        _suite_reference_shape(
            target.get("policy_orders_ref"), path=f"{path}.policy_orders_ref",
            schema_version=POLICY_ORDERS_SCHEMA_VERSION,
            id_key="policy_orders_id", id_prefix="policy-orders", row_count=False,
            errors=errors,
        )
        receipt = target.get("generation_receipt_ref")
        _suite_reference_shape(
            receipt, path=f"{path}.generation_receipt_ref",
            schema_version=discovery.GENERATION_RECEIPT_SCHEMA_VERSION,
            id_key="receipt_id", id_prefix=None, row_count=False,
            errors=errors,
        )
        if isinstance(receipt, dict):
            receipt_id = receipt.get("receipt_id")
            if not isinstance(receipt_id, str) or not re.fullmatch(
                r"receipt-sha256:[0-9a-f]{64}", receipt_id
            ):
                errors.append(f"{path}.generation_receipt_ref.receipt_id: invalid")
    _fail(errors)
    if targets:
        target_ids = [target.get("target_id") for target in targets]
        if all(isinstance(item, str) for item in target_ids) and (
            len(target_ids) != len(set(target_ids))
        ):
            errors.append("pre_verification_suite.targets: duplicate target IDs")
    _fail(errors)


def _load_validated_suite_bundles(
    suite_input: Any,
    *,
    repository_root: Path | None,
) -> tuple[str, list[dict[str, Any]]]:
    errors: list[str] = []
    errors.extend(discovery._validate_json_value(suite_input))
    _exact_keys(
        suite_input,
        {"schema_version", "suite_input_id", "stage", "pre_verification_suite_ref", "bundle_count", "bundles"},
        "suite_input",
        errors,
    )
    if not isinstance(suite_input, dict):
        _fail(errors)
        raise AssertionError("unreachable")
    if suite_input.get("schema_version") != BASELINE_SUITE_INPUT_SCHEMA_VERSION:
        errors.append("suite_input.schema_version: invalid")
    _typed_sha(
        suite_input.get("suite_input_id"),
        "baseline-suite-input",
        "suite_input.suite_input_id",
        errors,
    )
    stage = suite_input.get("stage")
    if stage not in {"stage_a", "stage_b"}:
        errors.append("suite_input.stage: must be stage_a or stage_b")
    if suite_input.get("bundle_count") != 6:
        errors.append("suite_input.bundle_count: must be 6")
    pre_ref = suite_input.get("pre_verification_suite_ref")
    _suite_reference_shape(
        pre_ref,
        path="suite_input.pre_verification_suite_ref",
        schema_version=PRE_VERIFICATION_SUITE_SCHEMA_VERSION,
        id_key="suite_id",
        id_prefix=None,
        row_count=False,
        errors=errors,
    )
    if isinstance(pre_ref, dict):
        if set(pre_ref) != {"path", "schema_version", "suite_id", "sha256"}:
            errors.append(
                "suite_input.pre_verification_suite_ref: requires suite_id"
            )
        suite_id = pre_ref.get("suite_id")
        if not isinstance(suite_id, str) or not re.fullmatch(
            r"suite-sha256:[0-9a-f]{64}", suite_id
        ):
            errors.append(
                "suite_input.pre_verification_suite_ref.suite_id: invalid"
            )
    bundles = suite_input.get("bundles")
    if not isinstance(bundles, list) or len(bundles) != 6:
        errors.append("suite_input.bundles: must contain exactly six bundles")
        bundles = []
    for index, bundle in enumerate(bundles):
        path = f"suite_input.bundles[{index}]"
        _exact_keys(bundle, _SUITE_BUNDLE_KEYS, path, errors)
        if not isinstance(bundle, dict):
            continue
        _typed_sha(bundle.get("target_id"), "target", f"{path}.target_id", errors)
        _typed_sha(bundle.get("pool_id"), "pool", f"{path}.pool_id", errors)
        _suite_reference_shape(
            bundle.get("target_ref"), path=f"{path}.target_ref",
            schema_version=discovery.TARGET_SCHEMA_VERSION,
            id_key="target_id", id_prefix="target", row_count=False,
            errors=errors,
        )
        _suite_reference_shape(
            bundle.get("pool_manifest_ref"), path=f"{path}.pool_manifest_ref",
            schema_version=discovery.POOL_SCHEMA_VERSION_V2,
            id_key="pool_id", id_prefix="pool", row_count=False,
            errors=errors,
        )
        _suite_reference_shape(
            bundle.get("proposals_ref"), path=f"{path}.proposals_ref",
            schema_version=discovery.PROPOSAL_SCHEMA_VERSION,
            id_key=None, id_prefix=None, row_count=True, errors=errors,
        )
        _suite_reference_shape(
            bundle.get("policy_orders_ref"), path=f"{path}.policy_orders_ref",
            schema_version=POLICY_ORDERS_SCHEMA_VERSION,
            id_key="policy_orders_id", id_prefix="policy-orders", row_count=False,
            errors=errors,
        )
        _suite_reference_shape(
            bundle.get("verifier_results_ref"), path=f"{path}.verifier_results_ref",
            schema_version=discovery.RESULT_SCHEMA_VERSION,
            id_key=None, id_prefix=None, row_count=True, errors=errors,
        )
        _suite_reference_shape(
            bundle.get("baseline_report_ref"), path=f"{path}.baseline_report_ref",
            schema_version=BASELINE_REPORT_SCHEMA_VERSION,
            id_key="report_id", id_prefix="baseline-report", row_count=False,
            errors=errors,
        )
    _fail(errors)
    if bundles:
        target_ids = [bundle.get("target_id") for bundle in bundles]
        pool_ids = [bundle.get("pool_id") for bundle in bundles]
        report_ids = [
            bundle.get("baseline_report_ref", {}).get("report_id")
            if isinstance(bundle, dict) else None
            for bundle in bundles
        ]
        if target_ids != sorted(target_ids):
            errors.append("suite_input.bundles: must be sorted by target_id")
        for name, values in (
            ("target_id", target_ids),
            ("pool_id", pool_ids),
            ("report_id", report_ids),
        ):
            if len(values) != len(set(values)):
                errors.append(f"suite_input.bundles: duplicate {name} values")
        all_paths = [
            bundle[ref]["path"]
            for bundle in bundles
            for ref in (
                "target_ref", "pool_manifest_ref", "proposals_ref",
                "policy_orders_ref", "verifier_results_ref", "baseline_report_ref",
            )
            if isinstance(bundle, dict) and isinstance(bundle.get(ref), dict)
        ]
        if len(all_paths) != len(set(all_paths)):
            errors.append("suite_input.bundles: artifact paths must be unique")
    if isinstance(suite_input.get("suite_input_id"), str) and (
        suite_input.get("suite_input_id") != baseline_suite_input_id_for(suite_input)
    ):
        errors.append("suite_input.suite_input_id: canonical identity mismatch")
    _fail(errors)

    root = Path.cwd() if repository_root is None else repository_root
    expected_rows = 1_024 if stage == "stage_a" else 4_096
    pre_suite, _ = _load_bound_artifact(
        root,
        suite_input["pre_verification_suite_ref"],
        path_label="suite_input.pre_verification_suite_ref",
        jsonl=False,
    )
    _validate_pre_verification_suite(
        pre_suite,
        expected_stage=str(stage),
        expected_rows=expected_rows,
        expected_ref=suite_input["pre_verification_suite_ref"],
    )
    pre_targets = {
        item["target_id"]: item for item in pre_suite["targets"]
    }
    contexts: list[dict[str, Any]] = []
    for index, bundle in enumerate(bundles):
        path = f"suite_input.bundles[{index}]"
        try:
            pre_target = pre_targets.get(bundle["target_id"])
            if pre_target is None:
                raise BaselineContractError(
                    f"{path}.target_id is absent from the pre-verification suite"
                )
            for post_key, pre_key in (
                ("target_ref", "target_ref"),
                ("pool_manifest_ref", "pool_manifest_ref"),
                ("proposals_ref", "proposals_ref"),
                ("policy_orders_ref", "policy_orders_ref"),
            ):
                if bundle[post_key] != pre_target[pre_key]:
                    raise BaselineContractError(
                        f"{path}.{post_key} differs from the frozen pre-verification suite"
                    )
            target, _ = _load_bound_artifact(
                root, bundle["target_ref"], path_label=f"{path}.target_ref", jsonl=False
            )
            pool, _ = _load_bound_artifact(
                root, bundle["pool_manifest_ref"], path_label=f"{path}.pool_manifest_ref", jsonl=False
            )
            proposals, proposals_path = _load_bound_artifact(
                root, bundle["proposals_ref"], path_label=f"{path}.proposals_ref", jsonl=True
            )
            orders, _ = _load_bound_artifact(
                root, bundle["policy_orders_ref"], path_label=f"{path}.policy_orders_ref", jsonl=False
            )
            results, _ = _load_bound_artifact(
                root, bundle["verifier_results_ref"], path_label=f"{path}.verifier_results_ref", jsonl=True
            )
            report, _ = _load_bound_artifact(
                root, bundle["baseline_report_ref"], path_label=f"{path}.baseline_report_ref", jsonl=False
            )
            exposed = {
                "target_id": target.get("target_id"),
                "pool_id": pool.get("pool_id"),
                "policy_orders_id": orders.get("policy_orders_id"),
                "report_id": report.get("report_id"),
            }
            expected_exposed = {
                "target_id": bundle["target_id"],
                "pool_id": bundle["pool_id"],
                "policy_orders_id": bundle["policy_orders_ref"]["policy_orders_id"],
                "report_id": bundle["baseline_report_ref"]["report_id"],
            }
            if exposed != expected_exposed:
                raise BaselineContractError(
                    f"{path}: loaded artifact IDs do not match bundle references"
                )
            if target.get("target_id") != bundle["target_ref"]["target_id"]:
                raise BaselineContractError(f"{path}.target_ref.target_id mismatch")
            if pool.get("pool_id") != bundle["pool_manifest_ref"]["pool_id"]:
                raise BaselineContractError(f"{path}.pool_manifest_ref.pool_id mismatch")
            if pool.get("source_repositories") != pre_suite.get(
                "source_repositories"
            ):
                raise BaselineContractError(
                    f"{path}: pool source repositories differ from pre-verification suite"
                )
            if pool.get("determinism", {}).get(
                "generation_receipt_ref"
            ) != pre_target["generation_receipt_ref"]:
                raise BaselineContractError(
                    f"{path}: pool receipt differs from the pre-verification suite"
                )
            if len(proposals) != expected_rows or len(results) != expected_rows:
                raise BaselineContractError(
                    f"{path}: {stage} requires exactly {expected_rows} proposals and results"
                )
            report_errors = validate_baseline_report(
                report,
                target,
                pool,
                proposals,
                results,
                orders,
                proposals_path=proposals_path,
                repository_root=root,
            )
            if report_errors:
                raise BaselineContractError("; ".join(report_errors))
            contexts.append(
                {
                    "target": target,
                    "pool": pool,
                    "proposals": proposals,
                    "results": results,
                    "policy_orders": orders,
                    "report": report,
                    "proposals_path": proposals_path,
                }
            )
        except (BaselineContractError, KeyError, TypeError, ValueError) as error:
            raise BaselineContractError(f"{path}: {error}") from error
    return str(stage), contexts


def validate_baseline_suite_input(
    suite_input: Any, *, repository_root: Path | None = None
) -> list[str]:
    try:
        _load_validated_suite_bundles(
            suite_input, repository_root=repository_root
        )
    except BaselineContractError as error:
        return [str(error)]
    return []


def build_baseline_suite_input(
    *,
    stage: str,
    pre_verification_suite_ref: dict[str, Any],
    bundles: list[dict[str, Any]],
    repository_root: Path | None = None,
) -> dict[str, Any]:
    ordered = sorted(deepcopy(bundles), key=lambda row: str(row.get("target_id")))
    manifest: dict[str, Any] = {
        "schema_version": BASELINE_SUITE_INPUT_SCHEMA_VERSION,
        "suite_input_id": "baseline-suite-input-sha256:" + "0" * 64,
        "stage": stage,
        "pre_verification_suite_ref": deepcopy(pre_verification_suite_ref),
        "bundle_count": len(ordered),
        "bundles": ordered,
    }
    manifest["suite_input_id"] = baseline_suite_input_id_for(manifest)
    _fail(
        validate_baseline_suite_input(
            manifest, repository_root=repository_root
        )
    )
    return manifest


def _metric_at(report: dict[str, Any], policy: str, budget: int, replicate: int | None = None) -> dict[str, Any]:
    if policy == "heuristic":
        metrics = report["heuristic"]["metrics"]
    else:
        if replicate is None:
            raise BaselineContractError("random macro metric requires a replicate")
        metrics = report["random"]["replicates"][replicate]["metrics"]
    for row in metrics["budget_metrics"]:
        if row["calls"] == budget:
            return row
    raise BaselineContractError(f"report lacks DE@{budget}")


def _bootstrap_seed(report_ids: list[str], stage: str) -> int:
    payload = (
        b"partizan/w69/target-bootstrap/v1\0"
        + stage.encode("ascii")
        + b"\0"
        + b"\0".join(item.encode("ascii") for item in report_ids)
    )
    return _first_u64_be_sha256(payload)


def _aggregate_validated_reports(
    reports: list[dict[str, Any]], *, stage: str, suite_input_id: str
) -> dict[str, Any]:
    """Macro-aggregate six reports only after source-bundle revalidation."""

    if stage not in {"stage_a", "stage_b"}:
        raise BaselineContractError("suite stage must be stage_a or stage_b")
    if len(reports) != 6:
        raise BaselineContractError("a Wave 69 suite report requires exactly six targets")
    reports = sorted(reports, key=lambda report: str(report.get("target_id")))
    report_ids = [report.get("report_id") for report in reports]
    target_ids = [report.get("target_id") for report in reports]
    pool_ids = [report.get("pool_id") for report in reports]
    if not all(isinstance(item, str) for item in report_ids):
        raise BaselineContractError("every target report must have a report_id")
    if len(set(report_ids)) != 6 or len(set(target_ids)) != 6 or len(set(pool_ids)) != 6:
        raise BaselineContractError("suite report, target, and pool IDs must be unique")
    for index, report in enumerate(reports):
        if report.get("schema_version") != BASELINE_REPORT_SCHEMA_VERSION:
            raise BaselineContractError(f"report[{index}] has an unsupported schema")
        if report.get("report_id") != baseline_report_id_for(report):
            raise BaselineContractError(f"report[{index}] has a tampered report hash")
        replicates = report.get("random", {}).get("replicates")
        if not isinstance(replicates, list) or len(replicates) != RANDOM_REPLICATE_COUNT:
            raise BaselineContractError(f"report[{index}] lacks 1000 random replicates")
        if [row.get("replicate") for row in replicates] != list(range(RANDOM_REPLICATE_COUNT)):
            raise BaselineContractError(f"report[{index}] has missing or duplicate replicate IDs")

    macro_budgets = []
    random_macro_by_budget: dict[int, list[int]] = {}
    for budget in METRIC_BUDGETS:
        heuristic_numerator = sum(
            _metric_at(report, "heuristic", budget)["symmetry_unique_successes"]
            for report in reports
        )
        random_numerators = [
            sum(
                _metric_at(report, "random", budget, replicate)[
                    "symmetry_unique_successes"
                ]
                for report in reports
            )
            for replicate in range(RANDOM_REPLICATE_COUNT)
        ]
        random_macro_by_budget[budget] = random_numerators
        macro_budgets.append(
            {
                "calls_per_target": budget,
                "heuristic_macro_de": _ratio(heuristic_numerator, 6 * budget),
                "random_macro_de_numerator_summary": _exact_summary(random_numerators),
                "random_macro_de_denominator": 6 * budget,
            }
        )

    primary_heuristic = sum(
        _metric_at(report, "heuristic", 256)["symmetry_unique_successes"]
        for report in reports
    )
    primary_random = random_macro_by_budget[256]
    random_total = sum(primary_random)
    # Contrast = heuristic/(6*256) - random_total/(1000*6*256).
    contrast_numerator = RANDOM_REPLICATE_COUNT * primary_heuristic - random_total
    contrast_denominator = RANDOM_REPLICATE_COUNT * 6 * 256
    tail_count = sum(value >= primary_heuristic for value in primary_random)

    # Bootstrap the six target-level heuristic-minus-random-mean contrasts.
    per_target_contrast_numerators = []
    for report in reports:
        heuristic = _metric_at(report, "heuristic", 256)["symmetry_unique_successes"]
        random_sum = sum(
            _metric_at(report, "random", 256, replicate)[
                "symmetry_unique_successes"
            ]
            for replicate in range(RANDOM_REPLICATE_COUNT)
        )
        per_target_contrast_numerators.append(
            RANDOM_REPLICATE_COUNT * heuristic - random_sum
        )
    rng = _SplitMix64(_bootstrap_seed(report_ids, stage))
    bootstrap_numerators = []
    for _ in range(TARGET_BOOTSTRAP_REPLICATES):
        bootstrap_numerators.append(
            sum(
                per_target_contrast_numerators[rng.randbelow(6)]
                for _ in range(6)
            )
        )
    ordered_bootstrap = sorted(bootstrap_numerators)
    bootstrap_count = len(ordered_bootstrap)
    lower_rank = (25 * bootstrap_count + 999) // 1_000
    upper_rank = (975 * bootstrap_count + 999) // 1_000
    bootstrap_lower = ordered_bootstrap[lower_rank - 1]
    bootstrap_upper = ordered_bootstrap[upper_rank - 1]

    total_calls = sum(report["join_contract"]["proposal_count"] for report in reports)
    outcome_counts = {
        key: sum(
            report["heuristic"]["metrics"]["full_pool"]["outcome_counts"][key]
            for report in reports
        )
        for key in RATE_KEYS
    }
    raw_successes = sum(
        report["heuristic"]["metrics"]["full_pool"]["raw_successes"]
        for report in reports
    )
    unique_successes = sum(
        report["heuristic"]["metrics"]["full_pool"]["symmetry_unique_successes"]
        for report in reports
    )
    heuristic_naudc_numerator = sum(
        report["heuristic"]["metrics"]["naudc_through_1024"]["numerator"]
        for report in reports
    )
    random_naudc_numerators = [
        sum(
            report["random"]["replicates"][replicate]["metrics"]
            ["naudc_through_1024"]["numerator"]
            for report in reports
        )
        for replicate in range(RANDOM_REPLICATE_COUNT)
    ]
    proposal_counts = [report["join_contract"]["proposal_count"] for report in reports]
    heuristic_first_calls = []
    heuristic_censored = 0
    for report, proposal_count in zip(reports, proposal_counts):
        value = report["heuristic"]["metrics"]["calls_to_first_success"]
        if value is None:
            value = proposal_count + 1
            heuristic_censored += 1
        heuristic_first_calls.append(value)
    random_first_macro_numerators: list[int] = []
    random_first_censor_counts: list[int] = []
    for replicate in range(RANDOM_REPLICATE_COUNT):
        values = []
        censored = 0
        for report, proposal_count in zip(reports, proposal_counts):
            value = report["random"]["replicates"][replicate]["metrics"][
                "calls_to_first_success"
            ]
            if value is None:
                value = proposal_count + 1
                censored += 1
            values.append(value)
        random_first_macro_numerators.append(sum(values))
        random_first_censor_counts.append(censored)
    suite: dict[str, Any] = {
        "schema_version": BASELINE_SUITE_REPORT_SCHEMA_VERSION,
        "suite_report_id": "baseline-suite-report-sha256:" + "0" * 64,
        "suite_input_id": suite_input_id,
        "stage": stage,
        "target_reports": [
            {
                "report_id": report["report_id"],
                "sha256": discovery.sha256_hex(discovery.canonical_json_bytes(report)),
                "target_id": report["target_id"],
                "pool_id": report["pool_id"],
            }
            for report in reports
        ],
        "primary": {
            "metric": "target_macro_symmetry_unique_de_at_256",
            "heuristic": _ratio(primary_heuristic, 6 * 256),
            "random_mean": _ratio(random_total, RANDOM_REPLICATE_COUNT * 6 * 256),
            "heuristic_minus_random_mean": _ratio(contrast_numerator, contrast_denominator),
            "fixed_1000_permutation_upper_tail_proportion": _ratio(
                tail_count, RANDOM_REPLICATE_COUNT
            ),
            "target_bootstrap_95_interval": {
                "lower_numerator": bootstrap_lower,
                "upper_numerator": bootstrap_upper,
                "denominator": RANDOM_REPLICATE_COUNT * 6 * 256,
                "replicates": TARGET_BOOTSTRAP_REPLICATES,
                "seed": _bootstrap_seed(report_ids, stage),
                "method": "six_target_resampling_with_replacement_nearest_rank_v1",
            },
        },
        "macro_by_budget": macro_budgets,
        "macro_secondary": {
            "naudc_through_1024": {
                "heuristic_macro": _ratio(
                    heuristic_naudc_numerator,
                    6 * NAUDC_BUDGET * NAUDC_BUDGET,
                ),
                "random_macro_numerator_summary": _exact_summary(
                    random_naudc_numerators
                ),
                "random_macro_denominator": 6 * NAUDC_BUDGET * NAUDC_BUDGET,
                "method": NAUDC_METHOD,
            },
            "calls_to_first_success": {
                "heuristic_target_summary": _exact_summary(heuristic_first_calls),
                "heuristic_macro_mean": _ratio(sum(heuristic_first_calls), 6),
                "heuristic_right_censored_targets": heuristic_censored,
                "random_macro_numerator_summary": _exact_summary(
                    random_first_macro_numerators
                ),
                "random_macro_denominator": 6,
                "random_right_censored_target_count_summary": _exact_summary(
                    random_first_censor_counts
                ),
                "censoring_rule": "per_target_pool_size_plus_one_v1",
            },
        },
        "full_ledger": {
            "aggregation": "equal_size_target_macro_equivalent_to_pooled_counts",
            "calls": total_calls,
            "raw_successes": raw_successes,
            "symmetry_unique_successes": unique_successes,
            "outcome_counts": outcome_counts,
            "outcome_rates": {
                key: _ratio(outcome_counts[key], total_calls) for key in RATE_KEYS
            },
        },
    }
    suite["suite_report_id"] = baseline_suite_report_id_for(suite)
    return suite


def aggregate_baseline_suite(
    suite_input: dict[str, Any], *, repository_root: Path | None = None
) -> dict[str, Any]:
    stage, contexts = _load_validated_suite_bundles(
        suite_input, repository_root=repository_root
    )
    return _aggregate_validated_reports(
        [context["report"] for context in contexts],
        stage=stage,
        suite_input_id=suite_input["suite_input_id"],
    )


def validate_baseline_suite_report(
    suite: Any,
    suite_input: dict[str, Any],
    *,
    repository_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(discovery._validate_json_value(suite))
    if not isinstance(suite, dict):
        return errors + ["suite: must be an object"]
    _exact_keys(
        suite,
        {"schema_version", "suite_report_id", "suite_input_id", "stage", "target_reports", "primary", "macro_by_budget", "macro_secondary", "full_ledger"},
        "suite",
        errors,
    )
    if suite.get("schema_version") != BASELINE_SUITE_REPORT_SCHEMA_VERSION:
        errors.append("suite.schema_version: invalid")
    _typed_sha(suite.get("suite_report_id"), "baseline-suite-report", "suite.suite_report_id", errors)
    if suite.get("suite_report_id") != baseline_suite_report_id_for(suite):
        errors.append("suite.suite_report_id: canonical identity mismatch")
    try:
        expected = aggregate_baseline_suite(
            suite_input, repository_root=repository_root
        )
    except (BaselineContractError, ValueError, KeyError, TypeError) as error:
        errors.append(f"suite inputs: {error}")
    else:
        if suite != expected:
            errors.append("suite: does not exactly match macro recomputation")
    return errors


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BaselineContractError(f"{path}: expected a JSON object")
    return value


def load_canonical_json(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if path.read_bytes() != discovery.canonical_json_bytes(value):
        raise BaselineContractError(f"{path}: JSON bytes are not canonical")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            raise BaselineContractError(f"{path}:{line_number}: blank lines are forbidden")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise BaselineContractError(f"{path}:{line_number}: expected an object")
        rows.append(value)
    return rows


def _common_inputs(arguments: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    return load_json(arguments.target), load_json(arguments.pool), load_jsonl(arguments.proposals)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="freeze 1000 random and one heuristic order")
    analyze = commands.add_parser("analyze", help="join frozen orders to one complete result ledger")
    validate = commands.add_parser("validate-report", help="recompute and validate a baseline report")
    aggregate = commands.add_parser("aggregate", help="macro-aggregate six target reports")
    validate_suite = commands.add_parser("validate-suite", help="recompute and validate a suite report")
    for command in (freeze, analyze, validate):
        command.add_argument("--target", type=Path, required=True)
        command.add_argument("--pool", type=Path, required=True)
        command.add_argument("--proposals", type=Path, required=True)
        command.add_argument(
            "--repository-root", type=Path, default=Path.cwd()
        )
    freeze.add_argument("--output", type=Path, required=True)
    for command in (analyze, validate):
        command.add_argument("--results", type=Path, required=True)
        command.add_argument("--policy-orders", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    validate.add_argument("--report", type=Path, required=True)
    for command in (aggregate, validate_suite):
        command.add_argument("--suite-input", type=Path, required=True)
        command.add_argument(
            "--repository-root", type=Path, default=Path.cwd()
        )
    aggregate.add_argument("--output", type=Path, required=True)
    validate_suite.add_argument("--suite", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command in {"aggregate", "validate-suite"}:
        root = arguments.repository_root.resolve(strict=True)
        suite_input_path = arguments.suite_input.resolve(strict=True)
        try:
            suite_input_path.relative_to(root)
        except ValueError as error:
            raise BaselineContractError(
                "suite input path must resolve inside repository_root"
            ) from error
        suite_input = load_canonical_json(suite_input_path)
        if arguments.command == "aggregate":
            suite = aggregate_baseline_suite(
                suite_input, repository_root=root
            )
            arguments.output.write_bytes(discovery.canonical_json_bytes(suite))
            return 0
        suite = load_json(arguments.suite)
        errors = validate_baseline_suite_report(
            suite, suite_input, repository_root=root
        )
        if errors:
            for error in errors:
                print(error)
            return 1
        print("valid baseline suite report")
        return 0
    target, pool, proposals = _common_inputs(arguments)
    if arguments.command == "freeze":
        artifact = build_policy_orders(
            target,
            pool,
            proposals,
            proposals_path=arguments.proposals,
            repository_root=arguments.repository_root,
        )
        arguments.output.write_bytes(discovery.canonical_json_bytes(artifact))
        return 0
    results = load_jsonl(arguments.results)
    orders = load_json(arguments.policy_orders)
    if arguments.command == "analyze":
        report = analyze_baselines(
            target,
            pool,
            proposals,
            results,
            orders,
            proposals_path=arguments.proposals,
            repository_root=arguments.repository_root,
        )
        arguments.output.write_bytes(discovery.canonical_json_bytes(report))
        return 0
    report = load_json(arguments.report)
    errors = validate_baseline_report(
        report,
        target,
        pool,
        proposals,
        results,
        orders,
        proposals_path=arguments.proposals,
        repository_root=arguments.repository_root,
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print("valid baseline report")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
