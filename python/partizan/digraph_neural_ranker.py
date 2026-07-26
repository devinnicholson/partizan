"""Deterministic neural proposal ranking for order-7 Digraph Placement.

The ranker consumes fields available before exact evaluation.  It never
replaces the exact verifier.  Historical event ledgers supply labels for
training and retrospective evaluation; rank artifacts contain no outcomes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any, Iterable, Iterator, Mapping, Sequence

try:
    import numpy as np
except ImportError as error:  # pragma: no cover - exercised by packaging
    raise RuntimeError(
        "the neural ranker requires NumPy; install partizan-cgt[neural]"
    ) from error


MODEL_SCHEMA = "partizan.digraph_order7_neural_ranker.v0.1"
ENSEMBLE_SCHEMA = "partizan.digraph_order7_neural_ensemble.v0.1"
GRID_REPORT_SCHEMA = "partizan.digraph_order7_neural_grid_report.v0.1"
REPORT_SCHEMA = "partizan.digraph_order7_neural_ranker_report.v0.1"
RANK_SCHEMA = "partizan.digraph_order7_neural_rank.v0.1"
FEATURE_CONTRACT = "partizan.digraph_order7_proposal_features.v0.1"
TRAINING_CONTRACT = "v1_full_ledger_training_only.v0.1"
POOL_CONTRACT = "toggle_one_arc_same_operator_pool.v0.1"
ARCHITECTURE = "directed_message_passing_graph_classifier_v1"
TARGETS = ("0", "*", "{0|1}")
OPERATORS = (
    "flip_colour",
    "toggle_one_arc",
    "toggle_two_arcs",
    "uniform_immigrant",
)
NODE_FEATURE_NAMES = ("is_blue", "is_red")
TARGET_EMBEDDING_WIDTH = 8
GRID_HIDDEN_WIDTHS = (32, 64)
GRID_LAYER_COUNTS = (2, 3)
GRID_LEARNING_RATES = (0.001, 0.0003)
ENSEMBLE_SEEDS = (
    10025726846852382910,
    7606199125901481151,
    1358850120366438448,
)
TRAINING_EPOCHS = 80
TRAINING_BATCH_SIZE = 256
TRAINING_WEIGHT_DECAY = 0.0001
TRAINING_DROPOUT = 0.1
DEFAULT_BUDGETS = (64, 256, 512, 1_024)
OUTCOME_FIELDS_FORBIDDEN_IN_POOL_SCORING = frozenset(
    {
        "descriptors",
        "eligible_for_validation_metric",
        "equality_certificate_sha256",
        "exact_decision",
        "exclusion_reasons",
        "literal_game_sha256",
        "measurements",
        "quotient",
        "rejection",
        "retention",
        "sidecars",
        "structural_quotient",
        "training_candidate_collision",
        "training_quotient_collision",
        "transition",
        "weakly_connected",
    }
)


class RankerContractError(ValueError):
    """Raised when a proposal or model violates the frozen ranker contract."""


@dataclass(frozen=True)
class ExampleMetadata:
    """Fields used for splitting, tie-breaking, and offline evaluation."""

    candidate_sha256: str
    target: str
    base_seed: int
    operator: str
    pool_id: str | None
    quotient_sha256: str | None
    literal_game_sha256: str | None
    global_event_index: int | None
    declared_weakly_connected: bool | None
    declared_training_candidate_collision: bool | None
    declared_training_quotient_collision: bool | None
    eligible_for_validation_metric: bool | None
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class Corpus:
    """Compact NumPy projection of an event or proposal JSONL artifact."""

    node_features: np.ndarray
    adjacency: np.ndarray
    target_indices: np.ndarray
    labels: np.ndarray | None
    metadata: tuple[ExampleMetadata, ...]
    source_sha256: str
    row_count: int
    censored_by_rejection_stage: Mapping[str, int]
    censored_by_rejection_reason: Mapping[str, int]


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON deterministically with one trailing newline."""

    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _candidate_digest(candidate: Mapping[str, Any]) -> str:
    payload = json.dumps(
        candidate,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _graph_arrays(
    candidate: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    if candidate.get("order") != 7:
        raise RankerContractError("candidate.order must equal 7")

    blue_value = candidate.get("blue_vertices")
    if not isinstance(blue_value, list):
        raise RankerContractError("candidate.blue_vertices must be a list")
    if any(
        not isinstance(vertex, int) or isinstance(vertex, bool) or not 0 <= vertex < 7
        for vertex in blue_value
    ):
        raise RankerContractError("candidate.blue_vertices contains an invalid vertex")
    if len(set(blue_value)) != len(blue_value):
        raise RankerContractError("candidate.blue_vertices contains duplicates")

    arc_value = candidate.get("arcs")
    if not isinstance(arc_value, list):
        raise RankerContractError("candidate.arcs must be a list")
    arcs: set[tuple[int, int]] = set()
    for arc in arc_value:
        if (
            not isinstance(arc, list)
            or len(arc) != 2
            or any(
                not isinstance(vertex, int)
                or isinstance(vertex, bool)
                or not 0 <= vertex < 7
                for vertex in arc
            )
            or arc[0] == arc[1]
        ):
            raise RankerContractError("candidate.arcs contains an invalid directed arc")
        arcs.add((arc[0], arc[1]))
    if len(arcs) != len(arc_value):
        raise RankerContractError("candidate.arcs contains duplicates")

    blue = np.zeros(7, dtype=np.float64)
    blue[list(blue_value)] = 1.0
    adjacency = np.zeros((7, 7), dtype=np.float64)
    for source, target in arcs:
        adjacency[source, target] = 1.0
    return blue, adjacency


def _weakly_connected(adjacency: np.ndarray) -> bool:
    undirected = np.logical_or(adjacency > 0.0, adjacency.T > 0.0)
    seen = {0}
    pending = [0]
    while pending:
        source = pending.pop()
        for target in np.flatnonzero(undirected[source]).tolist():
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return len(seen) == 7


def _pool_id_from_row(row: Mapping[str, Any]) -> str | None:
    """Read either supported outcome-free pool envelope.

    The public proposal API historically nested this identifier under
    ``ranker_pool``.  The frozen validation-ledger schema commits it at the
    top level.  Accepting both keeps the scorer compatible with that schema;
    supplying two conflicting identifiers fails closed.
    """

    nested_pool_id: str | None = None
    ranker_pool = row.get("ranker_pool")
    if ranker_pool is not None:
        if not isinstance(ranker_pool, Mapping):
            raise RankerContractError("ranker_pool must be an object")
        value = ranker_pool.get("pool_id")
        if not isinstance(value, str) or not value:
            raise RankerContractError("ranker_pool.pool_id must be non-empty")
        nested_pool_id = value

    top_level_pool_id: str | None = None
    if "pool_id" in row:
        value = row.get("pool_id")
        if not isinstance(value, str) or not value:
            raise RankerContractError("pool_id must be a non-empty string")
        top_level_pool_id = value

    if (
        nested_pool_id is not None
        and top_level_pool_id is not None
        and nested_pool_id != top_level_pool_id
    ):
        raise RankerContractError("top-level and nested pool ids disagree")
    return top_level_pool_id or nested_pool_id


def proposal_features(
    row: Mapping[str, Any],
    *,
    include_outcome_metadata: bool = False,
) -> tuple[np.ndarray, np.ndarray, int, ExampleMetadata]:
    """Project one proposal without reading any verifier-derived field.

    The node encoder is permutation equivariant and the model mean-pools the
    node embeddings, making the final score invariant to vertex relabeling.
    """

    candidate = row.get("candidate")
    if not isinstance(candidate, Mapping):
        raise RankerContractError("candidate must be an object")
    blue, adjacency = _graph_arrays(candidate)
    red = 1.0 - blue

    nodes = np.column_stack((blue, red))

    target = row.get("target")
    if target not in TARGETS:
        raise RankerContractError(f"unsupported target: {target!r}")
    proposal = row.get("proposal")
    if not isinstance(proposal, Mapping):
        raise RankerContractError("proposal must be an object")
    operator = proposal.get("operator")
    if operator not in OPERATORS:
        raise RankerContractError(f"unsupported proposal operator: {operator!r}")

    target_index = TARGETS.index(str(target))

    candidate_sha = row.get("candidate_sha256")
    computed_sha = _candidate_digest(candidate)
    if candidate_sha is None:
        candidate_sha = computed_sha
    if not _is_sha256(candidate_sha):
        raise RankerContractError("candidate_sha256 must be lowercase SHA-256")
    if candidate_sha != computed_sha:
        raise RankerContractError("candidate_sha256 does not match candidate")

    base_seed = row.get("base_seed")
    if not isinstance(base_seed, int) or isinstance(base_seed, bool) or base_seed < 0:
        raise RankerContractError("base_seed must be a non-negative integer")
    global_event_index = row.get("global_event_index")
    if global_event_index is not None and (
        not isinstance(global_event_index, int)
        or isinstance(global_event_index, bool)
        or global_event_index < 0
    ):
        raise RankerContractError(
            "global_event_index must be a non-negative integer when present"
        )

    quotient_sha: str | None = None
    literal_sha: str | None = None
    if include_outcome_metadata:
        quotient = row.get("structural_quotient")
        if not isinstance(quotient, Mapping):
            quotient = row.get("quotient")
        if isinstance(quotient, Mapping) and _is_sha256(
            quotient.get("quotient_sha256")
        ):
            quotient_sha = str(quotient["quotient_sha256"])
        decision = row.get("exact_decision")
        if isinstance(decision, Mapping) and _is_sha256(
            decision.get("candidate_root_game_sha256")
        ):
            literal_sha = str(decision["candidate_root_game_sha256"])

    eligible_marker: bool | None = None
    if include_outcome_metadata and "eligible_for_validation_metric" in row:
        if not isinstance(row["eligible_for_validation_metric"], bool):
            raise RankerContractError("eligible_for_validation_metric must be boolean")
        eligible_marker = row["eligible_for_validation_metric"]

    exclusion_reasons: tuple[str, ...] = ()
    if include_outcome_metadata and "exclusion_reasons" in row:
        reasons = row["exclusion_reasons"]
        if (
            not isinstance(reasons, list)
            or any(not isinstance(reason, str) or not reason for reason in reasons)
            or len(set(reasons)) != len(reasons)
        ):
            raise RankerContractError(
                "exclusion_reasons must contain unique non-empty strings"
            )
        exclusion_reasons = tuple(reasons)

    def optional_boolean(field: str) -> bool | None:
        if not include_outcome_metadata or field not in row:
            return None
        value = row[field]
        if not isinstance(value, bool):
            raise RankerContractError(f"{field} must be boolean")
        return value

    metadata = ExampleMetadata(
        candidate_sha256=candidate_sha,
        target=str(target),
        base_seed=base_seed,
        operator=str(operator),
        pool_id=_pool_id_from_row(row),
        quotient_sha256=quotient_sha,
        literal_game_sha256=literal_sha,
        global_event_index=global_event_index,
        declared_weakly_connected=optional_boolean("weakly_connected"),
        declared_training_candidate_collision=optional_boolean(
            "training_candidate_collision"
        ),
        declared_training_quotient_collision=optional_boolean(
            "training_quotient_collision"
        ),
        eligible_for_validation_metric=eligible_marker,
        exclusion_reasons=exclusion_reasons,
    )
    return nodes, adjacency, target_index, metadata


def _label_from_event(row: Mapping[str, Any]) -> float | None:
    decision = row.get("exact_decision")
    if decision is None:
        return None
    if not isinstance(decision, Mapping) or not isinstance(decision.get("equal"), bool):
        raise RankerContractError(
            "labeled rows require exact_decision.equal to be boolean or "
            "exact_decision to be null"
        )
    return float(decision["equal"])


def _jsonl_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                raise RankerContractError(f"{path}:{line_number}: blank JSONL row")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise RankerContractError(
                    f"{path}:{line_number}: invalid JSON: {error}"
                ) from error
            if not isinstance(row, dict):
                raise RankerContractError(f"{path}:{line_number}: expected an object")
            yield row


def load_corpus(path: Path, *, require_labels: bool) -> Corpus:
    """Stream the 158 MB study ledger into compact proposal-only arrays."""

    node_rows: list[np.ndarray] = []
    adjacency_rows: list[np.ndarray] = []
    target_rows: list[int] = []
    labels: list[float] = []
    metadata: list[ExampleMetadata] = []
    censored: dict[str, int] = {}
    censored_reasons: dict[str, int] = {}
    for line_number, row in enumerate(_jsonl_rows(path), start=1):
        try:
            (
                node_values,
                adjacency_values,
                target_index,
                row_metadata,
            ) = proposal_features(row, include_outcome_metadata=require_labels)
            label = _label_from_event(row) if require_labels else None
        except RankerContractError as error:
            raise RankerContractError(f"{path}:{line_number}: {error}") from error
        node_rows.append(node_values)
        adjacency_rows.append(adjacency_values)
        target_rows.append(target_index)
        metadata.append(row_metadata)
        if require_labels:
            labels.append(float("nan") if label is None else label)
            if label is None:
                rejection = row.get("rejection")
                stage = (
                    str(rejection.get("stage"))
                    if isinstance(rejection, Mapping)
                    and isinstance(rejection.get("stage"), str)
                    else "unspecified"
                )
                censored[stage] = censored.get(stage, 0) + 1
                reason = (
                    str(rejection.get("reason"))
                    if isinstance(rejection, Mapping)
                    and isinstance(rejection.get("reason"), str)
                    else "unspecified"
                )
                censored_reasons[reason] = censored_reasons.get(reason, 0) + 1
    if not metadata:
        raise RankerContractError(f"{path}: no proposal rows")
    return Corpus(
        node_features=np.stack(node_rows),
        adjacency=np.stack(adjacency_rows),
        target_indices=np.asarray(target_rows, dtype=np.int64),
        labels=np.asarray(labels, dtype=np.float64) if require_labels else None,
        metadata=tuple(metadata),
        source_sha256=sha256_file(path),
        row_count=len(metadata),
        censored_by_rejection_stage=dict(sorted(censored.items())),
        censored_by_rejection_reason=dict(sorted(censored_reasons.items())),
    )


def labeled_indices(corpus: Corpus) -> np.ndarray:
    """Return semantically evaluated rows; censored rows remain excluded."""

    if corpus.labels is None:
        raise RankerContractError("labeled indices require an event corpus")
    return np.flatnonzero(np.isfinite(corpus.labels)).astype(np.int64)


def identity_commitments(corpus: Corpus) -> dict[str, Any]:
    """Commit to training identities without embedding the full private sets."""

    candidate_values = sorted(
        {metadata.candidate_sha256 for metadata in corpus.metadata}
    )
    quotient_values = sorted(
        {
            metadata.quotient_sha256
            for metadata in corpus.metadata
            if metadata.quotient_sha256 is not None
        }
    )
    return {
        "candidate_unique_count": len(candidate_values),
        "candidate_sha256_set_commitment": hashlib.sha256(
            canonical_json_bytes(candidate_values)
        ).hexdigest(),
        "quotient_count": len(quotient_values),
        "quotient_sha256_set_commitment": hashlib.sha256(
            canonical_json_bytes(quotient_values)
        ).hexdigest(),
    }


def feature_contract_record() -> dict[str, Any]:
    """Return the exact model-input contract embedded in every artifact."""

    return {
        "contract": FEATURE_CONTRACT,
        "model_feature_paths": [
            "/candidate/arcs",
            "/candidate/blue_vertices",
            "/candidate/order",
            "/target",
        ],
        "ranking_metadata_paths": [
            "/candidate_sha256",
            "/base_seed",
            "/proposal/operator",
            "/pool_id",
            "/ranker_pool/pool_id",
        ],
        "proposal_operator_is_model_feature": False,
        "quotient_code_is_model_feature": False,
        "forbidden_at_inference": [
            "/exact_decision",
            "/measurements",
            "/quotient",
            "/rejection",
            "/retention",
            "/structural_quotient",
            "/transition",
        ],
        "vertex_relabeling": (
            "equivariant_directed_message_passing_then_invariant_" "mean_max_pooling"
        ),
    }


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    output = np.empty_like(logits)
    positive = logits >= 0
    output[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
    negative_exp = np.exp(logits[~positive])
    output[~positive] = negative_exp / (1.0 + negative_exp)
    return output


def _binary_log_loss(labels: np.ndarray, probabilities: np.ndarray) -> float:
    clipped = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
    return float(
        -np.mean(labels * np.log(clipped) + (1.0 - labels) * np.log(1.0 - clipped))
    )


def _normalization(
    values: np.ndarray, axes: tuple[int, ...]
) -> tuple[np.ndarray, np.ndarray]:
    mean = values.mean(axis=axes)
    scale = values.std(axis=axes)
    scale = np.where(scale < 1e-8, 1.0, scale)
    return mean, scale


class DirectedMPNNRanker:
    """Directed message-passing graph classifier with invariant readout."""

    def __init__(
        self,
        *,
        hidden_width: int = 32,
        layer_count: int = 2,
        dropout: float = TRAINING_DROPOUT,
        random_seed: int = ENSEMBLE_SEEDS[0],
    ) -> None:
        if hidden_width not in GRID_HIDDEN_WIDTHS:
            raise RankerContractError("hidden_width is outside the frozen grid")
        if layer_count not in GRID_LAYER_COUNTS:
            raise RankerContractError("layer_count is outside the frozen grid")
        if not 0.0 <= dropout < 1.0:
            raise RankerContractError("dropout must lie in [0, 1)")
        self.hidden_width = hidden_width
        self.layer_count = layer_count
        self.dropout = dropout
        self.random_seed = random_seed
        rng = np.random.default_rng(random_seed)
        self.parameters: dict[str, np.ndarray] = {
            "input_weight": rng.normal(
                0.0,
                math.sqrt(2.0 / len(NODE_FEATURE_NAMES)),
                (len(NODE_FEATURE_NAMES), hidden_width),
            ),
            "input_bias": np.zeros(hidden_width),
            "target_embedding": rng.normal(
                0.0, 0.1, (len(TARGETS), TARGET_EMBEDDING_WIDTH)
            ),
            "head_weight": rng.normal(
                0.0,
                math.sqrt(2.0 / (2 * hidden_width + TARGET_EMBEDDING_WIDTH)),
                (2 * hidden_width + TARGET_EMBEDDING_WIDTH, hidden_width),
            ),
            "head_bias": np.zeros(hidden_width),
            "output_weight": rng.normal(
                0.0, math.sqrt(2.0 / hidden_width), (hidden_width, 1)
            ),
            "output_bias": np.zeros(1),
        }
        for layer in range(layer_count):
            for kind in ("self", "incoming", "outgoing"):
                self.parameters[f"layer_{layer}_{kind}_weight"] = rng.normal(
                    0.0,
                    math.sqrt(2.0 / hidden_width),
                    (hidden_width, hidden_width),
                )
            self.parameters[f"layer_{layer}_bias"] = np.zeros(hidden_width)
        self.training_summary: dict[str, Any] = {}

    @property
    def parameter_count(self) -> int:
        return sum(int(value.size) for value in self.parameters.values())

    def _dropout(
        self, values: np.ndarray, rng: np.random.Generator | None
    ) -> tuple[np.ndarray, np.ndarray | None]:
        if rng is None or self.dropout == 0.0:
            return values, None
        mask = rng.random(values.shape) >= self.dropout
        return values * mask / (1.0 - self.dropout), mask

    def _forward(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
        target_indices: np.ndarray,
        *,
        dropout_rng: np.random.Generator | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        input_pre = (
            node_features @ self.parameters["input_weight"]
            + self.parameters["input_bias"]
        )
        hidden = np.maximum(input_pre, 0.0)
        layer_caches: list[tuple[np.ndarray, ...]] = []
        for layer in range(self.layer_count):
            incoming = np.einsum("bst,bsh->bth", adjacency, hidden)
            outgoing = np.einsum("bst,bth->bsh", adjacency, hidden)
            layer_pre = (
                hidden @ self.parameters[f"layer_{layer}_self_weight"]
                + incoming @ self.parameters[f"layer_{layer}_incoming_weight"]
                + outgoing @ self.parameters[f"layer_{layer}_outgoing_weight"]
                + self.parameters[f"layer_{layer}_bias"]
            )
            activated = np.maximum(layer_pre, 0.0)
            next_hidden, layer_mask = self._dropout(activated, dropout_rng)
            layer_caches.append(
                (
                    hidden,
                    incoming,
                    outgoing,
                    layer_pre,
                    layer_mask,
                )
            )
            hidden = next_hidden

        pooled_mean = hidden.mean(axis=1)
        pooled_max = hidden.max(axis=1)
        max_ties = hidden == pooled_max[:, None, :]
        target_embedding = self.parameters["target_embedding"][target_indices]
        head_input = np.concatenate((pooled_mean, pooled_max, target_embedding), axis=1)
        head_pre = (
            head_input @ self.parameters["head_weight"] + self.parameters["head_bias"]
        )
        head_hidden, head_mask = self._dropout(np.maximum(head_pre, 0.0), dropout_rng)
        logits = (
            head_hidden @ self.parameters["output_weight"]
            + self.parameters["output_bias"]
        )[:, 0]
        return logits, {
            "node_features": node_features,
            "adjacency": adjacency,
            "target_indices": target_indices,
            "input_pre": input_pre,
            "layers": layer_caches,
            "final_hidden": hidden,
            "max_ties": max_ties,
            "head_input": head_input,
            "head_pre": head_pre,
            "head_hidden": head_hidden,
            "head_mask": head_mask,
        }

    def predict_logits(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
        target_indices: np.ndarray,
    ) -> np.ndarray:
        logits, _ = self._forward(
            node_features, adjacency, target_indices, dropout_rng=None
        )
        return logits

    def predict_proba(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
        target_indices: np.ndarray,
    ) -> np.ndarray:
        return _sigmoid(self.predict_logits(node_features, adjacency, target_indices))

    def _backward(
        self, cache: Mapping[str, Any], gradient_logits: np.ndarray
    ) -> dict[str, np.ndarray]:
        gradients = {
            name: np.zeros_like(value) for name, value in self.parameters.items()
        }
        gradient_logits = gradient_logits[:, None]
        gradients["output_weight"] = cache["head_hidden"].T @ gradient_logits
        gradients["output_bias"] = gradient_logits.sum(axis=0)
        gradient_head = gradient_logits @ self.parameters["output_weight"].T
        if cache["head_mask"] is not None:
            gradient_head *= cache["head_mask"] / (1.0 - self.dropout)
        gradient_head_pre = gradient_head * (cache["head_pre"] > 0.0)
        gradients["head_weight"] = cache["head_input"].T @ gradient_head_pre
        gradients["head_bias"] = gradient_head_pre.sum(axis=0)
        gradient_head_input = gradient_head_pre @ self.parameters["head_weight"].T

        width = self.hidden_width
        gradient_mean = gradient_head_input[:, :width]
        gradient_max = gradient_head_input[:, width : 2 * width]
        gradient_target = gradient_head_input[:, 2 * width :]
        np.add.at(
            gradients["target_embedding"],
            cache["target_indices"],
            gradient_target,
        )
        gradient_hidden = gradient_mean[:, None, :] / 7.0
        tie_count = cache["max_ties"].sum(axis=1)
        gradient_hidden = gradient_hidden + (
            gradient_max[:, None, :] * cache["max_ties"] / tie_count[:, None, :]
        )

        adjacency = cache["adjacency"]
        for layer in reversed(range(self.layer_count)):
            (
                previous_hidden,
                incoming,
                outgoing,
                layer_pre,
                layer_mask,
            ) = cache[
                "layers"
            ][layer]
            if layer_mask is not None:
                gradient_hidden *= layer_mask / (1.0 - self.dropout)
            gradient_pre = gradient_hidden * (layer_pre > 0.0)
            gradients[f"layer_{layer}_self_weight"] = np.einsum(
                "bvi,bvh->ih", previous_hidden, gradient_pre
            )
            gradients[f"layer_{layer}_incoming_weight"] = np.einsum(
                "bvi,bvh->ih", incoming, gradient_pre
            )
            gradients[f"layer_{layer}_outgoing_weight"] = np.einsum(
                "bvi,bvh->ih", outgoing, gradient_pre
            )
            gradients[f"layer_{layer}_bias"] = gradient_pre.sum(axis=(0, 1))
            gradient_previous = (
                gradient_pre @ self.parameters[f"layer_{layer}_self_weight"].T
            )
            gradient_incoming = (
                gradient_pre @ self.parameters[f"layer_{layer}_incoming_weight"].T
            )
            gradient_outgoing = (
                gradient_pre @ self.parameters[f"layer_{layer}_outgoing_weight"].T
            )
            gradient_previous += np.einsum("bst,bth->bsh", adjacency, gradient_incoming)
            gradient_previous += np.einsum("bst,bsh->bth", adjacency, gradient_outgoing)
            gradient_hidden = gradient_previous

        gradient_input_pre = gradient_hidden * (cache["input_pre"] > 0.0)
        gradients["input_weight"] = np.einsum(
            "bvi,bvh->ih", cache["node_features"], gradient_input_pre
        )
        gradients["input_bias"] = gradient_input_pre.sum(axis=(0, 1))
        return gradients

    def fit(
        self,
        corpus: Corpus,
        *,
        epochs: int = TRAINING_EPOCHS,
        batch_size: int = TRAINING_BATCH_SIZE,
        learning_rate: float = GRID_LEARNING_RATES[0],
        weight_decay: float = TRAINING_WEIGHT_DECAY,
        random_seed: int | None = None,
        capture_checkpoints: bool = False,
    ) -> list[dict[str, np.ndarray]]:
        if corpus.labels is None:
            raise RankerContractError("training requires event labels")
        if epochs < 1 or batch_size < 1 or learning_rate <= 0.0:
            raise RankerContractError("invalid optimization configuration")
        train_indices = labeled_indices(corpus)
        labels = corpus.labels[train_indices]
        if not len(train_indices) or labels.min() == labels.max():
            raise RankerContractError("training requires both exact label classes")
        seed = self.random_seed if random_seed is None else random_seed
        rng = np.random.default_rng(seed)
        first_moment = {
            name: np.zeros_like(value) for name, value in self.parameters.items()
        }
        second_moment = {
            name: np.zeros_like(value) for name, value in self.parameters.items()
        }
        update = 0
        checkpoints: list[dict[str, np.ndarray]] = []
        decay_names = {
            name
            for name in self.parameters
            if name.endswith("_weight") or name == "target_embedding"
        }
        for _epoch in range(epochs):
            shuffled = rng.permutation(train_indices)
            for offset in range(0, len(shuffled), batch_size):
                batch = shuffled[offset : offset + batch_size]
                batch_labels = corpus.labels[batch]
                logits, cache = self._forward(
                    corpus.node_features[batch],
                    corpus.adjacency[batch],
                    corpus.target_indices[batch],
                    dropout_rng=rng,
                )
                gradient_logits = (_sigmoid(logits) - batch_labels) / len(batch)
                gradients = self._backward(cache, gradient_logits)
                update += 1
                for name in self.parameters:
                    first_moment[name] = (
                        0.9 * first_moment[name] + 0.1 * gradients[name]
                    )
                    second_moment[name] = (
                        0.999 * second_moment[name]
                        + 0.001 * gradients[name] * gradients[name]
                    )
                    corrected_first = first_moment[name] / (1.0 - 0.9**update)
                    corrected_second = second_moment[name] / (1.0 - 0.999**update)
                    if name in decay_names:
                        self.parameters[name] *= 1.0 - (learning_rate * weight_decay)
                    self.parameters[name] -= (
                        learning_rate
                        * corrected_first
                        / (np.sqrt(corrected_second) + 1e-8)
                    )
            if capture_checkpoints:
                checkpoints.append(
                    {name: value.copy() for name, value in self.parameters.items()}
                )
        probabilities = self.predict_proba(
            corpus.node_features[train_indices],
            corpus.adjacency[train_indices],
            corpus.target_indices[train_indices],
        )
        self.training_summary = {
            "training_only": True,
            "validated": False,
            "epochs_completed": epochs,
            "labeled_rows": int(len(train_indices)),
            "censored_rows": int(corpus.row_count - len(train_indices)),
            "censored_by_rejection_stage": dict(corpus.censored_by_rejection_stage),
            "censored_by_rejection_reason": dict(corpus.censored_by_rejection_reason),
            "all_proposal_operators_included": True,
            "training_binary_metrics": binary_metrics(labels, probabilities),
        }
        return checkpoints

    def config_record(self) -> dict[str, Any]:
        return {
            "contract": ARCHITECTURE,
            "hidden_width": self.hidden_width,
            "message_passing_layers": self.layer_count,
            "target_embedding_width": TARGET_EMBEDDING_WIDTH,
            "dropout": self.dropout,
            "node_features": list(NODE_FEATURE_NAMES),
            "directed_aggregation": {
                "incoming": "unnormalized_sum",
                "outgoing": "unnormalized_sum",
                "self": True,
            },
            "activation": "relu",
            "pooling": ["mean", "max"],
            "head": "linear_relu_dropout_linear_logit",
            "parameter_count": self.parameter_count,
        }

    def to_record(
        self,
        *,
        corpus: Corpus,
        optimization: Mapping[str, Any],
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema_version": MODEL_SCHEMA,
            "model_id": "model-sha256:" + "0" * 64,
            "architecture": self.config_record(),
            "feature_contract": feature_contract_record(),
            "training_source": {
                "events_sha256": corpus.source_sha256,
                "row_count": corpus.row_count,
                "contract": TRAINING_CONTRACT,
                "paper_evidence": False,
                "use": "training_only",
                **identity_commitments(corpus),
            },
            "optimization": dict(optimization),
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
                "float_dtype": "float64",
            },
            "training_summary": dict(self.training_summary),
            "parameters": {
                name: value.tolist() for name, value in sorted(self.parameters.items())
            },
        }
        payload = dict(record)
        payload.pop("model_id")
        record["model_id"] = (
            "model-sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        )
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "DirectedMPNNRanker":
        if record.get("schema_version") != MODEL_SCHEMA:
            raise RankerContractError("unsupported model schema")
        architecture = record.get("architecture")
        if (
            not isinstance(architecture, Mapping)
            or architecture.get("contract") != ARCHITECTURE
        ):
            raise RankerContractError("unsupported model architecture")
        payload = dict(record)
        supplied_id = payload.pop("model_id", None)
        expected_id = (
            "model-sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        )
        if supplied_id != expected_id:
            raise RankerContractError("model_id does not match model content")
        optimization = record.get("optimization")
        if not isinstance(optimization, Mapping):
            raise RankerContractError("model optimization record is missing")
        try:
            model = cls(
                hidden_width=int(architecture["hidden_width"]),
                layer_count=int(architecture["message_passing_layers"]),
                dropout=float(architecture["dropout"]),
                random_seed=int(optimization.get("random_seed", 0)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RankerContractError("model architecture is malformed") from error
        if dict(architecture) != model.config_record():
            raise RankerContractError(
                "model architecture record disagrees with implementation"
            )
        if record.get("feature_contract") != feature_contract_record():
            raise RankerContractError(
                "model feature contract disagrees with implementation"
            )
        parameters = record.get("parameters")
        if not isinstance(parameters, Mapping):
            raise RankerContractError("model parameters are missing")
        if set(parameters) != set(model.parameters):
            raise RankerContractError("model parameter names do not match architecture")
        for name, expected in model.parameters.items():
            supplied = np.asarray(parameters.get(name), dtype=np.float64)
            if supplied.shape != expected.shape or not np.isfinite(supplied).all():
                raise RankerContractError(f"invalid model parameter: {name}")
            model.parameters[name] = supplied
        model.training_summary = dict(record.get("training_summary", {}))
        return model


class LogitEnsemble:
    """Three-seed ensemble that averages member logits exactly once."""

    def __init__(self, members: Sequence[DirectedMPNNRanker]) -> None:
        if len(members) != len(ENSEMBLE_SEEDS):
            raise RankerContractError("ensemble must contain exactly three members")
        if [member.random_seed for member in members] != list(ENSEMBLE_SEEDS):
            raise RankerContractError(
                "ensemble members must follow the frozen seed order"
            )
        configs = {
            (member.hidden_width, member.layer_count, member.dropout)
            for member in members
        }
        if len(configs) != 1:
            raise RankerContractError("ensemble members must share one configuration")
        self.members = tuple(members)

    def predict_logits(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
        target_indices: np.ndarray,
    ) -> np.ndarray:
        return np.mean(
            np.stack(
                [
                    member.predict_logits(node_features, adjacency, target_indices)
                    for member in self.members
                ]
            ),
            axis=0,
        )

    def predict_proba(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
        target_indices: np.ndarray,
    ) -> np.ndarray:
        return _sigmoid(self.predict_logits(node_features, adjacency, target_indices))

    def _validate_selection(self, selection: Mapping[str, Any]) -> None:
        grid_report_id = selection.get("grid_report_id")
        if (
            not isinstance(grid_report_id, str)
            or not grid_report_id.startswith("grid-report-sha256:")
            or not _is_sha256(grid_report_id.removeprefix("grid-report-sha256:"))
        ):
            raise RankerContractError("ensemble selection has invalid grid report id")
        selected = selection.get("selected")
        if not isinstance(selected, Mapping):
            raise RankerContractError("ensemble selection record is missing")

        required = {
            "config_id",
            "hidden_width",
            "layer_count",
            "learning_rate",
            "epoch",
            "parameter_count",
            "member_checkpoint_sha256",
        }
        if not required.issubset(selected):
            raise RankerContractError(
                "ensemble selected checkpoint binding is incomplete"
            )
        first = self.members[0]
        learning_rate = selected["learning_rate"]
        if (
            not isinstance(learning_rate, (int, float))
            or isinstance(learning_rate, bool)
            or not math.isfinite(float(learning_rate))
        ):
            raise RankerContractError("ensemble selection has invalid learning rate")
        expected_config_id = (
            f"h{first.hidden_width:02d}-l{first.layer_count}-"
            f"lr{float(learning_rate):.4f}"
        )
        if (
            selected["config_id"] != expected_config_id
            or selected["hidden_width"] != first.hidden_width
            or selected["layer_count"] != first.layer_count
            or learning_rate not in GRID_LEARNING_RATES
            or not isinstance(selected["epoch"], int)
            or isinstance(selected["epoch"], bool)
            or not 1 <= selected["epoch"] <= TRAINING_EPOCHS
            or selected["parameter_count"] != first.parameter_count
        ):
            raise RankerContractError(
                "ensemble selection disagrees with member configuration"
            )
        checkpoint_digests = selected["member_checkpoint_sha256"]
        observed_digests = [
            _parameters_digest(member.parameters) for member in self.members
        ]
        if checkpoint_digests != observed_digests:
            raise RankerContractError(
                "ensemble members do not match selected checkpoint digests"
            )

    def to_record(
        self,
        *,
        corpus: Corpus,
        selection: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._validate_selection(selection)
        member_records = []
        selected = selection["selected"]
        for seed, member in zip(ENSEMBLE_SEEDS, self.members):
            member_records.append(
                member.to_record(
                    corpus=corpus,
                    optimization={
                        "random_seed": seed,
                        "epochs": selected["epoch"],
                        "batch_size": TRAINING_BATCH_SIZE,
                        "learning_rate": selected["learning_rate"],
                        "weight_decay": TRAINING_WEIGHT_DECAY,
                        "dropout": TRAINING_DROPOUT,
                        "optimizer": "adamw_v1",
                        "loss": "unweighted_mean_binary_cross_entropy",
                    },
                )
            )
        record: dict[str, Any] = {
            "schema_version": ENSEMBLE_SCHEMA,
            "model_id": "ensemble-sha256:" + "0" * 64,
            "aggregation": "arithmetic_mean_member_logits",
            "member_seeds": list(ENSEMBLE_SEEDS),
            "members": member_records,
            "selection": dict(selection),
        }
        payload = dict(record)
        payload.pop("model_id")
        record["model_id"] = (
            "ensemble-sha256:"
            + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        )
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "LogitEnsemble":
        if record.get("schema_version") != ENSEMBLE_SCHEMA:
            raise RankerContractError("unsupported ensemble schema")
        payload = dict(record)
        supplied_id = payload.pop("model_id", None)
        expected_id = (
            "ensemble-sha256:"
            + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        )
        if supplied_id != expected_id:
            raise RankerContractError("ensemble model_id does not match content")
        if record.get("aggregation") != "arithmetic_mean_member_logits":
            raise RankerContractError("unsupported ensemble aggregation")
        if record.get("member_seeds") != list(ENSEMBLE_SEEDS):
            raise RankerContractError("ensemble seeds do not match frozen contract")
        members_value = record.get("members")
        if not isinstance(members_value, list):
            raise RankerContractError("ensemble members are missing")
        ensemble = cls(
            [DirectedMPNNRanker.from_record(member) for member in members_value]
        )
        selection = record.get("selection")
        if not isinstance(selection, Mapping):
            raise RankerContractError("ensemble selection binding is missing")
        ensemble._validate_selection(selection)
        return ensemble


def _parameters_digest(parameters: Mapping[str, np.ndarray]) -> str:
    payload = {name: value.tolist() for name, value in sorted(parameters.items())}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _validation_eligible_indices(
    training_corpus: Corpus, validation_corpus: Corpus
) -> tuple[np.ndarray, dict[str, int]]:
    if validation_corpus.labels is None:
        raise RankerContractError("validation selection requires labels")
    training_candidates = {
        metadata.candidate_sha256 for metadata in training_corpus.metadata
    }
    training_quotients = {
        metadata.quotient_sha256
        for metadata in training_corpus.metadata
        if metadata.quotient_sha256 is not None
    }
    candidate_collision = {
        index
        for index, metadata in enumerate(validation_corpus.metadata)
        if metadata.candidate_sha256 in training_candidates
    }
    quotient_collision = {
        index
        for index, metadata in enumerate(validation_corpus.metadata)
        if metadata.quotient_sha256 is not None
        and metadata.quotient_sha256 in training_quotients
    }
    collision = candidate_collision | quotient_collision
    censored = {
        index
        for index, label in enumerate(validation_corpus.labels)
        if not np.isfinite(label)
    }
    disconnected = {
        index
        for index, adjacency in enumerate(validation_corpus.adjacency)
        if not _weakly_connected(adjacency)
    }
    if any(
        metadata.eligible_for_validation_metric is None
        for metadata in validation_corpus.metadata
    ):
        raise RankerContractError(
            "validation rows require eligible_for_validation_metric"
        )
    marker_excluded: set[int] = set()
    for index, metadata in enumerate(validation_corpus.metadata):
        expected_reasons: list[str] = []
        if index in disconnected:
            expected_reasons.append("weakly_disconnected")
        if index in candidate_collision:
            expected_reasons.append("training_candidate_collision")
        if index in quotient_collision:
            expected_reasons.append("training_quotient_collision")
        if index in censored:
            expected_reasons.append("censored_null_exact_decision")
        expected_eligible = not expected_reasons

        if metadata.declared_weakly_connected is None:
            raise RankerContractError("validation rows require weakly_connected")
        if metadata.declared_weakly_connected != (index not in disconnected):
            raise RankerContractError(
                "validation weakly_connected marker disagrees with graph"
            )
        if metadata.declared_training_candidate_collision is None:
            raise RankerContractError(
                "validation rows require training_candidate_collision"
            )
        if metadata.declared_training_candidate_collision != (
            index in candidate_collision
        ):
            raise RankerContractError(
                "validation candidate-collision marker disagrees with registry"
            )
        if metadata.declared_training_quotient_collision is None:
            raise RankerContractError(
                "validation rows require training_quotient_collision"
            )
        if metadata.declared_training_quotient_collision != (
            index in quotient_collision
        ):
            raise RankerContractError(
                "validation quotient-collision marker disagrees with registry"
            )
        if metadata.eligible_for_validation_metric != expected_eligible:
            raise RankerContractError(
                "validation eligibility marker disagrees with replayed exclusions"
            )
        if metadata.exclusion_reasons != tuple(expected_reasons):
            raise RankerContractError(
                "validation exclusion_reasons disagree with replayed exclusions"
            )
        if not expected_eligible:
            marker_excluded.add(index)

    eligible = np.asarray(
        [
            index
            for index in range(validation_corpus.row_count)
            if index not in collision
            and index not in censored
            and index not in marker_excluded
        ],
        dtype=np.int64,
    )
    return eligible, {
        "training_candidate_collision_rows": len(candidate_collision),
        "training_quotient_collision_rows": len(quotient_collision),
        "training_identity_collision_rows": len(collision),
        "weakly_disconnected_rows": len(disconnected),
        "censored_rows": len(censored),
        "builder_ineligible_rows": len(marker_excluded),
        "eligible_rows": len(eligible),
    }


def validation_selection_metrics(
    scores: np.ndarray,
    training_corpus: Corpus,
    validation_corpus: Corpus,
) -> dict[str, Any]:
    """Compute the frozen target-macro selector on static validation pools."""

    eligible, exclusions = _validation_eligible_indices(
        training_corpus, validation_corpus
    )
    if not len(eligible):
        raise RankerContractError("validation has no eligible rows")
    if len(scores) != validation_corpus.row_count:
        raise RankerContractError("validation score count does not match corpus")
    eligible_set = set(eligible.tolist())
    groups: dict[str, list[int]] = {}
    for index, metadata in enumerate(validation_corpus.metadata):
        if metadata.operator != "toggle_one_arc":
            raise RankerContractError(
                "validation selector requires toggle_one_arc pools"
            )
        if metadata.pool_id is None:
            raise RankerContractError("validation row lacks pool_id")
        groups.setdefault(metadata.pool_id, []).append(index)
    top_one_by_target: dict[str, list[float]] = {target: [] for target in TARGETS}
    group_counts = {
        "committed": len(groups),
        "eligible": 0,
        "excluded_empty": 0,
    }
    for pool_id, indices in sorted(groups.items()):
        if len(indices) != 16:
            raise RankerContractError(
                f"validation pool {pool_id} must contain exactly 16 rows"
            )
        targets = {validation_corpus.metadata[index].target for index in indices}
        seeds = {validation_corpus.metadata[index].base_seed for index in indices}
        identities = {
            validation_corpus.metadata[index].candidate_sha256 for index in indices
        }
        if len(targets) != 1 or len(seeds) != 1:
            raise RankerContractError(f"validation pool {pool_id} mixes target or seed")
        if len(identities) != len(indices):
            raise RankerContractError(
                f"validation pool {pool_id} contains duplicate candidates"
            )
        candidates = [index for index in indices if index in eligible_set]
        if not candidates:
            group_counts["excluded_empty"] += 1
            continue
        group_counts["eligible"] += 1
        top = _learned_order(candidates, validation_corpus.metadata, scores=scores)[0]
        target = next(iter(targets))
        top_one_by_target[target].append(float(validation_corpus.labels[top] > 0.5))
    if any(not values for values in top_one_by_target.values()):
        raise RankerContractError(
            "every target requires at least one eligible validation pool"
        )
    target_top_one = {
        target: float(np.mean(values)) for target, values in top_one_by_target.items()
    }
    target_bce = {}
    probabilities = _sigmoid(scores)
    for target in TARGETS:
        target_indices = np.asarray(
            [
                index
                for index in eligible.tolist()
                if validation_corpus.metadata[index].target == target
            ],
            dtype=np.int64,
        )
        if not len(target_indices):
            raise RankerContractError(
                f"validation target {target} has no eligible rows"
            )
        target_bce[target] = _binary_log_loss(
            validation_corpus.labels[target_indices],
            probabilities[target_indices],
        )
    return {
        "target_macro_top1_exact_rate": float(np.mean(list(target_top_one.values()))),
        "target_macro_bce": float(np.mean(list(target_bce.values()))),
        "per_target_top1_exact_rate": target_top_one,
        "per_target_bce": target_bce,
        "groups": group_counts,
        "exclusions": exclusions,
    }


def frozen_grid_configs() -> list[dict[str, Any]]:
    configs = []
    for hidden_width in GRID_HIDDEN_WIDTHS:
        for layer_count in GRID_LAYER_COUNTS:
            for learning_rate in GRID_LEARNING_RATES:
                config_id = (
                    f"h{hidden_width:02d}-l{layer_count}-" f"lr{learning_rate:.4f}"
                )
                configs.append(
                    {
                        "config_id": config_id,
                        "hidden_width": hidden_width,
                        "layer_count": layer_count,
                        "learning_rate": learning_rate,
                    }
                )
    return sorted(configs, key=lambda value: value["config_id"])


def select_frozen_grid(
    training_corpus: Corpus,
    validation_corpus: Corpus,
    *,
    seeds: Sequence[int] = ENSEMBLE_SEEDS,
    epochs: int = TRAINING_EPOCHS,
    batch_size: int = TRAINING_BATCH_SIZE,
) -> tuple[LogitEnsemble, dict[str, Any]]:
    """Train every frozen config/seed/epoch and select one logit ensemble."""

    config_values = frozen_grid_configs()
    if list(seeds) != list(ENSEMBLE_SEEDS):
        raise RankerContractError("grid selector requires the three frozen seeds")
    if epochs != TRAINING_EPOCHS or batch_size != TRAINING_BATCH_SIZE:
        raise RankerContractError("grid selector requires frozen epochs and batch")
    candidate_records: list[dict[str, Any]] = []
    selected_key: tuple[Any, ...] | None = None
    selected_models: list[DirectedMPNNRanker] | None = None
    selected_record: dict[str, Any] | None = None

    for config in config_values:
        hidden_width = int(config["hidden_width"])
        layer_count = int(config["layer_count"])
        learning_rate = float(config["learning_rate"])
        config_id = str(config["config_id"])
        if (
            hidden_width not in GRID_HIDDEN_WIDTHS
            or layer_count not in GRID_LAYER_COUNTS
            or learning_rate not in GRID_LEARNING_RATES
        ):
            raise RankerContractError(f"config {config_id} is outside frozen grid")
        models: list[DirectedMPNNRanker] = []
        checkpoints_by_seed: list[list[dict[str, np.ndarray]]] = []
        for seed in seeds:
            model = DirectedMPNNRanker(
                hidden_width=hidden_width,
                layer_count=layer_count,
                dropout=TRAINING_DROPOUT,
                random_seed=seed,
            )
            checkpoints = model.fit(
                training_corpus,
                epochs=epochs,
                batch_size=batch_size,
                learning_rate=learning_rate,
                weight_decay=TRAINING_WEIGHT_DECAY,
                random_seed=seed,
                capture_checkpoints=True,
            )
            models.append(model)
            checkpoints_by_seed.append(checkpoints)

        for epoch_index in range(epochs):
            checkpoint_digests = []
            for model, checkpoints in zip(models, checkpoints_by_seed):
                checkpoint = checkpoints[epoch_index]
                model.parameters = {
                    name: value.copy() for name, value in checkpoint.items()
                }
                checkpoint_digests.append(_parameters_digest(checkpoint))
            ensemble = LogitEnsemble(models)
            scores = ensemble.predict_logits(
                validation_corpus.node_features,
                validation_corpus.adjacency,
                validation_corpus.target_indices,
            )
            metrics = validation_selection_metrics(
                scores, training_corpus, validation_corpus
            )
            record = {
                "config_id": config_id,
                "hidden_width": hidden_width,
                "layer_count": layer_count,
                "learning_rate": learning_rate,
                "epoch": epoch_index + 1,
                "parameter_count": models[0].parameter_count,
                "member_checkpoint_sha256": checkpoint_digests,
                **metrics,
            }
            candidate_records.append(record)
            key = (
                -record["target_macro_top1_exact_rate"],
                record["target_macro_bce"],
                record["parameter_count"],
                record["epoch"],
                record["config_id"],
            )
            if selected_key is None or key < selected_key:
                selected_key = key
                selected_record = dict(record)
                selected_models = [
                    DirectedMPNNRanker(
                        hidden_width=hidden_width,
                        layer_count=layer_count,
                        dropout=TRAINING_DROPOUT,
                        random_seed=seed,
                    )
                    for seed in seeds
                ]
                for selected_model, checkpoint in zip(
                    selected_models,
                    [values[epoch_index] for values in checkpoints_by_seed],
                ):
                    selected_model.parameters = {
                        name: value.copy() for name, value in checkpoint.items()
                    }
                    selected_model.training_summary = {
                        "training_only": True,
                        "validated": True,
                        "selected_epoch": epoch_index + 1,
                        "labeled_rows": int(len(labeled_indices(training_corpus))),
                        "censored_rows": int(
                            training_corpus.row_count
                            - len(labeled_indices(training_corpus))
                        ),
                        "censored_by_rejection_stage": dict(
                            training_corpus.censored_by_rejection_stage
                        ),
                        "censored_by_rejection_reason": dict(
                            training_corpus.censored_by_rejection_reason
                        ),
                    }
    if selected_models is None or selected_record is None:
        raise RankerContractError("frozen grid contains no candidates")
    report: dict[str, Any] = {
        "schema_version": GRID_REPORT_SCHEMA,
        "report_id": "grid-report-sha256:" + "0" * 64,
        "contract": {
            "architecture": ARCHITECTURE,
            "grid": frozen_grid_configs(),
            "seeds": list(ENSEMBLE_SEEDS),
            "epochs": TRAINING_EPOCHS,
            "batch_size": TRAINING_BATCH_SIZE,
            "weight_decay": TRAINING_WEIGHT_DECAY,
            "dropout": TRAINING_DROPOUT,
            "optimizer": "adamw_v1",
            "loss": "unweighted_mean_binary_cross_entropy",
            "ensemble": "arithmetic_mean_member_logits",
            "selection_order": [
                "maximum_target_macro_top1_exact_rate",
                "minimum_target_macro_bce",
                "minimum_parameter_count",
                "minimum_epoch",
                "lexicographic_config_id",
            ],
        },
        "training_source": {
            "events_sha256": training_corpus.source_sha256,
            "row_count": training_corpus.row_count,
        },
        "validation_source": {
            "events_sha256": validation_corpus.source_sha256,
            "row_count": validation_corpus.row_count,
        },
        "candidates": candidate_records,
        "selected": selected_record,
    }
    payload = dict(report)
    payload.pop("report_id")
    report["report_id"] = (
        "grid-report-sha256:"
        + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    )
    return LogitEnsemble(selected_models), report


def _rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = rank
        start = end
    return ranks


def binary_metrics(labels: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    if len(labels) != len(scores) or not len(labels):
        raise RankerContractError("metric arrays must have the same non-zero length")
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    ranks = _rankdata(scores)
    roc_auc = (
        float(
            (ranks[labels > 0.5].sum() - positives * (positives + 1) / 2.0)
            / (positives * negatives)
        )
        if positives and negatives
        else None
    )
    order = np.argsort(-scores, kind="mergesort")
    ordered_labels = labels[order]
    cumulative = np.cumsum(ordered_labels)
    average_precision = (
        float(
            (
                cumulative
                / np.arange(1, len(labels) + 1, dtype=np.float64)
                * ordered_labels
            ).sum()
            / positives
        )
        if positives
        else None
    )
    return {
        "row_count": len(labels),
        "positive_count": positives,
        "positive_rate": float(labels.mean()),
        "log_loss": _binary_log_loss(labels, scores),
        "brier_score": float(np.mean((scores - labels) ** 2)),
        "roc_auc": roc_auc,
        "average_precision": average_precision,
    }


def _learned_order(
    indices: Sequence[int],
    metadata: Sequence[ExampleMetadata],
    *,
    scores: np.ndarray,
) -> list[int]:
    return sorted(
        indices,
        key=lambda index: (
            -float(scores[index]),
            metadata[index].candidate_sha256,
        ),
    )


def _discovery_at(
    order: Sequence[int],
    labels: np.ndarray,
    metadata: Sequence[ExampleMetadata],
    budget: int,
) -> dict[str, int]:
    prefix = order[: min(budget, len(order))]
    matches = [index for index in prefix if labels[index] > 0.5]
    quotient_values = {
        metadata[index].quotient_sha256
        for index in matches
        if metadata[index].quotient_sha256 is not None
    }
    literal_values = {
        metadata[index].literal_game_sha256
        for index in matches
        if metadata[index].literal_game_sha256 is not None
    }
    return {
        "calls": len(prefix),
        "certified_matches": len(matches),
        "quotient_unique_matches": len(quotient_values),
        "literal_unique_matches": len(literal_values),
    }


def _random_order(
    indices: Sequence[int],
    metadata: Sequence[ExampleMetadata],
    *,
    pool_id: str,
    replicate: int,
) -> list[int]:
    domain = f"{POOL_CONTRACT}\0{pool_id}\0{replicate}\0"
    return sorted(
        indices,
        key=lambda index: hashlib.sha256(
            (domain + metadata[index].candidate_sha256).encode("ascii")
        ).digest(),
    )


def _distribution_summary(values: Sequence[int]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        raise RankerContractError("cannot summarize an empty distribution")

    def percentile(numerator: int, denominator: int) -> int:
        index = math.ceil(numerator * len(ordered) / denominator) - 1
        return int(ordered[max(0, min(index, len(ordered) - 1))])

    return {
        "mean": float(sum(ordered) / len(ordered)),
        "minimum": int(ordered[0]),
        "p025_nearest_rank": percentile(25, 1_000),
        "median_nearest_rank": percentile(1, 2),
        "p975_nearest_rank": percentile(975, 1_000),
        "maximum": int(ordered[-1]),
    }


def _identity_overlap(
    training_corpus: Corpus, evaluation_corpus: Corpus
) -> dict[str, Any]:
    training_candidates = {
        metadata.candidate_sha256 for metadata in training_corpus.metadata
    }
    evaluation_candidates = {
        metadata.candidate_sha256 for metadata in evaluation_corpus.metadata
    }
    training_quotients = {
        metadata.quotient_sha256
        for metadata in training_corpus.metadata
        if metadata.quotient_sha256 is not None
    }
    evaluation_quotients = {
        metadata.quotient_sha256
        for metadata in evaluation_corpus.metadata
        if metadata.quotient_sha256 is not None
    }
    candidate_overlap = sorted(training_candidates & evaluation_candidates)
    quotient_overlap = sorted(training_quotients & evaluation_quotients)
    return {
        "candidate_overlap_count": len(candidate_overlap),
        "candidate_overlap_sample": candidate_overlap[:10],
        "quotient_overlap_count": len(quotient_overlap),
        "quotient_overlap_sample": quotient_overlap[:10],
        "pass": not candidate_overlap and not quotient_overlap,
    }


def evaluate_model(
    model: DirectedMPNNRanker | LogitEnsemble,
    training_corpus: Corpus,
    evaluation_corpus: Corpus,
    *,
    model_id: str,
    role: str,
    budgets: Sequence[int],
    random_replicates: int,
) -> dict[str, Any]:
    """Compare neural and random ordering on fresh same-operator pools."""

    if role not in {"validation", "test"}:
        raise RankerContractError("evaluation role must be validation or test")
    if evaluation_corpus.labels is None:
        raise RankerContractError("evaluation requires verifier labels")
    if any(budget < 1 for budget in budgets) or not budgets:
        raise RankerContractError("evaluation budgets must be positive")
    if random_replicates < 1:
        raise RankerContractError("random_replicates must be positive")

    overlap = _identity_overlap(training_corpus, evaluation_corpus)
    training_candidates = {
        metadata.candidate_sha256 for metadata in training_corpus.metadata
    }
    training_quotients = {
        metadata.quotient_sha256
        for metadata in training_corpus.metadata
        if metadata.quotient_sha256 is not None
    }
    collision_indices = {
        index
        for index, metadata in enumerate(evaluation_corpus.metadata)
        if metadata.candidate_sha256 in training_candidates
        or (
            metadata.quotient_sha256 is not None
            and metadata.quotient_sha256 in training_quotients
        )
    }
    censored_indices = {
        index
        for index, label in enumerate(evaluation_corpus.labels)
        if not np.isfinite(label)
    }
    effective_labels = np.nan_to_num(evaluation_corpus.labels.copy(), nan=0.0)
    for index in collision_indices:
        effective_labels[index] = 0.0
    validation_eligible_set: set[int] | None = None
    validation_marker_audit: dict[str, int] | None = None
    if role == "validation":
        validation_eligible, validation_marker_audit = _validation_eligible_indices(
            training_corpus, evaluation_corpus
        )
        validation_eligible_set = set(validation_eligible.tolist())

    pools: dict[str, list[int]] = {}
    for index, metadata in enumerate(evaluation_corpus.metadata):
        if metadata.operator != "toggle_one_arc":
            raise RankerContractError(
                "primary evaluation accepts toggle_one_arc proposals only"
            )
        if metadata.pool_id is None:
            raise RankerContractError(
                "fresh evaluation rows require ranker_pool.pool_id"
            )
        pools.setdefault(metadata.pool_id, []).append(index)
    if not pools:
        raise RankerContractError("evaluation contains no candidate pools")

    scores = model.predict_proba(
        evaluation_corpus.node_features,
        evaluation_corpus.adjacency,
        evaluation_corpus.target_indices,
    )
    learned_values: dict[int, dict[str, list[int]]] = {
        budget: {
            "certified_matches": [],
            "quotient_unique_matches": [],
            "literal_unique_matches": [],
        }
        for budget in budgets
    }
    random_values: dict[int, dict[str, list[int]]] = {
        budget: {
            "certified_matches": [],
            "quotient_unique_matches": [],
            "literal_unique_matches": [],
        }
        for budget in budgets
    }
    per_pool: list[dict[str, Any]] = []
    for pool_id, indices in sorted(pools.items()):
        identities = [
            evaluation_corpus.metadata[index].candidate_sha256 for index in indices
        ]
        if len(set(identities)) != len(identities):
            raise RankerContractError(f"pool {pool_id} has duplicate candidates")
        targets = {evaluation_corpus.metadata[index].target for index in indices}
        seeds = {evaluation_corpus.metadata[index].base_seed for index in indices}
        if len(targets) != 1 or len(seeds) != 1:
            raise RankerContractError(f"pool {pool_id} mixes target or seed domains")

        excluded = {
            "training_identity_collision": sorted(set(indices) & collision_indices),
            "censored_without_exact_label": sorted(set(indices) & censored_indices),
            "builder_ineligible": sorted(
                index
                for index in indices
                if evaluation_corpus.metadata[index].eligible_for_validation_metric
                is False
            ),
        }
        if role == "validation":
            ranking_indices = [
                index
                for index in indices
                if validation_eligible_set is not None
                and index in validation_eligible_set
            ]
        else:
            ranking_indices = list(indices)
        if not ranking_indices:
            per_pool.append(
                {
                    "pool_id": pool_id,
                    "target": next(iter(targets)),
                    "base_seed": next(iter(seeds)),
                    "pool_size": len(indices),
                    "eligible_count": 0,
                    "excluded_group": True,
                    "exclusions": {
                        key: len(values) for key, values in excluded.items()
                    },
                }
            )
            continue

        learned_order = _learned_order(
            ranking_indices,
            evaluation_corpus.metadata,
            scores=scores,
        )
        learned_by_budget: dict[str, Any] = {}
        random_by_budget: dict[str, Any] = {}
        random_discoveries = {
            budget: {
                "certified_matches": [],
                "quotient_unique_matches": [],
                "literal_unique_matches": [],
            }
            for budget in budgets
        }
        for replicate in range(random_replicates):
            random_order = _random_order(
                ranking_indices,
                evaluation_corpus.metadata,
                pool_id=pool_id,
                replicate=replicate,
            )
            for budget in budgets:
                result = _discovery_at(
                    random_order,
                    effective_labels,
                    evaluation_corpus.metadata,
                    budget,
                )
                for metric in random_discoveries[budget]:
                    random_discoveries[budget][metric].append(result[metric])

        for budget in budgets:
            learned_result = _discovery_at(
                learned_order,
                effective_labels,
                evaluation_corpus.metadata,
                budget,
            )
            learned_by_budget[str(budget)] = learned_result
            random_by_budget[str(budget)] = {
                metric: _distribution_summary(values)
                for metric, values in random_discoveries[budget].items()
            }
            for metric in learned_values[budget]:
                learned_values[budget][metric].append(learned_result[metric])
                random_values[budget][metric].extend(random_discoveries[budget][metric])
        per_pool.append(
            {
                "pool_id": pool_id,
                "target": next(iter(targets)),
                "base_seed": next(iter(seeds)),
                "pool_size": len(indices),
                "eligible_count": len(ranking_indices),
                "excluded_group": False,
                "exclusions": {key: len(values) for key, values in excluded.items()},
                "learned": learned_by_budget,
                "random": random_by_budget,
            }
        )

    aggregate: dict[str, Any] = {}
    if not any(not pool.get("excluded_group", False) for pool in per_pool):
        raise RankerContractError("evaluation has no eligible candidate pools")
    for budget in budgets:
        learned_summary = {
            metric: {
                "mean_over_pools": float(np.mean(values)),
                "minimum": int(min(values)),
                "maximum": int(max(values)),
            }
            for metric, values in learned_values[budget].items()
        }
        random_summary = {
            metric: _distribution_summary(values)
            for metric, values in random_values[budget].items()
        }
        aggregate[str(budget)] = {
            "learned": learned_summary,
            "random": random_summary,
            "learned_minus_random_mean": {
                metric: (
                    learned_summary[metric]["mean_over_pools"]
                    - random_summary[metric]["mean"]
                )
                for metric in learned_summary
            },
        }

    metric_indices = (
        np.asarray(sorted(validation_eligible_set), dtype=np.int64)
        if role == "validation" and validation_eligible_set is not None
        else np.asarray(
            [
                index
                for index in range(evaluation_corpus.row_count)
                if index not in collision_indices and index not in censored_indices
            ],
            dtype=np.int64,
        )
    )
    if not len(metric_indices):
        raise RankerContractError("evaluation has no metric-eligible rows")
    return {
        "schema_version": REPORT_SCHEMA,
        "model_id": model_id,
        "role": role,
        "training_source": {
            "events_sha256": training_corpus.source_sha256,
            "row_count": training_corpus.row_count,
        },
        "evaluation_source": {
            "events_sha256": evaluation_corpus.source_sha256,
            "row_count": evaluation_corpus.row_count,
        },
        "identity_leakage_audit": overlap,
        "exclusion_policy": {
            "training_identity_collision_rows": len(collision_indices),
            "censored_rows": len(censored_indices),
            "validation_marker_audit": validation_marker_audit,
            "validation": (
                "exclude rows before ranking and metrics; exclude group only "
                "when no eligible rows remain"
            ),
            "test": (
                "retain rows in ranking and call count; collisions and "
                "censored rows cannot count as discoveries"
            ),
        },
        "contract": {
            "pool_contract": POOL_CONTRACT,
            "operator": "toggle_one_arc",
            "comparison": "neural_ordering_vs_random_ordering",
            "same_candidate_pool": True,
            "same_operator": True,
            "same_verifier_budget": True,
            "random_replicates": random_replicates,
            "budgets": list(budgets),
            "exact_verifier_authoritative": True,
        },
        "binary_metrics": binary_metrics(
            effective_labels[metric_indices], scores[metric_indices]
        ),
        "discovery": {
            "aggregate": aggregate,
            "per_pool": per_pool,
        },
    }


def rank_records(
    model: DirectedMPNNRanker | LogitEnsemble,
    corpus: Corpus,
    *,
    model_id: str,
) -> list[dict[str, Any]]:
    """Return outcome-free score records in deterministic rank order."""

    scores = model.predict_proba(
        corpus.node_features, corpus.adjacency, corpus.target_indices
    )
    if not np.isfinite(scores).all():
        raise RankerContractError("model produced a non-finite score")
    indices = list(range(corpus.row_count))
    indices.sort(
        key=lambda index: (
            corpus.metadata[index].target,
            corpus.metadata[index].base_seed,
            corpus.metadata[index].pool_id or "",
            -float(scores[index]),
            corpus.metadata[index].candidate_sha256,
        )
    )
    ranks: dict[tuple[str, int, str], int] = {}
    records: list[dict[str, Any]] = []
    for index in indices:
        metadata = corpus.metadata[index]
        group = (
            metadata.target,
            metadata.base_seed,
            metadata.pool_id or "",
        )
        rank = ranks.get(group, 0)
        ranks[group] = rank + 1
        record = {
            "schema_version": RANK_SCHEMA,
            "model_id": model_id,
            "candidate_sha256": metadata.candidate_sha256,
            "target": metadata.target,
            "base_seed": metadata.base_seed,
            "operator": metadata.operator,
            "rank_zero_based": rank,
            "score": float(scores[index]),
        }
        if metadata.pool_id is not None:
            record["pool_id"] = metadata.pool_id
        records.append(record)
    return records


def rank_pool(
    model: DirectedMPNNRanker | LogitEnsemble,
    proposal_rows: Sequence[Mapping[str, Any]],
    *,
    model_id: str,
) -> list[dict[str, Any]]:
    """Rank one fresh, outcome-free toggle-one-arc proposal pool.

    This is the narrow integration API used between candidate generation and
    exact verification.  All rows must share one pool id, target, and seed.
    """

    if not proposal_rows:
        raise RankerContractError("rank_pool requires at least one proposal")
    node_rows: list[np.ndarray] = []
    adjacency_rows: list[np.ndarray] = []
    target_rows: list[int] = []
    metadata_rows: list[ExampleMetadata] = []
    source = bytearray()
    for row in proposal_rows:
        forbidden = OUTCOME_FIELDS_FORBIDDEN_IN_POOL_SCORING & set(row)
        if forbidden:
            raise RankerContractError(
                "rank_pool received outcome fields: " + ", ".join(sorted(forbidden))
            )
        nodes, adjacency, target_index, metadata = proposal_features(
            row, include_outcome_metadata=False
        )
        if metadata.operator != "toggle_one_arc":
            raise RankerContractError("rank_pool accepts toggle_one_arc proposals only")
        if metadata.pool_id is None:
            raise RankerContractError("rank_pool rows require ranker_pool.pool_id")
        node_rows.append(nodes)
        adjacency_rows.append(adjacency)
        target_rows.append(target_index)
        metadata_rows.append(metadata)
        source.extend(canonical_json_bytes(dict(row)))
    groups = {
        (metadata.pool_id, metadata.target, metadata.base_seed)
        for metadata in metadata_rows
    }
    if len(groups) != 1:
        raise RankerContractError("rank_pool rows must share pool, target, and seed")
    candidate_ids = [metadata.candidate_sha256 for metadata in metadata_rows]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise RankerContractError("rank_pool contains duplicate candidates")
    corpus = Corpus(
        node_features=np.stack(node_rows),
        adjacency=np.stack(adjacency_rows),
        target_indices=np.asarray(target_rows, dtype=np.int64),
        labels=None,
        metadata=tuple(metadata_rows),
        source_sha256=hashlib.sha256(source).hexdigest(),
        row_count=len(metadata_rows),
        censored_by_rejection_stage={},
        censored_by_rejection_reason={},
    )
    return rank_records(model, corpus, model_id=model_id)


def _load_model(
    path: Path,
) -> tuple[DirectedMPNNRanker | LogitEnsemble, dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RankerContractError(f"{path}: expected a JSON object")
    if value.get("schema_version") == ENSEMBLE_SCHEMA:
        return LogitEnsemble.from_record(value), value
    return DirectedMPNNRanker.from_record(value), value


def build_resource_preflight_ranker(
    *,
    model_artifact_path: Path,
    model_id: str,
):
    """Load a self-hashed artifact and return an outcome-free pool scorer.

    This is the public adapter factory bound by the neural-policy resource
    preflight.  The callback returns one deterministic probability per input
    row in the original order.  ``rank_pool`` performs the same-operator,
    same-pool, duplicate-identity, and forbidden-outcome checks before any
    score is exposed.
    """

    model, record = _load_model(Path(model_artifact_path))
    observed_model_id = record.get("model_id")
    if observed_model_id != model_id:
        raise RankerContractError(
            "requested model_id does not match self-hashed model artifact"
        )

    def score_pool(rows: Sequence[Mapping[str, object]]) -> list[float]:
        ranked = rank_pool(model, rows, model_id=model_id)
        scores_by_candidate = {
            record["candidate_sha256"]: float(record["score"]) for record in ranked
        }
        output: list[float] = []
        for row in rows:
            candidate = row.get("candidate")
            if not isinstance(candidate, Mapping):
                raise RankerContractError("candidate must be an object")
            candidate_sha = row.get("candidate_sha256")
            if candidate_sha is None:
                candidate_sha = _candidate_digest(candidate)
            if candidate_sha not in scores_by_candidate:
                raise RankerContractError(
                    "ranked candidate identity is missing from scorer output"
                )
            output.append(scores_by_candidate[candidate_sha])
        if len(output) != len(rows) or not all(
            math.isfinite(value) for value in output
        ):
            raise RankerContractError("pool scorer produced invalid output")
        return output

    return score_pool


def _model_training_source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    if record.get("schema_version") == ENSEMBLE_SCHEMA:
        members = record.get("members")
        if not isinstance(members, list) or not members:
            raise RankerContractError("ensemble has no member source bindings")
        sources = [member.get("training_source") for member in members]
        if any(source != sources[0] for source in sources):
            raise RankerContractError("ensemble members disagree on training source")
        if not isinstance(sources[0], Mapping):
            raise RankerContractError("ensemble training source is missing")
        return sources[0]
    source = record.get("training_source")
    if not isinstance(source, Mapping):
        raise RankerContractError("model training source is missing")
    return source


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as destination:
        for row in rows:
            destination.write(canonical_json_bytes(dict(row)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train and audit a deterministic neural proposal ranker while "
            "leaving exact verification authoritative."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fit = commands.add_parser(
        "train",
        help="fit a training-only model on the complete historical ledger",
    )
    fit.add_argument("--events", type=Path, required=True)
    fit.add_argument("--model-out", type=Path, required=True)
    fit.add_argument(
        "--hidden-width",
        choices=GRID_HIDDEN_WIDTHS,
        type=int,
        default=GRID_HIDDEN_WIDTHS[0],
    )
    fit.add_argument(
        "--layers",
        choices=GRID_LAYER_COUNTS,
        type=int,
        default=GRID_LAYER_COUNTS[0],
    )
    fit.add_argument(
        "--learning-rate",
        choices=GRID_LEARNING_RATES,
        type=float,
        default=GRID_LEARNING_RATES[0],
    )
    fit.add_argument(
        "--random-seed",
        choices=ENSEMBLE_SEEDS,
        type=int,
        default=ENSEMBLE_SEEDS[0],
    )

    evaluate = commands.add_parser(
        "evaluate",
        help="evaluate on a separately generated fresh same-operator pool ledger",
    )
    evaluate.add_argument("--training-events", type=Path, required=True)
    evaluate.add_argument("--evaluation-events", type=Path, required=True)
    evaluate.add_argument("--model", type=Path, required=True)
    evaluate.add_argument("--report-out", type=Path, required=True)
    evaluate.add_argument("--role", choices=("validation", "test"), required=True)
    evaluate.add_argument(
        "--budgets",
        type=int,
        nargs="+",
        default=list(DEFAULT_BUDGETS),
    )
    evaluate.add_argument("--random-replicates", type=int, default=256)

    select = commands.add_parser(
        "select-grid",
        help=(
            "train the frozen 8x3 grid, score all 80 epochs on validation, "
            "and write the selected three-member ensemble"
        ),
    )
    select.add_argument("--training-events", type=Path, required=True)
    select.add_argument("--validation-events", type=Path, required=True)
    select.add_argument("--ensemble-out", type=Path, required=True)
    select.add_argument("--report-out", type=Path, required=True)

    rank = commands.add_parser(
        "rank",
        help="write outcome-free model scores for event or proposal rows",
    )
    rank.add_argument("--proposals", type=Path, required=True)
    rank.add_argument("--model", type=Path, required=True)
    rank.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "train":
            corpus = load_corpus(args.events, require_labels=True)
            optimization = {
                "random_seed": args.random_seed,
                "epochs": TRAINING_EPOCHS,
                "batch_size": TRAINING_BATCH_SIZE,
                "learning_rate": args.learning_rate,
                "weight_decay": TRAINING_WEIGHT_DECAY,
                "dropout": TRAINING_DROPOUT,
                "optimizer": "adamw_v1",
                "loss": "unweighted_mean_binary_cross_entropy",
            }
            model = DirectedMPNNRanker(
                hidden_width=args.hidden_width,
                layer_count=args.layers,
                dropout=TRAINING_DROPOUT,
                random_seed=args.random_seed,
            )
            model.fit(
                corpus,
                epochs=TRAINING_EPOCHS,
                batch_size=TRAINING_BATCH_SIZE,
                learning_rate=args.learning_rate,
                weight_decay=TRAINING_WEIGHT_DECAY,
                random_seed=args.random_seed,
            )
            model_record = model.to_record(
                corpus=corpus,
                optimization=optimization,
            )
            _write_json(args.model_out, model_record)
            print(
                f"model: {model_record['model_id']} "
                f"(training_rows={model.training_summary['labeled_rows']}, "
                "status=training_only_unvalidated)"
            )
            print(f"wrote {args.model_out}")
            return 0

        if args.command == "select-grid":
            training_corpus = load_corpus(args.training_events, require_labels=True)
            validation_corpus = load_corpus(args.validation_events, require_labels=True)
            ensemble, report = select_frozen_grid(training_corpus, validation_corpus)
            ensemble_record = ensemble.to_record(
                corpus=training_corpus,
                selection={
                    "grid_report_id": report["report_id"],
                    "selected": report["selected"],
                },
            )
            _write_json(args.ensemble_out, ensemble_record)
            _write_json(args.report_out, report)
            print(
                f"ensemble: {ensemble_record['model_id']} "
                f"(selected={report['selected']['config_id']}, "
                f"epoch={report['selected']['epoch']})"
            )
            print(f"wrote {args.ensemble_out}")
            print(f"wrote {args.report_out}")
            return 0

        model, model_record = _load_model(args.model)
        if args.command == "evaluate":
            training_corpus = load_corpus(args.training_events, require_labels=True)
            evaluation_corpus = load_corpus(args.evaluation_events, require_labels=True)
            source = _model_training_source(model_record)
            if (
                source.get("events_sha256") != training_corpus.source_sha256
                or source.get("row_count") != training_corpus.row_count
            ):
                raise RankerContractError(
                    "training ledger does not match the model source binding"
                )
            report = evaluate_model(
                model,
                training_corpus,
                evaluation_corpus,
                model_id=model_record["model_id"],
                role=args.role,
                budgets=tuple(sorted(set(args.budgets))),
                random_replicates=args.random_replicates,
            )
            _write_json(args.report_out, report)
            print(f"wrote {args.report_out}")
            return 0

        if args.command == "rank":
            corpus = load_corpus(args.proposals, require_labels=False)
            records = rank_records(
                model,
                corpus,
                model_id=model_record["model_id"],
            )
            _write_jsonl(args.output, records)
            print(f"wrote {args.output} (rows={len(records)})")
            return 0
    except (
        OSError,
        RankerContractError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        print(f"partizan-digraph-ranker: {error}", file=sys.stderr)
        return 1

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
