"""Exact fixed-value search for finite normal-play short games.

The module treats a target game as a fixed mathematical constraint. Candidate
representations are admitted only after exact recursive comparison with that
target. The resulting repertoire records which differences occur solely in
the embodiment and which cross into a different literal option tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

TARGET_SCHEMA_VERSION = "partizan.fixed_value_target.v0.1"
CANDIDATE_SCHEMA_VERSION = "partizan.fixed_value_candidate.v0.1"
CERTIFICATE_SCHEMA_VERSION = "partizan.fixed_value_certificate.v0.1"
REPERTOIRE_SCHEMA_VERSION = "partizan.fixed_value_repertoire.v0.1"
COMPARISON_CONTRACT = "conway_recursive_order_v1"
DOMAIN = "formal_domain:finite_normal_play_short_games:v0"
ORDERING_CONTRACT = "sha256_seeded_candidate_order_v1"
MAX_LITERAL_NODES = 100_000
MAX_LITERAL_DEPTH = 128
MAX_CANDIDATES = 100_000
MAX_COMPARISON_PAIRS = 1_000_000
MAX_TOTAL_CANDIDATE_NODES = 1_000_000
MAX_CANDIDATE_STREAM_BYTES = 256 * 1024 * 1024
MAX_GENERATED_CANDIDATES = 10_000
MAX_GENERATION_DEPTH = 8
U64_MAX = (1 << 64) - 1
I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LiteralGameStats:
    """Structural counts for one fully expanded literal game tree."""

    node_count: int
    option_count: int
    max_depth: int
    root_left_options: int
    root_right_options: int


@dataclass(frozen=True)
class ShortGameComparison:
    """Exact order and equality result for two finite short games."""

    left_ge_right: bool
    right_ge_left: bool
    equivalent: bool
    distinct_pairs_evaluated: int


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON to the repository's canonical UTF-8 form."""

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
    """Serialize a sequence of JSON records without blank lines."""

    return b"".join(canonical_json_bytes(value) for value in values)


def sha256_hex(data: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(data).hexdigest()


def _identity(prefix: str, payload: Any) -> str:
    return f"{prefix}-sha256:{sha256_hex(canonical_json_bytes(payload))}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_metadata_json(value: Any, path: str) -> list[str]:
    errors: list[str] = []
    if isinstance(value, float):
        return [f"{path} cannot contain floats"]
    if value is None or isinstance(value, (str, bool)):
        return []
    if _is_int(value):
        if not I64_MIN <= value <= I64_MAX:
            errors.append(f"{path} integer must fit signed 64-bit")
        return errors
    if isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_validate_metadata_json(item, f"{path}[{index}]"))
        return errors
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                errors.append(f"{path} keys must be strings")
                continue
            errors.extend(_validate_metadata_json(item, f"{path}.{key}"))
        return errors
    return [f"{path} contains an unsupported JSON value"]


def _validate_literal_game(
    game: Any,
    *,
    label: str,
) -> tuple[list[str], LiteralGameStats | None]:
    errors: list[str] = []
    if not isinstance(game, dict):
        return [f"{label} must be an object"], None

    node_count = 0
    option_count = 0
    max_depth = 0
    stack: list[tuple[Any, str, int]] = [(game, label, 0)]
    while stack:
        node, path, depth = stack.pop()
        if not isinstance(node, dict):
            errors.append(f"{path} must be an object")
            continue
        if set(node) != {"left", "right"}:
            errors.append(f"{path} fields must be exactly left and right")
            continue
        left = node.get("left")
        right = node.get("right")
        if not isinstance(left, list):
            errors.append(f"{path}.left must be an array")
            left = []
        if not isinstance(right, list):
            errors.append(f"{path}.right must be an array")
            right = []

        node_count += 1
        option_count += len(left) + len(right)
        max_depth = max(max_depth, depth)
        if node_count > MAX_LITERAL_NODES:
            errors.append(f"{label} exceeds the {MAX_LITERAL_NODES} node contract")
            break
        if depth > MAX_LITERAL_DEPTH:
            errors.append(f"{label} exceeds the {MAX_LITERAL_DEPTH} depth contract")
            break
        for index in range(len(right) - 1, -1, -1):
            stack.append((right[index], f"{path}.right[{index}]", depth + 1))
        for index in range(len(left) - 1, -1, -1):
            stack.append((left[index], f"{path}.left[{index}]", depth + 1))

    if errors:
        return errors, None
    return (
        [],
        LiteralGameStats(
            node_count=node_count,
            option_count=option_count,
            max_depth=max_depth,
            root_left_options=len(game["left"]),
            root_right_options=len(game["right"]),
        ),
    )


