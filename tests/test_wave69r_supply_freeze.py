from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "python/partizan/wave69r_supply.py"
SPEC = importlib.util.spec_from_file_location("wave69r_supply_freeze_tests", MODULE_PATH)
supply = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(supply)

TEST_DOMAIN = "partizan/test/w69r/supply/v1"
TEST_COMMITS = {
    "partizan": "1" * 40,
    "astralbase": "2" * 40,
    "bitmesh": "3" * 40,
    "thermograph": "4" * 40,
}


class Wave69RSupplyFreezeTests(unittest.TestCase):
    def freeze(self, output: Path, *, shard_count=2, rows_per_shard=8):
        with patch.object(
            supply, "collect_clean_repository_commits", return_value=TEST_COMMITS
        ):
            return supply.freeze_supply_suite(
                output_root=output,
                partizan_dir=ROOT,
                astralbase_dir=ROOT,
                bitmesh_dir=ROOT,
                thermograph_dir=ROOT,
                shard_count=shard_count,
                rows_per_shard=rows_per_shard,
                seed_domain=TEST_DOMAIN,
            )

    def validate(self, output: Path, *, shard_count=2, rows_per_shard=8):
        return supply.validate_supply_suite(
            input_root=output,
            expected_shard_count=shard_count,
            expected_rows_per_shard=rows_per_shard,
            expected_seed_domain=TEST_DOMAIN,
            expected_commits=TEST_COMMITS,
            repository_root=ROOT,
        )

    def test_seed_derivation_uses_first_big_endian_u64_under_test_domain(self) -> None:
        import hashlib

        expected = int.from_bytes(
            hashlib.sha256(TEST_DOMAIN.encode("ascii") + b"\0" + b"2").digest()[:8],
            "big",
            signed=False,
        )
        self.assertEqual(supply.derive_supply_seed(2, domain=TEST_DOMAIN), expected)
        self.assertEqual(supply.shard_id(2), "wave69r-supply-shard-2")

    def test_synthetic_suite_runs_each_shard_twice_and_freezes_complete_inventory(self) -> None:
        original = supply._run_generator_process
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "inputs"
            with patch.object(
                supply, "_run_generator_process", wraps=original
            ) as process:
                suite = self.freeze(output)
            self.assertEqual(process.call_count, 4)
            self.assertEqual(suite["totals"]["row_count"], 16)
            self.assertEqual(suite["totals"]["unique_board_id_count"], 16)
            self.assertEqual(suite["totals"]["unique_reflection_orbit_count"], 16)
            self.assertFalse(suite["pre_result_boundary"]["checker_invoked"])
            self.assertEqual(suite["pre_result_boundary"]["target_fields_consumed"], [])
            self.assertTrue((output / "checker-requests.jsonl").is_file())
            for index in range(2):
                directory = output / f"shard-{index}"
                self.assertEqual(
                    {path.name for path in directory.iterdir()},
                    {
                        "board-stream.jsonl",
                        "construction-certificates.jsonl",
                        "generation-report.json",
                        "shard-manifest.json",
                    },
                )
                report = json.loads((directory / "generation-report.json").read_text())
                self.assertEqual(report["executions"]["run_count"], 2)
                self.assertEqual(
                    report["executions"]["raw_artifact_sha256"],
                    [
                        report["board_stream_artifact"]["sha256"],
                        report["board_stream_artifact"]["sha256"],
                    ],
                )
                self.assertEqual(report["source_repositories"], TEST_COMMITS)
                board_row = json.loads(
                    (directory / "board-stream.jsonl").read_text().splitlines()[0]
                )
                certificate = json.loads(
                    (directory / "construction-certificates.jsonl")
                    .read_text()
                    .splitlines()[0]
                )
                self.assertEqual(
                    certificate["schema_version"],
                    "partizan.structural_construction_certificate.v0.1",
                )
                self.assertIn("certificate_id", certificate)
                self.assertIn("left", certificate)
                self.assertIn("right", certificate)
                self.assertNotIn("shard_id", certificate)
                self.assertNotIn("construction", certificate)
                catalog, _ = supply._catalog_bundle(ROOT)
                self.assertEqual(
                    supply._discovery().validate_structural_construction_certificate(
                        certificate, board_row=board_row, catalog=catalog
                    ),
                    [],
                )
                false_claim = deepcopy(board_row)
                false_claim["construction"]["left_active_piece_count"] = (
                    false_claim["construction"]["left_active_piece_count"] % 5 + 1
                )
                if false_claim["construction"]["left_active_piece_count"] == board_row[
                    "construction"
                ]["left_active_piece_count"]:
                    false_claim["construction"]["left_active_piece_count"] = 0
                with self.assertRaisesRegex(ValueError, "does not match board witness"):
                    supply._discovery().construction_certificate_for_board_row(
                        false_claim, catalog
                    )
            all_bytes = b"".join(
                path.read_bytes() for path in output.rglob("*") if path.is_file()
            )
            self.assertNotIn(b'"target"', all_bytes)
            self.assertNotIn(b'"target_id"', all_bytes)
            self.assertNotIn(b'"outcome"', all_bytes)
            self.assertEqual(self.validate(output), suite)

    def test_check_only_validation_never_spawns_a_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "inputs"
            suite = self.freeze(output)
            with patch.object(
                supply.subprocess,
                "run",
                side_effect=AssertionError("check-only mode spawned a process"),
            ):
                self.assertEqual(self.validate(output), suite)

    def test_check_never_accepts_an_unpinned_suite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "inputs"
            self.freeze(output)
            with self.assertRaisesRegex(
                supply.SupplyFreezeError, "current clean commits or an explicit expected I"
            ):
                supply.validate_supply_suite(
                    input_root=output,
                    expected_shard_count=2,
                    expected_rows_per_shard=8,
                    expected_seed_domain=TEST_DOMAIN,
                    repository_root=ROOT,
                )

    def test_unbound_or_result_like_artifacts_fail_complete_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "inputs"
            self.freeze(output)
            extra = output / "stage-b-results.jsonl"
            extra.write_bytes(b"{}\n")
            with self.assertRaisesRegex(
                supply.SupplyFreezeError, "filesystem inventory drift"
            ):
                self.validate(output)

    def test_tampered_certificate_and_receipt_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "inputs"
            self.freeze(output)
            certificate_path = output / "shard-0/construction-certificates.jsonl"
            original = certificate_path.read_bytes()
            certificate_path.write_bytes(original.replace(b'"ordinal":0', b'"ordinal":9', 1))
            with self.assertRaisesRegex(supply.SupplyFreezeError, "does not bind bytes"):
                self.validate(output)
            certificate_path.write_bytes(original)

            report_path = output / "shard-0/generation-report.json"
            report = json.loads(report_path.read_text())
            report["executions"]["byte_identical"] = False
            report_path.write_bytes(supply.canonical_json_bytes(report))
            with self.assertRaisesRegex(supply.SupplyFreezeError, "does not bind bytes"):
                self.validate(output)

    def test_global_duplicate_from_reused_seed_is_rejected_before_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "inputs"
            with (
                patch.object(
                    supply, "collect_clean_repository_commits", return_value=TEST_COMMITS
                ),
                patch.object(supply, "derive_supply_seed", return_value=7),
            ):
                with self.assertRaisesRegex(
                    supply.SupplyFreezeError, "globally unique"
                ):
                    supply.freeze_supply_suite(
                        output_root=output,
                        partizan_dir=ROOT,
                        astralbase_dir=ROOT,
                        bitmesh_dir=ROOT,
                        thermograph_dir=ROOT,
                        shard_count=2,
                        rows_per_shard=8,
                        seed_domain=TEST_DOMAIN,
                    )
            self.assertFalse(output.exists())

    def test_production_contract_is_declared_without_materialized_seed_values(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('PRODUCTION_SEED_DOMAIN = "partizan/w69r/supply/v1"', source)
        self.assertEqual(supply.PRODUCTION_SHARD_COUNT, 4)
        self.assertEqual(supply.PRODUCTION_ROWS_PER_SHARD, 1024)
        self.assertNotIn("PRODUCTION_SEEDS", source)
        self.assertEqual(supply.DEFAULT_ASTRALBASE_DIR, ROOT.parent / "astralbase")
        self.assertEqual(supply.DEFAULT_BITMESH_DIR, ROOT.parent / "bitmesh")
        self.assertEqual(supply.DEFAULT_THERMOGRAPH_DIR, ROOT.parent / "thermograph")

    def test_production_source_boundary_locks_external_heads_and_direct_parent(self) -> None:
        implementation = "5" * 40
        commits = {"partizan": implementation, **supply.PINNED_EXTERNAL_COMMITS}
        with patch.object(
            supply,
            "_git_output",
            return_value=f"{implementation} {supply.IMPLEMENTATION_PARENT_COMMIT}",
        ):
            supply._verify_production_source_boundary(
                commits,
                partizan_dir=ROOT,
                expected_implementation_commit=implementation,
            )

        wrong_external = dict(commits)
        wrong_external["bitmesh"] = "6" * 40
        with self.assertRaisesRegex(supply.SupplyFreezeError, "external commits"):
            supply._verify_production_source_boundary(
                wrong_external, partizan_dir=ROOT
            )

        with (
            patch.object(
                supply,
                "_git_output",
                return_value=f"{implementation} {'7' * 40}",
            ),
            self.assertRaisesRegex(supply.SupplyFreezeError, "direct child"),
        ):
            supply._verify_production_source_boundary(commits, partizan_dir=ROOT)

    def test_check_provenance_accepts_only_an_ancestor_of_current_partizan(self) -> None:
        success = subprocess.CompletedProcess(
            args=("git",), returncode=0, stdout="", stderr=""
        )
        with patch.object(supply.subprocess, "run", return_value=success) as run:
            supply._require_commit_ancestor(
                repository=ROOT, ancestor="5" * 40, descendant="6" * 40
            )
        self.assertIn("merge-base", run.call_args.args[0])
        self.assertIn("--is-ancestor", run.call_args.args[0])

        not_ancestor = subprocess.CompletedProcess(
            args=("git",), returncode=1, stdout="", stderr=""
        )
        with (
            patch.object(supply.subprocess, "run", return_value=not_ancestor),
            self.assertRaisesRegex(supply.SupplyFreezeError, "not an ancestor"),
        ):
            supply._require_commit_ancestor(
                repository=ROOT, ancestor="5" * 40, descendant="6" * 40
            )

    def test_checked_in_supply_schemas_close_every_object_shape(self) -> None:
        schema_paths = sorted(
            (ROOT / "docs/schemas").glob("partizan-wave69r-supply-*.schema.json")
        )
        schema_paths.append(
            ROOT
            / "docs/schemas/partizan-structural-construction-certificate-v0.1.schema.json"
        )
        self.assertEqual(len(schema_paths), 4)

        def check_closed(value, path="$"):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(
                        value.get("additionalProperties"),
                        False,
                        f"unclosed object schema at {path}",
                    )
                    self.assertIn("properties", value, f"missing properties at {path}")
                for key, item in value.items():
                    check_closed(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    check_closed(item, f"{path}[{index}]")

        for schema_path in schema_paths:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
            check_closed(schema, schema_path.name)


if __name__ == "__main__":
    unittest.main()
