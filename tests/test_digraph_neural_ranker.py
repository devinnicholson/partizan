from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

MODULE_PATH = (
    Path(__file__).parents[1] / "python" / "partizan" / "digraph_neural_ranker.py"
)
SPEC = importlib.util.spec_from_file_location(
    "partizan_digraph_neural_ranker_for_tests", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("could not load neural ranker")
ranker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ranker
SPEC.loader.exec_module(ranker)


def graph(variant: int) -> dict:
    arcs = {(vertex, (vertex + 1) % 7) for vertex in range(7)}
    optional = [
        (source, target)
        for source in range(7)
        for target in range(7)
        if source != target and (source, target) not in arcs
    ]
    for bit, arc in enumerate(optional):
        if variant & (1 << bit):
            arcs.add(arc)
    return {
        "order": 7,
        "blue_vertices": sorted({variant % 7, (variant + 2) % 7, (variant + 4) % 7}),
        "arcs": [list(arc) for arc in sorted(arcs)],
    }


def row(
    variant: int,
    *,
    equal: bool,
    target: str = "0",
    base_seed: int = 1,
    operator: str = "toggle_one_arc",
    pool_id: str | None = None,
) -> dict:
    candidate = graph(variant)
    value = {
        "candidate": candidate,
        "candidate_sha256": ranker._candidate_digest(candidate),
        "target": target,
        "base_seed": base_seed,
        "proposal": {
            "mode": "local_mutation",
            "operator": operator,
        },
        "exact_decision": {
            "equal": equal,
            "candidate_root_game_sha256": hashlib.sha256(
                f"literal-{variant}".encode("ascii")
            ).hexdigest(),
        },
        "quotient": (
            {
                "quotient_sha256": hashlib.sha256(
                    f"quotient-{variant}".encode("ascii")
                ).hexdigest()
            }
            if equal
            else None
        ),
    }
    if pool_id is not None:
        value["ranker_pool"] = {"pool_id": pool_id}
    return value


def relabel(candidate: dict, permutation: list[int]) -> dict:
    return {
        "order": 7,
        "blue_vertices": sorted(
            permutation[vertex] for vertex in candidate["blue_vertices"]
        ),
        "arcs": sorted(
            [
                [permutation[source], permutation[target]]
                for source, target in candidate["arcs"]
            ]
        ),
    }


def persist_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_bytes(b"".join(ranker.canonical_json_bytes(value) for value in rows))


class DigraphNeuralRankerTests(unittest.TestCase):
    def test_frozen_grid_has_exactly_eight_configurations(self) -> None:
        configs = ranker.frozen_grid_configs()
        self.assertEqual(len(configs), 8)
        self.assertEqual(
            {
                (
                    config["hidden_width"],
                    config["layer_count"],
                    config["learning_rate"],
                )
                for config in configs
            },
            {
                (hidden, layers, learning_rate)
                for hidden in (32, 64)
                for layers in (2, 3)
                for learning_rate in (0.001, 0.0003)
            },
        )

    def test_validation_selector_uses_static_groups_and_row_markers(self) -> None:
        training_rows = [
            row(100 + index, equal=index % 2 == 0, base_seed=10 + index)
            for index in range(6)
        ]
        validation_rows = []
        for target_index, target in enumerate(ranker.TARGETS):
            for member in range(16):
                value = row(
                    target_index * 16 + member,
                    equal=member == 0,
                    target=target,
                    base_seed=900 + target_index,
                    pool_id=f"pool-{target_index}",
                )
                value["weakly_connected"] = True
                value["training_candidate_collision"] = False
                value["training_quotient_collision"] = False
                value["eligible_for_validation_metric"] = True
                value["exclusion_reasons"] = []
                validation_rows.append(value)
        with tempfile.TemporaryDirectory(prefix="partizan-selector-metrics-") as temp:
            training_path = Path(temp) / "training.jsonl"
            validation_path = Path(temp) / "validation.jsonl"
            persist_jsonl(training_path, training_rows)
            persist_jsonl(validation_path, validation_rows)
            training = ranker.load_corpus(training_path, require_labels=True)
            validation = ranker.load_corpus(validation_path, require_labels=True)
            scores = np.asarray(
                [10.0 if label > 0.5 else -10.0 for label in validation.labels]
            )
            metrics = ranker.validation_selection_metrics(scores, training, validation)
            self.assertEqual(metrics["target_macro_top1_exact_rate"], 1.0)
            self.assertEqual(
                metrics["groups"],
                {"committed": 3, "eligible": 3, "excluded_empty": 0},
            )

    def test_package_cli_help_does_not_require_native_extension(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "python")
        environment["PYTHONPYCACHEPREFIX"] = "/tmp/partizan-neural-test-pyc"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "partizan.digraph_neural_ranker",
                "--help",
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("{train,evaluate,select-grid,rank}", completed.stdout)

    def test_score_is_invariant_to_vertex_relabeling(self) -> None:
        original = row(3, equal=True)
        permutation = [4, 0, 6, 2, 5, 1, 3]
        transformed = deepcopy(original)
        transformed["candidate"] = relabel(original["candidate"], permutation)
        transformed["candidate_sha256"] = ranker._candidate_digest(
            transformed["candidate"]
        )

        (
            original_nodes,
            original_adjacency,
            original_target,
            _,
        ) = ranker.proposal_features(original)
        (
            transformed_nodes,
            transformed_adjacency,
            transformed_target,
            _,
        ) = ranker.proposal_features(transformed)
        model = ranker.DirectedMPNNRanker(random_seed=17)
        original_score = model.predict_proba(
            original_nodes[None, :, :],
            original_adjacency[None, :, :],
            np.asarray([original_target]),
        )[0]
        transformed_score = model.predict_proba(
            transformed_nodes[None, :, :],
            transformed_adjacency[None, :, :],
            np.asarray([transformed_target]),
        )[0]
        self.assertAlmostEqual(
            float(original_score), float(transformed_score), places=14
        )

    def test_operator_and_outcomes_are_not_model_features(self) -> None:
        first = row(2, equal=True, operator="toggle_one_arc")
        second = deepcopy(first)
        second["proposal"]["operator"] = "uniform_immigrant"
        second["exact_decision"] = None
        second["quotient"] = None
        second["rejection"] = {"reason": "fixture"}
        second["retention"] = {"inserted": False}

        (
            first_nodes,
            first_adjacency,
            first_target,
            first_metadata,
        ) = ranker.proposal_features(first)
        (
            second_nodes,
            second_adjacency,
            second_target,
            second_metadata,
        ) = ranker.proposal_features(second)
        np.testing.assert_array_equal(first_nodes, second_nodes)
        np.testing.assert_array_equal(first_adjacency, second_adjacency)
        self.assertEqual(first_target, second_target)
        self.assertNotEqual(first_metadata.operator, second_metadata.operator)
        self.assertIsNone(first_metadata.quotient_sha256)
        self.assertIsNone(first_metadata.literal_game_sha256)

    def test_censored_rows_are_excluded_and_counted_by_stage_and_reason(self) -> None:
        evaluated = row(1, equal=True)
        censored = row(2, equal=False)
        censored["exact_decision"] = None
        censored["rejection"] = {
            "stage": "representation_grammar",
            "reason": "weakly_disconnected",
        }
        with tempfile.TemporaryDirectory(prefix="partizan-neural-censor-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, [evaluated, censored])
            corpus = ranker.load_corpus(path, require_labels=True)
            self.assertEqual(ranker.labeled_indices(corpus).tolist(), [0])
            self.assertTrue(np.isnan(corpus.labels[1]))
            self.assertEqual(
                corpus.censored_by_rejection_stage,
                {"representation_grammar": 1},
            )
            self.assertEqual(
                corpus.censored_by_rejection_reason,
                {"weakly_disconnected": 1},
            )

    def test_mpnn_backward_matches_finite_differences(self) -> None:
        nodes = np.asarray(
            [
                [[1, 0], [0, 1], [1, 0], [0, 1], [0, 1], [1, 0], [0, 1]],
                [[0, 1], [1, 0], [0, 1], [1, 0], [1, 0], [0, 1], [1, 0]],
            ],
            dtype=np.float64,
        )
        adjacency = np.zeros((2, 7, 7), dtype=np.float64)
        arc_sets = (
            ((0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (4, 5), (5, 6), (1, 6)),
            ((0, 2), (2, 1), (1, 4), (4, 3), (3, 6), (6, 5), (0, 5), (2, 6)),
        )
        for batch, arcs in enumerate(arc_sets):
            for source, target in arcs:
                adjacency[batch, source, target] = 1.0
        targets = np.asarray([0, 1], dtype=np.int64)
        labels = np.asarray([1.0, 0.0])
        model = ranker.DirectedMPNNRanker(
            hidden_width=32,
            layer_count=2,
            dropout=0.0,
            random_seed=17,
        )

        _, initial_cache = model._forward(nodes, adjacency, targets)
        tied_dimensions = initial_cache["max_ties"].sum(axis=1).max(axis=0) > 1
        model.parameters["head_weight"][model.hidden_width : 2 * model.hidden_width][
            tied_dimensions
        ] = 0.0
        logits, cache = model._forward(nodes, adjacency, targets)
        analytic = model._backward(
            cache, (ranker._sigmoid(logits) - labels) / len(labels)
        )

        def loss() -> float:
            current = model.predict_logits(nodes, adjacency, targets)
            return float(np.mean(np.logaddexp(0.0, current) - labels * current))

        epsilon = 1e-5
        checked = (
            "input_weight",
            "layer_0_incoming_weight",
            "layer_0_outgoing_weight",
            "target_embedding",
            "head_weight",
            "output_weight",
        )
        for name in checked:
            index = np.unravel_index(
                int(np.argmax(np.abs(analytic[name]))), analytic[name].shape
            )
            self.assertGreater(abs(float(analytic[name][index])), 1e-8, name)
            original = float(model.parameters[name][index])
            model.parameters[name][index] = original + epsilon
            positive = loss()
            model.parameters[name][index] = original - epsilon
            negative = loss()
            model.parameters[name][index] = original
            numeric = (positive - negative) / (2.0 * epsilon)
            self.assertAlmostEqual(
                float(analytic[name][index]),
                numeric,
                delta=3e-4 * max(1.0, abs(numeric)),
                msg=name,
            )

    def test_mpnn_can_overfit_a_tiny_fixture(self) -> None:
        rows = [
            row(
                variant,
                equal=variant % 2 == 0,
                target="0" if variant % 2 == 0 else "*",
                base_seed=700 + variant,
            )
            for variant in range(12)
        ]
        with tempfile.TemporaryDirectory(prefix="partizan-neural-overfit-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, rows)
            corpus = ranker.load_corpus(path, require_labels=True)
            model = ranker.DirectedMPNNRanker(
                hidden_width=32,
                layer_count=2,
                dropout=0.0,
                random_seed=41,
            )
            before = ranker._binary_log_loss(
                corpus.labels,
                model.predict_proba(
                    corpus.node_features,
                    corpus.adjacency,
                    corpus.target_indices,
                ),
            )
            model.fit(
                corpus,
                epochs=60,
                batch_size=6,
                learning_rate=0.01,
                weight_decay=0.0,
                random_seed=41,
            )
            probabilities = model.predict_proba(
                corpus.node_features,
                corpus.adjacency,
                corpus.target_indices,
            )
            after = ranker._binary_log_loss(corpus.labels, probabilities)
            accuracy = np.mean((probabilities >= 0.5) == corpus.labels)
            self.assertLess(after, before * 0.1)
            self.assertEqual(float(accuracy), 1.0)

    def test_training_and_serialization_are_deterministic(self) -> None:
        rows = [
            row(
                variant,
                equal=variant % 3 != 0,
                target=ranker.TARGETS[variant % len(ranker.TARGETS)],
                base_seed=100 + variant // 6,
            )
            for variant in range(18)
        ]
        with tempfile.TemporaryDirectory(prefix="partizan-neural-test-") as temp:
            events = Path(temp) / "events.jsonl"
            persist_jsonl(events, rows)
            corpus = ranker.load_corpus(events, require_labels=True)
            records = []
            for _ in range(2):
                model = ranker.DirectedMPNNRanker(random_seed=23)
                model.fit(
                    corpus,
                    epochs=4,
                    batch_size=5,
                    random_seed=23,
                )
                records.append(
                    model.to_record(
                        corpus=corpus,
                        optimization={
                            "random_seed": 23,
                            "epochs": 4,
                            "batch_size": 5,
                        },
                    )
                )
            self.assertEqual(
                ranker.canonical_json_bytes(records[0]),
                ranker.canonical_json_bytes(records[1]),
            )
            loaded = ranker.DirectedMPNNRanker.from_record(records[0])
            np.testing.assert_array_equal(
                loaded.predict_proba(
                    corpus.node_features,
                    corpus.adjacency,
                    corpus.target_indices,
                ),
                model.predict_proba(
                    corpus.node_features,
                    corpus.adjacency,
                    corpus.target_indices,
                ),
            )

    def test_rank_output_carries_no_outcomes(self) -> None:
        rows = [row(index, equal=index % 2 == 0) for index in range(4)]
        with tempfile.TemporaryDirectory(prefix="partizan-neural-rank-") as temp:
            events = Path(temp) / "events.jsonl"
            persist_jsonl(events, rows)
            corpus = ranker.load_corpus(events, require_labels=False)
            model = ranker.DirectedMPNNRanker(random_seed=31)
            records = ranker.rank_records(
                model,
                corpus,
                model_id="model-sha256:" + "0" * 64,
            )
            forbidden = {
                "exact_decision",
                "quotient",
                "rejection",
                "retention",
                "transition",
            }
            self.assertTrue(records)
            for record in records:
                self.assertFalse(forbidden & set(record))

    def test_rank_pool_accepts_one_outcome_free_same_operator_pool(self) -> None:
        rows = [
            row(
                index,
                equal=index % 2 == 0,
                base_seed=91,
                pool_id="pool-fixture",
            )
            for index in range(4)
        ]
        for value in rows:
            value.pop("exact_decision")
            value.pop("quotient")
        records = ranker.rank_pool(
            ranker.DirectedMPNNRanker(random_seed=11),
            rows,
            model_id="model-sha256:" + "0" * 64,
        )
        self.assertEqual(
            [record["rank_zero_based"] for record in records],
            list(range(4)),
        )
        self.assertEqual({record["pool_id"] for record in records}, {"pool-fixture"})

    def test_rank_pool_accepts_frozen_top_level_pool_id(self) -> None:
        rows = [
            row(
                index,
                equal=False,
                base_seed=92,
                pool_id=None,
            )
            for index in range(4)
        ]
        for value in rows:
            value["pool_id"] = "frozen-validation-pool"
            value.pop("exact_decision")
            value.pop("quotient")
        records = ranker.rank_pool(
            ranker.DirectedMPNNRanker(random_seed=11),
            rows,
            model_id="model-sha256:" + "0" * 64,
        )
        self.assertEqual(
            {record["pool_id"] for record in records},
            {"frozen-validation-pool"},
        )
        rows[0]["ranker_pool"] = {"pool_id": "different-pool"}
        with self.assertRaisesRegex(ranker.RankerContractError, "pool ids disagree"):
            ranker.rank_pool(
                ranker.DirectedMPNNRanker(random_seed=11),
                rows,
                model_id="model-sha256:" + "0" * 64,
            )

    def test_pool_scoring_rejects_outcome_fields(self) -> None:
        rows = [
            row(
                index,
                equal=False,
                base_seed=93,
                pool_id="pool-outcome-adversary",
            )
            for index in range(4)
        ]
        for value in rows:
            value.pop("exact_decision")
            value.pop("quotient")
        rows[0]["retention"] = {"inserted": False}
        with self.assertRaisesRegex(
            ranker.RankerContractError, "outcome fields: retention"
        ):
            ranker.rank_pool(
                ranker.DirectedMPNNRanker(random_seed=11),
                rows,
                model_id="model-sha256:" + "0" * 64,
            )

    def test_ensemble_round_trip_can_rank_a_pool(self) -> None:
        training_rows = [
            row(index, equal=index % 2 == 0, base_seed=100 + index)
            for index in range(6)
        ]
        pool_rows = [
            row(
                20 + index,
                equal=False,
                base_seed=999,
                pool_id="pool-ensemble-fixture",
            )
            for index in range(4)
        ]
        for value in pool_rows:
            value.pop("exact_decision")
            value.pop("quotient")
        with tempfile.TemporaryDirectory(prefix="partizan-ensemble-roundtrip-") as temp:
            training_path = Path(temp) / "training.jsonl"
            ensemble_path = Path(temp) / "ensemble.json"
            persist_jsonl(training_path, training_rows)
            corpus = ranker.load_corpus(training_path, require_labels=True)
            ensemble = ranker.LogitEnsemble(
                [
                    ranker.DirectedMPNNRanker(random_seed=seed)
                    for seed in ranker.ENSEMBLE_SEEDS
                ]
            )
            checkpoint_digests = [
                ranker._parameters_digest(member.parameters)
                for member in ensemble.members
            ]
            record = ensemble.to_record(
                corpus=corpus,
                selection={
                    "grid_report_id": "grid-report-sha256:" + "0" * 64,
                    "selected": {
                        "config_id": "h32-l2-lr0.0010",
                        "hidden_width": 32,
                        "layer_count": 2,
                        "learning_rate": 0.001,
                        "epoch": 1,
                        "parameter_count": ensemble.members[0].parameter_count,
                        "member_checkpoint_sha256": checkpoint_digests,
                    },
                },
            )
            ranker._write_json(ensemble_path, record)
            loaded, loaded_record = ranker._load_model(ensemble_path)
            self.assertIsInstance(loaded, ranker.LogitEnsemble)
            first = ranker.rank_pool(
                ensemble,
                pool_rows,
                model_id=record["model_id"],
            )
            second = ranker.rank_pool(
                loaded,
                pool_rows,
                model_id=loaded_record["model_id"],
            )
            self.assertEqual(first, second)

    def test_resource_preflight_factory_verifies_artifact_and_preserves_order(
        self,
    ) -> None:
        training_rows = [
            row(index, equal=index % 2 == 0, base_seed=300 + index)
            for index in range(6)
        ]
        pool_rows = [
            row(
                30 + index,
                equal=False,
                base_seed=1200,
                pool_id="pool-preflight-factory",
            )
            for index in (2, 0, 3, 1)
        ]
        for value in pool_rows:
            value.pop("exact_decision")
            value.pop("quotient")
        with tempfile.TemporaryDirectory(prefix="partizan-factory-") as temp:
            training_path = Path(temp) / "training.jsonl"
            model_path = Path(temp) / "model.json"
            persist_jsonl(training_path, training_rows)
            corpus = ranker.load_corpus(training_path, require_labels=True)
            model = ranker.DirectedMPNNRanker(random_seed=31)
            model_record = model.to_record(
                corpus=corpus,
                optimization={"random_seed": 31},
            )
            ranker._write_json(model_path, model_record)
            callback = ranker.build_resource_preflight_ranker(
                model_artifact_path=model_path,
                model_id=model_record["model_id"],
            )
            first = callback(pool_rows)
            second = callback(pool_rows)
            self.assertEqual(first, second)
            expected_by_candidate = {
                record["candidate_sha256"]: record["score"]
                for record in ranker.rank_pool(
                    model,
                    pool_rows,
                    model_id=model_record["model_id"],
                )
            }
            self.assertEqual(
                first,
                [
                    expected_by_candidate[value["candidate_sha256"]]
                    for value in pool_rows
                ],
            )
            with self.assertRaisesRegex(
                ranker.RankerContractError, "model_id does not match"
            ):
                ranker.build_resource_preflight_ranker(
                    model_artifact_path=model_path,
                    model_id="model-sha256:" + "f" * 64,
                )

    def test_ensemble_loader_rejects_checkpoint_binding_mismatch(self) -> None:
        training_rows = [
            row(index, equal=index % 2 == 0, base_seed=1300 + index)
            for index in range(6)
        ]
        with tempfile.TemporaryDirectory(prefix="partizan-ensemble-binding-") as temp:
            training_path = Path(temp) / "training.jsonl"
            persist_jsonl(training_path, training_rows)
            corpus = ranker.load_corpus(training_path, require_labels=True)
            ensemble = ranker.LogitEnsemble(
                [
                    ranker.DirectedMPNNRanker(random_seed=seed)
                    for seed in ranker.ENSEMBLE_SEEDS
                ]
            )
            selected = {
                "config_id": "h32-l2-lr0.0010",
                "hidden_width": 32,
                "layer_count": 2,
                "learning_rate": 0.001,
                "epoch": 1,
                "parameter_count": ensemble.members[0].parameter_count,
                "member_checkpoint_sha256": [
                    ranker._parameters_digest(member.parameters)
                    for member in ensemble.members
                ],
            }
            record = ensemble.to_record(
                corpus=corpus,
                selection={
                    "grid_report_id": "grid-report-sha256:" + "0" * 64,
                    "selected": selected,
                },
            )
            changed = deepcopy(record)
            changed["selection"]["selected"]["member_checkpoint_sha256"][0] = "f" * 64
            payload = dict(changed)
            payload.pop("model_id")
            changed["model_id"] = (
                "ensemble-sha256:"
                + hashlib.sha256(ranker.canonical_json_bytes(payload)).hexdigest()
            )
            with self.assertRaisesRegex(
                ranker.RankerContractError, "selected checkpoint"
            ):
                ranker.LogitEnsemble.from_record(changed)

    def test_grid_selector_visits_all_checkpoints_and_restores_selection(
        self,
    ) -> None:
        rows = [
            row(index, equal=index % 2 == 0, base_seed=1400 + index)
            for index in range(4)
        ]
        with tempfile.TemporaryDirectory(prefix="partizan-grid-audit-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, rows)
            corpus = ranker.load_corpus(path, require_labels=True)
            metric_calls: list[float] = []
            desired_code = (
                64 * 100_000 + 3 * 10_000 + int(0.0003 * 1_000_000) * 100 + 17
            )

            def fake_fit(
                model,
                _corpus,
                *,
                epochs,
                batch_size,
                learning_rate,
                weight_decay,
                random_seed,
                capture_checkpoints,
            ):
                self.assertEqual(epochs, ranker.TRAINING_EPOCHS)
                self.assertTrue(capture_checkpoints)
                checkpoints = []
                base = (
                    model.hidden_width * 100_000
                    + model.layer_count * 10_000
                    + int(learning_rate * 1_000_000) * 100
                )
                for epoch in range(1, epochs + 1):
                    checkpoint = {
                        name: np.zeros_like(value)
                        for name, value in model.parameters.items()
                    }
                    checkpoint["output_bias"][0] = base + epoch
                    checkpoints.append(checkpoint)
                return checkpoints

            def fake_metrics(scores, _training, _validation):
                code = float(scores[0])
                metric_calls.append(code)
                return {
                    "target_macro_top1_exact_rate": (
                        1.0 if code == desired_code else 0.0
                    ),
                    "target_macro_bce": 0.25,
                    "per_target_top1_exact_rate": {
                        target: 0.0 for target in ranker.TARGETS
                    },
                    "per_target_bce": {target: 0.25 for target in ranker.TARGETS},
                    "groups": {
                        "committed": 1,
                        "eligible": 1,
                        "excluded_empty": 0,
                    },
                    "exclusions": {"eligible_rows": 1},
                }

            with (
                mock.patch.object(ranker.DirectedMPNNRanker, "fit", new=fake_fit),
                mock.patch.object(
                    ranker,
                    "validation_selection_metrics",
                    new=fake_metrics,
                ),
            ):
                ensemble, report = ranker.select_frozen_grid(corpus, corpus)
            self.assertEqual(
                len(metric_calls),
                8 * ranker.TRAINING_EPOCHS,
            )
            self.assertEqual(report["selected"]["config_id"], "h64-l3-lr0.0003")
            self.assertEqual(report["selected"]["epoch"], 17)
            for member in ensemble.members:
                self.assertEqual(
                    float(member.parameters["output_bias"][0]),
                    float(desired_code),
                )
            self.assertEqual(
                report["selected"]["member_checkpoint_sha256"],
                [
                    ranker._parameters_digest(member.parameters)
                    for member in ensemble.members
                ],
            )

    def test_validation_rejects_selective_false_exclusion(self) -> None:
        training_rows = [
            row(100 + index, equal=index % 2 == 0, base_seed=1500 + index)
            for index in range(4)
        ]
        clean = row(
            7,
            equal=True,
            base_seed=1600,
            pool_id="pool-selective-exclusion",
        )
        clean["weakly_connected"] = True
        clean["training_candidate_collision"] = False
        clean["training_quotient_collision"] = False
        clean["eligible_for_validation_metric"] = False
        clean["exclusion_reasons"] = ["invented_hard_example"]
        with tempfile.TemporaryDirectory(prefix="partizan-eligibility-audit-") as temp:
            training_path = Path(temp) / "training.jsonl"
            validation_path = Path(temp) / "validation.jsonl"
            persist_jsonl(training_path, training_rows)
            persist_jsonl(validation_path, [clean])
            training = ranker.load_corpus(training_path, require_labels=True)
            validation = ranker.load_corpus(validation_path, require_labels=True)
            with self.assertRaisesRegex(
                ranker.RankerContractError,
                "eligibility marker disagrees",
            ):
                ranker._validation_eligible_indices(training, validation)

    def test_all_colliding_validation_pool_fails_closed(self) -> None:
        training_rows = [row(index, equal=index % 2 == 0) for index in range(6)]
        evaluation_rows = [deepcopy(value) for value in training_rows]
        for value in evaluation_rows:
            quotient_collision = value["quotient"] is not None
            value["ranker_pool"] = {"pool_id": "pool-1"}
            value["weakly_connected"] = True
            value["training_candidate_collision"] = True
            value["training_quotient_collision"] = quotient_collision
            value["eligible_for_validation_metric"] = False
            value["exclusion_reasons"] = [
                "training_candidate_collision",
                *(["training_quotient_collision"] if quotient_collision else []),
            ]
        with tempfile.TemporaryDirectory(prefix="partizan-neural-leak-") as temp:
            training_path = Path(temp) / "training.jsonl"
            evaluation_path = Path(temp) / "evaluation.jsonl"
            persist_jsonl(training_path, training_rows)
            persist_jsonl(evaluation_path, evaluation_rows)
            training = ranker.load_corpus(training_path, require_labels=True)
            evaluation = ranker.load_corpus(evaluation_path, require_labels=True)
            model = ranker.DirectedMPNNRanker(random_seed=7)
            with self.assertRaisesRegex(
                ranker.RankerContractError, "no eligible candidate pools"
            ):
                ranker.evaluate_model(
                    model,
                    training,
                    evaluation,
                    model_id="model-sha256:" + "0" * 64,
                    role="validation",
                    budgets=(2,),
                    random_replicates=4,
                )


if __name__ == "__main__":
    unittest.main()
