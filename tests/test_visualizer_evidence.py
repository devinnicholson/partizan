from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import partizan

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_visualizer_evidence.py"
EVIDENCE = ROOT / "visualizer" / "public" / "evidence" / "crossing.json"
SPEC = importlib.util.spec_from_file_location("partizan_visualizer_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
visualizer_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(visualizer_evidence)


class VisualizerEvidenceTests(unittest.TestCase):
    def test_committed_crossing_is_a_clean_native_rebuild(self) -> None:
        rebuilt = visualizer_evidence.build_evidence()
        self.assertEqual(
            EVIDENCE.read_bytes(),
            partizan.canonical_json_bytes(rebuilt),
        )
        self.assertEqual(
            [item["statistics"]["literal_game_nodes"] for item in rebuilt["realizations"]],
            [19, 11],
        )
        self.assertEqual(
            [item["witness"]["move"] for item in rebuilt["realizations"]],
            ["Qg1-g7", "Qg6-g7"],
        )
        self.assertEqual(rebuilt["comparison"]["equal_to_value"], [True, True])
        self.assertTrue(rebuilt["comparison"]["equal_to_each_other"])
        self.assertIn(
            "literal_game_crossing",
            rebuilt["comparison"]["transition_kinds"],
        )


if __name__ == "__main__":
    unittest.main()