def literal_game_sha256(game: dict[str, Any]) -> str:
    """Return the order-independent literal option-tree digest."""

    return sha256_hex(canonical_json_bytes(canonicalize_literal_game(game)))


def canonicalize_literal_game(game: dict[str, Any]) -> dict[str, Any]:
    """Sort and deduplicate literal options recursively.

    Options in a combinatorial game form a set. Their serialized order and
    repeated identical subtrees do not define a new literal game.
    """

    errors, _ = _validate_literal_game(game, label="literal_game")
    if errors:
        raise ValueError("; ".join(errors))

    def canonicalize(node: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, list[dict[str, Any]]] = {}
        for side in ("left", "right"):
            unique: dict[bytes, dict[str, Any]] = {}
            for option in node[side]:
                canonical_option = canonicalize(option)
                encoded = canonical_json_bytes(canonical_option)
                unique.setdefault(encoded, canonical_option)
            result[side] = [unique[key] for key in sorted(unique)]
        return result

    return canonicalize(game)


def _target_identity_payload(value: dict[str, Any]) -> dict[str, Any]:
    literal_game = value.get("literal_game")
    if isinstance(literal_game, dict):
        try:
            literal_game = canonicalize_literal_game(literal_game)
        except ValueError:
            pass
    return {
        "comparison_contract": value.get("comparison_contract"),
        "domain": value.get("domain"),
        "literal_game": literal_game,
    }


def target_id_for(value: dict[str, Any]) -> str:
    """Compute the identity of a fixed-value target."""

    return _identity("fixed-target", _target_identity_payload(value))


def make_target(name: str, literal_game: dict[str, Any]) -> dict[str, Any]:
    """Construct a canonical exact short-game target."""

    target = {
        "schema_version": TARGET_SCHEMA_VERSION,
        "target_id": "",
        "domain": DOMAIN,
        "comparison_contract": COMPARISON_CONTRACT,
        "name": name,
        "literal_game": canonicalize_literal_game(literal_game),
    }
    target["target_id"] = target_id_for(target)
    errors = validate_target(target)
    if errors:
        raise ValueError("; ".join(errors))
    return target


def validate_target(value: Any) -> list[str]:
    """Return deterministic validation errors for a target."""

    if not isinstance(value, dict):
        return ["target must be an object"]
    errors: list[str] = []
    expected_keys = {
        "schema_version",
        "target_id",
        "domain",
        "comparison_contract",
        "name",
        "literal_game",
    }
    if set(value) != expected_keys:
        errors.append("target fields do not match the v0.1 contract")
    if value.get("schema_version") != TARGET_SCHEMA_VERSION:
        errors.append(f"schema_version must be {TARGET_SCHEMA_VERSION}")
    if value.get("domain") != DOMAIN:
        errors.append(f"domain must be {DOMAIN}")
    if value.get("comparison_contract") != COMPARISON_CONTRACT:
        errors.append(f"comparison_contract must be {COMPARISON_CONTRACT}")
    if not isinstance(value.get("name"), str) or not value.get("name"):
        errors.append("target.name must be a non-empty string")
    game_errors, _ = _validate_literal_game(
        value.get("literal_game"), label="target.literal_game"
    )
    errors.extend(game_errors)
    target_id = value.get("target_id")
    if not isinstance(target_id, str) or not target_id.startswith(
        "fixed-target-sha256:"
    ):
        errors.append("target.target_id must be a fixed-target SHA-256 identity")
    elif not errors and target_id != target_id_for(value):
        errors.append("target.target_id does not bind the target payload")
    return errors


