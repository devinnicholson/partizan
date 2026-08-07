from __future__ import annotations

import importlib.util
import hashlib
import json
import unittest
from pathlib import Path

import partizan

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_visualizer_evidence.py"
EVIDENCE = ROOT / "visualizer" / "public" / "evidence" / "crossing.json"
ATLAS = ROOT / "visualizer" / "public" / "evidence" / "fixed-value-atlas.json"
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

    def test_fixed_value_atlas_has_a_self_consistent_authority(self) -> None:
        atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
        atlas_sha256 = atlas.pop("atlas_sha256")
        self.assertEqual(
            hashlib.sha256(partizan.canonical_json_bytes(atlas)).hexdigest(),
            atlas_sha256,
        )
        self.assertEqual(
            atlas["counts"],
            {"exact_values": 3, "literal_games": 16120, "quotient_forms": 21697},
        )
        self.assertEqual(len(atlas["items"]), 21697)
        self.assertEqual(len(atlas["groups"]), 16120)
        self.assertEqual(
            atlas["source"]["representative_set_sha256"],
            "54488c811edd8a09155864fd1af3c469c7daba334c62788a86882e0e9c404a02",
        )
        self.assertTrue(atlas["source"]["independent_replay"])
        self.assertEqual(atlas["source"]["proposal_count"], 73728)
        self.assertEqual(atlas["source"]["negative_test_families_rejected"], 15)
        self.assertRegex(atlas["source"]["completion_file_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(atlas["source"]["negative_tests_file_sha256"], r"^[0-9a-f]{64}$")
        a = atlas["items"][atlas["motif"]["A"]]
        b = atlas["items"][atlas["motif"]["B"]]
        c = atlas["items"][atlas["motif"]["C"]]
        self.assertEqual([a["t"], b["t"], c["t"]], [0, 0, 0])
        self.assertEqual(len({a["q"], b["q"], c["q"]}), 3)
        self.assertEqual([a["n"], b["n"], c["n"]], [19, 15, 15])
        self.assertEqual(atlas["groups"][a["l"]]["c"], 32)
        self.assertEqual(atlas["groups"][b["l"]]["c"], 54)
        self.assertEqual(b["l"], c["l"])
        self.assertNotEqual(a["l"], b["l"])
        self.assertTrue(all(len(item["p"]) == 6 for item in atlas["items"]))
        self.assertTrue(all(len(group["p"]) == 2 for group in atlas["groups"]))

        def arcs(item: dict[str, object]) -> set[tuple[int, int]]:
            bits = int(str(item["g"]), 16)
            return {
                (source, target)
                for source in range(7)
                for target in range(7)
                if bits & (1 << (source * 7 + target))
            }

        a_arcs, b_arcs, c_arcs = arcs(a), arcs(b), arcs(c)
        self.assertEqual(a_arcs - b_arcs, {(2, 3)})
        self.assertFalse(b_arcs - a_arcs)
        self.assertEqual(c_arcs - b_arcs, {(6, 0)})
        self.assertFalse(b_arcs - c_arcs)
        for label in ("A", "B"):
            dag = atlas["motif_dags"][label]
            item = atlas["items"][atlas["motif"][label]]
            group = atlas["groups"][item["l"]]
            self.assertEqual(dag["nodes"][dag["root"]]["d"], group["d"])


if __name__ == "__main__":
    unittest.main()
