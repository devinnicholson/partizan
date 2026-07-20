from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


discovery = load_module(
    "partizan_discovery_for_baseline_tests",
    ROOT / "python" / "partizan" / "discovery.py",
)
baselines = load_module(
    "partizan_discovery_baselines_tests",
    ROOT / "python" / "partizan" / "discovery_baselines.py",
)
orchestrator = load_module(
    "partizan_orchestrator_for_baseline_tests",
    ROOT / "engine" / "orchestrator.py",
)
baseline_cli = load_module(
    "partizan_discovery_baseline_cli_tests",
    ROOT / "scripts" / "wave69_discovery_baselines.py",
)

FIXTURES = ROOT / "tests" / "fixtures" / "discovery"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


PARTIZAN_COMMIT = "89c325d52a67bde4d6ac997f4527b7c56a119cf7"


def synthetic_bundle(
    repository_root: Path,
    *,
    bundle_name: str = "bundle-0",
    target_variant: int = 0,
    row_count: int = 1_024,
):
    directory = repository_root / bundle_name
    directory.mkdir(parents=True)
    target = load_json(FIXTURES / "target.valid.json")
    target["search_limits"]["max_pool_size"] = row_count
    target["search_limits"]["max_verifier_calls"] = row_count
    if target_variant:
        identity = discovery.sha256_hex(
            f"suite-target-{target_variant}".encode("ascii")
        )
        target["target"]["identity_sha256"] = identity
        target["ranker_view"]["identity_sha256"] = identity
    target["target_id"] = discovery.target_id_for(target)

    proposals = orchestrator.generate_discovery_candidate_pool_v1(
        target=target,
        pool_size=row_count,
        random_seed=69001,
        generator_code_commit=PARTIZAN_COMMIT,
    )
    response_bases = [
        row["verifier_io"]["response"]
        for row in load_jsonl(FIXTURES / "verifier-results.valid.jsonl")
    ]
    proposal_bytes = discovery.canonical_jsonl_bytes(proposals)
    proposal_sha = discovery.sha256_hex(proposal_bytes)
    target_path = directory / "target.json"
    proposals_path = directory / "proposals.jsonl"
    receipt_path = directory / "generation-receipt.json"
    manifest_path = directory / "manifest.json"
    target_path.write_bytes(discovery.canonical_json_bytes(target))
    proposals_path.write_bytes(proposal_bytes)
    receipt = orchestrator.build_discovery_generation_receipt_v1(
        target=target,
        proposals=proposals,
        raw_artifact_sha256=[proposal_sha, proposal_sha],
    )
    receipt_path.write_bytes(discovery.canonical_json_bytes(receipt))
    fixture_pool = load_json(
        FIXTURES / "candidate-pool.valid.manifest.json"
    )
    source_repositories = dict(fixture_pool["source_repositories"])
    source_repositories["partizan"] = PARTIZAN_COMMIT
    pool = orchestrator.freeze_discovery_pool(
        target_path=target_path,
        proposals_input_path=proposals_path,
        proposals_output_path=proposals_path,
        manifest_output_path=manifest_path,
        source_repositories=source_repositories,
        candidate_artifact_path=(
            f"artifacts/generated/wave69-baseline-test-{target_variant}.jsonl"
        ),
        generation_receipt_path=receipt_path,
        repository_root=repository_root,
    )

    results = []
    for index, proposal in enumerate(proposals):
        response = deepcopy(response_bases[index % len(response_bases)])
        response["request_id"] = proposal["proposal_id"]
        if response["status"] == "verified_match":
            response["actual"]["digest_v1_sha256"] = target["target"][
                "identity_sha256"
            ]
            response["actual"]["value_class"] = target["target"]["value_class"]
        elif response["status"] == "verified_nonmatch" and (
            response["actual"]["digest_v1_sha256"]
            == target["target"]["identity_sha256"]
            and response["actual"]["value_class"] == target["target"]["value_class"]
        ):
            response["actual"]["digest_v1_sha256"] = "f" * 64
        result = orchestrator._translate_astralbase_result(
            target=target,
            proposal=proposal,
            response=response,
            source_repositories=pool["source_repositories"],
        )
        results.append(result)
    return target, pool, proposals, results, proposals_path, receipt_path


def artifact_sha(path: Path) -> str:
    return discovery.sha256_hex(path.read_bytes())