def representation_sha256(representation: dict[str, Any]) -> str:
    """Return the embodiment fingerprint for a validated representation."""

    errors = _validate_representation(representation)
    if errors:
        raise ValueError("; ".join(errors))
    return sha256_hex(canonical_json_bytes(representation))


def _validate_representation(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["candidate.representation must be an object"]
    errors: list[str] = []
    if set(value) != {"encoding", "text", "metadata"}:
        errors.append(
            "candidate.representation fields must be encoding, text, and metadata"
        )
    if not isinstance(value.get("encoding"), str) or not value.get("encoding"):
        errors.append("candidate.representation.encoding must be non-empty")
    if not isinstance(value.get("text"), str) or not value.get("text"):
        errors.append("candidate.representation.text must be non-empty")
    if not isinstance(value.get("metadata"), dict):
        errors.append("candidate.representation.metadata must be an object")
    else:
        errors.extend(
            _validate_metadata_json(
                value["metadata"], "candidate.representation.metadata"
            )
        )
        try:
            canonical_json_bytes(value["metadata"])
        except (TypeError, ValueError):
            errors.append("candidate.representation.metadata must be finite JSON")
    return errors


def _validate_generator(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["candidate.generator must be an object"]
    errors: list[str] = []
    if set(value) != {"name", "version", "seed", "operator"}:
        errors.append(
            "candidate.generator fields must be name, version, seed, and operator"
        )
    for field in ("name", "version", "operator"):
        if not isinstance(value.get(field), str) or not value.get(field):
            errors.append(f"candidate.generator.{field} must be non-empty")
    if not _is_int(value.get("seed")) or not 0 <= value["seed"] <= U64_MAX:
        errors.append("candidate.generator.seed must be an unsigned 64-bit integer")
    return errors


def _candidate_identity_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "generator": value.get("generator"),
        "literal_game": value.get("literal_game"),
        "ordinal": value.get("ordinal"),
        "representation": value.get("representation"),
    }


def candidate_id_for(value: dict[str, Any]) -> str:
    """Compute the identity of one proposed realization."""

    return _identity("fixed-candidate", _candidate_identity_payload(value))


def make_candidate(
    *,
    ordinal: int,
    representation: dict[str, Any],
    literal_game: dict[str, Any],
    generator: dict[str, Any],
) -> dict[str, Any]:
    """Construct a canonical fixed-value candidate."""

    candidate = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "candidate_id": "",
        "ordinal": ordinal,
        "representation": representation,
        "literal_game": canonicalize_literal_game(literal_game),
        "generator": generator,
    }
    candidate["candidate_id"] = candidate_id_for(candidate)
    errors = validate_candidate(candidate)
    if errors:
        raise ValueError("; ".join(errors))
    return candidate


def _reversible_left_expansion(game: dict[str, Any]) -> dict[str, Any]:
    base = canonicalize_literal_game(game)
    reversible_option = {"left": [], "right": [base]}
    return canonicalize_literal_game(
        {
            "left": [*base["left"], reversible_option],
            "right": base["right"],
        }
    )


def _reversible_right_expansion(game: dict[str, Any]) -> dict[str, Any]:
    base = canonicalize_literal_game(game)
    reversible_option = {"left": [base], "right": []}
    return canonicalize_literal_game(
        {
            "left": base["left"],
            "right": [*base["right"], reversible_option],
        }
    )


