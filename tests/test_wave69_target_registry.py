from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "select_wave69_targets.py"
SPEC = importlib.util.spec_from_file_location("wave69_target_registry", SCRIPT_PATH)
selector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(selector)

ATLAS = ROOT / "data" / "discovery" / "wave_69" / "reference-atlas.jsonl.gz"
PLAIN_ATLAS = Path("/tmp/w69-clean-reference-atlas.jsonl")
REPLAY = ROOT / "data" / "discovery" / "wave_69" / "reference-atlas-replay.json"
REGISTRY = ROOT / "docs" / "discovery_targets" / "wave_69_target_registry.v0.1.json"
REPORT = ROOT / "docs" / "discovery_wave_69_target_selection_report.md"


class Wave69TargetRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = selector.build_registry(ATLAS, REPLAY)

    def test_bound_sources_and_expected_snapshot(self) -> None:
        self.assertEqual(
            selector.sha256_hex(ATLAS.read_bytes()), selector.ATLAS_GZIP_SHA256
        )
        self.assertEqual(
            selector.sha256_hex(REPLAY.read_bytes()), selector.ATLAS_REPLAY_SHA256
        )
        self.assertEqual(
            self.registry["source_boundary"]["replay_attestation"],
            {
                "availability": "checked_in",
                "path": selector.CHECKED_IN_REPLAY_ATTESTATION,
                "sha256": selector.ATLAS_REPLAY_SHA256,
                "summary": selector.ATLAS_REPLAY_SUMMARY,
            },
        )
        self.assertEqual(
            self.registry["registry_id"],
            "registry-sha256:e7383432360d848b0fd2996a8d4b3c2bf85ebd1492c6e4fff596f7b3391fb4a5",
        )
        self.assertEqual(
            [item["source_row"]["row_number"] for item in self.registry["targets"]],
            [46, 85, 40, 67, 115, 91, 48, 75, 27, 81, 87, 93, 38, 56, 83, 113, 41, 32],
        )

    def test_eighteen_targets_obey_bins_and_stage_schedule(self) -> None:
        self.assertEqual(self.registry["target_count"], 18)
        targets = self.registry["targets"]
        self.assertEqual(
            {(item["family"], item["bin"]["index"]) for item in targets},
            {
                (family, index)
                for family in selector.ELIGIBLE_FAMILIES
                for index in range(selector.BIN_COUNT)
            },
        )
        for item in targets:
            self.assertEqual(item["stage"], selector.STAGE_BY_BIN[item["bin"]["index"]])
            self.assertEqual(
                item["source_boundary_sha256"], self.registry["source_boundary_sha256"]
            )
            self.assertEqual(
                item["bin"]["size"],
                item["bin"]["sorted_stop_exclusive"]
                - item["bin"]["sorted_start_inclusive"],
            )
        for family in selector.ELIGIBLE_FAMILIES:
            family_targets = [item for item in targets if item["family"] == family]
            sizes = [item["bin"]["size"] for item in family_targets]
            self.assertLessEqual(max(sizes) - min(sizes), 1)
            self.assertEqual(
                [item["bin"]["sorted_start_inclusive"] for item in family_targets],
                [0]
                + [
                    item["bin"]["sorted_stop_exclusive"]
                    for item in family_targets[:-1]
                ],
            )

    def test_selected_row_is_minimum_identity_in_each_contiguous_bin(self) -> None:
        rows = selector.load_bound_atlas(ATLAS)
        by_family = selector.eligible_records(rows)
        target_by_key = {
            (item["family"], item["bin"]["index"]): item
            for item in self.registry["targets"]
        }
        for family, records in by_family.items():
            for index, bin_rows in enumerate(selector.contiguous_balanced_bins(records)):
                expected = min(
                    bin_rows, key=lambda row: (row["identity_sha256"], row["row_id"])
                )
                selected = target_by_key[(family, index)]["source_row"]
                self.assertEqual(selected["row_id"], expected["row_id"])
                self.assertEqual(selected["identity_sha256"], expected["identity_sha256"])
        selected_numbers = {
            item["source_row"]["row_number"] for item in self.registry["targets"]
        }
        self.assertTrue(selected_numbers.isdisjoint(selector.EXCLUDED_ROW_NUMBERS))
        self.assertEqual(
            self.registry["selection_contract"]["substitution_policy"], "forbidden"
        )

    def test_all_target_specs_are_strict_discovery_contracts(self) -> None:
        for item in self.registry["targets"]:
            target = item["target_spec"]
            self.assertEqual(selector.discovery.validate_target_spec(target), [])
            self.assertEqual(
                target["provenance"]["source_artifact"], selector.CHECKED_IN_ATLAS
            )
            self.assertEqual(target["search_limits"]["max_pool_size"], 4096)
            self.assertEqual(target["search_limits"]["max_verifier_calls"], 4096)
            self.assertEqual(
                target["search_limits"]["max_recursive_nodes_per_candidate"], 100000
            )
            self.assertEqual(
                target["target"]["identity_sha256"],
                item["source_row"]["identity_sha256"],
            )

    def test_generated_artifacts_are_canonical_and_current(self) -> None:
        self.assertEqual(
            REGISTRY.read_bytes(), selector.discovery.canonical_json_bytes(self.registry)
        )
        self.assertEqual(REPORT.read_text(), selector.render_report(self.registry))
        self.assertEqual(
            selector.main(
                [
                    "--atlas",
                    str(ATLAS),
                    "--check",
                ]
            ),
            0,
        )

    def test_byte_change_is_refused_before_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            changed = Path(tempdir) / "atlas.jsonl.gz"
            changed.write_bytes(ATLAS.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "compressed SHA-256 mismatch"):
                selector.load_bound_atlas(changed)

    def test_replay_attestation_is_required_and_byte_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            missing = Path(tempdir) / "missing-replay.json"
            with self.assertRaises(FileNotFoundError):
                selector.validate_replay_attestation(missing)
            changed = Path(tempdir) / "changed-replay.json"
            changed.write_bytes(REPLAY.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                selector.validate_replay_attestation(changed)

    def test_conservative_decomposition_proof_kind_is_required(self) -> None:
        rows = deepcopy(selector.load_bound_atlas(ATLAS))
        row = next(
            item
            for item in rows
            if int(item["exact"]["value"]["row_number"])
            not in selector.EXCLUDED_ROW_NUMBERS
        )
        row["exact"]["value"]["proof_kind"] = "unchecked"
        with self.assertRaisesRegex(
            ValueError, "unsupported conservative decomposition proof kind"
        ):
            selector.eligible_records(rows)

    def test_plain_and_gzip_inputs_select_identically(self) -> None:
        if not PLAIN_ATLAS.exists():
            self.skipTest("plain /tmp atlas is unavailable")
        self.assertEqual(
            selector.eligible_records(selector.load_bound_atlas(ATLAS)),
            selector.eligible_records(selector.load_bound_atlas(PLAIN_ATLAS)),
        )

    def test_registry_identity_binds_selection(self) -> None:
        mutated = deepcopy(self.registry)
        mutated["targets"][0]["stage"] = "stage_b"
        payload = dict(mutated)
        payload.pop("registry_id")
        mutated_id = f"registry-sha256:{selector._fingerprint(payload)}"
        self.assertNotEqual(mutated_id, self.registry["registry_id"])


if __name__ == "__main__":
    unittest.main()
