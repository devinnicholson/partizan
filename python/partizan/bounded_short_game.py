"""Bounded exact comparison and semantic validation for finite short games.

This module is the Partizan implementation of
``partizan.bounded_short_game_contract.v1``.  Its semantic reducer is an
independent Python validation lane.  Thermograph supplies the separately
implemented release cross-check and canonical-form certificate authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


CONTRACT_ID = "partizan.bounded_short_game_contract.v1"
TRANSPORT_SCHEMA_VERSION = "partizan.bounded_short_game_transport.v1"
CERTIFICATE_SCHEMA_VERSION = "partizan.short_game_comparison_certificate.v1"
# The v1 schema and null semantic boundary remain frozen. New certificates
# bind independently validated semantic IDs through the additive v2 schema.
CERTIFICATE_SCHEMA_VERSION_V2 = "partizan.short_game_comparison_certificate.v2"
CANONICALIZATION_STATUS = "thermograph_semantic_api_required"
INDEPENDENT_CANONICALIZATION_STATUS = "partizan_independent_validation_v1"
LITERAL_SHA256_V1_PREFIX = b"partizan.explicit_short_game.v1\n"
SEMANTIC_CANONICAL_SHA256_V1_PREFIX = b"partizan.semantic_canonical_game.v1\n"
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class BoundedGameContractError(ValueError):
    """Base class for a rejected bounded-game request."""


class InvalidGameError(BoundedGameContractError):
    """Raised when an explicit game does not satisfy the transport grammar."""


class DigestCollisionError(BoundedGameContractError):
    """Raised if one digest is observed for two different literal byte strings."""


class ResourceLimitError(BoundedGameContractError):
    """A typed operational-profile refusal."""

    def __init__(self, resource: str, limit: int, observed: int) -> None:
        self.resource = resource
        self.limit = limit
        self.observed = observed
        super().__init__(
            f"{resource} limit {limit} exceeded by observed count {observed}"
        )

    def as_record(self) -> dict[str, Any]:
        """Return the portable typed-refusal record."""

        return {
            "status": "resource_limit",
            "resource": self.resource,
            "limit": self.limit,
            "observed": self.observed,
        }


@dataclass(frozen=True)
class BoundedResourceProfile:
    """Exact operational limits attached to a comparison or certificate."""

    profile_id: str = "partizan.bounded_short_game.order7.v1"
    maximum_root_birthday: int = 7
    maximum_canonical_birthday: int = 7
    maximum_source_nodes_per_root: int = 128
    maximum_options_per_side: int = 7
    maximum_option_references: int = 1_792
    maximum_intermediate_nodes: int = 4_096
    maximum_comparison_dag_rows: int = 262_144
    maximum_literal_serialization_bytes_per_root: int = 16_777_216
    maximum_certificate_bytes: int = 67_108_864

    def __post_init__(self) -> None:
        for name, value in self.as_record().items():
            if name == "profile_id":
                if not isinstance(value, str) or not value:
                    raise ValueError("profile_id must be a nonempty string")
            elif type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")

    def as_record(self) -> dict[str, Any]:
        """Return the cross-language JSON representation."""

        return {
            "profile_id": self.profile_id,
            "maximum_root_birthday": self.maximum_root_birthday,
            "maximum_canonical_birthday": self.maximum_canonical_birthday,
            "maximum_source_nodes_per_root": self.maximum_source_nodes_per_root,
            "maximum_options_per_side": self.maximum_options_per_side,
            "maximum_option_references": self.maximum_option_references,
            "maximum_intermediate_nodes": self.maximum_intermediate_nodes,
            "maximum_comparison_dag_rows": self.maximum_comparison_dag_rows,
            "maximum_literal_serialization_bytes_per_root": (
                self.maximum_literal_serialization_bytes_per_root
            ),
            "maximum_certificate_bytes": self.maximum_certificate_bytes,
        }

    @classmethod
    def from_record(cls, value: Any) -> "BoundedResourceProfile":
        """Parse an exact named profile, permitting only stricter caller limits."""

        if not isinstance(value, dict):
            raise ValueError("profile must be an object")
        expected = set(ORDER7_RESOURCE_PROFILE.as_record())
        if set(value) != expected:
            raise ValueError("profile fields do not match the v1 contract")
        profile = cls(**value)
        named = {
            ORDER7_RESOURCE_PROFILE.profile_id: ORDER7_RESOURCE_PROFILE,
            DIGRAPH8_RESOURCE_PROFILE.profile_id: DIGRAPH8_RESOURCE_PROFILE,
        }.get(profile.profile_id)
        if named is None:
            raise ValueError("unsupported bounded-game profile_id")
        for field, limit in named.as_record().items():
            if field != "profile_id" and profile.as_record()[field] > limit:
                raise ValueError(f"profile relaxes unsupported v1 limit {field}")
        return profile

    @classmethod
    def order7_v1(cls) -> "BoundedResourceProfile":
        """Return the order-7 experiment profile."""

        return ORDER7_RESOURCE_PROFILE

    @classmethod
    def digraph8_v1(cls) -> "BoundedResourceProfile":
        """Return the separately named order-8 expansion profile."""

        return DIGRAPH8_RESOURCE_PROFILE


ORDER7_RESOURCE_PROFILE = BoundedResourceProfile()
DIGRAPH8_RESOURCE_PROFILE = BoundedResourceProfile(
    profile_id="partizan.bounded_short_game.digraph8.v1",
    maximum_root_birthday=8,
    maximum_canonical_birthday=8,
    maximum_source_nodes_per_root=256,
    maximum_options_per_side=8,
    maximum_option_references=4_096,
    maximum_intermediate_nodes=8_192,
    maximum_comparison_dag_rows=1_000_000,
    maximum_literal_serialization_bytes_per_root=33_554_432,
    maximum_certificate_bytes=134_217_728,
)
DEFAULT_RESOURCE_PROFILE = ORDER7_RESOURCE_PROFILE


@dataclass(frozen=True)
class LiteralResourceUsage:
    """Unambiguous tree-occurrence and distinct-DAG resource measurements."""

    root_birthday: int
    literal_occurrence_node_count: int
    literal_distinct_dag_node_count: int
    literal_option_reference_count: int
    literal_serialization_bytes: int

    def as_record(self) -> dict[str, int]:
        """Return the cross-language JSON representation."""

        return {
            "root_birthday": self.root_birthday,
            "literal_occurrence_node_count": self.literal_occurrence_node_count,
            "literal_distinct_dag_node_count": self.literal_distinct_dag_node_count,
            "literal_option_reference_count": self.literal_option_reference_count,
            "literal_serialization_bytes": self.literal_serialization_bytes,
        }


class ComparisonOutcome(str, Enum):
    """The four outcomes of Conway's partial order."""

    EQUAL = "equal"
    GREATER = "greater"
    LESS = "less"
    FUZZY = "fuzzy"


@dataclass(frozen=True)
class BoundedComparison:
    """Exact two-direction order result and its bounded proof data."""

    left_leq_right: bool
    right_leq_left: bool
    outcome: ComparisonOutcome
    legacy_literal_left_sha256: str
    legacy_literal_right_sha256: str
    literal_left_sha256_v1: str
    literal_right_sha256_v1: str
    left_resources: LiteralResourceUsage
    right_resources: LiteralResourceUsage
    combined_distinct_dag_node_count: int
    combined_option_reference_count: int
    comparison_dag_row_count: int
    game_table: tuple[dict[str, Any], ...]
    comparison_dag: tuple[dict[str, Any], ...]

    @property
    def equivalent(self) -> bool:
        """Return mathematical equality under the v1 normal-play relation."""

        return self.outcome is ComparisonOutcome.EQUAL


