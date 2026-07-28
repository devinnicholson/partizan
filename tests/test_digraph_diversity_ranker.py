from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

PYTHON_ROOT = Path(__file__).parents[1] / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from partizan import digraph_diversity_ranker as diversity  # noqa: E402
from partizan import digraph_neural_ranker as equality  # noqa: E402


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
    literal_group: int | None,
    target: str = "0",
    base_seed: int = 1,
    pool_id: str | None = None,
) -> dict:
    candidate = graph(variant)
    value = {
        "candidate": candidate,
        "candidate_sha256": equality._candidate_digest(candidate),
        "target": target,
        "base_seed": base_seed,
        "proposal": {
            "mode": "local_mutation",
            "operator": "toggle_one_arc",
        },
        "exact_decision": (
            {
                "equal": variant % 2 == 0,
                "candidate_root_game_sha256": hashlib.sha256(
                    f"literal-group-{literal_group}".encode("ascii")
                ).hexdigest(),
            }
            if literal_group is not None
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
    path.write_bytes(b"".join(diversity.canonical_json_bytes(value) for value in rows))


def small_training_rows() -> list[dict]:
    return [
        row(0, literal_group=0, base_seed=100),
        row(1, literal_group=0, base_seed=101),
        row(2, literal_group=1, base_seed=102),
        row(3, literal_group=1, base_seed=103),
        row(4, literal_group=2, base_seed=104),
        row(5, literal_group=2, base_seed=105),
        row(6, literal_group=None, base_seed=106),
    ]


class DigraphDiversityRankerTests(unittest.TestCase):
    def test_feature_contract_excludes_target_and_semantic_fields(self) -> None:
        contract = diversity.feature_contract_record()
        self.assertEqual(
            contract["model_feature_paths"],
            [
                "/candidate/arcs",
                "/candidate/blue_vertices",
                "/candidate/order",
            ],
        )
        self.assertFalse(contract["target_token_is_model_feature"])
        self.assertIn("/exact_decision", contract["forbidden_at_inference"])
        self.assertIn("/literal_game_sha256", contract["forbidden_at_inference"])
        self.assertIn("/quotient", contract["forbidden_at_inference"])

    def test_corpus_replays_repeated_digest_groups_and_censoring(self) -> None:
        with tempfile.TemporaryDirectory(prefix="partizan-diversity-corpus-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, small_training_rows())
            corpus = diversity.load_contrastive_corpus(path)
        self.assertEqual(corpus.row_count, 7)
        self.assertEqual(corpus.labeled_row_count, 6)
        self.assertEqual(corpus.literal_digest_group_count, 3)
        self.assertEqual(corpus.eligible_group_count, 3)
        self.assertEqual(corpus.eligible_row_count, 6)
        self.assertIsNone(corpus.literal_game_sha256[-1])

    def test_singleton_digest_cannot_supply_a_false_positive_pair(self) -> None:
        rows = small_training_rows()
        rows.append(row(7, literal_group=7, base_seed=107))
        with tempfile.TemporaryDirectory(
            prefix="partizan-diversity-singleton-"
        ) as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, rows)
            corpus = diversity.load_contrastive_corpus(path)
        self.assertEqual(corpus.literal_digest_group_count, 4)
        self.assertEqual(corpus.eligible_group_count, 3)
        self.assertEqual(corpus.eligible_row_count, 6)

    def test_nt_xent_gradient_matches_finite_differences(self) -> None:
        raw = np.asarray(
            [
                [0.9, 0.2, -0.1],
                [0.7, 0.4, 0.1],
                [-0.3, 0.8, 0.2],
                [-0.5, 0.6, 0.4],
            ],
            dtype=np.float64,
        )
        embeddings, _ = diversity._l2_normalize(raw)
        positives = np.asarray([1, 0, 3, 2], dtype=np.int64)
        _, analytic = diversity.supervised_nt_xent(
            embeddings,
            positives,
            temperature=0.1,
        )

        epsilon = 1e-6
        for row_index, column_index in ((0, 0), (1, 2), (3, 1)):
            plus = embeddings.copy()
            minus = embeddings.copy()
            plus[row_index, column_index] += epsilon
            minus[row_index, column_index] -= epsilon
            plus_loss, _ = diversity.supervised_nt_xent(
                plus,
                positives,
                temperature=0.1,
            )
            minus_loss, _ = diversity.supervised_nt_xent(
                minus,
                positives,
                temperature=0.1,
            )
            numeric = (plus_loss - minus_loss) / (2.0 * epsilon)
            self.assertAlmostEqual(
                float(analytic[row_index, column_index]),
                numeric,
                places=6,
            )

    def test_encoder_backward_matches_finite_difference(self) -> None:
        candidates = [graph(index) for index in range(4)]
        arrays = [diversity._candidate_arrays(candidate) for candidate in candidates]
        nodes = np.stack([values[0] for values in arrays])
        adjacency = np.stack([values[1] for values in arrays])
        positives = np.asarray([1, 0, 3, 2], dtype=np.int64)
        model = diversity.DirectedMPNNDiversityEncoder(
            embedding_width=16,
            dropout=0.0,
            random_seed=17,
        )
        embeddings, cache = model._forward(nodes, adjacency)
        _, gradient_embeddings = diversity.supervised_nt_xent(
            embeddings,
            positives,
            temperature=0.2,
        )
        gradients = model._backward(cache, gradient_embeddings)

        epsilon = 1e-5

        def loss() -> float:
            current = model.embed(nodes, adjacency)
            value, _ = diversity.supervised_nt_xent(
                current,
                positives,
                temperature=0.2,
            )
            return value

        checked = 0
        for name in (
            "projection_output_weight",
            "projection_hidden_weight",
            "layer_2_self_weight",
            "input_weight",
        ):
            flat_gradient = gradients[name].reshape(-1)
            eligible = np.flatnonzero(np.abs(flat_gradient) > 1e-7)
            self.assertTrue(len(eligible), name)
            index = int(eligible[len(eligible) // 2])
            parameter = model.parameters[name].reshape(-1)
            original = float(parameter[index])
            parameter[index] = original + epsilon
            plus = loss()
            parameter[index] = original - epsilon
            minus = loss()
            parameter[index] = original
            numeric = (plus - minus) / (2.0 * epsilon)
            self.assertAlmostEqual(
                float(flat_gradient[index]),
                numeric,
                delta=max(2e-4, abs(numeric) * 2e-3),
                msg=name,
            )
            checked += 1
        self.assertEqual(checked, 4)

    def test_embedding_is_invariant_to_vertex_relabeling(self) -> None:
        original = graph(11)
        transformed = relabel(original, [4, 0, 6, 2, 5, 1, 3])
        original_values = diversity._candidate_arrays(original)
        transformed_values = diversity._candidate_arrays(transformed)
        model = diversity.DirectedMPNNDiversityEncoder(
            embedding_width=16,
            dropout=0.0,
            random_seed=23,
        )
        first = model.embed(
            original_values[0][None, :, :],
            original_values[1][None, :, :],
        )
        second = model.embed(
            transformed_values[0][None, :, :],
            transformed_values[1][None, :, :],
        )
        np.testing.assert_allclose(first, second, rtol=0.0, atol=1e-14)

    def test_embedding_has_unit_norm_and_no_target_input(self) -> None:
        candidates = [graph(index) for index in range(3)]
        arrays = [diversity._candidate_arrays(candidate) for candidate in candidates]
        model = diversity.DirectedMPNNDiversityEncoder(random_seed=29)
        embeddings = model.embed(
            np.stack([values[0] for values in arrays]),
            np.stack([values[1] for values in arrays]),
        )
        np.testing.assert_allclose(
            np.linalg.norm(embeddings, axis=1),
            np.ones(3),
            rtol=0.0,
            atol=1e-14,
        )

    def test_training_and_artifact_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="partizan-diversity-fit-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, small_training_rows())
            corpus = diversity.load_contrastive_corpus(path)
            records = []
            for _ in range(2):
                model = diversity.DirectedMPNNDiversityEncoder(
                    embedding_width=16,
                    random_seed=diversity.ENSEMBLE_SEEDS[0],
                )
                model.fit(
                    corpus,
                    temperature=0.1,
                    epochs=2,
                    random_seed=diversity.ENSEMBLE_SEEDS[0],
                )
                records.append(
                    model.to_record(
                        corpus=corpus,
                        optimization={
                            "random_seed": diversity.ENSEMBLE_SEEDS[0],
                            "epochs": 2,
                            "contrastive_temperature": 0.1,
                        },
                    )
                )
        self.assertEqual(
            diversity.canonical_json_bytes(records[0]),
            diversity.canonical_json_bytes(records[1]),
        )
        loaded = diversity.DirectedMPNNDiversityEncoder.from_record(records[0])
        np.testing.assert_array_equal(
            loaded.embed(corpus.node_features[:3], corpus.adjacency[:3]),
            model.embed(corpus.node_features[:3], corpus.adjacency[:3]),
        )

    def test_model_record_rejects_content_rehash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="partizan-diversity-record-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, small_training_rows())
            corpus = diversity.load_contrastive_corpus(path)
        model = diversity.DirectedMPNNDiversityEncoder(random_seed=31)
        record = model.to_record(
            corpus=corpus,
            optimization={"random_seed": 31},
        )
        changed = deepcopy(record)
        changed["parameters"]["projection_output_bias"][0] += 0.1
        with self.assertRaisesRegex(
            diversity.RankerContractError, "model_id does not match"
        ):
            diversity.DirectedMPNNDiversityEncoder.from_record(changed)

    def test_ensemble_rejects_selected_checkpoint_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="partizan-diversity-ensemble-") as temp:
            path = Path(temp) / "events.jsonl"
            persist_jsonl(path, small_training_rows())
            corpus = diversity.load_contrastive_corpus(path)
        ensemble = diversity.DiversityEnsemble(
            [
                diversity.DirectedMPNNDiversityEncoder(random_seed=seed)
                for seed in diversity.ENSEMBLE_SEEDS
            ]
        )
        selection = {
            "grid_report_id": "grid-report-sha256:" + "0" * 64,
            "embedding_width": 16,
            "contrastive_temperature": 0.1,
            "epoch": 1,
            "lambda": 0.5,
            "member_checkpoint_sha256": [
                diversity._parameters_digest(member.parameters)
                for member in ensemble.members
            ],
        }
        record = ensemble.to_record(corpus=corpus, selection=selection)
        changed = deepcopy(record)
        changed["selection"]["member_checkpoint_sha256"][0] = "f" * 64
        payload = dict(changed)
        payload.pop("model_id")
        changed["model_id"] = (
            "ensemble-sha256:"
            + hashlib.sha256(diversity.canonical_json_bytes(payload)).hexdigest()
        )
        with self.assertRaisesRegex(
            diversity.RankerContractError, "selected checkpoint"
        ):
            diversity.DiversityEnsemble.from_record(changed)

    def test_midrank_fraction_preserves_ties(self) -> None:
        observed = diversity.midrank_fraction([4.0, 1.0, 4.0, 2.0])
        np.testing.assert_array_equal(
            observed,
            np.asarray([5 / 6, 0.0, 5 / 6, 1 / 3]),
        )
        np.testing.assert_array_equal(
            diversity.midrank_fraction([7.0]),
            np.asarray([0.5]),
        )

    def test_rank_fusion_uses_only_scores_embeddings_and_hash_tie_break(self) -> None:
        pool = [
            row(
                index,
                literal_group=None,
                target="*",
                base_seed=991,
                pool_id="pool-rank-fusion",
            )
            for index in range(4)
        ]
        for value in pool:
            value.pop("exact_decision")
        members = [
            diversity.DirectedMPNNDiversityEncoder(random_seed=seed)
            for seed in diversity.ENSEMBLE_SEEDS
        ]
        ensemble = diversity.DiversityEnsemble(members)
        novelty = np.asarray([0.1, 0.9, 0.2, 0.8])
        with mock.patch.object(
            diversity,
            "candidate_novelty_scores",
            return_value=novelty,
        ):
            records = diversity.rank_fusion_pool(
                equality_scores=[0.9, 0.1, 0.8, 0.2],
                novelty_ensemble=ensemble,
                proposal_rows=pool,
                memory_candidates=[graph(30)],
                lambda_weight=1.0,
                equality_model_id="ensemble-sha256:" + "e" * 64,
                novelty_model_id="ensemble-sha256:" + "d" * 64,
            )
        self.assertEqual(
            [record["rank_zero_based"] for record in records], [0, 1, 2, 3]
        )
        self.assertEqual(
            records[0]["candidate_sha256"],
            min(value["candidate_sha256"] for value in pool),
        )
        forbidden = {
            "exact_decision",
            "literal_game_sha256",
            "quotient",
            "retention",
        }
        for record in records:
            self.assertFalse(forbidden & set(record))

    def test_rank_fusion_rejects_outcome_bearing_pool(self) -> None:
        pool = [
            row(
                index,
                literal_group=None,
                base_seed=992,
                pool_id="pool-outcome",
            )
            for index in range(2)
        ]
        pool[0]["retention"] = {"inserted": False}
        ensemble = diversity.DiversityEnsemble(
            [
                diversity.DirectedMPNNDiversityEncoder(random_seed=seed)
                for seed in diversity.ENSEMBLE_SEEDS
            ]
        )
        with self.assertRaisesRegex(diversity.RankerContractError, "outcome fields"):
            diversity.rank_fusion_pool(
                equality_scores=[0.4, 0.6],
                novelty_ensemble=ensemble,
                proposal_rows=pool,
                memory_candidates=[graph(20)],
                lambda_weight=0.5,
                equality_model_id="ensemble-sha256:" + "e" * 64,
                novelty_model_id="ensemble-sha256:" + "d" * 64,
            )

    def test_novelty_score_is_memberwise_before_averaging(self) -> None:
        ensemble = diversity.DiversityEnsemble(
            [
                diversity.DirectedMPNNDiversityEncoder(random_seed=seed)
                for seed in diversity.ENSEMBLE_SEEDS
            ]
        )
        candidates = [diversity._candidate_arrays(graph(index)) for index in (1, 2)]
        memory = [diversity._candidate_arrays(graph(index)) for index in (3, 4)]
        first = diversity.candidate_novelty_scores(
            ensemble,
            np.stack([value[0] for value in candidates]),
            np.stack([value[1] for value in candidates]),
            np.stack([value[0] for value in memory]),
            np.stack([value[1] for value in memory]),
        )
        second = diversity.candidate_novelty_scores(
            ensemble,
            np.stack([value[0] for value in candidates]),
            np.stack([value[1] for value in candidates]),
            np.stack([value[0] for value in memory]),
            np.stack([value[1] for value in memory]),
        )
        np.testing.assert_array_equal(first, second)
        self.assertTrue(np.isfinite(first).all())
        self.assertTrue((first >= 0.0).all())
        self.assertTrue((first <= 2.0).all())

    def test_resource_preflight_factory_binds_both_model_artifacts(self) -> None:
        training_rows = small_training_rows()
        pool = [
            row(
                20 + index,
                literal_group=None,
                target="{0|1}",
                base_seed=2000,
                pool_id="pool-factory",
            )
            for index in range(4)
        ]
        for value in pool:
            value.pop("exact_decision")
        with tempfile.TemporaryDirectory(prefix="partizan-diversity-factory-") as temp:
            training_path = Path(temp) / "training.jsonl"
            equality_path = Path(temp) / "equality.json"
            novelty_path = Path(temp) / "novelty.json"
            persist_jsonl(training_path, training_rows)

            equality_corpus = equality.load_corpus(
                training_path,
                require_labels=True,
            )
            equality_model = equality.DirectedMPNNRanker(random_seed=31)
            equality_record = equality_model.to_record(
                corpus=equality_corpus,
                optimization={"random_seed": 31},
            )
            equality._write_json(equality_path, equality_record)

            diversity_corpus = diversity.load_contrastive_corpus(training_path)
            ensemble = diversity.DiversityEnsemble(
                [
                    diversity.DirectedMPNNDiversityEncoder(random_seed=seed)
                    for seed in diversity.ENSEMBLE_SEEDS
                ]
            )
            novelty_record = ensemble.to_record(
                corpus=diversity_corpus,
                selection={
                    "grid_report_id": "grid-report-sha256:" + "0" * 64,
                    "embedding_width": 16,
                    "contrastive_temperature": 0.1,
                    "epoch": 1,
                    "lambda": 0.5,
                    "member_checkpoint_sha256": [
                        diversity._parameters_digest(member.parameters)
                        for member in ensemble.members
                    ],
                },
            )
            diversity._write_json(novelty_path, novelty_record)

            callback = diversity.build_resource_preflight_diversity_ranker(
                equality_model_artifact_path=equality_path,
                equality_model_id=equality_record["model_id"],
                novelty_model_artifact_path=novelty_path,
                novelty_model_id=novelty_record["model_id"],
                lambda_weight=0.5,
            )
            first = callback(pool, [graph(40)])
            second = callback(pool, [graph(40)])
            self.assertEqual(first, second)
            self.assertEqual(len(first), 4)
            self.assertEqual(
                [record["rank_zero_based"] for record in first],
                [0, 1, 2, 3],
            )
            with self.assertRaisesRegex(
                diversity.RankerContractError,
                "novelty_model_id",
            ):
                diversity.build_resource_preflight_diversity_ranker(
                    equality_model_artifact_path=equality_path,
                    equality_model_id=equality_record["model_id"],
                    novelty_model_artifact_path=novelty_path,
                    novelty_model_id="ensemble-sha256:" + "f" * 64,
                    lambda_weight=0.5,
                )

    def test_package_cli_help_requires_no_native_extension(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(PYTHON_ROOT)
        environment["PYTHONPYCACHEPREFIX"] = "/tmp/partizan-diversity-test-pyc"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "partizan.digraph_diversity_ranker",
                "--help",
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("{train,rank}", completed.stdout)


if __name__ == "__main__":
    unittest.main()