def generate_candidates(
    target: dict[str, Any],
    *,
    seed: int,
    count: int,
    max_expansion_depth: int = 3,
) -> list[dict[str, Any]]:
    """Generate deterministic embodiments and reversible literal expansions."""

    errors = validate_target(target)
    if not _is_int(seed) or not 0 <= seed <= U64_MAX:
        errors.append("seed must be an unsigned 64-bit integer")
    if not _is_int(count) or not 1 <= count <= MAX_GENERATED_CANDIDATES:
        errors.append(
            "count must be an integer from 1 through " f"{MAX_GENERATED_CANDIDATES}"
        )
    if (
        not _is_int(max_expansion_depth)
        or not 1 <= max_expansion_depth <= MAX_GENERATION_DEPTH
    ):
        errors.append(
            "max_expansion_depth must be an integer from 1 through "
            f"{MAX_GENERATION_DEPTH}"
        )
    if errors:
        raise ValueError("; ".join(errors))

    candidates: list[dict[str, Any]] = []
    generated_nodes = 0
    for ordinal in range(count):
        literal_game = target["literal_game"]
        operator_path: list[str] = []
        if ordinal >= 2:
            rank = sha256_hex(
                canonical_json_bytes(
                    {
                        "generator": "reversible_option_v1",
                        "target_id": target["target_id"],
                        "seed": seed,
                        "ordinal": ordinal,
                    }
                )
            )
            depth = 1 + int(rank[:8], 16) % max_expansion_depth
            for step in range(depth):
                current_nodes = _literal_stats(literal_game).node_count
                if 2 * current_nodes + 1 > MAX_LITERAL_NODES:
                    raise ValueError(
                        f"candidate {ordinal} expansion exceeds the "
                        f"{MAX_LITERAL_NODES} node contract"
                    )
                selector = int(rank[8 + 2 * step : 10 + 2 * step], 16)
                if selector % 2 == 0:
                    literal_game = _reversible_left_expansion(literal_game)
                    operator_path.append("reversible_left")
                else:
                    literal_game = _reversible_right_expansion(literal_game)
                    operator_path.append("reversible_right")

        operator = "identity" if not operator_path else "+".join(operator_path)
        candidate = make_candidate(
            ordinal=ordinal,
            representation={
                "encoding": "abstract-short-game-v1",
                "text": (
                    f"{target['name']} realization {ordinal:04d} " f"[{operator}]"
                ),
                "metadata": {
                    "operator_path": operator_path,
                    "target_id": target["target_id"],
                },
            },
            literal_game=literal_game,
            generator={
                "name": "partizan-reversible-option-generator",
                "version": "0.1.0",
                "seed": seed,
                "operator": operator,
            },
        )
        generated_nodes += _literal_stats(candidate["literal_game"]).node_count
        if generated_nodes > MAX_TOTAL_CANDIDATE_NODES:
            raise ValueError(
                "generated candidates exceed the "
                f"{MAX_TOTAL_CANDIDATE_NODES} total-node contract"
            )
        candidates.append(candidate)
    return candidates


def validate_candidate(value: Any) -> list[str]:
    """Return deterministic validation errors for a candidate."""

    if not isinstance(value, dict):
        return ["candidate must be an object"]
    errors: list[str] = []
    expected_keys = {
        "schema_version",
        "candidate_id",
        "ordinal",
        "representation",
        "literal_game",
        "generator",
    }
    if set(value) != expected_keys:
        errors.append("candidate fields do not match the v0.1 contract")
    if value.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {CANDIDATE_SCHEMA_VERSION}")
    candidate_id = value.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.startswith(
        "fixed-candidate-sha256:"
    ):
        errors.append(
            "candidate.candidate_id must be a fixed-candidate SHA-256 identity"
        )
    if not _is_int(value.get("ordinal")) or not 0 <= value["ordinal"] <= U64_MAX:
        errors.append("candidate.ordinal must be an unsigned 64-bit integer")
    errors.extend(_validate_representation(value.get("representation")))
    errors.extend(_validate_generator(value.get("generator")))
    game_errors, _ = _validate_literal_game(
        value.get("literal_game"), label="candidate.literal_game"
    )
    errors.extend(game_errors)
    if not errors and candidate_id != candidate_id_for(value):
        errors.append("candidate.candidate_id does not bind the candidate payload")
    return errors