@dataclass(frozen=True)
class SemanticCanonicalForm:
    """One independently reduced semantic canonical form and its audits."""

    input_legacy_literal_sha256: str
    input_literal_sha256_v1: str
    canonical_serialization: str
    semantic_canonical_id_v1: str
    canonical_game: dict[str, Any]
    input_resources: LiteralResourceUsage
    canonical_resources: LiteralResourceUsage
    rewrite_count: int
    rewrite_trace: tuple[dict[str, Any], ...]
    soundness_equal: bool
    irreducible: bool
    idempotent: bool


@dataclass(frozen=True)
class _Node:
    node_id: int
    left: tuple[int, ...]
    right: tuple[int, ...]
    serialization: bytes
    legacy_literal_sha256: str
    literal_sha256_v1: str
    birthday: int


@dataclass(frozen=True)
class _ReductionNode:
    node_id: int
    left: tuple[int, ...]
    right: tuple[int, ...]
    serialization: bytes
    birthday: int


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize certificate JSON deterministically without a trailing newline."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _literal_sha256_v1(serialization: bytes) -> str:
    return _sha256(LITERAL_SHA256_V1_PREFIX + serialization)


class _GameInterner:
    """Intern nodes by collision-checked literal bytes, never by digest alone."""

    def __init__(
        self,
        profile: BoundedResourceProfile,
        *,
        legacy_digest_function: Callable[[bytes], str] = _sha256,
        versioned_digest_function: Callable[[bytes], str] = _literal_sha256_v1,
    ) -> None:
        self.profile = profile
        self.legacy_digest_function = legacy_digest_function
        self.versioned_digest_function = versioned_digest_function
        self.nodes: list[_Node] = []
        self._node_by_serialization: dict[bytes, int] = {}
        self._serialization_by_legacy_digest: dict[str, bytes] = {}
        self._serialization_by_versioned_digest: dict[str, bytes] = {}
        self._active_object_ids: set[int] = set()

    def intern(self, value: Any, path: str = "game") -> int:
        """Validate and intern one explicit recursive ``left``/``right`` tree."""

        if not isinstance(value, dict):
            raise InvalidGameError(f"{path} must be an object")
        if set(value) != {"left", "right"}:
            raise InvalidGameError(f"{path} fields must be exactly left and right")
        if not isinstance(value["left"], list) or not isinstance(value["right"], list):
            raise InvalidGameError(f"{path} options must be arrays")

        object_id = id(value)
        if object_id in self._active_object_ids:
            raise InvalidGameError(f"{path} contains a cycle")
        self._active_object_ids.add(object_id)
        try:
            side_ids: dict[str, tuple[int, ...]] = {}
            for side in ("left", "right"):
                child_ids = [
                    self.intern(option, f"{path}.{side}[{index}]")
                    for index, option in enumerate(value[side])
                ]
                side_ids[side] = tuple(
                    sorted(
                        set(child_ids),
                        key=lambda node_id: self.nodes[node_id].serialization,
                    )
                )
        finally:
            self._active_object_ids.remove(object_id)

        left = side_ids["left"]
        right = side_ids["right"]
        for side_name, side in (("left", left), ("right", right)):
            if len(side) > self.profile.maximum_options_per_side:
                raise ResourceLimitError(
                    f"{side_name}_options_per_node",
                    self.profile.maximum_options_per_side,
                    len(side),
                )
        serialization = (
            b"{"
            + b",".join(self.nodes[node_id].serialization for node_id in left)
            + b"|"
            + b",".join(self.nodes[node_id].serialization for node_id in right)
            + b"}"
        )
        if (
            len(serialization)
            > self.profile.maximum_literal_serialization_bytes_per_root
        ):
            raise ResourceLimitError(
                "literal_serialization_bytes_per_root",
                self.profile.maximum_literal_serialization_bytes_per_root,
                len(serialization),
            )
        known_node = self._node_by_serialization.get(serialization)
        if known_node is not None:
            return known_node

        legacy_digest = self.legacy_digest_function(serialization)
        versioned_digest = self.versioned_digest_function(serialization)
        if (
            not isinstance(legacy_digest, str)
            or not _HEX_256.fullmatch(legacy_digest)
            or not isinstance(versioned_digest, str)
            or not _HEX_256.fullmatch(versioned_digest)
        ):
            raise InvalidGameError("digest function did not return lowercase SHA-256")
        for digest, observed in (
            (legacy_digest, self._serialization_by_legacy_digest),
            (versioned_digest, self._serialization_by_versioned_digest),
        ):
            prior_serialization = observed.get(digest)
            if prior_serialization is not None and prior_serialization != serialization:
                raise DigestCollisionError(
                    "one literal digest was observed for distinct serializations"
                )
        birthday = (
            0
            if not left and not right
            else 1 + max(self.nodes[node_id].birthday for node_id in left + right)
        )
        if birthday > self.profile.maximum_root_birthday:
            raise ResourceLimitError(
                "root_birthday",
                self.profile.maximum_root_birthday,
                birthday,
            )
        node_id = len(self.nodes)
        node = _Node(
            node_id=node_id,
            left=left,
            right=right,
            serialization=serialization,
            legacy_literal_sha256=legacy_digest,
            literal_sha256_v1=versioned_digest,
            birthday=birthday,
        )
        if len(self.nodes) + 1 > 2 * self.profile.maximum_source_nodes_per_root:
            raise ResourceLimitError(
                "combined_source_nodes",
                2 * self.profile.maximum_source_nodes_per_root,
                len(self.nodes) + 1,
            )
        self.nodes.append(node)
        self._node_by_serialization[serialization] = node_id
        self._serialization_by_legacy_digest[legacy_digest] = serialization
        self._serialization_by_versioned_digest[versioned_digest] = serialization
        return node_id

    def closure(self, roots: tuple[int, ...]) -> set[int]:
        pending = list(roots)
        seen: set[int] = set()
        while pending:
            node_id = pending.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            node = self.nodes[node_id]
            pending.extend(node.left)
            pending.extend(node.right)
        return seen

    def occurrence_count(self, root: int) -> int:
        memo: dict[int, int] = {}

        def visit(node_id: int) -> int:
            if node_id not in memo:
                node = self.nodes[node_id]
                memo[node_id] = 1 + sum(
                    visit(child) for child in node.left + node.right
                )
            return memo[node_id]

        return visit(root)

    def resources(self, root: int) -> LiteralResourceUsage:
        closure = self.closure((root,))
        return LiteralResourceUsage(
            root_birthday=self.nodes[root].birthday,
            literal_occurrence_node_count=self.occurrence_count(root),
            literal_distinct_dag_node_count=len(closure),
            literal_option_reference_count=sum(
                len(self.nodes[node_id].left) + len(self.nodes[node_id].right)
                for node_id in closure
            ),
            literal_serialization_bytes=len(self.nodes[root].serialization),
        )

    def enforce_combined_limits(self, roots: tuple[int, ...]) -> tuple[int, int]:
        for root in roots:
            source_nodes = len(self.closure((root,)))
            if source_nodes > self.profile.maximum_source_nodes_per_root:
                raise ResourceLimitError(
                    "source_nodes_per_root",
                    self.profile.maximum_source_nodes_per_root,
                    source_nodes,
                )
        closure = self.closure(roots)
        distinct = len(closure)
        edges = sum(
            len(self.nodes[node_id].left) + len(self.nodes[node_id].right)
            for node_id in closure
        )
        if distinct > self.profile.maximum_intermediate_nodes:
            raise ResourceLimitError(
                "intermediate_nodes",
                self.profile.maximum_intermediate_nodes,
                distinct,
            )
        if edges > self.profile.maximum_option_references:
            raise ResourceLimitError(
                "option_references",
                self.profile.maximum_option_references,
                edges,
            )
        return distinct, edges

    def game_table(self, roots: tuple[int, ...]) -> tuple[dict[str, Any], ...]:
        rows = []
        for node_id in self.closure(roots):
            node = self.nodes[node_id]
            rows.append(
                {
                    "legacy_literal_sha256": node.legacy_literal_sha256,
                    "literal_sha256_v1": node.literal_sha256_v1,
                    "literal_serialization": node.serialization.decode("ascii"),
                    "left_options": [
                        self.nodes[child].literal_sha256_v1 for child in node.left
                    ],
                    "right_options": [
                        self.nodes[child].literal_sha256_v1 for child in node.right
                    ],
                    "birthday": node.birthday,
                }
            )
        return tuple(sorted(rows, key=lambda row: row["literal_sha256_v1"]))


