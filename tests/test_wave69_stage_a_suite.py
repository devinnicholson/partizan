from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_wave69_stage_a_suite.py"
SPEC = importlib.util.spec_from_file_location("wave69_stage_a_suite", SCRIPT)
suite = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(suite)


def exact_inventory_fixture(root: Path):
    output_root = root / "data/discovery/wave_69/stage_a"
    output_root.mkdir(parents=True)
    suite_path = output_root / "suite-manifest.json"
    suite_path.write_bytes(suite._canonical_bytes({}))
    entries = []
    filenames = {
        "target_ref": "target.json",
        "proposals_ref": "proposals.jsonl",
        "generation_receipt_ref": "generation-receipt.json",
        "pool_manifest_ref": "pool-manifest.json",
        "policy_orders_ref": "policy-orders.json",
    }
    for index in range(6):
        digest = f"{index + 1:064x}"
        directory = output_root / digest
        directory.mkdir()
        entry = {"target_id": f"target-sha256:{digest}"}
        for offset, (ref_name, filename) in enumerate(filenames.items()):
            artifact = directory / filename
            artifact.write_text(f"{index}:{offset}\n")
            entry[ref_name] = {
                "path": artifact.relative_to(root).as_posix()
            }
        entries.append(entry)
    return {"targets": entries}, suite_path