def compare_short_games(
    left: dict[str, Any],
    right: dict[str, Any],
) -> ShortGameComparison:
    """Compare two finite normal-play games by Conway's recursive order."""

    left_errors, _ = _validate_literal_game(left, label="left")
    right_errors, _ = _validate_literal_game(right, label="right")
    errors = left_errors + right_errors
    if errors:
        raise ValueError("; ".join(errors))

    left = canonicalize_literal_game(left)
    right = canonicalize_literal_game(right)
    digest_cache: dict[int, str] = {}

    def digest(game: dict[str, Any]) -> str:
        object_id = id(game)
        known = digest_cache.get(object_id)
        if known is not None:
            return known
        value = sha256_hex(canonical_json_bytes(game))
        digest_cache[object_id] = value
        return value

    memo: dict[tuple[str, str], bool] = {}
    pairs_started = 0

    def ge(
        left_game: dict[str, Any],
        right_game: dict[str, Any],
    ) -> bool:
        nonlocal pairs_started
        key = (digest(left_game), digest(right_game))
        known = memo.get(key)
        if known is not None:
            return known
        if pairs_started >= MAX_COMPARISON_PAIRS:
            raise ValueError(
                "comparison exceeds the "
                f"{MAX_COMPARISON_PAIRS} distinct-pair contract"
            )
        pairs_started += 1
        for left_right_option in left_game["right"]:
            if ge(right_game, left_right_option):
                memo[key] = False
                return False
        for right_left_option in right_game["left"]:
            if ge(right_left_option, left_game):
                memo[key] = False
                return False
        memo[key] = True
        return True

    left_ge_right = ge(left, right)
    right_ge_left = ge(right, left)
    return ShortGameComparison(
        left_ge_right=left_ge_right,
        right_ge_left=right_ge_left,
        equivalent=left_ge_right and right_ge_left,
        distinct_pairs_evaluated=pairs_started,
    )


def _comparison_certificate(
    target: dict[str, Any],
    candidate: dict[str, Any],
    comparison: ShortGameComparison,
) -> dict[str, Any]:
    certificate = {
        "schema_version": CERTIFICATE_SCHEMA_VERSION,
        "certificate_sha256": "",
        "comparison_contract": COMPARISON_CONTRACT,
        "target_id": target["target_id"],
        "candidate_id": candidate["candidate_id"],
        "target_literal_game_sha256": literal_game_sha256(target["literal_game"]),
        "candidate_literal_game_sha256": literal_game_sha256(candidate["literal_game"]),
        "candidate_ge_target": comparison.left_ge_right,
        "target_ge_candidate": comparison.right_ge_left,
        "equivalent": comparison.equivalent,
        "distinct_pairs_evaluated": comparison.distinct_pairs_evaluated,
    }
    certificate["certificate_sha256"] = sha256_hex(
        canonical_json_bytes(
            {
                key: value
                for key, value in certificate.items()
                if key != "certificate_sha256"
            }
        )
    )
    return certificate


def _literal_stats(game: dict[str, Any]) -> LiteralGameStats:
    canonical_game = canonicalize_literal_game(game)
    errors, stats = _validate_literal_game(canonical_game, label="literal_game")
    if errors or stats is None:
        raise ValueError("; ".join(errors))
    return stats


def _descriptors(candidate: dict[str, Any]) -> dict[str, int]:
    stats = _literal_stats(candidate["literal_game"])
    representation = candidate["representation"]
    return {
        "literal_node_count": stats.node_count,
        "literal_option_count": stats.option_count,
        "literal_max_depth": stats.max_depth,
        "root_left_option_count": stats.root_left_options,
        "root_right_option_count": stats.root_right_options,
        "representation_utf8_bytes": len(representation["text"].encode("utf-8")),
    }


def _transition_kind(
    left_fingerprint: dict[str, str],
    right_fingerprint: dict[str, str],
) -> str:
    if left_fingerprint["embodiment_sha256"] == right_fingerprint["embodiment_sha256"]:
        if (
            left_fingerprint["literal_game_sha256"]
            == right_fingerprint["literal_game_sha256"]
        ):
            return "identical_representation"
        return "embodiment_conflict"
    if (
        left_fingerprint["literal_game_sha256"]
        == right_fingerprint["literal_game_sha256"]
    ):
        return "embodiment_only"
    return "literal_game_crossing"