class _SemanticReducer:
    """Deterministic Conway reduction over one validated explicit game."""

    _RULE_PRIORITY = {
        "left_domination": 0,
        "right_domination": 1,
        "left_reversibility": 2,
        "right_reversibility": 3,
    }

    def __init__(
        self,
        source: _GameInterner,
        profile: BoundedResourceProfile,
        maximum_rewrite_steps: int,
    ) -> None:
        self.source = source
        self.profile = profile
        self.maximum_rewrite_steps = maximum_rewrite_steps
        self.nodes: list[_ReductionNode] = []
        self._node_by_serialization: dict[bytes, int] = {}
        self._reduced_source: dict[int, int] = {}
        self._leq_memo: dict[tuple[int, int], bool] = {}
        self.trace: list[dict[str, Any]] = []

    def intern(self, left: tuple[int, ...], right: tuple[int, ...]) -> int:
        left = tuple(
            sorted(set(left), key=lambda node_id: self.nodes[node_id].serialization)
        )
        right = tuple(
            sorted(set(right), key=lambda node_id: self.nodes[node_id].serialization)
        )
        serialization = (
            b"{"
            + b",".join(self.nodes[node_id].serialization for node_id in left)
            + b"|"
            + b",".join(self.nodes[node_id].serialization for node_id in right)
            + b"}"
        )
        known = self._node_by_serialization.get(serialization)
        if known is not None:
            return known
        observed = len(self.nodes) + 1
        if observed > self.profile.maximum_intermediate_nodes:
            raise ResourceLimitError(
                "canonical_intermediate_nodes",
                self.profile.maximum_intermediate_nodes,
                observed,
            )
        birthday = (
            0
            if not left and not right
            else 1 + max(self.nodes[node_id].birthday for node_id in left + right)
        )
        node_id = len(self.nodes)
        self.nodes.append(
            _ReductionNode(
                node_id=node_id,
                left=left,
                right=right,
                serialization=serialization,
                birthday=birthday,
            )
        )
        self._node_by_serialization[serialization] = node_id
        return node_id

    def leq(self, left: int, right: int) -> bool:
        pair = (left, right)
        if pair in self._leq_memo:
            return self._leq_memo[pair]
        left_node = self.nodes[left]
        right_node = self.nodes[right]
        dependencies = [(right, option) for option in left_node.left] + [
            (option, left) for option in right_node.right
        ]
        results = [
            self.leq(dependency_left, dependency_right)
            for dependency_left, dependency_right in dependencies
        ]
        result = not any(results)
        self._leq_memo[pair] = result
        return result

    def _rewrite_key(self, rewrite: dict[str, Any]) -> tuple[Any, ...]:
        def serialization(node_id: int | None) -> bytes:
            return b"" if node_id is None else self.nodes[node_id].serialization

        return (
            self._RULE_PRIORITY[rewrite["rule"]],
            serialization(rewrite["removed"]),
            serialization(rewrite.get("witness")),
            serialization(rewrite.get("response")),
            tuple(self.nodes[node_id].serialization for node_id in rewrite["inserted"]),
        )

    def first_rewrite(self, root: int) -> dict[str, Any] | None:
        node = self.nodes[root]
        rewrites: list[dict[str, Any]] = []
        for removed in node.left:
            for witness in node.left:
                if removed != witness and self.leq(removed, witness):
                    rewrites.append(
                        {
                            "rule": "left_domination",
                            "removed": removed,
                            "witness": witness,
                            "response": None,
                            "inserted": (),
                        }
                    )
            removed_node = self.nodes[removed]
            for response in removed_node.right:
                if self.leq(response, root):
                    rewrites.append(
                        {
                            "rule": "left_reversibility",
                            "removed": removed,
                            "witness": None,
                            "response": response,
                            "inserted": self.nodes[response].left,
                        }
                    )
        for removed in node.right:
            for witness in node.right:
                if removed != witness and self.leq(witness, removed):
                    rewrites.append(
                        {
                            "rule": "right_domination",
                            "removed": removed,
                            "witness": witness,
                            "response": None,
                            "inserted": (),
                        }
                    )
            removed_node = self.nodes[removed]
            for response in removed_node.left:
                if self.leq(root, response):
                    rewrites.append(
                        {
                            "rule": "right_reversibility",
                            "removed": removed,
                            "witness": None,
                            "response": response,
                            "inserted": self.nodes[response].right,
                        }
                    )
        return min(rewrites, key=self._rewrite_key) if rewrites else None

    def apply_rewrite(self, root: int, rewrite: dict[str, Any]) -> int:
        observed = len(self.trace) + 1
        if observed > self.maximum_rewrite_steps:
            raise ResourceLimitError(
                "canonical_rewrite_steps",
                self.maximum_rewrite_steps,
                observed,
            )
        node = self.nodes[root]
        if rewrite["rule"].startswith("left_"):
            left = tuple(
                option for option in node.left if option != rewrite["removed"]
            ) + tuple(rewrite["inserted"])
            right = node.right
        else:
            left = node.left
            right = tuple(
                option for option in node.right if option != rewrite["removed"]
            ) + tuple(rewrite["inserted"])
        reduced = self.intern(left, right)

        def text(node_id: int | None) -> str | None:
            if node_id is None:
                return None
            return self.nodes[node_id].serialization.decode("ascii")

        self.trace.append(
            {
                "step_index": len(self.trace),
                "rule": rewrite["rule"],
                "before_serialization": node.serialization.decode("ascii"),
                "after_serialization": self.nodes[reduced].serialization.decode(
                    "ascii"
                ),
                "removed_option_serialization": text(rewrite["removed"]),
                "witness_option_serialization": text(rewrite.get("witness")),
                "response_serialization": text(rewrite.get("response")),
                "inserted_option_serializations": [
                    text(node_id) for node_id in rewrite["inserted"]
                ],
            }
        )
        return reduced

    def reduce_source(self, source_id: int) -> int:
        known = self._reduced_source.get(source_id)
        if known is not None:
            return known
        source_node = self.source.nodes[source_id]
        left = tuple(self.reduce_source(option) for option in source_node.left)
        right = tuple(self.reduce_source(option) for option in source_node.right)
        current = self.intern(left, right)
        while True:
            rewrite = self.first_rewrite(current)
            if rewrite is None:
                break
            current = self.apply_rewrite(current, rewrite)
        self._reduced_source[source_id] = current
        return current

    def closure(self, root: int) -> set[int]:
        pending = [root]
        result: set[int] = set()
        while pending:
            node_id = pending.pop()
            if node_id in result:
                continue
            result.add(node_id)
            node = self.nodes[node_id]
            pending.extend(node.left)
            pending.extend(node.right)
        return result

    def irreducible(self, root: int) -> bool:
        return all(
            self.first_rewrite(node_id) is None for node_id in self.closure(root)
        )

    def explicit_game(self, root: int) -> dict[str, Any]:
        memo: dict[int, dict[str, Any]] = {}

        def build(node_id: int) -> dict[str, Any]:
            if node_id not in memo:
                node = self.nodes[node_id]
                memo[node_id] = {
                    "left": [build(option) for option in node.left],
                    "right": [build(option) for option in node.right],
                }
            return memo[node_id]

        return copy.deepcopy(build(root))