def persist_analysis_bundle(
    repository_root: Path,
    *,
    target,
    pool,
    proposals,
    results,
    proposals_path: Path,
    orders,
    report,
):
    directory = proposals_path.parent
    target_path = directory / "target.json"
    pool_path = directory / "manifest.json"
    results_path = directory / "results.jsonl"
    orders_path = directory / "policy-orders.json"
    report_path = directory / "baseline-report.json"
    results_path.write_bytes(discovery.canonical_jsonl_bytes(results))
    orders_path.write_bytes(discovery.canonical_json_bytes(orders))
    report_path.write_bytes(discovery.canonical_json_bytes(report))

    def relative(path: Path) -> str:
        return path.relative_to(repository_root).as_posix()

    return {
        "target_id": target["target_id"],
        "pool_id": pool["pool_id"],
        "target_ref": {
            "path": relative(target_path),
            "schema_version": discovery.TARGET_SCHEMA_VERSION,
            "target_id": target["target_id"],
            "sha256": artifact_sha(target_path),
        },
        "pool_manifest_ref": {
            "path": relative(pool_path),
            "schema_version": discovery.POOL_SCHEMA_VERSION_V2,
            "pool_id": pool["pool_id"],
            "sha256": artifact_sha(pool_path),
        },
        "proposals_ref": {
            "path": relative(proposals_path),
            "schema_version": discovery.PROPOSAL_SCHEMA_VERSION,
            "sha256": artifact_sha(proposals_path),
            "row_count": len(proposals),
        },
        "policy_orders_ref": {
            "path": relative(orders_path),
            "schema_version": baselines.POLICY_ORDERS_SCHEMA_VERSION,
            "policy_orders_id": orders["policy_orders_id"],
            "sha256": artifact_sha(orders_path),
        },
        "verifier_results_ref": {
            "path": relative(results_path),
            "schema_version": discovery.RESULT_SCHEMA_VERSION,
            "sha256": artifact_sha(results_path),
            "row_count": len(results),
        },
        "baseline_report_ref": {
            "path": relative(report_path),
            "schema_version": baselines.BASELINE_REPORT_SCHEMA_VERSION,
            "report_id": report["report_id"],
            "sha256": artifact_sha(report_path),
        },
    }


def persist_pre_verification_suite(repository_root: Path, entries, contexts):
    targets = []
    for index, (entry, context) in enumerate(zip(entries, contexts)):
        targets.append(
            {
                "target_id": entry["target_id"],
                "family": f"test_family_{index // 2}",
                "bin_index": 0 if index % 2 == 0 else 3,
                "seed": context["proposals"][0]["generator"]["random_seed"],
                "target_ref": deepcopy(entry["target_ref"]),
                "proposals_ref": deepcopy(entry["proposals_ref"]),
                "generation_receipt_ref": deepcopy(
                    context["pool"]["determinism"]["generation_receipt_ref"]
                ),
                "pool_manifest_ref": deepcopy(entry["pool_manifest_ref"]),
                "policy_orders_ref": deepcopy(entry["policy_orders_ref"]),
            }
        )
    suite = {
        "schema_version": baselines.PRE_VERIFICATION_SUITE_SCHEMA_VERSION,
        "suite_id": "suite-sha256:" + "0" * 64,
        "stage": "stage_a",
        "phase": "pre_verification_freeze",
        "registry_ref": {
            "path": "docs/test-registry.json",
            "registry_id": "registry-sha256:" + "1" * 64,
            "sha256": "2" * 64,
        },
        "preregistration_ref": {
            "path": "docs/test-preregistration.md",
            "preregistration_id": "prereg-sha256:" + "3" * 64,
            "sha256": "4" * 64,
        },
        "implementation": {
            "implementation_id": "implementation-sha256:" + "5" * 64,
            "partizan_commit": PARTIZAN_COMMIT,
            "components": [
                {"path": f"scripts/test-component-{index}.py", "sha256": f"{index + 6:064x}"}
                for index in range(3)
            ],
        },
        "source_repositories": deepcopy(contexts[0]["pool"]["source_repositories"]),
        "seed_contract": {
            "algorithm": "sha256_first_u64_big_endian_v1",
            "domain_hex": "70617274697a616e2f7736392f706f6f6c2f763100",
            "stage": "stage_a",
            "target_id_encoding": "utf8",
        },
        "target_count": 6,
        "proposal_count_per_target": 1024,
        "targets": targets,
        "freeze_boundary": {
            "verifier_calls": 0,
            "results_artifacts_present": False,
            "policy_orders_frozen_before_verification": True,
            "wave70_material_present": False,
        },
    }
    suite["suite_id"] = "suite-sha256:" + discovery.sha256_hex(
        discovery.canonical_json_bytes(
            {key: value for key, value in suite.items() if key != "suite_id"}
        )
    )
    path = repository_root / "pre-verification-suite.json"
    path.write_bytes(discovery.canonical_json_bytes(suite))
    return {
        "path": path.relative_to(repository_root).as_posix(),
        "schema_version": baselines.PRE_VERIFICATION_SUITE_SCHEMA_VERSION,
        "suite_id": suite["suite_id"],
        "sha256": artifact_sha(path),
    }