def _search_rank(seed: int, candidate_id: str) -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "ordering_contract": ORDERING_CONTRACT,
                "seed": seed,
                "candidate_id": candidate_id,
            }
        )
    )


def _validate_search_settings(
    seed: Any,
    budget: Any,
    max_results: Any,
) -> list[str]:
    errors: list[str] = []
    if not _is_int(seed) or not 0 <= seed <= U64_MAX:
        errors.append("seed must be an unsigned 64-bit integer")
    if not _is_int(budget) or not 1 <= budget <= MAX_CANDIDATES:
        errors.append(f"budget must be an integer from 1 through {MAX_CANDIDATES}")
    if not _is_int(max_results) or not 1 <= max_results <= MAX_CANDIDATES:
        errors.append(f"max_results must be an integer from 1 through {MAX_CANDIDATES}")
    return errors


def build_repertoire(
    target: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    seed: int,
    budget: int,
    max_results: int,
) -> dict[str, Any]:
    """Search a candidate stream and retain exact fixed-value realizations."""

    errors = validate_target(target)
    errors.extend(_validate_search_settings(seed, budget, max_results))
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        candidates = []
    if len(candidates) > MAX_CANDIDATES:
        errors.append(f"candidate count exceeds {MAX_CANDIDATES}")
    seen_ids: set[str] = set()
    seen_ordinals: set[int] = set()
    literal_by_embodiment: dict[str, str] = {}
    total_candidate_nodes = 0
    for index, candidate in enumerate(candidates):
        errors.extend(
            f"candidates[{index}]: {error}" for error in validate_candidate(candidate)
        )
        if isinstance(candidate, dict):
            candidate_id = candidate.get("candidate_id")
            ordinal = candidate.get("ordinal")
            if candidate_id in seen_ids:
                errors.append(f"candidates[{index}]: duplicate candidate_id")
            elif isinstance(candidate_id, str):
                seen_ids.add(candidate_id)
            if ordinal in seen_ordinals:
                errors.append(f"candidates[{index}]: duplicate ordinal")
            elif _is_int(ordinal):
                seen_ordinals.add(ordinal)
            game_errors, stats = _validate_literal_game(
                candidate.get("literal_game"),
                label=f"candidates[{index}].literal_game",
            )
            if not game_errors and stats is not None:
                total_candidate_nodes += stats.node_count
            if (
                not _validate_representation(candidate.get("representation"))
                and not game_errors
            ):
                embodiment_digest = representation_sha256(candidate["representation"])
                literal_digest = literal_game_sha256(candidate["literal_game"])
                prior_literal = literal_by_embodiment.get(embodiment_digest)
                if prior_literal is not None and prior_literal != literal_digest:
                    errors.append(
                        f"candidates[{index}]: embodiment binds "
                        "conflicting literal games"
                    )
                else:
                    literal_by_embodiment[embodiment_digest] = literal_digest
    if total_candidate_nodes > MAX_TOTAL_CANDIDATE_NODES:
        errors.append(
            "candidate stream exceeds the "
            f"{MAX_TOTAL_CANDIDATE_NODES} total-node contract"
        )
    if errors:
        raise ValueError("; ".join(errors))

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            _search_rank(seed, candidate["candidate_id"]),
            candidate["candidate_id"],
        ),
    )
    entries: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    admitted_by_embodiment: dict[str, str] = {}
    admitted_by_literal: dict[str, dict[str, Any]] = {}
    termination_reason = "candidate_stream_exhausted"

    for candidate in ranked:
        if len(evaluations) >= budget:
            termination_reason = "verification_budget_reached"
            break
        if len(entries) >= max_results:
            termination_reason = "repertoire_limit_reached"
            break

        comparison = compare_short_games(
            candidate["literal_game"], target["literal_game"]
        )
        certificate = _comparison_certificate(target, candidate, comparison)
        fingerprint = {
            "embodiment_sha256": representation_sha256(candidate["representation"]),
            "literal_game_sha256": certificate["candidate_literal_game_sha256"],
            "fixed_target_id": target["target_id"],
        }
        outcome = "admitted"
        reason_codes: list[str] = []
        if not comparison.equivalent:
            outcome = "rejected"
            reason_codes.append("value_mismatch")
        elif fingerprint["embodiment_sha256"] in admitted_by_embodiment:
            outcome = "rejected"
            reason_codes.append("duplicate_embodiment")

        evaluation = {
            "candidate_id": candidate["candidate_id"],
            "search_rank_sha256": _search_rank(seed, candidate["candidate_id"]),
            "outcome": outcome,
            "reason_codes": reason_codes,
            "fingerprint": fingerprint,
            "certificate": certificate,
        }
        evaluations.append(evaluation)

        if outcome == "admitted":
            if not entries:
                admission_relation = {
                    "transition_kind": "initial",
                    "witness_candidate_id": None,
                }
            else:
                same_literal = admitted_by_literal.get(
                    fingerprint["literal_game_sha256"]
                )
                witness = same_literal if same_literal is not None else entries[0]
                admission_relation = {
                    "transition_kind": _transition_kind(
                        witness["fingerprint"], fingerprint
                    ),
                    "witness_candidate_id": witness["candidate_id"],
                }
            entry = {
                "admission_index": len(entries),
                "candidate_id": candidate["candidate_id"],
                "representation": candidate["representation"],
                "fingerprint": fingerprint,
                "descriptors": _descriptors(candidate),
                "certificate_sha256": certificate["certificate_sha256"],
                "admission_relation": admission_relation,
            }
            entries.append(entry)
            admitted_by_embodiment[fingerprint["embodiment_sha256"]] = candidate[
                "candidate_id"
            ]
            admitted_by_literal.setdefault(fingerprint["literal_game_sha256"], entry)

    outcome_counts = {
        "admitted": sum(
            evaluation["outcome"] == "admitted" for evaluation in evaluations
        ),
        "duplicate_embodiment": sum(
            "duplicate_embodiment" in evaluation["reason_codes"]
            for evaluation in evaluations
        ),
        "value_mismatch": sum(
            "value_mismatch" in evaluation["reason_codes"] for evaluation in evaluations
        ),
    }
    repertoire = {
        "schema_version": REPERTOIRE_SCHEMA_VERSION,
        "repertoire_id": "",
        "target": target,
        "search": {
            "seed": seed,
            "budget": budget,
            "max_results": max_results,
            "ordering_contract": ORDERING_CONTRACT,
            "candidate_stream_sha256": sha256_hex(canonical_jsonl_bytes(candidates)),
        },
        "source_candidates": candidates,
        "evaluations": evaluations,
        "entries": entries,
        "summary": {
            "source_candidate_count": len(candidates),
            "evaluated_candidate_count": len(evaluations),
            "admitted_count": len(entries),
            "outcome_counts": outcome_counts,
            "termination_reason": termination_reason,
        },
    }
    repertoire["repertoire_id"] = _identity(
        "fixed-repertoire",
        {key: value for key, value in repertoire.items() if key != "repertoire_id"},
    )
    return repertoire