def _effective_rewrite_limit(
    profile: BoundedResourceProfile,
    maximum_rewrite_steps: int | None,
) -> int:
    if maximum_rewrite_steps is None:
        return profile.maximum_intermediate_nodes
    if type(maximum_rewrite_steps) is not int or maximum_rewrite_steps < 1:
        raise ValueError("maximum_rewrite_steps must be a positive integer")
    if maximum_rewrite_steps > profile.maximum_intermediate_nodes:
        raise ValueError(
            "maximum_rewrite_steps cannot relax the named profile's "
            "intermediate-node limit"
        )
    return maximum_rewrite_steps


def _reduce_semantic_only(
    game: dict[str, Any],
    profile: BoundedResourceProfile,
    maximum_rewrite_steps: int,
) -> tuple[
    _GameInterner,
    int,
    _SemanticReducer,
    int,
]:
    source = _GameInterner(profile)
    source_root = source.intern(game)
    source.enforce_combined_limits((source_root,))
    reducer = _SemanticReducer(source, profile, maximum_rewrite_steps)
    canonical_root = reducer.reduce_source(source_root)
    canonical_birthday = reducer.nodes[canonical_root].birthday
    if canonical_birthday > profile.maximum_canonical_birthday:
        raise ResourceLimitError(
            "canonical_birthday",
            profile.maximum_canonical_birthday,
            canonical_birthday,
        )
    return source, source_root, reducer, canonical_root


def _outcome(left_leq_right: bool, right_leq_left: bool) -> ComparisonOutcome:
    if left_leq_right and right_leq_left:
        return ComparisonOutcome.EQUAL
    if left_leq_right:
        return ComparisonOutcome.LESS
    if right_leq_left:
        return ComparisonOutcome.GREATER
    return ComparisonOutcome.FUZZY


def compare_short_game_bounded(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
) -> BoundedComparison:
    """Return the exact four-way order outcome under the bounded v1 contract."""

    interner = _GameInterner(profile)
    left_root = interner.intern(left, "left")
    right_root = interner.intern(right, "right")
    distinct, edges = interner.enforce_combined_limits((left_root, right_root))

    memo: dict[tuple[int, int], bool] = {}
    started: set[tuple[int, int]] = set()
    dependencies: dict[tuple[int, int], tuple[tuple[str, int, int], ...]] = {}

    def leq(lhs: int, rhs: int) -> bool:
        pair = (lhs, rhs)
        if pair in memo:
            return memo[pair]
        if pair in started:
            raise AssertionError("comparison recurrence was not well-founded")
        observed = len(started) + 1
        if observed > profile.maximum_comparison_dag_rows:
            raise ResourceLimitError(
                "comparison_dag_rows",
                profile.maximum_comparison_dag_rows,
                observed,
            )
        started.add(pair)
        lhs_node = interner.nodes[lhs]
        rhs_node = interner.nodes[rhs]
        children = [
            ("left_option_not_ge_right", rhs, option) for option in lhs_node.left
        ]
        children.extend(
            ("right_option_not_le_left", option, lhs) for option in rhs_node.right
        )
        children.sort(
            key=lambda row: (
                row[0],
                interner.nodes[row[1]].literal_sha256_v1,
                interner.nodes[row[2]].literal_sha256_v1,
            )
        )
        dependencies[pair] = tuple(children)
        child_results = [
            leq(child_lhs, child_rhs) for _, child_lhs, child_rhs in children
        ]
        result = not any(child_results)
        memo[pair] = result
        return result

    left_leq_right = leq(left_root, right_root)
    right_leq_left = leq(right_root, left_root)
    dag_rows = []
    for (lhs, rhs), result in memo.items():
        lhs_node = interner.nodes[lhs]
        rhs_node = interner.nodes[rhs]
        dag_rows.append(
            {
                "lhs_literal_sha256_v1": lhs_node.literal_sha256_v1,
                "rhs_literal_sha256_v1": rhs_node.literal_sha256_v1,
                "lhs_birthday": lhs_node.birthday,
                "rhs_birthday": rhs_node.birthday,
                "result": result,
                "dependencies": [
                    {
                        "kind": kind,
                        "lhs_literal_sha256_v1": interner.nodes[
                            child_lhs
                        ].literal_sha256_v1,
                        "rhs_literal_sha256_v1": interner.nodes[
                            child_rhs
                        ].literal_sha256_v1,
                    }
                    for kind, child_lhs, child_rhs in dependencies[(lhs, rhs)]
                ],
            }
        )
    dag_rows.sort(
        key=lambda row: (
            row["lhs_literal_sha256_v1"],
            row["rhs_literal_sha256_v1"],
        )
    )
    return BoundedComparison(
        left_leq_right=left_leq_right,
        right_leq_left=right_leq_left,
        outcome=_outcome(left_leq_right, right_leq_left),
        legacy_literal_left_sha256=interner.nodes[left_root].legacy_literal_sha256,
        legacy_literal_right_sha256=interner.nodes[right_root].legacy_literal_sha256,
        literal_left_sha256_v1=interner.nodes[left_root].literal_sha256_v1,
        literal_right_sha256_v1=interner.nodes[right_root].literal_sha256_v1,
        left_resources=interner.resources(left_root),
        right_resources=interner.resources(right_root),
        combined_distinct_dag_node_count=distinct,
        combined_option_reference_count=edges,
        comparison_dag_row_count=len(memo),
        game_table=interner.game_table((left_root, right_root)),
        comparison_dag=tuple(dag_rows),
    )


def equal_short_game_bounded(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
) -> bool:
    """Return semantic equality under the bounded exact relation."""

    return compare_short_game_bounded(left, right, profile=profile).equivalent


def literal_game_transport_bounded(
    game: dict[str, Any],
    *,
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
) -> dict[str, Any]:
    """Build a cross-language literal-game transport with exact measurements."""

    interner = _GameInterner(profile)
    root = interner.intern(game)
    interner.enforce_combined_limits((root,))
    node = interner.nodes[root]
    return {
        "schema_version": TRANSPORT_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "profile": profile.as_record(),
        "root_legacy_literal_sha256": node.legacy_literal_sha256,
        "root_literal_sha256_v1": node.literal_sha256_v1,
        "root_literal_serialization": node.serialization.decode("ascii"),
        "resources": interner.resources(root).as_record(),
        "game_table": list(interner.game_table((root,))),
    }


