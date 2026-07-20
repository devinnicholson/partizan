from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "6" * 40
ASTRALBASE_COMMIT = "1434fca1fc04d97798ec1b820c56f52f8014ccc7"
TARGET_FIXTURE = ROOT / "tests/fixtures/discovery/target.valid.json"
PROPOSALS_FIXTURE = ROOT / "tests/fixtures/discovery/proposals.valid.jsonl"
POOL_FIXTURE = ROOT / "tests/fixtures/discovery/candidate-pool.valid.manifest.json"


def load_orchestrator():
    spec = importlib.util.spec_from_file_location(
        "partizan_orchestrator_wave69r_lineage", ROOT / "engine/orchestrator.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


orchestrator = load_orchestrator()
discovery = orchestrator.discovery_contract


class Wave69RLineageContractTests(unittest.TestCase):
    def _bundle(self, repository_root: Path):
        target = discovery.load_json(TARGET_FIXTURE)
        target["search_limits"]["max_pool_size"] = 16
        target["target_id"] = discovery.target_id_for(target)
        boards = orchestrator.generate_discovery_board_states_v2(
            pool_size=8,
            random_seed=6902111,
            generator_code_commit=COMMIT,
        )
        catalog_source = (
            ROOT / orchestrator.DISCOVERY_POOL_GENERATOR_CATALOG_PATH_V2
        )
        catalog = discovery.load_json(catalog_source)
        certificates = [
            discovery.construction_certificate_for_board_row(row, catalog)
            for row in boards
        ]
        proposals = discovery.project_board_stream_to_proposals(target, boards)
        paths = {
            "target": "artifacts/target.json",
            "boards": "artifacts/boards.jsonl",
            "catalog": "artifacts/catalog.json",
            "certificates": "artifacts/certificates.jsonl",
            "proposals": "artifacts/proposals.jsonl",
            "receipt": "artifacts/receipt.json",
        }
        (repository_root / "artifacts").mkdir()
        (repository_root / paths["target"]).write_bytes(
            discovery.canonical_json_bytes(target)
        )
        (repository_root / paths["boards"]).write_bytes(
            discovery.canonical_jsonl_bytes(boards)
        )
        (repository_root / paths["catalog"]).write_bytes(
            catalog_source.read_bytes()
        )
        (repository_root / paths["certificates"]).write_bytes(
            discovery.canonical_jsonl_bytes(certificates)
        )
        (repository_root / paths["proposals"]).write_bytes(
            discovery.canonical_jsonl_bytes(proposals)
        )
        board_sha = discovery.sha256_hex(discovery.canonical_jsonl_bytes(boards))
        certificate_sha = discovery.sha256_hex(
            discovery.canonical_jsonl_bytes(certificates)
        )
        proposal_sha = discovery.sha256_hex(
            discovery.canonical_jsonl_bytes(proposals)
        )
        repos = {
            "astralbase": ASTRALBASE_COMMIT,
            "bitmesh": "b" * 40,
            "thermograph": "c" * 40,
            "partizan": COMMIT,
        }
        receipt = discovery.build_generation_receipt_v2(
            target_path=paths["target"],
            target_spec=target,
            board_stream_path=paths["boards"],
            board_rows=boards,
            construction_catalog_path=paths["catalog"],
            construction_catalog=catalog,
            construction_catalog_sha256=discovery.sha256_hex(
                catalog_source.read_bytes()
            ),
            construction_certificates_path=paths["certificates"],
            construction_certificates=certificates,
            candidate_artifact_path=paths["proposals"],
            proposals=proposals,
            board_stream_process_sha256=[board_sha, board_sha],
            construction_certificate_process_sha256=[
                certificate_sha,
                certificate_sha,
            ],
            projection_process_sha256=[proposal_sha, proposal_sha],
            source_repositories=repos,
        )
        (repository_root / paths["receipt"]).write_bytes(
            discovery.canonical_json_bytes(receipt)
        )
        manifest = discovery.build_candidate_pool_manifest_v3(
            generation_receipt=receipt,
            generation_receipt_path=paths["receipt"],
        )
        return target, boards, certificates, proposals, receipt, manifest, paths

    def test_complete_receipt_and_manifest_lineage_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, boards, certificates, proposals, receipt, manifest, _ = (
                self._bundle(root)
            )
            self.assertEqual(
                discovery.validate_generation_receipt_v2(
                    receipt, target, proposals, root
                ),
                [],
            )
            self.assertEqual(
                discovery.validate_candidate_pool_manifest_v3(
                    manifest, target, proposals, root
                ),
                [],
            )
            self.assertEqual(len(boards), len(certificates))
            self.assertEqual(
                [item["board_id"] for item in certificates],
                [item["board_id"] for item in boards],
            )

    def test_fully_rehashed_fen_metadata_mutation_is_rejected(self) -> None:
        row = orchestrator.generate_discovery_board_states_v2(
            pool_size=1, random_seed=6902112, generator_code_commit=COMMIT
        )[0]
        mutated = deepcopy(row)
        fields = mutated["position"]["text"].split()
        fields[1] = "b"
        fen = " ".join(fields)
        mutated["position"]["text"] = fen
        mutated["position"]["sha256"] = discovery.sha256_hex(fen.encode("utf-8"))
        mutated["position"]["symmetry_sha256"] = (
            discovery.fen_file_reflection_orbit_sha256(fen)
        )
        mutated["board_id"] = discovery.board_id_for(mutated["position"])
        errors = discovery.validate_candidate_board_stream_row(mutated)
        self.assertTrue(any("trailing FEN fields" in error for error in errors), errors)

    def test_rehashed_certificate_template_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, _, certificates, proposals, receipt, _, paths = self._bundle(root)
            tampered = deepcopy(certificates)
            tampered[0]["left"]["template_id"] = "template-sha256:" + "f" * 64
            tampered[0]["certificate_id"] = discovery.construction_certificate_id_for(
                tampered[0]
            )
            payload = discovery.canonical_jsonl_bytes(tampered)
            (root / paths["certificates"]).write_bytes(payload)
            receipt["construction_certificates"]["sha256"] = discovery.sha256_hex(payload)
            template_ids = [
                [item["left"]["template_id"], item["right"]["template_id"]]
                for item in tampered
            ]
            receipt["construction_certificates"]["template_ids_sha256"] = (
                discovery.sha256_hex(discovery.canonical_json_bytes(template_ids))
            )
            receipt["executions"]["construction_certificate_sha256"] = [
                discovery.sha256_hex(payload),
                discovery.sha256_hex(payload),
            ]
            receipt["receipt_id"] = discovery.generation_receipt_id_for(receipt)
            errors = discovery.validate_generation_receipt_v2(
                receipt, target, proposals, root
            )
            self.assertTrue(any("pure board/catalog projection" in error for error in errors), errors)

    def test_rehashed_nested_catalog_extension_is_rejected(self) -> None:
        catalog = discovery.load_json(
            ROOT / orchestrator.DISCOVERY_POOL_GENERATOR_CATALOG_PATH_V2
        )
        catalog["strata"]["outer_leaper"]["target_hint"] = "forbidden"
        catalog["catalog_id"] = discovery.construction_catalog_id_for(catalog)
        errors = discovery.validate_construction_catalog(catalog)
        self.assertTrue(any("fields mismatch" in error for error in errors), errors)

    def test_rehashed_projection_and_repo_tampers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, _, _, proposals, receipt, _, _ = self._bundle(root)
            mapping = deepcopy(receipt)
            mapping["projection"]["mapping"]["/position"] = "target:/target"
            mapping["receipt_id"] = discovery.generation_receipt_id_for(mapping)
            self.assertTrue(
                any(
                    "projection.mapping" in error
                    for error in discovery.validate_generation_receipt_v2(
                        mapping, target, proposals, root
                    )
                )
            )
            repo = deepcopy(receipt)
            repo["source_repositories"]["partizan"] = "d" * 40
            repo["receipt_id"] = discovery.generation_receipt_id_for(repo)
            errors = discovery.validate_generation_receipt_v2(
                repo, target, proposals, root
            )
            self.assertTrue(any("generator mismatch" in error for error in errors), errors)
            self.assertTrue(any("projection mismatch" in error for error in errors), errors)

    def test_repository_relative_escape_and_manifest_crosswalk_tampers_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target, _, _, proposals, receipt, manifest, _ = self._bundle(root)
            escaped = deepcopy(receipt)
            escaped["board_stream"]["path"] = "../boards.jsonl"
            escaped["receipt_id"] = discovery.generation_receipt_id_for(escaped)
            self.assertTrue(
                any(
                    "repository-relative" in error
                    for error in discovery.validate_generation_receipt_v2(
                        escaped, target, proposals, root
                    )
                )
            )
            changed = deepcopy(manifest)
            changed["construction_lineage"]["projection_contract_id"] = "wrong"
            changed["pool_id"] = discovery.candidate_pool_id_for(changed)
            errors = discovery.validate_candidate_pool_manifest_v3(
                changed, target, proposals, root
            )
            self.assertTrue(any("projection_contract_id" in error for error in errors), errors)
            self.assertTrue(any("generation receipt" in error for error in errors), errors)

    def test_legacy_validators_and_artifacts_remain_accepted(self) -> None:
        target = discovery.load_json(TARGET_FIXTURE)
        proposals = discovery.load_jsonl(PROPOSALS_FIXTURE)
        pool = discovery.load_json(POOL_FIXTURE)
        self.assertEqual(
            discovery.validate_candidate_pool_manifest(
                pool, target, proposals, PROPOSALS_FIXTURE
            ),
            [],
        )
        self.assertTrue(
            discovery.validate_candidate_pool_manifest_v3(
                pool, target, proposals, ROOT
            )
        )

    def test_all_wave69r_schemas_are_strict_at_root(self) -> None:
        names = (
            "partizan-dfile-two-component-constructive-catalog-v0.2.schema.json",
            "partizan-structural-construction-certificate-v0.1.schema.json",
            "partizan-candidate-generation-receipt-v0.2.schema.json",
            "partizan-candidate-pool-manifest-v0.3.schema.json",
        )
        for name in names:
            schema = json.loads((ROOT / "docs/schemas" / name).read_text())
            self.assertIs(schema["additionalProperties"], False, name)


if __name__ == "__main__":
    unittest.main()