class Wave69BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_directory = tempfile.TemporaryDirectory(
            prefix="partizan-wave69-baselines-v02-"
        )
        cls.repository_root = Path(cls.temp_directory.name)
        (
            cls.target,
            cls.pool,
            cls.proposals,
            cls.results,
            cls.proposals_path,
            cls.receipt_path,
        ) = synthetic_bundle(cls.repository_root)
        cls.orders = baselines.build_policy_orders(
            cls.target,
            cls.pool,
            cls.proposals,
            proposals_path=cls.proposals_path,
            repository_root=cls.repository_root,
        )
        cls.report = baselines.analyze_baselines(
            cls.target,
            cls.pool,
            cls.proposals,
            cls.results,
            cls.orders,
            proposals_path=cls.proposals_path,
            repository_root=cls.repository_root,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_directory.cleanup()

    def path_arguments(self) -> dict[str, Path]:
        return {
            "proposals_path": self.proposals_path,
            "repository_root": self.repository_root,
        }

    def test_random_seed_and_permutation_have_fixed_vectors(self) -> None:
        self.assertEqual(
            baselines.random_seed_for("pool-sha256:" + "0" * 64, 0),
            5920932200444365889,
        )
        self.assertEqual(
            baselines.stable_random_permutation(
                ["a", "b", "c", "d", "e"], 0x0123456789ABCDEF
            ),
            ["b", "e", "c", "d", "a"],
        )

    def test_policy_orders_freeze_exactly_1000_random_and_one_heuristic(self) -> None:
        self.assertEqual(
            self.orders["schema_version"], baselines.POLICY_ORDERS_SCHEMA_VERSION
        )
        self.assertEqual(len(self.orders["random_policy"]["orders"]), 1_000)
        self.assertEqual(
            self.orders["order_serialization"], discovery.SERIALIZATION
        )
        self.assertFalse(
            self.orders["generator_ordinal_audit"]["competitive_baseline"]
        )
        self.assertEqual(
            [row["replicate"] for row in self.orders["random_policy"]["orders"]],
            list(range(1_000)),
        )
        self.assertEqual(
            baselines.validate_policy_orders(
                self.orders,
                self.target,
                self.pool,
                self.proposals,
                **self.path_arguments(),
            ),
            [],
        )
        self.assertEqual(
            self.orders["policy_orders_id"],
            baselines.policy_orders_id_for(self.orders),
        )

    def test_script_wrapper_exports_v02_policy_validator(self) -> None:
        self.assertTrue(callable(baseline_cli.validate_policy_orders))
        self.assertEqual(
            baseline_cli.validate_policy_orders(
                self.orders,
                self.target,
                self.pool,
                self.proposals,
                **self.path_arguments(),
            ),
            [],
        )

    def test_heuristic_formula_and_candidate_key_tie_break(self) -> None:
        first = deepcopy(self.proposals[0])
        second = deepcopy(self.proposals[1])
        second["proposal_features"] = deepcopy(first["proposal_features"])
        if first["candidate_key"] < second["candidate_key"]:
            expected = [first["proposal_id"], second["proposal_id"]]
        else:
            expected = [second["proposal_id"], first["proposal_id"]]
        self.assertEqual(baselines.heuristic_order([first, second]), expected)
        self.assertEqual(
            self.orders["heuristic_policy"]["features"],
            list(baselines.HEURISTIC_FEATURES),
        )
        self.assertNotIn("pawn_count", self.orders["heuristic_policy"]["features"])

    def test_orders_reject_tampering_missing_duplicate_and_extra_order_ids(self) -> None:
        cases = []
        tampered_hash = deepcopy(self.orders)
        tampered_hash["random_policy"]["orders"][0][
            "ordered_proposal_ids_sha256"
        ] = "0" * 64
        tampered_hash["random_policy"]["orders"][0]["order_id"] = (
            baselines.policy_order_id_for(tampered_hash["random_policy"]["orders"][0])
        )
        tampered_hash["policy_orders_id"] = baselines.policy_orders_id_for(tampered_hash)
        cases.append(tampered_hash)

        missing = deepcopy(self.orders)
        missing["random_policy"]["orders"].pop()
        missing["policy_orders_id"] = baselines.policy_orders_id_for(missing)
        cases.append(missing)

        duplicate = deepcopy(self.orders)
        duplicate["random_policy"]["orders"][1] = deepcopy(
            duplicate["random_policy"]["orders"][0]
        )
        duplicate["policy_orders_id"] = baselines.policy_orders_id_for(duplicate)
        cases.append(duplicate)

        extra = deepcopy(self.orders)
        extra["random_policy"]["orders"].append(
            deepcopy(extra["random_policy"]["orders"][-1])
        )
        extra["policy_orders_id"] = baselines.policy_orders_id_for(extra)
        cases.append(extra)

        for artifact in cases:
            with self.subTest(case=len(artifact["random_policy"]["orders"])):
                self.assertTrue(
                    baselines.validate_policy_orders(
                        artifact,
                        self.target,
                        self.pool,
                        self.proposals,
                        **self.path_arguments(),
                    )
                )

    def test_analysis_reports_all_metrics_and_every_outcome(self) -> None:
        heuristic = self.report["heuristic"]["metrics"]
        self.assertEqual(
            [row["calls"] for row in heuristic["budget_metrics"]], [64, 256, 1024]
        )
        self.assertEqual(heuristic["naudc_method"], baselines.NAUDC_METHOD)
        self.assertEqual(
            set(heuristic["full_pool"]["outcome_rates"]), set(baselines.RATE_KEYS)
        )
        self.assertEqual(sum(heuristic["full_pool"]["outcome_counts"].values()), 1024)
        self.assertEqual(
            heuristic["full_pool"]["raw_successes"],
            heuristic["full_pool"]["symmetry_unique_successes"],
        )
        self.assertEqual(self.report["random"]["summary"]["replicate_count"], 1000)
        self.assertIn("generator_ordinal_audit", self.report)
        self.assertTrue(
            self.report["join_contract"]["every_proposal_consumes_one_call"]
        )

    def test_analysis_rejects_missing_extra_duplicate_and_reordered_results(self) -> None:
        bad_ledgers = [
            self.results[:-1],
            self.results + [deepcopy(self.results[-1])],
            [self.results[0], self.results[0], *self.results[2:]],
            [self.results[1], self.results[0], *self.results[2:]],
        ]
        for ledger in bad_ledgers:
            with self.subTest(rows=len(ledger)):
                with self.assertRaises(baselines.BaselineContractError):
                    baselines.analyze_baselines(
                        self.target,
                        self.pool,
                        self.proposals,
                        ledger,
                        self.orders,
                        **self.path_arguments(),
                    )

    def test_analysis_rejects_tampered_result_hash(self) -> None:
        ledger = deepcopy(self.results)
        ledger[0]["verifier_io"]["response"]["actual"]["legacy_digest"] = "tampered"
        with self.assertRaises(baselines.BaselineContractError):
            baselines.analyze_baselines(
                self.target,
                self.pool,
                self.proposals,
                ledger,
                self.orders,
                **self.path_arguments(),
            )

    def test_analysis_rejects_duplicate_proposal_ids(self) -> None:
        proposals = deepcopy(self.proposals)
        proposals[1] = deepcopy(proposals[0])
        with self.assertRaises(baselines.BaselineContractError):
            baselines.analyze_baselines(
                self.target,
                self.pool,
                proposals,
                self.results,
                self.orders,
                **self.path_arguments(),
            )

    def test_policy_freeze_is_result_blind_and_analysis_has_no_verifier_runner(self) -> None:
        source = (ROOT / "python" / "partizan" / "discovery_baselines.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("cargo run", source)
        before = baselines.build_policy_orders(
            self.target,
            self.pool,
            self.proposals,
            **self.path_arguments(),
        )
        changed_results = deepcopy(self.results)
        changed_results.reverse()
        after = baselines.build_policy_orders(
            self.target,
            self.pool,
            self.proposals,
            **self.path_arguments(),
        )
        self.assertEqual(before, after)
        self.assertNotEqual(
            discovery.sha256_hex(discovery.canonical_jsonl_bytes(self.results)),
            discovery.sha256_hex(discovery.canonical_jsonl_bytes(changed_results)),
        )

    def test_report_rejects_tampered_metric_and_input_hash(self) -> None:
        tampered = deepcopy(self.report)
        tampered["heuristic"]["metrics"]["budget_metrics"][0][
            "symmetry_unique_successes"
        ] += 1
        tampered["report_id"] = baselines.baseline_report_id_for(tampered)
        self.assertTrue(
            baselines.validate_baseline_report(
                tampered,
                self.target,
                self.pool,
                self.proposals,
                self.results,
                self.orders,
                **self.path_arguments(),
            )
        )

    def test_v02_missing_receipt_blocks_freeze_analysis_report_and_cli(self) -> None:
        receipt_bytes = self.receipt_path.read_bytes()
        self.receipt_path.unlink()
        try:
            with self.assertRaises(baselines.BaselineContractError):
                baselines.build_policy_orders(
                    self.target,
                    self.pool,
                    self.proposals,
                    **self.path_arguments(),
                )
            with self.assertRaises(baselines.BaselineContractError):
                baselines.analyze_baselines(
                    self.target,
                    self.pool,
                    self.proposals,
                    self.results,
                    self.orders,
                    **self.path_arguments(),
                )
            self.assertTrue(
                baselines.validate_baseline_report(
                    self.report,
                    self.target,
                    self.pool,
                    self.proposals,
                    self.results,
                    self.orders,
                    **self.path_arguments(),
                )
            )
            target_path = self.proposals_path.parent / "target.json"
            pool_path = self.proposals_path.parent / "manifest.json"
            with self.assertRaises(baselines.BaselineContractError):
                baselines.main(
                    [
                        "freeze",
                        "--target",
                        str(target_path),
                        "--pool",
                        str(pool_path),
                        "--proposals",
                        str(self.proposals_path),
                        "--repository-root",
                        str(self.repository_root),
                        "--output",
                        str(self.repository_root / "should-not-exist.json"),
                    ]
                )
        finally:
            self.receipt_path.write_bytes(receipt_bytes)

    def test_v02_altered_or_wrong_receipt_blocks_policy_freeze(self) -> None:
        receipt_bytes = self.receipt_path.read_bytes()
        try:
            self.receipt_path.write_bytes(receipt_bytes + b"\n")
            with self.assertRaises(baselines.BaselineContractError):
                baselines.build_policy_orders(
                    self.target,
                    self.pool,
                    self.proposals,
                    **self.path_arguments(),
                )

            wrong_proposals = self.proposals[:-1]
            wrong_sha = discovery.sha256_hex(
                discovery.canonical_jsonl_bytes(wrong_proposals)
            )
            wrong_receipt = orchestrator.build_discovery_generation_receipt_v1(
                target=self.target,
                proposals=wrong_proposals,
                raw_artifact_sha256=[wrong_sha, wrong_sha],
            )
            wrong_bytes = discovery.canonical_json_bytes(wrong_receipt)
            self.receipt_path.write_bytes(wrong_bytes)
            forged_pool = deepcopy(self.pool)
            reference = forged_pool["determinism"]["generation_receipt_ref"]
            reference["receipt_id"] = wrong_receipt["receipt_id"]
            reference["sha256"] = discovery.sha256_hex(wrong_bytes)
            forged_pool["pool_id"] = discovery.candidate_pool_id_for(forged_pool)
            with self.assertRaises(baselines.BaselineContractError):
                baselines.build_policy_orders(
                    self.target,
                    forged_pool,
                    self.proposals,
                    **self.path_arguments(),
                )
        finally:
            self.receipt_path.write_bytes(receipt_bytes)



class Wave69SourceBoundSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_directory = tempfile.TemporaryDirectory(
            prefix="partizan-wave69-source-suite-"
        )
        cls.repository_root = Path(cls.temp_directory.name)
        cls.contexts = []
        entries = []
        for index in range(6):
            (
                target,
                pool,
                proposals,
                results,
                proposals_path,
                receipt_path,
            ) = synthetic_bundle(
                cls.repository_root,
                bundle_name=f"bundle-{index}",
                target_variant=index,
            )
            orders = baselines.build_policy_orders(
                target,
                pool,
                proposals,
                proposals_path=proposals_path,
                repository_root=cls.repository_root,
            )
            report = baselines.analyze_baselines(
                target,
                pool,
                proposals,
                results,
                orders,
                proposals_path=proposals_path,
                repository_root=cls.repository_root,
            )
            entry = persist_analysis_bundle(
                cls.repository_root,
                target=target,
                pool=pool,
                proposals=proposals,
                results=results,
                proposals_path=proposals_path,
                orders=orders,
                report=report,
            )
            cls.contexts.append(
                {
                    "target": target,
                    "pool": pool,
                    "proposals": proposals,
                    "results": results,
                    "orders": orders,
                    "report": report,
                    "proposals_path": proposals_path,
                    "receipt_path": receipt_path,
                    "entry": entry,
                }
            )
            entries.append(entry)
        cls.pre_verification_suite_ref = persist_pre_verification_suite(
            cls.repository_root, entries, cls.contexts
        )
        cls.suite_input = baselines.build_baseline_suite_input(
            stage="stage_a",
            pre_verification_suite_ref=cls.pre_verification_suite_ref,
            bundles=entries,
            repository_root=cls.repository_root,
        )
        cls.suite_report = baselines.aggregate_baseline_suite(
            cls.suite_input, repository_root=cls.repository_root
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_directory.cleanup()

    def resolved(self, relative: str) -> Path:
        return self.repository_root / Path(*PurePosixPath(relative).parts)

    def rehash_input(self, suite_input):
        suite_input["suite_input_id"] = baselines.baseline_suite_input_id_for(
            suite_input
        )

    def test_six_real_bundles_macro_all_preregistered_metrics(self) -> None:
        suite = self.suite_report
        self.assertEqual(
            suite["primary"]["metric"],
            "target_macro_symmetry_unique_de_at_256",
        )
        self.assertIn(
            "fixed_1000_permutation_upper_tail_proportion", suite["primary"]
        )
        self.assertEqual(
            [row["calls_per_target"] for row in suite["macro_by_budget"]],
            [64, 256, 1024],
        )
        self.assertEqual(
            set(suite["macro_secondary"]),
            {"naudc_through_1024", "calls_to_first_success"},
        )
        self.assertEqual(
            suite["primary"]["target_bootstrap_95_interval"]["replicates"],
            10_000,
        )
        self.assertEqual(
            baselines.validate_baseline_suite_report(
                suite,
                self.suite_input,
                repository_root=self.repository_root,
            ),
            [],
        )

    def test_fabricated_rehashed_report_is_recomputed_and_rejected(self) -> None:
        forged_input = deepcopy(self.suite_input)
        bundle = forged_input["bundles"][0]
        report_path = self.resolved(bundle["baseline_report_ref"]["path"])
        original = report_path.read_bytes()
        try:
            report = json.loads(original)
            report["random"]["replicates"][0]["metrics"]["budget_metrics"][1][
                "symmetry_unique_successes"
            ] = 999999
            report["heuristic"]["metrics"]["full_pool"]["outcome_counts"][
                "verified_match"
            ] = 999999
            report["report_id"] = baselines.baseline_report_id_for(report)
            report_path.write_bytes(discovery.canonical_json_bytes(report))
            reference = bundle["baseline_report_ref"]
            reference["report_id"] = report["report_id"]
            reference["sha256"] = artifact_sha(report_path)
            self.rehash_input(forged_input)
            with self.assertRaises(baselines.BaselineContractError):
                baselines.aggregate_baseline_suite(
                    forged_input, repository_root=self.repository_root
                )
        finally:
            report_path.write_bytes(original)

    def test_altered_and_reordered_ledgers_are_rejected(self) -> None:
        for mode in ("altered", "reordered", "duplicate"):
            suite_input = deepcopy(self.suite_input)
            bundle = suite_input["bundles"][0]
            path = self.resolved(bundle["verifier_results_ref"]["path"])
            original = path.read_bytes()
            try:
                rows = discovery.load_jsonl(path)
                if mode == "altered":
                    rows[0]["verifier_io"]["response"]["actual"][
                        "legacy_digest"
                    ] = "fabricated"
                else:
                    rows[0], rows[1] = rows[1], rows[0]
                if mode == "duplicate":
                    rows[1] = deepcopy(rows[0])
                path.write_bytes(discovery.canonical_jsonl_bytes(rows))
                bundle["verifier_results_ref"]["sha256"] = artifact_sha(path)
                self.rehash_input(suite_input)
                with self.subTest(mode=mode):
                    with self.assertRaises(baselines.BaselineContractError):
                        baselines.aggregate_baseline_suite(
                            suite_input, repository_root=self.repository_root
                        )
            finally:
                path.write_bytes(original)

    def test_missing_noncanonical_and_wrong_receipts_are_rejected(self) -> None:
        bundle = self.suite_input["bundles"][0]
        pool_path = self.resolved(bundle["pool_manifest_ref"]["path"])
        pool = discovery.load_json(pool_path)
        receipt_path = self.resolved(
            pool["determinism"]["generation_receipt_ref"]["path"]
        )
        original = receipt_path.read_bytes()
        try:
            receipt_path.unlink()
            with self.assertRaises(baselines.BaselineContractError):
                baselines.aggregate_baseline_suite(
                    self.suite_input, repository_root=self.repository_root
                )
            receipt_path.write_bytes(original + b"\n")
            with self.assertRaises(baselines.BaselineContractError):
                baselines.aggregate_baseline_suite(
                    self.suite_input, repository_root=self.repository_root
                )
            context = next(
                item for item in self.contexts
                if item["target"]["target_id"] == bundle["target_id"]
            )
            wrong_proposals = context["proposals"][:-1]
            wrong_sha = discovery.sha256_hex(
                discovery.canonical_jsonl_bytes(wrong_proposals)
            )
            wrong_receipt = orchestrator.build_discovery_generation_receipt_v1(
                target=context["target"],
                proposals=wrong_proposals,
                raw_artifact_sha256=[wrong_sha, wrong_sha],
            )
            receipt_path.write_bytes(discovery.canonical_json_bytes(wrong_receipt))
            with self.assertRaises(baselines.BaselineContractError):
                baselines.aggregate_baseline_suite(
                    self.suite_input, repository_root=self.repository_root
                )
        finally:
            receipt_path.write_bytes(original)

    def test_wrong_pairings_swaps_stage_and_path_escapes_are_rejected(self) -> None:
        wrong_order = deepcopy(self.suite_input)
        wrong_order["bundles"][0]["policy_orders_ref"], wrong_order["bundles"][1][
            "policy_orders_ref"
        ] = (
            wrong_order["bundles"][1]["policy_orders_ref"],
            wrong_order["bundles"][0]["policy_orders_ref"],
        )
        self.rehash_input(wrong_order)
        with self.assertRaises(baselines.BaselineContractError):
            baselines.aggregate_baseline_suite(
                wrong_order, repository_root=self.repository_root
            )

        wrong_pool = deepcopy(self.suite_input)
        wrong_pool["bundles"][0]["pool_manifest_ref"], wrong_pool["bundles"][1][
            "pool_manifest_ref"
        ] = (
            wrong_pool["bundles"][1]["pool_manifest_ref"],
            wrong_pool["bundles"][0]["pool_manifest_ref"],
        )
        self.rehash_input(wrong_pool)
        with self.assertRaises(baselines.BaselineContractError):
            baselines.aggregate_baseline_suite(
                wrong_pool, repository_root=self.repository_root
            )

        wrong_stage = deepcopy(self.suite_input)
        wrong_stage["stage"] = "stage_b"
        self.rehash_input(wrong_stage)
        with self.assertRaises(baselines.BaselineContractError):
            baselines.aggregate_baseline_suite(
                wrong_stage, repository_root=self.repository_root
            )

        for escaped_path in ("../escape.json", "./bundle-0/target.json"):
            escaped = deepcopy(self.suite_input)
            escaped["bundles"][0]["target_ref"]["path"] = escaped_path
            self.rehash_input(escaped)
            with self.subTest(path=escaped_path):
                self.assertTrue(
                    baselines.validate_baseline_suite_input(
                        escaped, repository_root=self.repository_root
                    )
                )

    def test_malformed_suite_input_returns_errors_without_crashing(self) -> None:
        cases = [
            {},
            {"schema_version": baselines.BASELINE_SUITE_INPUT_SCHEMA_VERSION},
            {**deepcopy(self.suite_input), "bundles": [None] * 6},
        ]
        for value in cases:
            with self.subTest(value_type=type(value).__name__):
                self.assertTrue(
                    baselines.validate_baseline_suite_input(
                        value, repository_root=self.repository_root
                    )
                )


if __name__ == "__main__":
    unittest.main()