def semantic_canonical_form_bounded(
    game: dict[str, Any],
    *,
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
    maximum_rewrite_steps: int | None = None,
) -> SemanticCanonicalForm:
    """Construct and audit the deterministic semantic canonical form."""

    rewrite_limit = _effective_rewrite_limit(profile, maximum_rewrite_steps)
    source, source_root, reducer, canonical_root = _reduce_semantic_only(
        game,
        profile,
        rewrite_limit,
    )
    canonical_game = reducer.explicit_game(canonical_root)
    canonical_interner = _GameInterner(profile)
    canonical_literal_root = canonical_interner.intern(canonical_game, "canonical")
    canonical_interner.enforce_combined_limits((canonical_literal_root,))
    canonical_serialization = canonical_interner.nodes[
        canonical_literal_root
    ].serialization
    if canonical_serialization != reducer.nodes[canonical_root].serialization:
        raise AssertionError("canonical serialization changed during transport")

    soundness = compare_short_game_bounded(
        game,
        canonical_game,
        profile=profile,
    ).equivalent
    irreducible = reducer.irreducible(canonical_root)
    _, _, second_reducer, second_root = _reduce_semantic_only(
        canonical_game,
        profile,
        rewrite_limit,
    )
    idempotent = (
        second_reducer.nodes[second_root].serialization == canonical_serialization
        and not second_reducer.trace
        and second_reducer.irreducible(second_root)
    )
    if not soundness:
        raise AssertionError("canonical reduction failed the equality audit")
    if not irreducible:
        raise AssertionError("canonical reduction failed the irreducibility audit")
    if not idempotent:
        raise AssertionError("canonical reduction failed the idempotence audit")

    input_node = source.nodes[source_root]
    return SemanticCanonicalForm(
        input_legacy_literal_sha256=input_node.legacy_literal_sha256,
        input_literal_sha256_v1=input_node.literal_sha256_v1,
        canonical_serialization=canonical_serialization.decode("ascii"),
        semantic_canonical_id_v1=_sha256(
            SEMANTIC_CANONICAL_SHA256_V1_PREFIX + canonical_serialization
        ),
        canonical_game=canonical_game,
        input_resources=source.resources(source_root),
        canonical_resources=canonical_interner.resources(canonical_literal_root),
        rewrite_count=len(reducer.trace),
        rewrite_trace=tuple(copy.deepcopy(reducer.trace)),
        soundness_equal=soundness,
        irreducible=irreducible,
        idempotent=idempotent,
    )


def semantic_canonical_id_v1(
    game: dict[str, Any],
    *,
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
    maximum_rewrite_steps: int | None = None,
) -> str:
    """Return the domain-separated semantic identity of an explicit short game."""

    return semantic_canonical_form_bounded(
        game,
        profile=profile,
        maximum_rewrite_steps=maximum_rewrite_steps,
    ).semantic_canonical_id_v1