def validate_repertoire(value: Any) -> list[str]:
    """Replay an entire repertoire and report any divergence."""

    if not isinstance(value, dict):
        return ["repertoire must be an object"]
    expected_keys = {
        "schema_version",
        "repertoire_id",
        "target",
        "search",
        "source_candidates",
        "evaluations",
        "entries",
        "summary",
    }
    errors: list[str] = []
    if set(value) != expected_keys:
        errors.append("repertoire fields do not match the v0.1 contract")
    if value.get("schema_version") != REPERTOIRE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {REPERTOIRE_SCHEMA_VERSION}")
    repertoire_id = value.get("repertoire_id")
    if not isinstance(repertoire_id, str) or not repertoire_id.startswith(
        "fixed-repertoire-sha256:"
    ):
        errors.append("repertoire_id must be a fixed-repertoire SHA-256 identity")
    search = value.get("search")
    if not isinstance(search, dict):
        errors.append("search must be an object")
        return errors
    if set(search) != {
        "seed",
        "budget",
        "max_results",
        "ordering_contract",
        "candidate_stream_sha256",
    }:
        errors.append("search fields do not match the v0.1 contract")
    if search.get("ordering_contract") != ORDERING_CONTRACT:
        errors.append(f"search.ordering_contract must be {ORDERING_CONTRACT}")
    stream_digest = search.get("candidate_stream_sha256")
    if not isinstance(stream_digest, str) or not _SHA256_RE.fullmatch(stream_digest):
        errors.append(
            "search.candidate_stream_sha256 must be a lowercase SHA-256 digest"
        )
    settings_errors = _validate_search_settings(
        search.get("seed"),
        search.get("budget"),
        search.get("max_results"),
    )
    errors.extend(settings_errors)
    if errors:
        return errors

    try:
        replayed = build_repertoire(
            value.get("target"),
            value.get("source_candidates"),
            seed=search["seed"],
            budget=search["budget"],
            max_results=search["max_results"],
        )
    except (TypeError, ValueError) as error:
        return [f"deterministic replay failed: {error}"]
    if canonical_json_bytes(value) != canonical_json_bytes(replayed):
        errors.append("repertoire does not match deterministic replay")
    return errors


