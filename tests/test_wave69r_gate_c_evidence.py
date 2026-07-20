from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/discovery"


def load_evidence_module():
    spec = importlib.util.spec_from_file_location(
        "wave69r_gate_c_evidence_test",
        ROOT / "python/partizan/wave69r_gate_c_evidence.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate_c = load_evidence_module()
discovery = gate_c.discovery


def load_orchestrator():
    spec = importlib.util.spec_from_file_location(
        "wave69r_gate_c_evidence_mock_orchestrator", ROOT / "engine/orchestrator.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def gate_row(target_id: str, **overrides):
    gates = {
        "coverage_at_least_95_percent": True,
        "certified_matches_at_least_8": True,
        "symmetry_unique_matches_at_least_4": True,
        "internal_errors_zero": True,
    }
    gates.update(overrides)
    return {"target_id": target_id, "gates": gates}


class Wave69RGateCEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = discovery.load_json(FIXTURES / "target.valid.json")
        self.proposals = discovery.load_jsonl(FIXTURES / "proposals.valid.jsonl")
        self.results = discovery.load_jsonl(
            FIXTURES / "verifier-results.valid.jsonl"
        )
        self.pool = discovery.load_json(
            FIXTURES / "candidate-pool.valid.manifest.json"
        )

    def test_complete_ledger_reuses_result_contract_and_generator_order(self) -> None:
        gate_c.validate_complete_ledger(
            target=self.target,
            pool=self.pool,
            proposals=self.proposals,
            results=self.results,
            expected_rows=4,
        )
        with self.assertRaisesRegex(gate_c.GateCEvidenceError, "generator order"):
            gate_c.validate_complete_ledger(
                target=self.target,
                pool=self.pool,
                proposals=self.proposals,
                results=list(reversed(self.results)),
                expected_rows=4,
            )
        with self.assertRaisesRegex(gate_c.GateCEvidenceError, "one row"):
            gate_c.validate_complete_ledger(
                target=self.target,
                pool=self.pool,
                proposals=self.proposals,
                results=self.results[:-1],
                expected_rows=4,
            )

    def test_complete_ledger_requires_all_four_frozen_pins(self) -> None:
        corrupted_pool = deepcopy(self.pool)
        corrupted_pool["source_repositories"]["astralbase"] = "f" * 40
        with self.assertRaisesRegex(gate_c.GateCEvidenceError, "four pins"):
            gate_c.validate_complete_ledger(
                target=self.target,
                pool=corrupted_pool,
                proposals=self.proposals,
                results=self.results,
                expected_rows=4,
            )

    def test_counts_retain_all_four_verifier_outcomes(self) -> None:
        counts = gate_c.target_counts(self.proposals, self.results)
        self.assertEqual(
            counts,
            {
                "certified_matches": 1,
                "certified_nonmatches": 1,
                "rejections": 1,
                "internal_errors": 1,
                "certified_coverage_numerator": 2,
                "certified_coverage_denominator": 4,
                "symmetry_unique_matches": 1,
            },
        )

    def test_gate_thresholds_use_exact_integer_arithmetic(self) -> None:
        counts = {
            "certified_matches": 8,
            "certified_nonmatches": 965,
            "rejections": 51,
            "internal_errors": 0,
            "certified_coverage_numerator": 973,
            "certified_coverage_denominator": 1024,
            "symmetry_unique_matches": 4,
        }
        self.assertTrue(all(gate_c.target_gates(counts).values()))
        counts["certified_nonmatches"] -= 1
        counts["rejections"] += 1
        counts["certified_coverage_numerator"] -= 1
        self.assertFalse(
            gate_c.target_gates(counts)["coverage_at_least_95_percent"]
        )

    def test_decision_precedence_is_integrity_construction_semantic_calibration(self) -> None:
        target_ids = ["target-sha256:" + str(index) * 64 for index in range(1, 7)]
        rows = [gate_row(target_id) for target_id in target_ids]
        self.assertEqual(gate_c.categorized_decision(rows)["category"], "Calibration")
        rows[4] = gate_row(
            target_ids[4], symmetry_unique_matches_at_least_4=False
        )
        self.assertEqual(gate_c.categorized_decision(rows)["category"], "Semantic")
        rows[3] = gate_row(target_ids[3], coverage_at_least_95_percent=False)
        self.assertEqual(
            gate_c.categorized_decision(rows)["category"], "Construction"
        )
        rows[2] = gate_row(target_ids[2], internal_errors_zero=False)
        decision = gate_c.categorized_decision(rows)
        self.assertEqual(decision["category"], "Construction")
        self.assertEqual(decision["status"], "NO-GO")
        self.assertFalse(decision["stage_b_automatically_opened"])

    def test_check_only_has_no_verifier_reachability(self) -> None:
        source = inspect.getsource(gate_c.check_only)
        self.assertNotIn("verifier_runner", source)
        self.assertNotIn("verify_discovery_pool", source)
        self.assertNotIn("cargo", source)
        runner = inspect.getsource(gate_c._generic_verifier_runner)
        self.assertIn("orchestrator.verify_discovery_pool", runner)
        self.assertNotIn("cargo", runner)
        self.assertIn("sys.dont_write_bytecode = True", runner)

    def test_temporal_boundary_requires_direct_linear_commits_and_pc_bytes(self) -> None:
        direct = inspect.getsource(gate_c._require_direct_parent)
        self.assertIn('"--format=%P"', direct)
        self.assertIn("parents != [parent]", direct)
        boundary = inspect.getsource(gate_c._committed_suite_boundary)
        self.assertEqual(boundary.count("_require_direct_parent("), 3)
        self.assertIn('"show", f"{p_c}:{suite_relative}"', boundary)
        self.assertIn("for relative in ANALYSIS_COMPONENT_PATHS", boundary)
        self.assertIn('"show", f"{i_commit}:{relative}"', boundary)

    def test_execution_has_one_frozen_runner_call_and_no_retry_loop(self) -> None:
        source = inspect.getsource(gate_c.execute_gate_c)
        self.assertEqual(source.count("verifier_runner("), 1)
        self.assertNotIn("while ", source)
        self.assertNotIn("for attempt", source)
        self.assertNotIn("except ", source)
        self.assertLess(
            source.index("for entry in manifest[\"targets\"]"),
            source.index("# Phase 2 starts only after all six raw ledgers"),
        )

    def test_baseline_projection_reuses_existing_metric_primitives(self) -> None:
        source = inspect.getsource(gate_c._analyze_target)
        self.assertIn("baselines._metrics_for_order", source)
        self.assertIn("baselines._random_summary", source)
        self.assertIn("baselines.heuristic_order", source)
        self.assertIn("suite_contract.validate_policy_orders", source)

    def test_1024_row_mock_ledger_recomputes_existing_baseline_metrics(self) -> None:
        orchestrator = load_orchestrator()
        contract = orchestrator.discovery_contract
        target = contract.load_json(FIXTURES / "target.valid.json")
        target["search_limits"]["max_pool_size"] = 1024
        target["target_id"] = contract.target_id_for(target)
        boards = orchestrator.generate_discovery_board_states_v2(
            pool_size=1024,
            random_seed=20260717,
            generator_code_commit="7" * 40,
        )
        proposals = contract.project_board_stream_to_proposals(target, boards)
        sources = {
            "partizan": "7" * 40,
            "astralbase": "8" * 40,
            "bitmesh": "9" * 40,
            "thermograph": "a" * 40,
        }
        pool = {
            "pool_id": "pool-sha256:" + "b" * 64,
            "source_repositories": sources,
        }
        policy = gate_c.suite_contract.build_policy_orders(
            target,
            pool,
            proposals,
            seed_domain=gate_c.suite_contract.SYNTHETIC_SEED_DOMAIN,
            replicates=1000,
        )
        results = []
        for index, proposal in enumerate(proposals):
            matches = index < 8
            observed = (
                target["target"]["identity_sha256"]
                if matches
                else hashlib.sha256(f"synthetic-other-{index}".encode()).hexdigest()
            )
            actual = {
                "identity_kind": target["target"]["identity_contract"],
                "semantics": "structural_tree_identity_only",
                "value_class": target["target"]["value_class"],
                "digest_v1_sha256": observed,
                "legacy_digest": f"synthetic-{index}",
                "recursive_nodes": 1,
                "decomposition_digest": hashlib.sha256(
                    f"synthetic-decomposition-{index}".encode()
                ).hexdigest(),
                "composition_digest": hashlib.sha256(
                    f"synthetic-composition-{index}".encode()
                ).hexdigest(),
                "component_legacy_digests": {"root-0": f"synthetic-{index}"},
            }
            results.append(
                orchestrator._translate_astralbase_result(
                    target=target,
                    proposal=proposal,
                    response={
                        "request_id": proposal["proposal_id"],
                        "status": "verified_match" if matches else "verified_nonmatch",
                        "actual": actual,
                    },
                    source_repositories=sources,
                )
            )
        report = gate_c._analyze_target(
            target=target,
            pool=pool,
            proposals=proposals,
            results=results,
            policy_orders=policy,
            proposals_path=Path("/synthetic/not-read.jsonl"),
            production_policy=False,
        )
        self.assertEqual(len(report["random"]["replicates"]), 1000)
        self.assertEqual(report["join_contract"]["result_count"], 1024)
        self.assertEqual(
            report["heuristic"]["metrics"]["full_pool"]["raw_successes"], 8
        )
        self.assertEqual(
            report["report_id"], gate_c.baselines.baseline_report_id_for(report)
        )

    def test_strict_evidence_schema_forbids_scope_expansion(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "docs/schemas/partizan-wave69r-gate-c-evidence-v0.1.schema.json"
            ).read_text()
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["scope_boundary"]["properties"],
            {
                "stage_b_material_present": {"const": False},
                "wave70_material_present": {"const": False},
                "paper_evidence_claim": {"const": False},
                "automatic_follow_on_execution": {"const": False},
            },
        )
        self.assertFalse(schema["$defs"]["target_evidence"]["additionalProperties"])
        analysis = schema["properties"]["analysis_implementation"]
        self.assertFalse(analysis["additionalProperties"])
        self.assertEqual(analysis["properties"]["components"]["minItems"], 3)
        self.assertEqual(analysis["properties"]["components"]["maxItems"], 3)
        self.assertEqual(
            schema["properties"]["execution"]["properties"][
                "proposal_verifier_call_count"
            ],
            {"const": 6144},
        )


if __name__ == "__main__":
    unittest.main()