def validate_semantic_canonical_form_bounded(
    game: dict[str, Any],
    claimed_canonical_game: dict[str, Any],
    *,
    claimed_semantic_canonical_id_v1: str | None = None,
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
    maximum_rewrite_steps: int | None = None,
) -> tuple[bool, str]:
    """Recompute and validate one claimed semantic canonical form."""

    try:
        observed = semantic_canonical_form_bounded(
            game,
            profile=profile,
            maximum_rewrite_steps=maximum_rewrite_steps,
        )
        claimed_transport = literal_game_transport_bounded(
            claimed_canonical_game,
            profile=profile,
        )
        if (
            claimed_transport["root_literal_serialization"]
            != observed.canonical_serialization
        ):
            raise ValueError("claimed canonical form is not the deterministic form")
        if (
            claimed_semantic_canonical_id_v1 is not None
            and claimed_semantic_canonical_id_v1 != observed.semantic_canonical_id_v1
        ):
            raise ValueError("claimed semantic canonical identifier mismatch")
    except (
        BoundedGameContractError,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        return False, str(error)
    return True, "valid"


def _binding(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} binding must be an object")
    canonical_json_bytes(value)
    return copy.deepcopy(value)


def build_short_game_comparison_certificate_v1(
    candidate: dict[str, Any],
    target: dict[str, Any],
    *,
    candidate_binding: dict[str, Any],
    target_binding: dict[str, Any],
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
) -> dict[str, Any]:
    """Build a self-contained exact comparison certificate for any outcome."""

    comparison = compare_short_game_bounded(candidate, target, profile=profile)
    payload = {
        "schema_version": CERTIFICATE_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "profile": profile.as_record(),
        "bindings": {
            "candidate": _binding(candidate_binding, "candidate"),
            "target": _binding(target_binding, "target"),
        },
        "roots": {
            "candidate_legacy_literal_sha256": (comparison.legacy_literal_left_sha256),
            "target_legacy_literal_sha256": (comparison.legacy_literal_right_sha256),
            "candidate_literal_sha256_v1": comparison.literal_left_sha256_v1,
            "target_literal_sha256_v1": comparison.literal_right_sha256_v1,
        },
        "resources": {
            "candidate": comparison.left_resources.as_record(),
            "target": comparison.right_resources.as_record(),
            "combined_distinct_dag_node_count": (
                comparison.combined_distinct_dag_node_count
            ),
            "combined_option_reference_count": (
                comparison.combined_option_reference_count
            ),
            "comparison_dag_row_count": comparison.comparison_dag_row_count,
        },
        "game_table": list(comparison.game_table),
        "comparison_dag": list(comparison.comparison_dag),
        "verdict": {
            "candidate_leq_target": comparison.left_leq_right,
            "target_leq_candidate": comparison.right_leq_left,
            "outcome": comparison.outcome.value,
            "equivalent": comparison.equivalent,
        },
        "semantic_canonical": {
            "status": CANONICALIZATION_STATUS,
            "candidate_semantic_canonical_id": None,
            "target_semantic_canonical_id": None,
        },
    }
    certificate = copy.deepcopy(payload)
    certificate["certificate_sha256"] = _sha256(canonical_json_bytes(payload))
    certificate_bytes = len(canonical_json_bytes(certificate))
    if certificate_bytes > profile.maximum_certificate_bytes:
        raise ResourceLimitError(
            "certificate_bytes",
            profile.maximum_certificate_bytes,
            certificate_bytes,
        )
    valid, reason = verify_short_game_comparison_certificate_v1(
        certificate,
        expected_candidate_binding=candidate_binding,
        expected_target_binding=target_binding,
    )
    if not valid:
        raise AssertionError(f"built certificate failed self-verification: {reason}")
    return certificate


def _exact_keys(value: Any, expected: set[str], context: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{context} has unexpected or missing fields")


def _verify_resource_record(
    record: Any,
    expected: LiteralResourceUsage,
    context: str,
) -> None:
    if record != expected.as_record():
        raise ValueError(f"{context} resource measurements mismatch")


def verify_short_game_comparison_certificate_v1(
    certificate: Any,
    *,
    expected_candidate_binding: dict[str, Any] | None = None,
    expected_target_binding: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Replay a v1 certificate without trusting its comparison verdicts."""

    try:
        _exact_keys(
            certificate,
            {
                "schema_version",
                "contract_id",
                "profile",
                "bindings",
                "roots",
                "resources",
                "game_table",
                "comparison_dag",
                "verdict",
                "semantic_canonical",
                "certificate_sha256",
            },
            "certificate",
        )
        if certificate["schema_version"] != CERTIFICATE_SCHEMA_VERSION:
            raise ValueError("unsupported certificate schema")
        if certificate["contract_id"] != CONTRACT_ID:
            raise ValueError("contract identifier mismatch")
        supplied_hash = certificate["certificate_sha256"]
        if not isinstance(supplied_hash, str) or not _HEX_256.fullmatch(supplied_hash):
            raise ValueError("certificate hash is malformed")
        payload = copy.deepcopy(certificate)
        payload.pop("certificate_sha256")
        if _sha256(canonical_json_bytes(payload)) != supplied_hash:
            raise ValueError("certificate hash mismatch")
        profile = BoundedResourceProfile.from_record(certificate["profile"])
        certificate_bytes = len(canonical_json_bytes(certificate))
        if certificate_bytes > profile.maximum_certificate_bytes:
            raise ResourceLimitError(
                "certificate_bytes",
                profile.maximum_certificate_bytes,
                certificate_bytes,
            )

        _exact_keys(certificate["bindings"], {"candidate", "target"}, "bindings")
        for name in ("candidate", "target"):
            if not isinstance(certificate["bindings"][name], dict):
                raise ValueError(f"{name} binding must be an object")
            canonical_json_bytes(certificate["bindings"][name])
        if (
            expected_candidate_binding is not None
            and certificate["bindings"]["candidate"] != expected_candidate_binding
        ):
            raise ValueError("candidate binding mismatch")
        if (
            expected_target_binding is not None
            and certificate["bindings"]["target"] != expected_target_binding
        ):
            raise ValueError("target binding mismatch")

        _exact_keys(
            certificate["roots"],
            {
                "candidate_legacy_literal_sha256",
                "target_legacy_literal_sha256",
                "candidate_literal_sha256_v1",
                "target_literal_sha256_v1",
            },
            "roots",
        )
        candidate_root = certificate["roots"]["candidate_literal_sha256_v1"]
        target_root = certificate["roots"]["target_literal_sha256_v1"]
        candidate_legacy_root = certificate["roots"]["candidate_legacy_literal_sha256"]
        target_legacy_root = certificate["roots"]["target_legacy_literal_sha256"]
        if not all(
            isinstance(value, str) and _HEX_256.fullmatch(value)
            for value in (
                candidate_root,
                target_root,
                candidate_legacy_root,
                target_legacy_root,
            )
        ):
            raise ValueError("root literal digest is malformed")

        rows = certificate["game_table"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("game table must be a nonempty list")
        maximum_source_rows = 2 * profile.maximum_source_nodes_per_root
        if len(rows) > maximum_source_rows:
            raise ResourceLimitError(
                "combined_source_nodes",
                maximum_source_rows,
                len(rows),
            )
        if rows != sorted(rows, key=lambda row: row.get("literal_sha256_v1", "")):
            raise ValueError("game table is not in canonical order")
        games: dict[str, dict[str, Any]] = {}
        legacy_serializations: dict[str, str] = {}
        for row in rows:
            _exact_keys(
                row,
                {
                    "legacy_literal_sha256",
                    "literal_sha256_v1",
                    "literal_serialization",
                    "left_options",
                    "right_options",
                    "birthday",
                },
                "game-table row",
            )
            legacy_digest = row["legacy_literal_sha256"]
            digest = row["literal_sha256_v1"]
            serialization = row["literal_serialization"]
            if (
                not isinstance(digest, str)
                or not _HEX_256.fullmatch(digest)
                or not isinstance(legacy_digest, str)
                or not _HEX_256.fullmatch(legacy_digest)
                or not isinstance(serialization, str)
            ):
                raise ValueError("game-table identity is malformed")
            try:
                serialization_bytes = serialization.encode("ascii")
            except UnicodeEncodeError as error:
                raise ValueError("literal serialization must be ASCII") from error
            if _sha256(serialization_bytes) != legacy_digest:
                raise ValueError("legacy literal digest does not bind serialization")
            if _literal_sha256_v1(serialization_bytes) != digest:
                raise ValueError("versioned literal digest does not bind serialization")
            if digest in games:
                raise ValueError("duplicate game-table row")
            prior_serialization = legacy_serializations.get(legacy_digest)
            if prior_serialization is not None and prior_serialization != serialization:
                raise DigestCollisionError(
                    "legacy literal digest binds distinct serializations"
                )
            legacy_serializations[legacy_digest] = serialization
            for side in ("left_options", "right_options"):
                options = row[side]
                if (
                    not isinstance(options, list)
                    or len(options) != len(set(options))
                    or any(
                        not isinstance(option, str) or not _HEX_256.fullmatch(option)
                        for option in options
                    )
                ):
                    raise ValueError("option list is malformed")
                if len(options) > profile.maximum_options_per_side:
                    raise ResourceLimitError(
                        f"{side[:-8]}_options_per_node",
                        profile.maximum_options_per_side,
                        len(options),
                    )
            if type(row["birthday"]) is not int or row["birthday"] < 0:
                raise ValueError("birthday is malformed")
            games[digest] = row
        if candidate_root not in games or target_root not in games:
            raise ValueError("a root is absent from the game table")
        if (
            games[candidate_root]["legacy_literal_sha256"] != candidate_legacy_root
            or games[target_root]["legacy_literal_sha256"] != target_legacy_root
        ):
            raise ValueError("legacy root literal digest mismatch")

        birthdays: dict[str, int] = {}
        active: set[str] = set()

        def validate_game(digest: str) -> int:
            if digest in birthdays:
                return birthdays[digest]
            if digest in active:
                raise ValueError("game table contains a cycle")
            if digest not in games:
                raise ValueError("game table references a missing option")
            active.add(digest)
            row = games[digest]
            left = row["left_options"]
            right = row["right_options"]
            option_birthdays = [validate_game(option) for option in left + right]
            left_serializations = [
                games[option]["literal_serialization"] for option in left
            ]
            right_serializations = [
                games[option]["literal_serialization"] for option in right
            ]
            if left_serializations != sorted(set(left_serializations)):
                raise ValueError("left options are not a canonical set")
            if right_serializations != sorted(set(right_serializations)):
                raise ValueError("right options are not a canonical set")
            reconstructed = (
                "{"
                + ",".join(left_serializations)
                + "|"
                + ",".join(right_serializations)
                + "}"
            )
            if reconstructed != row["literal_serialization"]:
                raise ValueError("literal serialization does not match options")
            expected_birthday = 0 if not option_birthdays else 1 + max(option_birthdays)
            if row["birthday"] != expected_birthday:
                raise ValueError("birthday mismatch")
            if expected_birthday > profile.maximum_root_birthday:
                raise ResourceLimitError(
                    "root_birthday",
                    profile.maximum_root_birthday,
                    expected_birthday,
                )
            active.remove(digest)
            birthdays[digest] = expected_birthday
            return expected_birthday

        validate_game(candidate_root)
        validate_game(target_root)
        reachable_games: set[str] = set()
        pending_games = [candidate_root, target_root]
        while pending_games:
            digest = pending_games.pop()
            if digest in reachable_games:
                continue
            reachable_games.add(digest)
            pending_games.extend(
                games[digest]["left_options"] + games[digest]["right_options"]
            )
        if reachable_games != set(games):
            raise ValueError("game table contains unreachable rows")
        distinct_count = len(reachable_games)
        edge_count = sum(
            len(games[digest]["left_options"]) + len(games[digest]["right_options"])
            for digest in reachable_games
        )

        def closure(root: str) -> set[str]:
            result: set[str] = set()
            pending = [root]
            while pending:
                digest = pending.pop()
                if digest in result:
                    continue
                result.add(digest)
                pending.extend(
                    games[digest]["left_options"] + games[digest]["right_options"]
                )
            return result

        for root in (candidate_root, target_root):
            source_nodes = len(closure(root))
            if source_nodes > profile.maximum_source_nodes_per_root:
                raise ResourceLimitError(
                    "source_nodes_per_root",
                    profile.maximum_source_nodes_per_root,
                    source_nodes,
                )
        if distinct_count > profile.maximum_intermediate_nodes:
            raise ResourceLimitError(
                "intermediate_nodes",
                profile.maximum_intermediate_nodes,
                distinct_count,
            )
        if edge_count > profile.maximum_option_references:
            raise ResourceLimitError(
                "option_references",
                profile.maximum_option_references,
                edge_count,
            )
        for root in (candidate_root, target_root):
            size = len(games[root]["literal_serialization"].encode("ascii"))
            if size > profile.maximum_literal_serialization_bytes_per_root:
                raise ResourceLimitError(
                    "literal_serialization_bytes_per_root",
                    profile.maximum_literal_serialization_bytes_per_root,
                    size,
                )

        def occurrence_count(root: str) -> int:
            memo: dict[str, int] = {}

            def visit(digest: str) -> int:
                if digest not in memo:
                    row = games[digest]
                    memo[digest] = 1 + sum(
                        visit(child)
                        for child in row["left_options"] + row["right_options"]
                    )
                return memo[digest]

            return visit(root)

        def usage(root: str) -> LiteralResourceUsage:
            root_closure = closure(root)
            return LiteralResourceUsage(
                root_birthday=birthdays[root],
                literal_occurrence_node_count=occurrence_count(root),
                literal_distinct_dag_node_count=len(root_closure),
                literal_option_reference_count=sum(
                    len(games[digest]["left_options"])
                    + len(games[digest]["right_options"])
                    for digest in root_closure
                ),
                literal_serialization_bytes=len(
                    games[root]["literal_serialization"].encode("ascii")
                ),
            )

        dag_rows = certificate["comparison_dag"]
        if not isinstance(dag_rows, list) or not dag_rows:
            raise ValueError("comparison DAG must be a nonempty list")
        if len(dag_rows) > profile.maximum_comparison_dag_rows:
            raise ResourceLimitError(
                "comparison_dag_rows",
                profile.maximum_comparison_dag_rows,
                len(dag_rows),
            )
        if dag_rows != sorted(
            dag_rows,
            key=lambda row: (
                row.get("lhs_literal_sha256_v1", ""),
                row.get("rhs_literal_sha256_v1", ""),
            ),
        ):
            raise ValueError("comparison DAG is not in canonical order")
        comparisons: dict[tuple[str, str], dict[str, Any]] = {}
        for row in dag_rows:
            _exact_keys(
                row,
                {
                    "lhs_literal_sha256_v1",
                    "rhs_literal_sha256_v1",
                    "lhs_birthday",
                    "rhs_birthday",
                    "result",
                    "dependencies",
                },
                "comparison row",
            )
            pair = (
                row["lhs_literal_sha256_v1"],
                row["rhs_literal_sha256_v1"],
            )
            if pair in comparisons:
                raise ValueError("duplicate comparison row")
            if pair[0] not in games or pair[1] not in games:
                raise ValueError("comparison references a missing game")
            if (
                row["lhs_birthday"] != birthdays[pair[0]]
                or row["rhs_birthday"] != birthdays[pair[1]]
            ):
                raise ValueError("comparison birthday mismatch")
            if type(row["result"]) is not bool:
                raise ValueError("comparison result is not Boolean")
            comparisons[pair] = row

        reachable_pairs: set[tuple[str, str]] = set()
        pending_pairs = [
            (candidate_root, target_root),
            (target_root, candidate_root),
        ]
        while pending_pairs:
            pair = pending_pairs.pop()
            if pair in reachable_pairs:
                continue
            if pair not in comparisons:
                raise ValueError("comparison DAG is not closed")
            reachable_pairs.add(pair)
            lhs, rhs = pair
            expected_dependencies = [
                {
                    "kind": "left_option_not_ge_right",
                    "lhs_literal_sha256_v1": rhs,
                    "rhs_literal_sha256_v1": option,
                }
                for option in games[lhs]["left_options"]
            ]
            expected_dependencies.extend(
                {
                    "kind": "right_option_not_le_left",
                    "lhs_literal_sha256_v1": option,
                    "rhs_literal_sha256_v1": lhs,
                }
                for option in games[rhs]["right_options"]
            )
            expected_dependencies.sort(
                key=lambda row: (
                    row["kind"],
                    row["lhs_literal_sha256_v1"],
                    row["rhs_literal_sha256_v1"],
                )
            )
            if comparisons[pair]["dependencies"] != expected_dependencies:
                raise ValueError("comparison dependency list is not exact")
            child_pairs = [
                (
                    dependency["lhs_literal_sha256_v1"],
                    dependency["rhs_literal_sha256_v1"],
                )
                for dependency in expected_dependencies
            ]
            for child in child_pairs:
                if child not in comparisons:
                    raise ValueError("comparison dependency row is missing")
                if (
                    birthdays[child[0]] + birthdays[child[1]]
                    >= birthdays[lhs] + birthdays[rhs]
                ):
                    raise ValueError("comparison dependency is not well-founded")
            expected_result = not any(
                comparisons[child]["result"] for child in child_pairs
            )
            if comparisons[pair]["result"] != expected_result:
                raise ValueError("comparison recurrence is false")
            pending_pairs.extend(child_pairs)
        if reachable_pairs != set(comparisons):
            raise ValueError("comparison DAG contains unreachable rows")

        candidate_leq_target = comparisons[(candidate_root, target_root)]["result"]
        target_leq_candidate = comparisons[(target_root, candidate_root)]["result"]
        expected_outcome = _outcome(candidate_leq_target, target_leq_candidate)
        verdict = certificate["verdict"]
        _exact_keys(
            verdict,
            {
                "candidate_leq_target",
                "target_leq_candidate",
                "outcome",
                "equivalent",
            },
            "verdict",
        )
        expected_verdict = {
            "candidate_leq_target": candidate_leq_target,
            "target_leq_candidate": target_leq_candidate,
            "outcome": expected_outcome.value,
            "equivalent": expected_outcome is ComparisonOutcome.EQUAL,
        }
        if verdict != expected_verdict:
            raise ValueError("comparison verdict mismatch")

        semantic = certificate["semantic_canonical"]
        _exact_keys(
            semantic,
            {
                "status",
                "candidate_semantic_canonical_id",
                "target_semantic_canonical_id",
            },
            "semantic canonical boundary",
        )
        if semantic != {
            "status": CANONICALIZATION_STATUS,
            "candidate_semantic_canonical_id": None,
            "target_semantic_canonical_id": None,
        }:
            raise ValueError("unsupported semantic canonical claim")

        resources = certificate["resources"]
        _exact_keys(
            resources,
            {
                "candidate",
                "target",
                "combined_distinct_dag_node_count",
                "combined_option_reference_count",
                "comparison_dag_row_count",
            },
            "resources",
        )
        _verify_resource_record(
            resources["candidate"], usage(candidate_root), "candidate"
        )
        _verify_resource_record(resources["target"], usage(target_root), "target")
        if resources["combined_distinct_dag_node_count"] != distinct_count:
            raise ValueError("combined distinct-DAG-node count mismatch")
        if resources["combined_option_reference_count"] != edge_count:
            raise ValueError("combined option-reference count mismatch")
        if resources["comparison_dag_row_count"] != len(comparisons):
            raise ValueError("comparison-DAG-row count mismatch")
    except (
        BoundedGameContractError,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        return False, str(error)
    return True, "valid"


def _explicit_game_from_certificate(
    certificate: dict[str, Any],
    root: str,
) -> dict[str, Any]:
    rows = {row["literal_sha256_v1"]: row for row in certificate["game_table"]}
    memo: dict[str, dict[str, Any]] = {}

    def build(digest: str) -> dict[str, Any]:
        if digest not in memo:
            row = rows[digest]
            memo[digest] = {
                "left": [build(option) for option in row["left_options"]],
                "right": [build(option) for option in row["right_options"]],
            }
        return memo[digest]

    return copy.deepcopy(build(root))


def build_short_game_comparison_certificate_v2(
    candidate: dict[str, Any],
    target: dict[str, Any],
    *,
    candidate_binding: dict[str, Any],
    target_binding: dict[str, Any],
    profile: BoundedResourceProfile = DEFAULT_RESOURCE_PROFILE,
    maximum_rewrite_steps: int | None = None,
) -> dict[str, Any]:
    """Build an additive v2 certificate binding independent semantic IDs."""

    rewrite_limit = _effective_rewrite_limit(profile, maximum_rewrite_steps)
    certificate = build_short_game_comparison_certificate_v1(
        candidate,
        target,
        candidate_binding=candidate_binding,
        target_binding=target_binding,
        profile=profile,
    )
    candidate_canonical = semantic_canonical_form_bounded(
        candidate,
        profile=profile,
        maximum_rewrite_steps=rewrite_limit,
    )
    target_canonical = semantic_canonical_form_bounded(
        target,
        profile=profile,
        maximum_rewrite_steps=rewrite_limit,
    )
    certificate["schema_version"] = CERTIFICATE_SCHEMA_VERSION_V2
    certificate["semantic_canonical"] = {
        "status": INDEPENDENT_CANONICALIZATION_STATUS,
        "candidate_semantic_canonical_id": (
            candidate_canonical.semantic_canonical_id_v1
        ),
        "target_semantic_canonical_id": (target_canonical.semantic_canonical_id_v1),
        "maximum_rewrite_steps": rewrite_limit,
    }
    certificate.pop("certificate_sha256")
    certificate["certificate_sha256"] = _sha256(canonical_json_bytes(certificate))
    certificate_bytes = len(canonical_json_bytes(certificate))
    if certificate_bytes > profile.maximum_certificate_bytes:
        raise ResourceLimitError(
            "certificate_bytes",
            profile.maximum_certificate_bytes,
            certificate_bytes,
        )
    valid, reason = verify_short_game_comparison_certificate_v2(
        certificate,
        expected_candidate_binding=candidate_binding,
        expected_target_binding=target_binding,
        maximum_rewrite_steps=rewrite_limit,
    )
    if not valid:
        raise AssertionError(f"built v2 certificate failed self-verification: {reason}")
    return certificate


def verify_short_game_comparison_certificate_v2(
    certificate: Any,
    *,
    expected_candidate_binding: dict[str, Any] | None = None,
    expected_target_binding: dict[str, Any] | None = None,
    maximum_rewrite_steps: int | None = None,
) -> tuple[bool, str]:
    """Replay comparison recurrence and semantic reduction for a v2 certificate."""

    try:
        _exact_keys(
            certificate,
            {
                "schema_version",
                "contract_id",
                "profile",
                "bindings",
                "roots",
                "resources",
                "game_table",
                "comparison_dag",
                "verdict",
                "semantic_canonical",
                "certificate_sha256",
            },
            "certificate",
        )
        if certificate["schema_version"] != CERTIFICATE_SCHEMA_VERSION_V2:
            raise ValueError("unsupported v2 certificate schema")
        supplied_hash = certificate["certificate_sha256"]
        if not isinstance(supplied_hash, str) or not _HEX_256.fullmatch(supplied_hash):
            raise ValueError("certificate hash is malformed")
        payload = copy.deepcopy(certificate)
        payload.pop("certificate_sha256")
        if _sha256(canonical_json_bytes(payload)) != supplied_hash:
            raise ValueError("certificate hash mismatch")
        profile = BoundedResourceProfile.from_record(certificate["profile"])
        certificate_bytes = len(canonical_json_bytes(certificate))
        if certificate_bytes > profile.maximum_certificate_bytes:
            raise ResourceLimitError(
                "certificate_bytes",
                profile.maximum_certificate_bytes,
                certificate_bytes,
            )

        semantic = certificate["semantic_canonical"]
        _exact_keys(
            semantic,
            {
                "status",
                "candidate_semantic_canonical_id",
                "target_semantic_canonical_id",
                "maximum_rewrite_steps",
            },
            "semantic canonical boundary",
        )
        if semantic["status"] != INDEPENDENT_CANONICALIZATION_STATUS:
            raise ValueError("unsupported independent canonicalization status")
        for field in (
            "candidate_semantic_canonical_id",
            "target_semantic_canonical_id",
        ):
            if not isinstance(semantic[field], str) or not _HEX_256.fullmatch(
                semantic[field]
            ):
                raise ValueError("semantic canonical identifier is malformed")
        rewrite_limit = _effective_rewrite_limit(
            profile,
            semantic["maximum_rewrite_steps"],
        )
        if maximum_rewrite_steps is not None and rewrite_limit != maximum_rewrite_steps:
            raise ValueError("canonical rewrite limit mismatch")

        comparison_only = copy.deepcopy(certificate)
        comparison_only["schema_version"] = CERTIFICATE_SCHEMA_VERSION
        comparison_only["semantic_canonical"] = {
            "status": CANONICALIZATION_STATUS,
            "candidate_semantic_canonical_id": None,
            "target_semantic_canonical_id": None,
        }
        comparison_only.pop("certificate_sha256")
        comparison_only["certificate_sha256"] = _sha256(
            canonical_json_bytes(comparison_only)
        )
        valid, reason = verify_short_game_comparison_certificate_v1(
            comparison_only,
            expected_candidate_binding=expected_candidate_binding,
            expected_target_binding=expected_target_binding,
        )
        if not valid:
            raise ValueError(f"embedded v1 comparison is invalid: {reason}")

        candidate = _explicit_game_from_certificate(
            certificate,
            certificate["roots"]["candidate_literal_sha256_v1"],
        )
        target = _explicit_game_from_certificate(
            certificate,
            certificate["roots"]["target_literal_sha256_v1"],
        )
        candidate_id = semantic_canonical_id_v1(
            candidate,
            profile=profile,
            maximum_rewrite_steps=rewrite_limit,
        )
        target_id = semantic_canonical_id_v1(
            target,
            profile=profile,
            maximum_rewrite_steps=rewrite_limit,
        )
        if semantic["candidate_semantic_canonical_id"] != candidate_id:
            raise ValueError("candidate semantic canonical identifier mismatch")
        if semantic["target_semantic_canonical_id"] != target_id:
            raise ValueError("target semantic canonical identifier mismatch")
        if certificate["verdict"]["equivalent"] != (candidate_id == target_id):
            raise ValueError("comparison equality and semantic identity disagree")
    except (
        BoundedGameContractError,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        return False, str(error)
    return True, "valid"


__all__ = [
    "BoundedComparison",
    "BoundedGameContractError",
    "BoundedResourceProfile",
    "CANONICALIZATION_STATUS",
    "CERTIFICATE_SCHEMA_VERSION",
    "CERTIFICATE_SCHEMA_VERSION_V2",
    "CONTRACT_ID",
    "ComparisonOutcome",
    "DEFAULT_RESOURCE_PROFILE",
    "DIGRAPH8_RESOURCE_PROFILE",
    "DigestCollisionError",
    "InvalidGameError",
    "INDEPENDENT_CANONICALIZATION_STATUS",
    "LITERAL_SHA256_V1_PREFIX",
    "LiteralResourceUsage",
    "ORDER7_RESOURCE_PROFILE",
    "ResourceLimitError",
    "SEMANTIC_CANONICAL_SHA256_V1_PREFIX",
    "SemanticCanonicalForm",
    "TRANSPORT_SCHEMA_VERSION",
    "build_short_game_comparison_certificate_v1",
    "build_short_game_comparison_certificate_v2",
    "canonical_json_bytes",
    "compare_short_game_bounded",
    "equal_short_game_bounded",
    "literal_game_transport_bounded",
    "semantic_canonical_form_bounded",
    "semantic_canonical_id_v1",
    "validate_semantic_canonical_form_bounded",
    "verify_short_game_comparison_certificate_v1",
    "verify_short_game_comparison_certificate_v2",
]
