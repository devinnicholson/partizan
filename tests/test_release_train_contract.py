from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from partizan import chess_adapter


ROOT = Path(__file__).resolve().parents[1]
CURRENT_COMMITS = {
    "astralbase": "0e36d14b78a7a4915689e510bff6d7c0f20152e4",
    "bitmesh": "410550c0964004cd7ba9677539f17ae82c139dd8",
    "thermograph": "32d6bfbc966f47a87e7249d4ed8818370288e079",
}
LEGACY_SHA256 = {
    "docs/schemas/partizan-bounded-chess-adapter-v0.1.schema.json": (
        "34839bf6f0b27689526cfadb0d5ad5571c037df9c3d58dba742791145510c391"
    ),
    "tests/fixtures/fixed_value/chess-adapter-v0.1.valid.json": (
        "d7193e945cf701ff731b8fa07039e1160b9b964cba37051491641f130b498c66"
    ),
}


class ReleaseTrainContractTests(unittest.TestCase):
    def test_current_adapter_pins_are_consistent_across_surfaces(self) -> None:
        self.assertEqual(
            {
                name: source["source_commit"]
                for name, source in chess_adapter.UPSTREAM_SOURCES.items()
            },
            CURRENT_COMMITS,
        )

        schema = json.loads(
            (
                ROOT
                / "docs/schemas/partizan-bounded-chess-adapter-v0.2.schema.json"
            ).read_text(encoding="utf-8")
        )
        schema_commits = {
            name: definition["allOf"][1]["properties"]["source_commit"]["const"]
            for name, definition in schema["$defs"]["upstream_sources"]
            ["properties"].items()
        }
        self.assertEqual(schema_commits, CURRENT_COMMITS)

        rust = (ROOT / "engine/src/chess_adapter.rs").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        development = (ROOT / "docs/development.md").read_text(encoding="utf-8")
        for commit in CURRENT_COMMITS.values():
            self.assertIn(commit, rust)
            self.assertIn(commit, workflow)
            self.assertIn(commit, development)

    def test_legacy_adapter_authorities_are_byte_frozen(self) -> None:
        for relative, expected in LEGACY_SHA256.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_ci_isolates_main_and_gate_s_cargo_patch_homes(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        main_home = "${{ runner.temp }}/partizan-main-cargo-home"
        gate_s_home = "${{ runner.temp }}/partizan-gate-s-cargo-home"

        self.assertNotIn('Path(os.environ.get("CARGO_HOME"', workflow)
        self.assertIn(
            'cargo_home = runner_temp / "partizan-main-cargo-home"', workflow
        )
        self.assertIn(
            'gate_s_home = runner_temp / "partizan-gate-s-cargo-home"', workflow
        )
        self.assertEqual(workflow.count(f"CARGO_HOME: {gate_s_home}"), 2)
        self.assertGreaterEqual(workflow.count(f"CARGO_HOME: {main_home}"), 5)


if __name__ == "__main__":
    unittest.main()
