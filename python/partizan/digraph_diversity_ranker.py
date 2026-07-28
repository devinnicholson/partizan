"""Neural diversity acquisition for order-7 Digraph Placement.

The module learns a target-free graph embedding from training-only
literal-game equivalence labels.  At proposal time it combines distance from
an arm-local graph repertoire with scores from the separately frozen equality
ranker.  Exact evaluation remains authoritative for value equality and every
repertoire update.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from . import digraph_neural_ranker as equality_ranker


MODEL_SCHEMA = "partizan.digraph_order7_diversity_encoder.v0.1"
ENSEMBLE_SCHEMA = "partizan.digraph_order7_diversity_ensemble.v0.1"
RANK_SCHEMA = "partizan.digraph_order7_diversity_rank.v0.1"
FEATURE_CONTRACT = "partizan.digraph_order7_diversity_features.v0.1"
TRAINING_CONTRACT = "v2_training_only_literal_digest_equivalence.v0.1"
ARCHITECTURE = "directed_message_passing_graph_embedding_v2"
HIDDEN_WIDTH = 64
MESSAGE_PASSING_LAYERS = 3
DROPOUT = 0.1
EMBEDDING_WIDTHS = (16, 32)
CONTRASTIVE_TEMPERATURES = (0.1, 0.2)
LEARNING_RATE = 0.001
WEIGHT_DECAY = 0.0001
GROUPS_PER_BATCH = 64
ROWS_PER_GROUP = 2
TRAINING_EPOCHS = 60
ENSEMBLE_SEEDS = (
    11554741894640848524,
    5751780749325247006,
    15000233837857862382,
)
LAMBDA_GRID = (0.25, 0.5, 1.0, 2.0)

RankerContractError = equality_ranker.RankerContractError
canonical_json_bytes = equality_ranker.canonical_json_bytes


@dataclass(frozen=True)
class DiversityCorpus:
    """Graph tensors and training-only literal-game equivalence groups."""

    node_features: np.ndarray
    adjacency: np.ndarray
    literal_game_sha256: tuple[str | None, ...]
    candidate_sha256: tuple[str, ...]
    source_sha256: str
    row_count: int
    labeled_row_count: int
    literal_digest_group_count: int
    eligible_group_count: int
    eligible_row_count: int


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def feature_contract_record() -> dict[str, Any]:
    """Return the complete target-free inference contract."""

    return {
        "contract": FEATURE_CONTRACT,
        "model_feature_paths": [
            "/candidate/arcs",
            "/candidate/blue_vertices",
            "/candidate/order",
        ],
        "ranking_metadata_paths": [
            "/candidate_sha256",
            "/base_seed",
            "/proposal/operator",
            "/pool_id",
            "/ranker_pool/pool_id",
        ],
        "target_token_is_model_feature": False,
        "proposal_operator_is_model_feature": False,
        "quotient_code_is_model_feature": False,
        "literal_game_digest_is_model_feature": False,
        "forbidden_at_inference": [
            "/descriptors",
            "/exact_decision",
            "/literal_game_sha256",
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


def _candidate_arrays(candidate: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    blue, adjacency = equality_ranker._graph_arrays(candidate)
    return np.column_stack((blue, 1.0 - blue)), adjacency


def load_contrastive_corpus(path: Path) -> DiversityCorpus:
    """Load exact-evaluated training rows and bind repeated digest groups."""

    node_rows: list[np.ndarray] = []
    adjacency_rows: list[np.ndarray] = []
    literal_rows: list[str | None] = []
    candidate_rows: list[str] = []
    digest_counts: Counter[str] = Counter()
    labeled_rows = 0
    for line_number, row in enumerate(equality_ranker._jsonl_rows(path), start=1):
        candidate = row.get("candidate")
        if not isinstance(candidate, Mapping):
            raise RankerContractError(f"{path}:{line_number}: candidate is missing")
        try:
            nodes, adjacency = _candidate_arrays(candidate)
        except RankerContractError as error:
            raise RankerContractError(f"{path}:{line_number}: {error}") from error
        candidate_sha = row.get("candidate_sha256")
        computed_sha = equality_ranker._candidate_digest(candidate)
        if candidate_sha is None:
            candidate_sha = computed_sha
        if candidate_sha != computed_sha:
            raise RankerContractError(
                f"{path}:{line_number}: candidate identity mismatch"
            )
        decision = row.get("exact_decision")
        literal_sha: str | None = None
        if decision is not None:
            if not isinstance(decision, Mapping):
                raise RankerContractError(
                    f"{path}:{line_number}: exact_decision must be an object or null"
                )
            literal_sha = decision.get("candidate_root_game_sha256")
            if not _is_sha256(literal_sha):
                raise RankerContractError(
                    f"{path}:{line_number}: exact decision lacks literal-game digest"
                )
            labeled_rows += 1
            digest_counts[str(literal_sha)] += 1
        node_rows.append(nodes)
        adjacency_rows.append(adjacency)
        literal_rows.append(literal_sha)
        candidate_rows.append(str(candidate_sha))
    if not node_rows:
        raise RankerContractError(f"{path}: no rows")
    repeated = {digest for digest, count in digest_counts.items() if count >= 2}
    eligible_rows = sum(
        literal_sha in repeated
        for literal_sha in literal_rows
        if literal_sha is not None
    )
    if not repeated:
        raise RankerContractError("contrastive training requires a repeated digest")
    return DiversityCorpus(
        node_features=np.stack(node_rows),
        adjacency=np.stack(adjacency_rows),
        literal_game_sha256=tuple(literal_rows),
        candidate_sha256=tuple(candidate_rows),
        source_sha256=equality_ranker.sha256_file(path),
        row_count=len(node_rows),
        labeled_row_count=labeled_rows,
        literal_digest_group_count=len(digest_counts),
        eligible_group_count=len(repeated),
        eligible_row_count=eligible_rows,
    )


def _l2_normalize(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    safe = np.maximum(norms, 1e-12)
    return values / safe, safe


def supervised_nt_xent(
    embeddings: np.ndarray,
    positive_indices: np.ndarray,
    *,
    temperature: float,
) -> tuple[float, np.ndarray]:
    """Return ordered-anchor NT-Xent loss and its embedding gradient."""

    if embeddings.ndim != 2 or len(embeddings) < 2:
        raise RankerContractError("contrastive loss requires a two-dimensional batch")
    if positive_indices.shape != (len(embeddings),):
        raise RankerContractError("positive-index shape mismatch")
    if temperature not in CONTRASTIVE_TEMPERATURES:
        raise RankerContractError("temperature is outside the frozen grid")
    if any(
        not 0 <= int(positive) < len(embeddings) or int(positive) == index
        for index, positive in enumerate(positive_indices)
    ):
        raise RankerContractError("invalid positive-index mapping")

    count = len(embeddings)
    similarities = embeddings @ embeddings.T / temperature
    np.fill_diagonal(similarities, -np.inf)
    row_max = np.max(similarities, axis=1)
    exponentials = np.exp(similarities - row_max[:, None])
    np.fill_diagonal(exponentials, 0.0)
    denominators = exponentials.sum(axis=1)
    if np.any(denominators <= 0.0):
        raise RankerContractError("contrastive softmax denominator is zero")
    probabilities = exponentials / denominators[:, None]
    losses = (
        -similarities[np.arange(count), positive_indices]
        + np.log(denominators)
        + row_max
    )

    gradient_similarity = probabilities
    gradient_similarity[np.arange(count), positive_indices] -= 1.0
    gradient_similarity /= count
    gradient_embeddings = (
        gradient_similarity @ embeddings + gradient_similarity.T @ embeddings
    ) / temperature
    return float(np.mean(losses)), gradient_embeddings


class DirectedMPNNDiversityEncoder:
    """Directed message-passing graph encoder with invariant normalized output."""

    def __init__(
        self,
        *,
        embedding_width: int = EMBEDDING_WIDTHS[0],
        dropout: float = DROPOUT,
        random_seed: int = ENSEMBLE_SEEDS[0],
    ) -> None:
        if embedding_width not in EMBEDDING_WIDTHS:
            raise RankerContractError("embedding_width is outside the frozen grid")
        if not 0.0 <= dropout < 1.0:
            raise RankerContractError("dropout must lie in [0, 1)")
        self.embedding_width = embedding_width
        self.dropout = dropout
        self.random_seed = random_seed
        rng = np.random.default_rng(random_seed)
        self.parameters: dict[str, np.ndarray] = {
            "input_weight": rng.normal(
                0.0,
                math.sqrt(2.0 / 2),
                (2, HIDDEN_WIDTH),
            ),
            "input_bias": np.zeros(HIDDEN_WIDTH),
            "projection_hidden_weight": rng.normal(
                0.0,
                math.sqrt(2.0 / (2 * HIDDEN_WIDTH)),
                (2 * HIDDEN_WIDTH, HIDDEN_WIDTH),
            ),
            "projection_hidden_bias": np.zeros(HIDDEN_WIDTH),
            "projection_output_weight": rng.normal(
                0.0,
                math.sqrt(2.0 / HIDDEN_WIDTH),
                (HIDDEN_WIDTH, embedding_width),
            ),
            "projection_output_bias": np.zeros(embedding_width),
        }
        for layer in range(MESSAGE_PASSING_LAYERS):
            for kind in ("self", "incoming", "outgoing"):
                self.parameters[f"layer_{layer}_{kind}_weight"] = rng.normal(
                    0.0,
                    math.sqrt(2.0 / HIDDEN_WIDTH),
                    (HIDDEN_WIDTH, HIDDEN_WIDTH),
                )
            self.parameters[f"layer_{layer}_bias"] = np.zeros(HIDDEN_WIDTH)
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
        *,
        dropout_rng: np.random.Generator | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        input_pre = (
            node_features @ self.parameters["input_weight"]
            + self.parameters["input_bias"]
        )
        hidden = np.maximum(input_pre, 0.0)
        layer_caches: list[tuple[np.ndarray, ...]] = []
        for layer in range(MESSAGE_PASSING_LAYERS):
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
            layer_caches.append((hidden, incoming, outgoing, layer_pre, layer_mask))
            hidden = next_hidden

        pooled_mean = hidden.mean(axis=1)
        pooled_max = hidden.max(axis=1)
        max_ties = hidden == pooled_max[:, None, :]
        pooled = np.concatenate((pooled_mean, pooled_max), axis=1)
        projection_hidden_pre = (
            pooled @ self.parameters["projection_hidden_weight"]
            + self.parameters["projection_hidden_bias"]
        )
        projection_hidden = np.maximum(projection_hidden_pre, 0.0)
        raw_embedding = (
            projection_hidden @ self.parameters["projection_output_weight"]
            + self.parameters["projection_output_bias"]
        )
        embedding, embedding_norm = _l2_normalize(raw_embedding)
        return embedding, {
            "node_features": node_features,
            "adjacency": adjacency,
            "input_pre": input_pre,
            "layers": layer_caches,
            "final_hidden": hidden,
            "max_ties": max_ties,
            "pooled": pooled,
            "projection_hidden_pre": projection_hidden_pre,
            "projection_hidden": projection_hidden,
            "raw_embedding": raw_embedding,
            "embedding": embedding,
            "embedding_norm": embedding_norm,
        }

    def embed(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
    ) -> np.ndarray:
        embedding, _ = self._forward(
            node_features,
            adjacency,
            dropout_rng=None,
        )
        return embedding

    def _backward(
        self,
        cache: Mapping[str, Any],
        gradient_embedding: np.ndarray,
    ) -> dict[str, np.ndarray]:
        gradients = {
            name: np.zeros_like(value) for name, value in self.parameters.items()
        }
        embedding = cache["embedding"]
        projection = np.sum(gradient_embedding * embedding, axis=1, keepdims=True)
        gradient_raw = (gradient_embedding - embedding * projection) / cache[
            "embedding_norm"
        ]

        gradients["projection_output_weight"] = (
            cache["projection_hidden"].T @ gradient_raw
        )
        gradients["projection_output_bias"] = gradient_raw.sum(axis=0)
        gradient_projection_hidden = (
            gradient_raw @ self.parameters["projection_output_weight"].T
        )
        gradient_projection_pre = gradient_projection_hidden * (
            cache["projection_hidden_pre"] > 0.0
        )
        gradients["projection_hidden_weight"] = (
            cache["pooled"].T @ gradient_projection_pre
        )
        gradients["projection_hidden_bias"] = gradient_projection_pre.sum(axis=0)
        gradient_pooled = (
            gradient_projection_pre @ self.parameters["projection_hidden_weight"].T
        )

        gradient_mean = gradient_pooled[:, :HIDDEN_WIDTH]
        gradient_max = gradient_pooled[:, HIDDEN_WIDTH:]
        gradient_hidden = gradient_mean[:, None, :] / 7.0
        tie_count = cache["max_ties"].sum(axis=1)
        gradient_hidden = gradient_hidden + (
            gradient_max[:, None, :] * cache["max_ties"] / tie_count[:, None, :]
        )

        adjacency = cache["adjacency"]
        for layer in reversed(range(MESSAGE_PASSING_LAYERS)):
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

    @staticmethod
    def _eligible_groups(corpus: DiversityCorpus) -> dict[str, np.ndarray]:
        grouped: dict[str, list[int]] = defaultdict(list)
        for index, digest in enumerate(corpus.literal_game_sha256):
            if digest is not None:
                grouped[digest].append(index)
        return {
            digest: np.asarray(indices, dtype=np.int64)
            for digest, indices in sorted(grouped.items())
            if len(indices) >= 2
        }

    @staticmethod
    def _batch_indices(
        groups: Mapping[str, np.ndarray],
        *,
        epoch: int,
        random_seed: int,
    ) -> Iterable[tuple[np.ndarray, np.ndarray]]:
        digests = list(groups)
        rng = np.random.default_rng(random_seed + epoch)
        ordered = [digests[index] for index in rng.permutation(len(digests))]
        for offset in range(0, len(ordered), GROUPS_PER_BATCH):
            batch_groups = ordered[offset : offset + GROUPS_PER_BATCH]
            rows: list[int] = []
            positives: list[int] = []
            for digest in batch_groups:
                members = groups[digest]
                digest_offset = int(digest[:16], 16)
                start = (random_seed + epoch + digest_offset) % len(members)
                first = int(members[start])
                second = int(members[(start + 1) % len(members)])
                position = len(rows)
                rows.extend((first, second))
                positives.extend((position + 1, position))
            yield (
                np.asarray(rows, dtype=np.int64),
                np.asarray(positives, dtype=np.int64),
            )

    def fit(
        self,
        corpus: DiversityCorpus,
        *,
        temperature: float,
        epochs: int = TRAINING_EPOCHS,
        learning_rate: float = LEARNING_RATE,
        weight_decay: float = WEIGHT_DECAY,
        random_seed: int | None = None,
        capture_checkpoints: bool = False,
    ) -> list[dict[str, np.ndarray]]:
        if temperature not in CONTRASTIVE_TEMPERATURES:
            raise RankerContractError("temperature is outside the frozen grid")
        if epochs < 1 or learning_rate <= 0.0 or weight_decay < 0.0:
            raise RankerContractError("invalid optimization configuration")
        groups = self._eligible_groups(corpus)
        if len(groups) != corpus.eligible_group_count:
            raise RankerContractError("corpus group commitment does not replay")
        seed = self.random_seed if random_seed is None else random_seed
        dropout_rng = np.random.default_rng(seed)
        first_moment = {
            name: np.zeros_like(value) for name, value in self.parameters.items()
        }
        second_moment = {
            name: np.zeros_like(value) for name, value in self.parameters.items()
        }
        decay_names = {name for name in self.parameters if name.endswith("_weight")}
        update = 0
        checkpoints: list[dict[str, np.ndarray]] = []
        epoch_losses: list[float] = []
        for epoch in range(epochs):
            batch_losses: list[float] = []
            for batch, positives in self._batch_indices(
                groups,
                epoch=epoch,
                random_seed=seed,
            ):
                embeddings, cache = self._forward(
                    corpus.node_features[batch],
                    corpus.adjacency[batch],
                    dropout_rng=dropout_rng,
                )
                loss, gradient_embedding = supervised_nt_xent(
                    embeddings,
                    positives,
                    temperature=temperature,
                )
                gradients = self._backward(cache, gradient_embedding)
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
                        self.parameters[name] *= 1.0 - learning_rate * weight_decay
                    self.parameters[name] -= (
                        learning_rate
                        * corrected_first
                        / (np.sqrt(corrected_second) + 1e-8)
                    )
                batch_losses.append(loss)
            epoch_losses.append(float(np.mean(batch_losses)))
            if capture_checkpoints:
                checkpoints.append(
                    {name: value.copy() for name, value in self.parameters.items()}
                )
        self.training_summary = {
            "training_only": True,
            "validated": False,
            "epochs_completed": epochs,
            "source_rows": corpus.row_count,
            "nonnull_exact_decision_rows": corpus.labeled_row_count,
            "literal_digest_groups": corpus.literal_digest_group_count,
            "eligible_digest_groups": corpus.eligible_group_count,
            "eligible_rows": corpus.eligible_row_count,
            "groups_per_batch": GROUPS_PER_BATCH,
            "rows_per_group_per_epoch": ROWS_PER_GROUP,
            "final_epoch_mean_nt_xent": epoch_losses[-1],
        }
        return checkpoints

    def config_record(self) -> dict[str, Any]:
        return {
            "contract": ARCHITECTURE,
            "hidden_width": HIDDEN_WIDTH,
            "message_passing_layers": MESSAGE_PASSING_LAYERS,
            "embedding_width": self.embedding_width,
            "dropout": self.dropout,
            "node_features": ["is_blue", "is_red"],
            "directed_aggregation": {
                "incoming": "unnormalized_sum",
                "outgoing": "unnormalized_sum",
                "self": True,
            },
            "activation": "relu",
            "pooling": ["mean", "max"],
            "projection_head": "linear_relu_linear_l2_normalize",
            "parameter_count": self.parameter_count,
        }

    def to_record(
        self,
        *,
        corpus: DiversityCorpus,
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
                "nonnull_exact_decision_rows": corpus.labeled_row_count,
                "literal_digest_groups": corpus.literal_digest_group_count,
                "eligible_digest_groups": corpus.eligible_group_count,
                "eligible_rows": corpus.eligible_row_count,
                "contract": TRAINING_CONTRACT,
                "paper_evidence": False,
                "use": "training_only",
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
    def from_record(cls, record: Mapping[str, Any]) -> "DirectedMPNNDiversityEncoder":
        if record.get("schema_version") != MODEL_SCHEMA:
            raise RankerContractError("unsupported diversity model schema")
        architecture = record.get("architecture")
        if (
            not isinstance(architecture, Mapping)
            or architecture.get("contract") != ARCHITECTURE
        ):
            raise RankerContractError("unsupported diversity architecture")
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
                embedding_width=int(architecture["embedding_width"]),
                dropout=float(architecture["dropout"]),
                random_seed=int(optimization["random_seed"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RankerContractError("diversity architecture is malformed") from error
        if dict(architecture) != model.config_record():
            raise RankerContractError(
                "diversity architecture record disagrees with implementation"
            )
        if record.get("feature_contract") != feature_contract_record():
            raise RankerContractError(
                "diversity feature contract disagrees with implementation"
            )
        parameters = record.get("parameters")
        if not isinstance(parameters, Mapping) or set(parameters) != set(
            model.parameters
        ):
            raise RankerContractError("diversity model parameters are incomplete")
        for name, expected in model.parameters.items():
            supplied = np.asarray(parameters[name], dtype=np.float64)
            if supplied.shape != expected.shape or not np.isfinite(supplied).all():
                raise RankerContractError(f"invalid diversity parameter: {name}")
            model.parameters[name] = supplied
        model.training_summary = dict(record.get("training_summary", {}))
        return model


class DiversityEnsemble:
    """Three-seed ensemble retaining member-specific embedding coordinates."""

    def __init__(self, members: Sequence[DirectedMPNNDiversityEncoder]) -> None:
        if len(members) != len(ENSEMBLE_SEEDS):
            raise RankerContractError("diversity ensemble requires three members")
        if [member.random_seed for member in members] != list(ENSEMBLE_SEEDS):
            raise RankerContractError("diversity members follow the frozen seed order")
        configs = {(member.embedding_width, member.dropout) for member in members}
        if len(configs) != 1:
            raise RankerContractError("diversity members must share one configuration")
        self.members = tuple(members)

    def embed_members(
        self,
        node_features: np.ndarray,
        adjacency: np.ndarray,
    ) -> tuple[np.ndarray, ...]:
        return tuple(member.embed(node_features, adjacency) for member in self.members)

    def _validate_selection(self, selection: Mapping[str, Any]) -> None:
        report_id = selection.get("grid_report_id")
        if (
            not isinstance(report_id, str)
            or not report_id.startswith("grid-report-sha256:")
            or not _is_sha256(report_id.removeprefix("grid-report-sha256:"))
        ):
            raise RankerContractError("diversity selection grid report id is invalid")
        temperature = selection.get("contrastive_temperature")
        epoch = selection.get("epoch")
        lambda_weight = selection.get("lambda")
        first = self.members[0]
        if (
            selection.get("embedding_width") != first.embedding_width
            or temperature not in CONTRASTIVE_TEMPERATURES
            or not isinstance(epoch, int)
            or isinstance(epoch, bool)
            or not 1 <= epoch <= TRAINING_EPOCHS
            or lambda_weight not in LAMBDA_GRID
        ):
            raise RankerContractError(
                "diversity selection disagrees with the frozen grid"
            )
        checkpoint_digests = selection.get("member_checkpoint_sha256")
        observed_digests = [
            _parameters_digest(member.parameters) for member in self.members
        ]
        if checkpoint_digests != observed_digests:
            raise RankerContractError(
                "diversity members do not match selected checkpoint digests"
            )

    def to_record(
        self,
        *,
        corpus: DiversityCorpus,
        selection: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._validate_selection(selection)
        temperature = selection["contrastive_temperature"]
        epoch = selection["epoch"]
        member_records = [
            member.to_record(
                corpus=corpus,
                optimization={
                    "random_seed": member.random_seed,
                    "epochs": epoch,
                    "learning_rate": LEARNING_RATE,
                    "weight_decay": WEIGHT_DECAY,
                    "dropout": DROPOUT,
                    "optimizer": "adamw_v1",
                    "loss": "supervised_nt_xent_one_same_digest_positive_per_anchor",
                    "contrastive_temperature": temperature,
                },
            )
            for member in self.members
        ]
        record: dict[str, Any] = {
            "schema_version": ENSEMBLE_SCHEMA,
            "model_id": "ensemble-sha256:" + "0" * 64,
            "aggregation": "mean_member_minimum_cosine_distance",
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
    def from_record(cls, record: Mapping[str, Any]) -> "DiversityEnsemble":
        if record.get("schema_version") != ENSEMBLE_SCHEMA:
            raise RankerContractError("unsupported diversity ensemble schema")
        payload = dict(record)
        supplied_id = payload.pop("model_id", None)
        expected_id = (
            "ensemble-sha256:"
            + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        )
        if supplied_id != expected_id:
            raise RankerContractError("ensemble model_id does not match content")
        if record.get("aggregation") != "mean_member_minimum_cosine_distance":
            raise RankerContractError("unsupported diversity ensemble aggregation")
        if record.get("member_seeds") != list(ENSEMBLE_SEEDS):
            raise RankerContractError("diversity ensemble seed binding changed")
        members = record.get("members")
        if not isinstance(members, list):
            raise RankerContractError("diversity ensemble members are missing")
        model = cls(
            [DirectedMPNNDiversityEncoder.from_record(member) for member in members]
        )
        selection = record.get("selection")
        if not isinstance(selection, Mapping):
            raise RankerContractError("diversity ensemble selection is missing")
        model._validate_selection(selection)
        return model


def _parameters_digest(parameters: Mapping[str, np.ndarray]) -> str:
    payload = {name: value.tolist() for name, value in sorted(parameters.items())}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def midrank_fraction(values: Sequence[float]) -> np.ndarray:
    """Map ascending numerical midranks to [0,1], preserving exact ties."""

    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or not len(array) or not np.isfinite(array).all():
        raise RankerContractError("midrank input must be a finite nonempty vector")
    if len(array) == 1:
        return np.asarray([0.5], dtype=np.float64)
    order = np.argsort(array, kind="mergesort")
    output = np.empty(len(array), dtype=np.float64)
    start = 0
    while start < len(array):
        end = start + 1
        while end < len(array) and array[order[end]] == array[order[start]]:
            end += 1
        output[order[start:end]] = (start + end - 1) / 2.0 / (len(array) - 1)
        start = end
    return output


def _pool_arrays(
    proposal_rows: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...], str, int, str]:
    if not proposal_rows:
        raise RankerContractError("rank fusion requires at least one proposal")
    node_rows: list[np.ndarray] = []
    adjacency_rows: list[np.ndarray] = []
    candidate_ids: list[str] = []
    groups: set[tuple[str, str, int]] = set()
    for row in proposal_rows:
        forbidden = equality_ranker.OUTCOME_FIELDS_FORBIDDEN_IN_POOL_SCORING & set(row)
        if forbidden:
            raise RankerContractError(
                "rank fusion received outcome fields: " + ", ".join(sorted(forbidden))
            )
        nodes, adjacency, _target_index, metadata = equality_ranker.proposal_features(
            row,
            include_outcome_metadata=False,
        )
        if metadata.operator != "toggle_one_arc":
            raise RankerContractError("rank fusion accepts toggle_one_arc only")
        if metadata.pool_id is None:
            raise RankerContractError("rank fusion requires a pool id")
        node_rows.append(nodes)
        adjacency_rows.append(adjacency)
        candidate_ids.append(metadata.candidate_sha256)
        groups.add((metadata.pool_id, metadata.target, metadata.base_seed))
    if len(groups) != 1:
        raise RankerContractError("rank fusion rows must share pool, target, and seed")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise RankerContractError("rank fusion pool contains duplicate candidates")
    pool_id, target, base_seed = next(iter(groups))
    return (
        np.stack(node_rows),
        np.stack(adjacency_rows),
        tuple(candidate_ids),
        target,
        base_seed,
        pool_id,
    )


def _memory_arrays(
    memory_candidates: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    if not memory_candidates:
        raise RankerContractError("novelty memory requires the Stage-0 graph")
    nodes: list[np.ndarray] = []
    adjacency: list[np.ndarray] = []
    for candidate in memory_candidates:
        if "candidate" in candidate:
            raise RankerContractError(
                "novelty memory accepts direct graph objects without event fields"
            )
        node_values, adjacency_values = _candidate_arrays(candidate)
        nodes.append(node_values)
        adjacency.append(adjacency_values)
    return np.stack(nodes), np.stack(adjacency)


def candidate_novelty_scores(
    ensemble: DiversityEnsemble,
    candidate_nodes: np.ndarray,
    candidate_adjacency: np.ndarray,
    memory_nodes: np.ndarray,
    memory_adjacency: np.ndarray,
) -> np.ndarray:
    """Average member-specific minimum cosine distance to the arm memory."""

    candidate_members = ensemble.embed_members(candidate_nodes, candidate_adjacency)
    memory_members = ensemble.embed_members(memory_nodes, memory_adjacency)
    scores = []
    for candidates, memory in zip(candidate_members, memory_members):
        similarities = np.clip(candidates @ memory.T, -1.0, 1.0)
        scores.append(np.min(1.0 - similarities, axis=1))
    output = np.mean(np.stack(scores), axis=0)
    if not np.isfinite(output).all():
        raise RankerContractError("novelty ensemble produced a non-finite score")
    return output


def rank_fusion_pool(
    *,
    equality_scores: Sequence[float],
    novelty_ensemble: DiversityEnsemble,
    proposal_rows: Sequence[Mapping[str, Any]],
    memory_candidates: Sequence[Mapping[str, Any]],
    lambda_weight: float,
    equality_model_id: str,
    novelty_model_id: str,
) -> list[dict[str, Any]]:
    """Rank one outcome-free proposal pool by frozen equality/novelty fusion."""

    if lambda_weight not in LAMBDA_GRID:
        raise RankerContractError("lambda is outside the frozen grid")
    (
        candidate_nodes,
        candidate_adjacency,
        candidate_ids,
        target,
        base_seed,
        pool_id,
    ) = _pool_arrays(proposal_rows)
    equality = np.asarray(equality_scores, dtype=np.float64)
    if equality.shape != (len(candidate_ids),) or not np.isfinite(equality).all():
        raise RankerContractError("equality scores do not match the proposal pool")
    memory_nodes, memory_adjacency = _memory_arrays(memory_candidates)
    novelty = candidate_novelty_scores(
        novelty_ensemble,
        candidate_nodes,
        candidate_adjacency,
        memory_nodes,
        memory_adjacency,
    )
    equality_rank = midrank_fraction(equality)
    novelty_rank = midrank_fraction(novelty)
    fused = equality_rank + lambda_weight * novelty_rank
    order = sorted(
        range(len(candidate_ids)),
        key=lambda index: (-float(fused[index]), candidate_ids[index]),
    )
    records: list[dict[str, Any]] = []
    for rank, index in enumerate(order):
        records.append(
            {
                "schema_version": RANK_SCHEMA,
                "candidate_sha256": candidate_ids[index],
                "target": target,
                "base_seed": base_seed,
                "pool_id": pool_id,
                "operator": "toggle_one_arc",
                "rank_zero_based": rank,
                "equality_model_id": equality_model_id,
                "novelty_model_id": novelty_model_id,
                "equality_score": float(equality[index]),
                "novelty_score": float(novelty[index]),
                "equality_midrank_fraction": float(equality_rank[index]),
                "novelty_midrank_fraction": float(novelty_rank[index]),
                "lambda": float(lambda_weight),
                "rank_fusion_score": float(fused[index]),
            }
        )
    return records


def _load_diversity_model(
    path: Path,
) -> tuple[DiversityEnsemble, dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RankerContractError(f"{path}: expected a JSON object")
    if value.get("schema_version") == MODEL_SCHEMA:
        raise RankerContractError(
            "acquisition requires a selected three-member diversity ensemble"
        )
    return DiversityEnsemble.from_record(value), value


def build_resource_preflight_diversity_ranker(
    *,
    equality_model_artifact_path: Path,
    equality_model_id: str,
    novelty_model_artifact_path: Path,
    novelty_model_id: str,
    lambda_weight: float,
):
    """Load both frozen artifacts and return the outcome-free fusion policy."""

    equality_score_pool = equality_ranker.build_resource_preflight_ranker(
        model_artifact_path=Path(equality_model_artifact_path),
        model_id=equality_model_id,
    )
    novelty_ensemble, novelty_record = _load_diversity_model(
        Path(novelty_model_artifact_path)
    )
    if novelty_record.get("model_id") != novelty_model_id:
        raise RankerContractError(
            "requested novelty_model_id does not match model artifact"
        )
    if lambda_weight not in LAMBDA_GRID:
        raise RankerContractError("lambda is outside the frozen grid")

    def rank_pool_with_memory(
        rows: Sequence[Mapping[str, Any]],
        memory_candidates: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        equality_scores = equality_score_pool(rows)
        return rank_fusion_pool(
            equality_scores=equality_scores,
            novelty_ensemble=novelty_ensemble,
            proposal_rows=rows,
            memory_candidates=memory_candidates,
            lambda_weight=lambda_weight,
            equality_model_id=equality_model_id,
            novelty_model_id=novelty_model_id,
        )

    return rank_pool_with_memory


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
            "Train a target-free graph diversity encoder while keeping exact "
            "Digraph Placement evaluation authoritative."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fit = commands.add_parser(
        "train",
        help="fit one frozen-grid member on training-only literal digest groups",
    )
    fit.add_argument("--events", type=Path, required=True)
    fit.add_argument("--model-out", type=Path, required=True)
    fit.add_argument(
        "--embedding-width",
        type=int,
        choices=EMBEDDING_WIDTHS,
        default=EMBEDDING_WIDTHS[0],
    )
    fit.add_argument(
        "--temperature",
        type=float,
        choices=CONTRASTIVE_TEMPERATURES,
        default=CONTRASTIVE_TEMPERATURES[0],
    )
    fit.add_argument(
        "--random-seed",
        type=int,
        choices=ENSEMBLE_SEEDS,
        default=ENSEMBLE_SEEDS[0],
    )

    rank = commands.add_parser(
        "rank",
        help="rank one outcome-free proposal pool with frozen equality and novelty",
    )
    rank.add_argument("--proposals", type=Path, required=True)
    rank.add_argument("--memory-candidates", type=Path, required=True)
    rank.add_argument("--equality-model", type=Path, required=True)
    rank.add_argument("--equality-model-id", required=True)
    rank.add_argument("--novelty-model", type=Path, required=True)
    rank.add_argument("--novelty-model-id", required=True)
    rank.add_argument("--lambda-weight", type=float, choices=LAMBDA_GRID, required=True)
    rank.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "train":
            corpus = load_contrastive_corpus(args.events)
            model = DirectedMPNNDiversityEncoder(
                embedding_width=args.embedding_width,
                dropout=DROPOUT,
                random_seed=args.random_seed,
            )
            model.fit(
                corpus,
                temperature=args.temperature,
                epochs=TRAINING_EPOCHS,
                learning_rate=LEARNING_RATE,
                weight_decay=WEIGHT_DECAY,
                random_seed=args.random_seed,
            )
            record = model.to_record(
                corpus=corpus,
                optimization={
                    "random_seed": args.random_seed,
                    "epochs": TRAINING_EPOCHS,
                    "learning_rate": LEARNING_RATE,
                    "weight_decay": WEIGHT_DECAY,
                    "dropout": DROPOUT,
                    "optimizer": "adamw_v1",
                    "loss": ("supervised_nt_xent_one_same_digest_positive_per_anchor"),
                    "contrastive_temperature": args.temperature,
                },
            )
            _write_json(args.model_out, record)
            print(
                f"model: {record['model_id']} "
                f"(groups={corpus.eligible_group_count}, "
                f"rows={corpus.eligible_row_count}, status=training_only)"
            )
            print(f"wrote {args.model_out}")
            return 0
        if args.command == "rank":
            proposals = list(equality_ranker._jsonl_rows(args.proposals))
            memory = list(equality_ranker._jsonl_rows(args.memory_candidates))
            callback = build_resource_preflight_diversity_ranker(
                equality_model_artifact_path=args.equality_model,
                equality_model_id=args.equality_model_id,
                novelty_model_artifact_path=args.novelty_model,
                novelty_model_id=args.novelty_model_id,
                lambda_weight=args.lambda_weight,
            )
            records = callback(proposals, memory)
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
        print(f"partizan-digraph-diversity-ranker: {error}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