class Wave69StageASuiteTests(unittest.TestCase):
    def test_registry_selects_exact_six_stage_a_targets_and_seed_golden(self) -> None:
        _, _, targets = suite.load_stage_a_targets(suite.DEFAULT_REGISTRY)
        self.assertEqual(len(targets), 6)
        self.assertEqual({item["stage"] for item in targets}, {"stage_a"})
        self.assertEqual(
            [item["bin"]["index"] for item in targets], [0, 3, 0, 3, 0, 3]
        )
        self.assertEqual(
            [
                suite.stage_seed(item["target_spec"]["target_id"])
                for item in targets
            ],
            [
                17672373659205594994,
                10750487050513559786,
                18084658403807373493,
                3801062396562257051,
                6801261912781277260,
                15824076400387734239,
            ],
        )

    def test_registry_refuses_a_seventh_stage_a_target(self) -> None:
        registry = suite.discovery.load_json(suite.DEFAULT_REGISTRY)
        mutated = deepcopy(registry)
        wave70 = next(item for item in mutated["targets"] if item["stage"] == "wave_70")
        wave70["stage"] = "stage_a"
        mutated["registry_id"] = suite._canonical_id(
            "registry", mutated, "registry_id"
        )
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "registry.json"
            path.write_bytes(suite._canonical_bytes(mutated))
            with self.assertRaisesRegex(suite.SuiteFreezeError, "exactly 6"):
                suite.load_stage_a_targets(path)

    def test_schema_is_stage_a_strict_and_has_no_result_fields(self) -> None:
        schema_path = (
            ROOT
            / "docs/schemas/partizan-wave69-stage-suite-v0.1.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            suite.SCHEMA_VERSION,
        )
        self.assertEqual(schema["properties"]["stage"]["const"], "stage_a")
        self.assertEqual(
            schema["properties"]["proposal_count_per_target"]["const"], 1024
        )
        self.assertEqual(schema["properties"]["targets"]["minItems"], 6)
        self.assertEqual(schema["properties"]["targets"]["maxItems"], 6)
        target_keys = set(schema["$defs"]["target_bundle"]["required"])
        self.assertNotIn("verifier_results_ref", target_keys)
        self.assertNotIn("baseline_report_ref", target_keys)

    def test_check_only_never_spawns_a_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            registry_path = root / "docs/registry.json"
            prereg_path = root / "docs/prereg.md"
            registry_path.parent.mkdir(parents=True)
            registry_path.write_bytes(suite.DEFAULT_REGISTRY.read_bytes())
            prereg_path.write_text("fixed preregistration\n")
            registry, registry_raw, targets = suite.load_stage_a_targets(registry_path)
            component_paths = (
                root / "scripts/suite.py",
                root / "engine/pool.py",
                root / "scripts/baseline.py",
            )
            for index, path in enumerate(component_paths):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# component {index}\n")
            source_repositories = {
                "partizan": "a" * 40,
                "astralbase": "b" * 40,
                "bitmesh": "c" * 40,
                "thermograph": "d" * 40,
            }
            output_root = root / "data/discovery/wave_69/stage_a"
            output_root.mkdir(parents=True)
            entries = []
            for registry_item in targets:
                target_id = registry_item["target_spec"]["target_id"]
                directory = output_root / target_id.split(":", 1)[1]
                directory.mkdir()
                ref_paths = {}
                for ref_name, filename in (
                    ("target_ref", "target.json"),
                    ("proposals_ref", "proposals.jsonl"),
                    ("generation_receipt_ref", "generation-receipt.json"),
                    ("pool_manifest_ref", "pool-manifest.json"),
                    ("policy_orders_ref", "policy-orders.json"),
                ):
                    path = directory / filename
                    path.write_text(f"{ref_name}\n")
                    ref_paths[ref_name] = {
                        "path": path.relative_to(root).as_posix()
                    }
                entries.append(
                    {
                        "target_id": target_id,
                        "family": registry_item["family"],
                        "bin_index": registry_item["bin"]["index"],
                        "seed": suite.stage_seed(target_id),
                        **ref_paths,
                    }
                )
            prereg_raw = prereg_path.read_bytes()
            manifest = {
                "schema_version": suite.SCHEMA_VERSION,
                "suite_id": "suite-sha256:" + "0" * 64,
                "stage": suite.STAGE,
                "phase": "pre_verification_freeze",
                "registry_ref": {
                    "path": registry_path.relative_to(root).as_posix(),
                    "registry_id": registry["registry_id"],
                    "sha256": suite.sha256_hex(registry_raw),
                },
                "preregistration_ref": {
                    "path": prereg_path.relative_to(root).as_posix(),
                    "preregistration_id": "prereg-sha256:" + suite.sha256_hex(prereg_raw),
                    "sha256": suite.sha256_hex(prereg_raw),
                },
                "implementation": suite._implementation_boundary(
                    root=root,
                    partizan_commit=source_repositories["partizan"],
                    paths=component_paths,
                ),
                "source_repositories": source_repositories,
                "seed_contract": {
                    "algorithm": "sha256_first_u64_big_endian_v1",
                    "domain_hex": suite.SEED_DOMAIN.hex(),
                    "stage": suite.STAGE,
                    "target_id_encoding": "utf8",
                },
                "target_count": 6,
                "proposal_count_per_target": 1024,
                "targets": entries,
                "freeze_boundary": {
                    "verifier_calls": 0,
                    "results_artifacts_present": False,
                    "policy_orders_frozen_before_verification": True,
                    "wave70_material_present": False,
                },
            }
            manifest["suite_id"] = suite.suite_id_for(manifest)
            suite_path = output_root / "suite-manifest.json"
            suite_path.write_bytes(suite._canonical_bytes(manifest))
            with (
                patch.object(suite, "_validate_target_artifacts"),
                patch.object(
                    suite,
                    "_load_baseline_contract",
                    return_value=SimpleNamespace(),
                ),
                patch.object(
                    suite.subprocess,
                    "run",
                    side_effect=AssertionError("check-only spawned a subprocess"),
                ),
            ):
                observed = suite.check_only(
                    root=root,
                    suite_path=suite_path,
                    baseline_orchestrator=component_paths[2],
                )
            self.assertEqual(observed, manifest)

    def test_pre_result_boundary_is_structural(self) -> None:
        source = SCRIPT.read_text()
        self.assertNotIn("discovery-verify-pool", source)
        self.assertNotIn("wave_70", source)

        ignored = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn("data/discovery/wave_69/stage_a/", ignored)

        workflow = (
            ROOT / "docs/discovery_wave_69_stage_a_suite_freeze.md"
        ).read_text()
        for commitment in (
            "I (implementation)",
            "P (pre-result)",
            "E (evidence)",
            "Stage B remains blocked",
        ):
            self.assertIn(commitment, workflow)

    def test_baseline_wrapper_exposes_the_real_contract(self) -> None:
        contract = suite._load_baseline_contract(
            ROOT / "scripts/wave69_discovery_baselines.py"
        )
        for name in (
            "validate_policy_orders",
            "build_baseline_suite_input",
            "aggregate_baseline_suite",
            "validate_baseline_suite_report",
        ):
            self.assertTrue(callable(getattr(contract, name)))

    def test_exact_pre_result_inventory_rejects_every_extra_entry(self) -> None:
        cases = (
            "ledger.jsonl",
            "outcomes.jsonl",
            "labels.json",
            "arbitrary.bin",
            "nested",
            "symlink",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir).resolve()
                manifest, suite_path = exact_inventory_fixture(root)
                suite._validate_exact_pre_result_tree(
                    manifest, root=root, suite_path=suite_path
                )
                target_dir = suite_path.parent / f"{1:064x}"
                extra = target_dir / case
                if case == "nested":
                    extra.mkdir()
                elif case == "symlink":
                    extra.symlink_to(target_dir / "target.json")
                else:
                    extra.write_text("unbound\n")
                with self.assertRaisesRegex(
                    suite.SuiteFreezeError, "unexpected inventory"
                ):
                    suite._validate_exact_pre_result_tree(
                        manifest, root=root, suite_path=suite_path
                    )

    def test_exact_inventory_rejects_symlink_at_a_bound_name(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            manifest, suite_path = exact_inventory_fixture(root)
            target_dir = suite_path.parent / f"{1:064x}"
            target_path = target_dir / "target.json"
            backing = root / "backing.json"
            backing.write_bytes(target_path.read_bytes())
            target_path.unlink()
            target_path.symlink_to(backing)
            with self.assertRaisesRegex(suite.SuiteFreezeError, "non-symlink"):
                suite._validate_exact_pre_result_tree(
                    manifest, root=root, suite_path=suite_path
                )

    def test_finalize_builds_validates_and_aggregates_without_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            output_root = root / "data/discovery/wave_69/stage_a"
            output_root.mkdir(parents=True)
            entries = []
            for index in range(6):
                digest = f"{index + 1:064x}"
                target_id = f"target-sha256:{digest}"
                pool_id = f"pool-sha256:{index + 11:064x}"
                directory = output_root / digest
                directory.mkdir()
                artifacts = {
                    "target.json": {"target_id": target_id},
                    "pool-manifest.json": {"pool_id": pool_id},
                    "policy-orders.json": {"policy_orders_id": f"policy-orders-sha256:{index + 21:064x}"},
                }
                for filename, value in artifacts.items():
                    (directory / filename).write_bytes(suite._canonical_bytes(value))
                (directory / "proposals.jsonl").write_bytes(
                    suite.discovery.canonical_jsonl_bytes([{}])
                )
                (directory / suite.RESULTS_FILENAME).write_bytes(
                    suite.discovery.canonical_jsonl_bytes([{}])
                )

                def ref(filename):
                    return {
                        "path": (directory / filename).relative_to(root).as_posix()
                    }

                entries.append(
                    {
                        "target_id": target_id,
                        "target_ref": ref("target.json"),
                        "proposals_ref": ref("proposals.jsonl"),
                        "pool_manifest_ref": {
                            **ref("pool-manifest.json"),
                            "pool_id": pool_id,
                        },
                        "policy_orders_ref": ref("policy-orders.json"),
                    }
                )
            manifest = {
                "suite_id": "suite-sha256:" + "9" * 64,
                "targets": entries,
            }
            suite_path = output_root / "suite-manifest.json"
            suite_path.write_bytes(suite._canonical_bytes(manifest))
            calls = {"analyze": 0, "build": None, "aggregate": 0}

            def analyze(*args, **kwargs):
                calls["analyze"] += 1
                target = args[0]
                return {
                    "report_id": "baseline-report-sha256:"
                    + target["target_id"].split(":", 1)[1]
                }

            def build(**kwargs):
                calls["build"] = kwargs
                return {
                    "suite_input_id": "baseline-suite-input-sha256:" + "8" * 64,
                    "bundles": kwargs["bundles"],
                }

            def aggregate(*args, **kwargs):
                calls["aggregate"] += 1
                return {"suite_report_id": "baseline-suite-report-sha256:" + "7" * 64}

            contract = SimpleNamespace(
                BASELINE_REPORT_SCHEMA_VERSION="partizan.baseline_report.v0.1",
                analyze_baselines=analyze,
                build_baseline_suite_input=build,
                validate_baseline_suite_input=lambda *a, **k: [],
                aggregate_baseline_suite=aggregate,
                validate_baseline_suite_report=lambda *a, **k: [],
            )
            with (
                patch.object(suite, "POOL_SIZE", 1),
                patch.object(suite, "validate_suite_manifest"),
                patch.object(suite, "_load_baseline_contract", return_value=contract),
                patch.object(
                    suite.subprocess,
                    "run",
                    side_effect=AssertionError("finalizer invoked a subprocess"),
                ),
            ):
                suite_input, suite_report = suite.finalize_baseline_input(
                    root=root,
                    suite_path=suite_path,
                    baseline_orchestrator=root / "baseline.py",
                )

            self.assertEqual(calls["analyze"], 6)
            self.assertEqual(calls["aggregate"], 1)
            self.assertEqual(
                calls["build"]["pre_verification_suite_ref"]["suite_id"],
                manifest["suite_id"],
            )
            self.assertEqual(len(suite_input["bundles"]), 6)
            self.assertEqual(
                suite_report["suite_report_id"],
                "baseline-suite-report-sha256:" + "7" * 64,
            )
            self.assertTrue((output_root / suite.BASELINE_SUITE_INPUT_FILENAME).is_file())
            self.assertTrue((output_root / suite.BASELINE_SUITE_REPORT_FILENAME).is_file())

    def test_freeze_dispatches_six_generate_freeze_and_policy_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            registry_path = root / "docs/registry.json"
            prereg_path = root / "docs/prereg.md"
            pool_script = root / "engine/orchestrator.py"
            baseline_script = root / "scripts/wave69_discovery_baselines.py"
            output_root = root / "data/discovery/wave_69/stage_a"
            registry_path.parent.mkdir(parents=True)
            pool_script.parent.mkdir(parents=True)
            baseline_script.parent.mkdir(parents=True)
            registry_path.write_bytes(suite.DEFAULT_REGISTRY.read_bytes())
            prereg_path.write_text("draft preregistration\n")
            pool_script.write_text("# pool\n")
            baseline_script.write_text("# baseline\n")
            calls: list[tuple[str, ...]] = []

            def fake_runner(command, cwd):
                self.assertEqual(cwd, root)
                command = tuple(command)
                calls.append(command)
                if "discovery-generate-pool-v1" in command:
                    output = Path(command[command.index("--output") + 1])
                    receipt = Path(command[command.index("--receipt") + 1])
                    output.write_bytes(
                        suite.discovery.canonical_jsonl_bytes(
                            [{} for _ in range(suite.POOL_SIZE)]
                        )
                    )
                    receipt.write_bytes(
                        suite._canonical_bytes(
                            {
                                "receipt_id": "receipt-sha256:" + "1" * 64,
                                "schema_version": suite.discovery.GENERATION_RECEIPT_SCHEMA_VERSION,
                            }
                        )
                    )
                elif "discovery-freeze-pool" in command:
                    output = Path(command[command.index("--manifest") + 1])
                    output.write_bytes(
                        suite._canonical_bytes(
                            {
                                "pool_id": "pool-sha256:" + "2" * 64,
                                "schema_version": suite.discovery.POOL_SCHEMA_VERSION_V2,
                            }
                        )
                    )
                elif "freeze" in command:
                    output = Path(command[command.index("--output") + 1])
                    target = suite.discovery.load_json(
                        Path(command[command.index("--target") + 1])
                    )
                    output.write_bytes(
                        suite._canonical_bytes(
                            {
                                "schema_version": suite.POLICY_ORDERS_SCHEMA_VERSION,
                                "policy_orders_id": "policy-orders-sha256:" + "3" * 64,
                                "target_id": target["target_id"],
                                "pool_id": "pool-sha256:" + "2" * 64,
                                "proposal_artifact": {},
                                "freeze_boundary": "before_any_verifier_result",
                                "random_policy": {
                                    "replicate_count": suite.RANDOM_REPLICATES,
                                    "orders": [{} for _ in range(suite.RANDOM_REPLICATES)],
                                },
                                "heuristic_policy": {"order": {}},
                            }
                        )
                    )
                else:
                    self.fail(f"unexpected command: {command}")

            commits = {
                "astralbase": "1434fca1fc04d97798ec1b820c56f52f8014ccc7",
                "bitmesh": "ade3417a007b9c8392d8a153abc4b3ed23edf0aa",
                "thermograph": "1d9b6b01c3921aca8c2a8fb13972fee8a4de5041",
                "partizan": "a" * 40,
            }
            baseline_contract = SimpleNamespace(validate_policy_orders=lambda *a, **k: [])
            implementation = {
                "implementation_id": "implementation-sha256:" + "4" * 64,
                "partizan_commit": commits["partizan"],
                "components": [],
            }
            with (
                patch.object(
                    suite,
                    "_clean_commit",
                    side_effect=lambda repo, name: commits[name],
                ),
                patch.object(suite, "_require_committed_bytes"),
                patch.object(suite, "_load_baseline_contract", return_value=baseline_contract),
                patch.object(suite, "_validate_target_artifacts"),
                patch.object(suite, "validate_suite_manifest"),
                patch.object(suite, "_implementation_boundary", return_value=implementation),
                patch.object(suite, "_run_git", return_value=b""),
            ):
                manifest = suite.freeze_stage_a_suite(
                    root=root,
                    registry_path=registry_path,
                    preregistration_path=prereg_path,
                    output_root=output_root,
                    pool_orchestrator=pool_script,
                    baseline_orchestrator=baseline_script,
                    astralbase_dir=root / "astralbase",
                    bitmesh_dir=root / "bitmesh",
                    thermograph_dir=root / "thermograph",
                    command_runner=fake_runner,
                )

            self.assertEqual(len(manifest["targets"]), 6)
            self.assertEqual(manifest["freeze_boundary"]["verifier_calls"], 0)
            self.assertFalse(manifest["freeze_boundary"]["wave70_material_present"])
            generate = [call for call in calls if "discovery-generate-pool-v1" in call]
            freeze = [call for call in calls if "discovery-freeze-pool" in call]
            policies = [
                call
                for call in calls
                if "freeze" in call and "discovery-freeze-pool" not in call
            ]
            self.assertEqual((len(generate), len(freeze), len(policies)), (6, 6, 6))
            self.assertTrue(
                all(call[call.index("--pool-size") + 1] == "1024" for call in generate)
            )
            self.assertFalse(any("discovery-verify-pool" in call for call in calls))
            self.assertFalse(any("wave_70" in " ".join(call) for call in calls))


if __name__ == "__main__":
    unittest.main()