def inspect_repertoire(value: dict[str, Any]) -> dict[str, Any]:
    """Return a compact human-readable projection of a valid repertoire."""

    errors = validate_repertoire(value)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "repertoire_id": value["repertoire_id"],
        "target": {
            "target_id": value["target"]["target_id"],
            "name": value["target"]["name"],
        },
        "summary": value["summary"],
        "entries": [
            {
                "admission_index": entry["admission_index"],
                "candidate_id": entry["candidate_id"],
                "representation": entry["representation"],
                "fingerprint": entry["fingerprint"],
                "descriptors": entry["descriptors"],
                "admission_relation": entry["admission_relation"],
            }
            for entry in value["entries"]
        ],
    }


def compare_repertoire_entries(
    value: dict[str, Any],
    left_candidate_id: str,
    right_candidate_id: str,
) -> dict[str, Any]:
    """Compare two admitted realizations in a valid repertoire."""

    errors = validate_repertoire(value)
    if errors:
        raise ValueError("; ".join(errors))
    entries = {entry["candidate_id"]: entry for entry in value["entries"]}
    left = entries.get(left_candidate_id)
    right = entries.get(right_candidate_id)
    if left is None:
        raise ValueError(f"unknown admitted candidate {left_candidate_id}")
    if right is None:
        raise ValueError(f"unknown admitted candidate {right_candidate_id}")
    descriptor_delta = {
        key: right["descriptors"][key] - left["descriptors"][key]
        for key in sorted(left["descriptors"])
    }
    return {
        "left_candidate_id": left_candidate_id,
        "right_candidate_id": right_candidate_id,
        "fixed_target_id": value["target"]["target_id"],
        "transition_kind": _transition_kind(left["fingerprint"], right["fingerprint"]),
        "same_embodiment": (
            left["fingerprint"]["embodiment_sha256"]
            == right["fingerprint"]["embodiment_sha256"]
        ),
        "same_literal_game": (
            left["fingerprint"]["literal_game_sha256"]
            == right["fingerprint"]["literal_game_sha256"]
        ),
        "descriptor_delta_right_minus_left": descriptor_delta,
    }


def load_json(path: Any) -> Any:
    """Load one UTF-8 JSON document."""

    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Any) -> list[Any]:
    """Load a UTF-8 JSONL stream and reject blank records."""

    if os.path.getsize(path) > MAX_CANDIDATE_STREAM_BYTES:
        raise ValueError(
            f"{path}: JSONL input exceeds {MAX_CANDIDATE_STREAM_BYTES} bytes"
        )
    values: list[Any] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL record")
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error.msg}"
                ) from error
    return values
